# coding=utf-8
from scipy.stats import rv_discrete, norm
import numpy as np
import math
import pandas as pd
from collections import defaultdict, OrderedDict
from datetime import timedelta,datetime
import copy
import pickle
import logging
import os


class Utils:

    def __init__(self):
        pass

    @staticmethod
    def generate_date_range(start_dt, end_dt):
        if type(start_dt) == str:
            start_dt = datetime.strptime(start_dt, '%Y-%m-%d')
        if type(end_dt) == str:
            end_dt = datetime.strptime(end_dt, '%Y-%m-%d')
        step = timedelta(days=1)
        date_range = []
        while start_dt <= end_dt:
            date_range.append(start_dt.strftime('%Y-%m-%d'))
            start_dt += step
        return date_range

    @staticmethod
    def truncate_vlt_distribution(val, prob):
        vlt_mean = (val * prob).sum()
        val_trunc = np.copy(val[val >= vlt_mean])
        prob_trunc = np.copy(prob[val >= vlt_mean])
        prob_trunc[0] += np.sum(prob[~(val >= vlt_mean)])
        return val_trunc, prob_trunc

    @staticmethod
    def getCategory(sales,):
        category=99 #normal
        percent = (sum(sales>0)*1.0/ len(sales))
        salesMean = np.mean(sales)
        if  (percent>=category_longTail_stable_DaysThreshold) & (salesMean<=category_longTail_stable_SalesThreshold):
            category=1 #longTail_stable
        return category

    @staticmethod
    def getPredictionErrorMultiple(sales,pred_sales,cur_index):
        """
        judge whether prediction sales exceed the actual sales
        """
        sales3days =  sum([sales[cur_index]]*3)
        pred_sales3days = sum([pred_sales[cur_index][0]]*3)
        if cur_index >= 3:
            sales3days = sum(sales[cur_index-3:cur_index])
            pred_sales3days = sum(pred_sales[cur_index-3][0:3])
        multiple = max((sales3days*1.0/pred_sales3days),1)
        return multiple

    @staticmethod
    def getWeightedActSales(sales,cur_index):
        """
        1. estimate whether error is too large
        2. return weighted
        """
        if cur_index>= salespredictionErrorFilldays:
            actualSale = sales[cur_index-salespredictionErrorFilldays:cur_index]
            return [np.mean(actualSale)],[np.std(actualSale)]
        else:
            rang = salespredictionErrorFilldays - cur_index
            mean_sale = np.nanmean(sales[0:cur_index])
            actualSale = np.concatenate((sales[0:cur_index],np.array([mean_sale]*(rang))))
            return [np.mean(actualSale)],[np.std(actualSale)]
def GetRunTime(func):
    def cal_time_func(*args, **args2):
        startTime = datetime.now()
        f =  func(*args,**args2)
        endTime = datetime.now()
        print '%s called'%func.__name__, endTime-startTime
        return f
    return cal_time_func

class inventory_proess:
    def __init__(self,sku_list,fdc_forecast_sales, fdc_forecast_std, fdc_alt, fdc_alt_prob, fdc_inv, white_flag,
                  fdc_list, rdc_inv, date_range, sales_retail,order_list, fdc_his_inv,system_small_s,system_bigger_S,
                 system_flag,rdc_sale_list,logger, save_data_path):
        ''' #类初始化函数，初始化类的各个参数'''
        self.sku_list=sku_list
        # 预测数据相关信息{fdc_sku_date:[7 days sales]},{fdc_sku_data:[7 days cv]}
        self.fdc_forecast_sales = fdc_forecast_sales
        self.fdc_forecast_std = fdc_forecast_std
        # RDC-->FDC时长分布,{fdc:[days]}}
        self.fdc_alt = defaultdict(list)
        self.fdc_alt.update(fdc_alt)
        self.fdc_alt_prob = defaultdict(list)
        self.fdc_alt_prob.update(fdc_alt_prob)
        # defaultdict(lamda:defaultdict(int)),包括库存，调拨量，在途，到达量
        self.fdc_inv = fdc_inv
        # # 白名单,不同日期的白名单不同{fdc:{date_s:[]}}
        # self.white_flag = white_flag
        # 调拨量字典,fdc_allocation=defaultdict(float)
        self.fdc_allocation = defaultdict(float)
        # fdc列表：
        self.fdc_list = fdc_list
        # RDC库存，{date_sku_rdc:库存量} defaultdict(int)
        # self.rdc_inv = defaultdict(int)
        self.rdc_inv=copy.deepcopy(rdc_inv)
        # 订单数据，订单ID，SKU，实际到达量，到达时间,将其转换为{到达时间:{SKU：到达量}}形式的字典，defaultdict(lambda :defaultdict(int))
        self.order_list = order_list
        # 仿真的时间窗口 时间格式如下：20161129
        self.date_range = date_range
        # 订单数据：{fdc_订单时间_订单id:{SKU：数量}}
        # self.orders_retail = orders_retail
        # 记录仿真订单结果，存在订单，部分SKU不满足的情况
        # self.simu_orders_retail = copy.deepcopy(self.orders_retail)
        # 便于kpi计算，标记{fdc:{date:{sku:销量}}}
        # self.fdc_simu_orders_retail = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        # # 订单类型:{订单id:类型}
        # self.orders_retail_type = defaultdict(str)
        # sku当天从FDC的出库量，从RDC的出库量
        # self.sku_fdc_sales = defaultdict(int)
        # self.sku_rdc_sales = defaultdict(int)
        # 全量SKU列表
        # self.all_sku_list = all_sku_list
        self.logger = logger
        self.save_data_path = save_data_path
        # 标记调拨记录单，标记{date:{sku:{fdc:调拨量}}}，如果为rdc则对应的为库存,同时用flag是否足够
        self.allocation_retail= defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        #记录销量 {fdc:{date:{sku:销量}}}
        self.sales_retail=sales_retail
        #记录仿真销量，分为FDC仿真销量和综合仿真销量
        self.fdc_sales_retail=defaultdict(int)
        self.sim_sales_retail=defaultdict(int)
        #记录补货点信息
        self.lop=defaultdict(int)
        #记录vlt信息
        self.alt_sim=defaultdict(int)
        #原来的历史库存
        self.fdc_his_inv=fdc_his_inv
        #保留该sku是否属于某个fdc的白名单，white_list_dict {dt{fdc:是否白名单}}
        self.white_list_dict=white_flag
        #记录FDC调拨次数
        self.all_cnt_sim=defaultdict(int)
        #传进运行系统参数需要的参数变量
        self.system_small_s=system_small_s
        self.system_bigger_S=system_bigger_S
        self.system_flag=system_flag
        #RDC销量
        self.rdc_sale_list=rdc_sale_list
        #增加变量标记fdc的期初库存
        self.fdc_begin_inv=defaultdict(int)


    def gene_whitelist(self,self_sku,date_s):
        '''获取该时间点的白名单,调用户一次刷新一次，只保存最新的白名单列表'''
        self.white_list = defaultdict(int)
        for f in self.fdc_list:
            index = self.gene_index(f, self_sku, date_s)
            self.white_list[f] =self.white_list_dict[index]
            # self.logger.info(u'当前日期--' + date_s + u'当前FDC--' + str(f) + u'拥有该SKU' + self_sku)
        # print self.white_list


    def cacl_rdc_inv(self,self_sku, date_s):
        '''  补货逻辑 #更新RDC库存,RDC库存的更新按照实际订单情况进行更新，rdc{index:库存量},同时扣除rdc销量'''
        index = self.gene_index('rdc', self_sku, date_s)
        self.rdc_inv[index] = self.rdc_inv[index] + self.order_list[date_s].get(self_sku, 0)
        self.rdc_inv[index] = max(self.rdc_inv[index] - self.rdc_sale_list[date_s].get(self_sku, 0),0)


    def calc_lop(self,self_sku,fdc, date_s, cr=0.99):
        '''    #计算某个FDC的某个SKU的补货点'''
        # sku的FDC销量预测，与RDC的cv系数
        index = self.gene_index(fdc, self_sku, date_s)
        sku_sales =self.fdc_forecast_sales[index]
        try:
            sku_std = self.fdc_forecast_std[index]
        except:
            sku_std = 0
        sku_sales_mean = np.mean(sku_sales)
        if self.system_flag==1:
            lop = sku_sales_mean* self.system_small_s[index]
        else:
            # 2、L_std 标准差拦截
            # if float(sku_sales_mean)==0:
            #     sku_std=0
            # elif sku_std > 10 and float(float(sku_std)/float(sku_sales_mean)) > 2:
            #     sku_std=2*sku_sales_mean
            lop=(sku_sales[0]+sku_sales[1]+sku_sales[2]+1.96*sku_std)
        # # # 默认将数据延展12周
        # sku_sales = np.tile(sku_sales, 12)
        # sku_std = np.tile(sku_std, 12)
        # # 具体的fdc对应的送货时长分布
        # fdc_vlt = self.fdc_alt[fdc]
        # fdc_vlt_porb = self.fdc_alt_prob[fdc]
        # if len(fdc_vlt) == 0:
        #     fdc_vlt = [2]
        #     fdc_vlt_porb = [1]
        # demand_mean = [sum(sku_sales[:(l + 1)]) for l in fdc_vlt]
        # # VLT期间总销量均值的概率分布
        # demand_mean_distribution = rv_discrete(values=(demand_mean, fdc_vlt_porb))
        # part1 = demand_mean_distribution.mean()
        # # 给定VLT，计算总销量的方差
        # demand_var = [sum([i ** 2 for i in sku_std[:(l + 1)]]) for l in fdc_vlt]
        # # demand_std = np.sqrt(demand_var)
        # # VLT期间总销量方差的概率分布
        # demand_var_distribution = rv_discrete(values=(demand_var, fdc_vlt_porb))
        # # 条件期望的方差
        # part21 = demand_mean_distribution.var()
        # # 条件方差的期望
        # part22 = demand_var_distribution.mean()
        # # 计算补货点
        # lop = np.ceil(part1 + norm.ppf(cr) * math.sqrt(part21 + part22 + 0.1))
        self.lop[index]=lop
        return lop


    def calc_replacement(self,self_sku,fdc, date_s, sku_lop, bp=10, cr=0.99):
        '''
        #计算某个FDC的SKU的补货量
        计算补货量补货量为lop+bp-在途-当前库存
        '''
        # sku的FDC销量预测，与RDC的cv系数
        index = self.gene_index(fdc, self_sku, date_s)
        sku_sales = self.fdc_forecast_sales[index]
        try:
            sku_std = self.fdc_forecast_std[index]
        except:
            sku_std = 0
        sku_sales_mean = np.mean(sku_sales)
        max_qtty = sku_sales_mean * self.system_bigger_S[index]
        inv = self.fdc_inv[index]['inv']
        open_on = self.fdc_inv[index]['open_po']
        cons_open_po=self.fdc_inv[index]['cons_open_po']
        if self.system_flag==1:
            lop_replacement = max(max_qtty - inv - open_on + cons_open_po,0)
        else:
            # 1、销量均值*8
            lop_replacement=sku_sales_mean * 8
            # lop_replacement = max(max_qtty - inv - open_on + cons_open_po,0)
            #  lop_replacement = max(sku_sales_mean * 7+1.53*1.96*sku_std- inv - open_on + cons_open_po,0)
            # if sku_sales_mean==0:
            #     lop_replacement=max(1.53*1.96*sku_std- inv - open_on + cons_open_po,0)
            # else:
            #     lop_replacement=sku_sales_mean * 7
        # 调整补货量
        if lop_replacement <= 10:
            pass
        else:
            div_num, mod_num = divmod(lop_replacement, 10)
            if mod_num <= 2:
                lop_replacement = div_num * 10
            elif mod_num <= 7:
                lop_replacement = div_num * 10 + 5
            else:
                lop_replacement = (div_num + 1) * 10
        # # 默认将数据延展12周
        # sku_sales = np.tile(sku_sales, 12)
        # sku_std = np.tile(sku_std, 12)
        # # 计算BP长度内的消费量
        # lop_replacement = max(np.ceil(sku_lop + sum(sku_sales[:(bp + 1)]) +
        #                 norm.ppf(cr) * math.sqrt(sum([i ** 2 for i in sku_std[:(bp + 1)]])) - inv - open_on), 0)
        return np.floor(lop_replacement)


    def calc_sku_allocation(self,self_sku, date_s):
        '''
        首先将当日到达量加到当日库存中
        @sku
        @调拨量
        ----输出---
        @date:日期
        @sku:sku
        @fdc:fdc
        @allocation：调拨量
        '''
        fdc_replacement = defaultdict(int)
        for f in self.fdc_list:
            if self.white_list[f]==0:
                fdc_replacement[f] = 0
            else:
                lop_tmp = self.calc_lop(self_sku,f, date_s)
                index = self.gene_index(f, self_sku, date_s)
                # 在途加上库存减去在途消耗低于补货点
                if (self.fdc_inv[index]['inv'] +self.fdc_inv[index]['arrive_quantity']+ self.fdc_inv[index]['open_po']-self.fdc_inv[index]['cons_open_po']) < lop_tmp:
                    fdc_replacement[f] = self.calc_replacement(self_sku,f, date_s, lop_tmp)
                    self.all_cnt_sim[f]=self.all_cnt_sim[f]+1
                else:
                    fdc_replacement[f] = 0
        index_rdc = self.gene_index('rdc', self_sku, date_s)
        rdc_inv_avail = max(np.min([self.rdc_inv[index_rdc] - 12, np.floor(self.rdc_inv[index_rdc] * 0.2)]),0)
        #记录FDC的库存
        self.allocation_retail[date_s][self_sku]['rdc']=self.rdc_inv[index_rdc]
        # 更新实际调拨，记录理论调拨和实际调拨，之所以将
        for f in self.fdc_list:
            index_fdc = self.gene_index(f, self_sku, date_s)
            self.allocation_retail[date_s][self_sku]['calc_'+str(f)]=fdc_replacement[f]
            fdc_inv_avail = np.min([fdc_replacement[f], rdc_inv_avail])
            self.allocation_retail[date_s][self_sku]['real_'+str(f)]=fdc_inv_avail
            self.fdc_allocation[index_fdc] = fdc_inv_avail
            self.rdc_inv[index_rdc] = self.rdc_inv[index_rdc] - fdc_inv_avail
            rdc_inv_avail -= fdc_inv_avail
            # need_replacement = sum(fdc_replacement.values())
            # index = self.gene_index('rdc', s, date_s)
            # if need_replacement > self.rdc_inv[index]:
            #     # 采用同比例缩放，亦可设置评判函数，采用贪心算法进行分类，可能存在非整数解，次数需要转换为整数解，待处理
            #     tmp_inv_sum = 0
            #     for f in self.fdc[:-1]:
            #         tmp = np.floor(fdc_replacement[f] / need_replacement * self.rdc_inv[index])
            #         fdc_replacement[f] = tmp
            #         tmp_inv_sum += tmp
            #     fdc_replacement[self.fdc[-1]] = max(self.rdc_inv[index] - tmp_inv_sum, 0)
            # # 更新调拨量
            # for f in self.fdc:
            #     index = self.gene_index(f, s, date_s)
            #     self.fdc_allocation[index] = fdc_replacement[f]
            # # 同时更新RDC库存
            # rdc_index = self.gene_index('rdc', s, date_s)
            # self.rdc_inv[rdc_index] = max(self.rdc_inv[rdc_index] - sum(fdc_replacement.values()), 0)


    def gene_index(self, fdc, sku, date_s=''):
        '''
        #生成调用索引,将在多个地方调用该函数
        '''
        return str(date_s) +':'+str(fdc)+':'+ str(sku)


    def gene_alt(self, fdc):
        '''
        生成对应的调拨时长，用以更新FDC的库存
        '''
        fdc_vlt = self.fdc_alt[fdc]
        fdc_vlt_porb = self.fdc_alt_prob[fdc]
        # 如果没有对应的调拨时长，默认为3天
        if len(fdc_vlt) == 0:
            return 3
        alt_distribution = rv_discrete(values=(fdc_vlt, fdc_vlt_porb))
        return alt_distribution.rvs()


    def calc_fdc_allocation(self,self_sku,date_s, fdc):
        '''
        ------输入数据格式----
        @date:日期 20161129,字符串格式
        @fdc:fdc
        ------输出数据格式,dataframe-----
        @date:日期
        @sku:sku
        @fdc:fdc
        @inv:当前库存
        @allocation：调拨量
        @open_po:在途量
        @arrive_quantity:当日到达量
        '''
        # 计算补货点，判断补货量
        # 假设一个RDC-FDC同一天的调拨 运达实际相同
        index = self.gene_index(fdc, self_sku, date_s)
        # 获取当前库存，当前库存已在订单循环部分完成
        # 获取调拨量,从调拨字典中获取调拨量
        if self.fdc_allocation[index] > 0:
            self.fdc_inv[index]['allocation'] = self.fdc_allocation[index]
            # 放在这里，因为同一个调拨单的也不能保证同一天到达，所以按照SKU进行时长抽样
            alt=-1
            while (alt<1 or alt >5):
                alt = self.gene_alt(fdc)
            #保持alt信息
            self.alt_sim[index]=alt
            # 更新在途量,c为标记变量
            c = 0
            format_date = '%Y-%m-%d'
            while c < alt:
                date_tmp = datetime.strptime(date_s, format_date) + timedelta(c)
                date_s_c = date_tmp.strftime('%Y-%m-%d')
                index_tmp = self.gene_index(fdc, self_sku, date_s_c)
                self.fdc_inv[index_tmp]['open_po'] = self.fdc_inv[index]['allocation'] + self.fdc_inv[index_tmp]['open_po']
                c += 1
            date_alt = datetime.strptime(date_s, format_date) +timedelta(alt)
            date_s_alt = date_alt.strftime(format_date)
            index_1 = self.gene_index(fdc, self_sku, date_s_alt)
            # 更新当日到达量
            self.fdc_inv[index_1]['arrive_quantity'] = self.fdc_inv[index]['allocation'] + self.fdc_inv[index_1]['arrive_quantity']
        #当天库存等于 当天00:00:00的库存+当天到达-在途消耗，当天到达量可能低于在途消耗，所以需要预处理
        #当天实际到达量为 min(self.fdc_inv[index]['arrive_quantity']-self.fdc_inv[index]['cons_open_po'],0),同时更新在途消耗为
        #max(self.fdc_inv[index]['cons_open_po']-self.fdc_inv[index]['arrive_quantity']，0),在途消耗仅仅小于在途量，与其他变量无直接关系
        self.fdc_inv[index]['inv'] = self.fdc_inv[index]['inv'] + \
                                     max(self.fdc_inv[index]['arrive_quantity']-self.fdc_inv[index]['cons_open_po'],0)
        self.fdc_inv[index]['cons_open_po']=max(self.fdc_inv[index]['cons_open_po']-self.fdc_inv[index]['arrive_quantity'],0)


    def gene_fdc_datasets(self):
        self.sku_allocation=defaultdict(int)
        self.sku_open_po=defaultdict(int)
        self.sku_arrive_quantity=defaultdict(int)
        self.sku_inv=defaultdict(int)
        self.sku_cons_open_po=defaultdict(int)
        for k,v in self.fdc_inv.items():
            self.sku_allocation[k] = v['allocation']
            self.sku_open_po[k] = v['open_po']
            self.sku_arrive_quantity[k] = v['arrive_quantity']
            self.sku_inv[k] = v['inv']
            self.sku_cons_open_po[k] = v['cons_open_po']
        self.allocation_retail_real=defaultdict(int)
        self.allocation_retail_cacl=defaultdict(int)
        self.allocation_retail_rdc=defaultdict(int)
        for k_date,v in self.allocation_retail.items():
            for k_sku,v1 in v.items():
                for k_fdc,v2 in v1.items():
                    if 'rdc' not in k_fdc:
                        allocation_value_type=k_fdc.split('_')[0]
                        allocation_fdc=k_fdc.split('_')[1]
                        if allocation_value_type=='real':
                            tmp_index=self.gene_index(allocation_fdc,k_sku,k_date)
                            self.allocation_retail_real[tmp_index]=v2
                        elif allocation_value_type=='calc':
                            tmp_index=self.gene_index(allocation_fdc,k_sku,k_date)
                            self.allocation_retail_cacl[tmp_index]=v2
                    else:
                        tmp_index=self.gene_index('rdc',k_sku,k_date)
                        self.allocation_retail_rdc[tmp_index]=v2


    def get_daily_data(self):
        self.gene_fdc_datasets()
        rdc_mid_inv=pd.DataFrame({"index":self.rdc_inv.keys(),"rdc_inv":self.rdc_inv.values()})
        # rdc_mid2_inv=pd.DataFrame(list(rdc_mid_inv['index'].apply(lambda x:x.split(':'),1)))
        #
        # rdc_mid2_inv.columns=['dt','rdc','sku_id']
        #
        # del rdc_mid_inv['index']
        #
        # rdc_inv_df=rdc_mid2_inv.join(rdc_mid_inv)
        # rdc_inv_df=rdc_inv_df.loc[:,['dt','sku_id','rdc_inv']]

        daily_data = {'sales_his_origin': self.sales_retail,
                      'inv_his': self.fdc_his_inv,
                      'inv_sim':self.fdc_begin_inv,
                      'cons_open_po':self.sku_cons_open_po,
                      'sales_sim': self.sim_sales_retail,
                       'fdc_sales_sim':self.fdc_sales_retail,
                      'lop': self.lop,
                      'allocation_qtty_sim': self.sku_allocation,
                      'open_po_sim': self.sku_open_po,
                      'alt_sim': self.alt_sim,
                      'arrive_qtty_sim': self.sku_arrive_quantity,
                      'allocation_retail_real':self.allocation_retail_real,
                      'allocation_retail_cacl':self.allocation_retail_cacl}
        daily_data_mid=pd.DataFrame(daily_data, columns=['sales_his_origin','inv_his','inv_sim',
                                                         'cons_open_po','sales_sim','fdc_sales_sim','lop',
                                                         'allocation_qtty_sim','open_po_sim','alt_sim','arrive_qtty_sim',
                                                         'allocation_retail_real','allocation_retail_cacl'])
        return rdc_mid_inv,daily_data_mid
        # daily_data_mid.fillna(0,inplace=True)
        # daily_data_mid.reset_index(inplace=True)
        # daily_data_mid2=pd.DataFrame(list(daily_data_mid['index'].apply(lambda x:x.split(':'),1)))
        # daily_data_mid2.columns=['dt','fdc_id','sku_id']
        # # print 'fdc_id',pd.unique(daily_data_mid2.fdc_id)
        # del daily_data_mid['index']
        # self.reuslt_daily_data=daily_data_mid2.join(daily_data_mid)
        # self.reuslt_daily_data=pd.merge(self.reuslt_daily_data,rdc_inv_df,on=['dt','sku_id'])
        # return self.reuslt_daily_data[self.reuslt_daily_data['fdc_id']!='rdc']


    def calc_kpi(self):
        fdc_kpi=defaultdict(lambda :defaultdict(float))
        for tmp_fdcid,fdcdata in self.reuslt_daily_data.groupby(['fdc_id']):
            if 'rdc' not in tmp_fdcid:
                # 现货率（cr）：有货天数除以总天数
                fdc_kpi['cr_his'][tmp_fdcid]=sum(fdcdata.inv_his>0)/float(len(self.date_range))
                fdc_kpi['cr_sim'][tmp_fdcid]=sum(fdcdata.inv_sim>0)/float(len(self.date_range))
                # 周转天数（ito）：平均库存除以平均销量
                fdc_kpi['ito_sim'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.sales_sim))<=0 else float(np.nanmean(fdcdata.inv_sim)) / float(np.nanmean(fdcdata.sales_sim))
                fdc_kpi['ito_his'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.sales_his_origin))<=0 else float(np.nanmean(fdcdata.inv_his)) / float(np.nanmean(fdcdata.sales_his_origin))
                # 总销量（ts）
                fdc_kpi['ts_sim'][tmp_fdcid] = np.sum(fdcdata.sales_sim)
                fdc_kpi['ts_his'][tmp_fdcid] = np.sum(fdcdata.sales_his_origin)
                fdc_kpi['ts_rate'][tmp_fdcid]=-1 if float(fdc_kpi['ts_his'][tmp_fdcid])<=0 else float(fdc_kpi['ts_sim'][tmp_fdcid])/float(fdc_kpi['ts_his'][tmp_fdcid])
        tmp_mid_kpi=pd.DataFrame(fdc_kpi)
        tmp_mid_kpi.reset_index(inplace=True)
        tmp_mid_kpi.rename(columns={'index':'fdc_id'},inplace=True)
        tmp_mid_kpi['sku_id']=self.sku
        # print tmp_mid_kpi
        return tmp_mid_kpi


    def calKpi_label(self, kpi_need_fdc, suffix=''):
        '''
        需要字段：sku_id, fdc_id, inv_his, inv_sim, fdc_sales_sim, sales_his_origin
        '''
        # # kpi_need_fdc = sim_all_sku_retail_keep
        # kpi_need_fdc.columns
        # rdc_inv
        sim_fdc_kpi=[]
        for label_fdcid, fdcdata in kpi_need_fdc.groupby(['fdc_id', 'label']):
            sku_cnt = len(np.unique(fdcdata.sku_id))
            tmp_fdcid, label = label_fdcid[0], label_fdcid[1]
            fdc_kpi = defaultdict(lambda: defaultdict(float))
            # 现货率（cr）：有货天数除以总天数
            fdc_kpi['cr_his'][tmp_fdcid] = sum(fdcdata.inv_his > 0) / float(30 * sku_cnt)
            # print label_fdcid[0]
            # print sku_cnt
            # print sum(fdcdata.inv_his > 0)
            # print float(30 * sku_cnt)
            fdc_kpi['cr_sim'][tmp_fdcid] = sum(fdcdata.inv_sim > 0) / float(30 * sku_cnt)
            # 周转天数（ito）：平均库存除以平均销量
            fdc_kpi['ito_sim'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.fdc_sales_sim)) <= 0 else float(
                np.nanmean(fdcdata.inv_sim)) / float(np.nanmean(fdcdata.fdc_sales_sim))
            fdc_kpi['ito_his'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.sales_his_origin)) <= 0 else float(
                np.nanmean(fdcdata.inv_his)) / float(np.nanmean(fdcdata.sales_his_origin))
            # 总销量（ts）
            fdc_kpi['ts_sim'][tmp_fdcid] = np.sum(fdcdata.fdc_sales_sim)
            fdc_kpi['ts_his'][tmp_fdcid] = np.sum(fdcdata.sales_his_origin)
            fdc_kpi['ts_rate'][tmp_fdcid] = -1 if float(fdc_kpi['ts_his'][tmp_fdcid]) <= 0 else float(
                fdc_kpi['ts_sim'][tmp_fdcid]) / float(fdc_kpi['ts_his'][tmp_fdcid])
            fdc_kpi['label'][tmp_fdcid]=label
            fdc_kpi['cr_his_new_0'][tmp_fdcid] = sum((fdcdata.inv_his > 0) | (fdcdata.rdc_inv > 0)) / float(30 * sku_cnt)
            fdc_kpi['cr_sim_new_0'][tmp_fdcid] = sum((fdcdata.inv_sim > 0) | (fdcdata.rdc_inv > 0)) / float(30 * sku_cnt)
            fdc_kpi['cr_his_new_12'][tmp_fdcid] = sum((fdcdata.inv_his > 0) | (fdcdata.rdc_inv > 12)) / float(30 * sku_cnt)
            fdc_kpi['cr_sim_new_12'][tmp_fdcid] = sum((fdcdata.inv_sim > 0) | (fdcdata.rdc_inv > 12)) / float(30 * sku_cnt)
            sim_fdc_kpi.append(pd.DataFrame(fdc_kpi))
        sim_fdc_kpi=pd.concat(sim_fdc_kpi)
        sim_fdc_kpi.columns = map(lambda x: x + suffix,list(sim_fdc_kpi.columns))
        sim_fdc_kpi.reset_index(inplace=True)
        sim_fdc_kpi.rename(columns={'index': 'fdc_id'}, inplace=True)
        sim_fdc_kpi.rename(columns={'label'+suffix: 'label'}, inplace=True)
        return sim_fdc_kpi


    def calKpi(self, kpi_need_fdc, suffix=''):
        '''
        需要字段：sku_id, fdc_id, inv_his, inv_sim, sales_sim, sales_his_origin
        '''
        # # kpi_need_fdc = sim_all_sku_retail_keep
        # kpi_need_fdc.columns
        # rdc_inv
        fdc_kpi = defaultdict(lambda: defaultdict(float))
        for tmp_fdcid, fdcdata in kpi_need_fdc.groupby(['fdc_id']):
            sku_cnt = len(np.unique(fdcdata.sku_id))
            # 现货率（cr）：有货天数除以总天数
            fdc_kpi['cr_his'][tmp_fdcid] = sum(fdcdata.inv_his > 0) / float(30 * sku_cnt)
            # print sku_cnt
            # print sum(fdcdata.inv_his > 0)
            # print float(30 * sku_cnt)
            fdc_kpi['cr_sim'][tmp_fdcid] = sum(fdcdata.inv_sim > 0) / float(30 * sku_cnt)
            # 周转天数（ito）：平均库存除以平均销量
            fdc_kpi['ito_sim'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.fdc_sales_sim)) <= 0 else float(
                np.nanmean(fdcdata.inv_sim)) / float(np.nanmean(fdcdata.fdc_sales_sim))
            fdc_kpi['ito_his'][tmp_fdcid] = -1 if float(np.nanmean(fdcdata.sales_his_origin)) <= 0 else float(
                np.nanmean(fdcdata.inv_his)) / float(np.nanmean(fdcdata.sales_his_origin))
            # 总销量（ts）
            fdc_kpi['ts_sim'][tmp_fdcid] = np.sum(fdcdata.fdc_sales_sim)
            fdc_kpi['ts_his'][tmp_fdcid] = np.sum(fdcdata.sales_his_origin)
            fdc_kpi['ts_rate'][tmp_fdcid] = -1 if float(fdc_kpi['ts_his'][tmp_fdcid]) <= 0 else float(
                fdc_kpi['ts_sim'][tmp_fdcid]) / float(fdc_kpi['ts_his'][tmp_fdcid])
            fdc_kpi['cr_his_new_0'][tmp_fdcid] = sum((fdcdata.inv_his > 0) | (fdcdata.rdc_inv > 0)) / float(30 * sku_cnt)
            fdc_kpi['cr_sim_new_0'][tmp_fdcid] = sum((fdcdata.inv_sim > 0) | (fdcdata.rdc_inv > 0)) / float(30 * sku_cnt)
            fdc_kpi['cr_his_new_12'][tmp_fdcid] = sum((fdcdata.inv_his > 0) | (fdcdata.rdc_inv > 12)) / float(30 * sku_cnt)
            fdc_kpi['cr_sim_new_12'][tmp_fdcid] = sum((fdcdata.inv_sim > 0) | (fdcdata.rdc_inv > 12)) / float(30 * sku_cnt)
        sim_fdc_kpi=pd.DataFrame(fdc_kpi)
        sim_fdc_kpi.columns = map(lambda x: x + suffix,list(sim_fdc_kpi.columns))
        sim_fdc_kpi.reset_index(inplace=True)
        sim_fdc_kpi.rename(columns={'index': 'fdc_id'}, inplace=True)
        return sim_fdc_kpi


    def kpi_analysis(self):
        analysis_path = r'D:\Lgb\WorkFiles\FDC_UNION_ALLOCATION\analysis_3_policy\Simulation_Results'
        all_files = ['simulation_results_L_std', 'simulation_results_S', 'simulation_results_select',
                     'simulation_results_replace_std',
                     'simulation_results_replace_std_7', 'simulation_results_replace_std_lop0.5',
                     'simulation_results_replace_std_lop1.5',
                     'simulation_results_inverse']
        all_suffix = ['_L_std', '_S', '_8', '_std', '_std_7', '_lop0.5', '_lop1.5', 'inverse']
        # files = ['simulation_results_replace_std_7', 'simulation_results_inverse',
        #          'system_all_sku_retail_inverse_system', 'sim_all_sku_retail_mix']
        # suffix = ['_std_7', 'inverse', '_inverse_system', '_mix']
        files = all_files
        suffix = all_suffix
        band = pd.read_table(r'D:\Lgb\WorkFiles\FDC_UNION_ALLOCATION\analysis_3_policy\SKUABCband_20170330153011.csv')
        band.columns = ['sku_id', 'label']
        first = 0
        add_true = True
        kpi_list = []
        kpi_band_list = []
        for i, each_file in enumerate(files):
            t1 = time.time()
            print "[ Read the File ]: {0}".format(each_file)
            # 1、--------------------------- 读取文件 ---------------------------
            # sim_all_sku_kpi = pd.read_table(analysis_path + os.sep + each_file + os.sep + 'sim_all_sku_kpi.csv')
            # system_all_sku_kpi = pd.read_table(analysis_path + os.sep + each_file + os.sep + 'system_all_sku_kpi.csv')
            sim_all_sku_retail = pd.read_table(analysis_path + os.sep + each_file + os.sep + 'sim_all_sku_retail.csv')
            system_all_sku_retail = pd.read_table(
                analysis_path + os.sep + each_file + os.sep + 'system_all_sku_retail.csv')
            sim_all_sku_retail = sim_all_sku_retail.merge(band, on=['sku_id'])
            system_all_sku_retail = system_all_sku_retail.merge(band, on=['sku_id'])
            printRunTime(t1, 'Read File')
            t1 = time.time()
            if first == 0:
                print '[ Calculate Del ] Calculate Del sku for Sale is zero ...'
                sku_del_list = []
                # 2、--------------------------- 筛选 剔除总销量 为0的 ---------------------------
                for key, value in sim_all_sku_retail.groupby(['fdc_id', 'sku_id']):
                    if np.sum(value['sales_his_origin']) == 0:
                        sku_del_list.append(key)
                first += 1
                sku_all_list = map(lambda x: (x[0], x[1]),
                                   sim_all_sku_retail.loc[:, ['fdc_id', 'sku_id']].drop_duplicates().values)
                sku_keep_list = set(sku_all_list) - set(sku_del_list)
                sku_del_list_pd = pd.DataFrame(sku_del_list, columns=['fdc_id', 'sku_id'])
                sku_del_list_pd.to_csv(analysis_path + os.sep + 'sku_del_list.csv', index=False)
                sku_keep_list_pd = pd.DataFrame(list(sku_keep_list), columns=['fdc_id', 'sku_id'])
                sku_keep_list_pd.to_csv(analysis_path + os.sep + 'sku_keep_list.csv', index=False)
                print '[ Calculate Del ] Finish the Calculate Del sku !'
            else:
                sku_del_list_pd = pd.read_csv(analysis_path + os.sep + 'sku_del_list.csv')
                sku_keep_list_pd = pd.read_csv(analysis_path + os.sep + 'sku_keep_list.csv')
            print '[ Calculate KPI ] ...'
            sim_all_sku_retail_keep = sim_all_sku_retail.merge(sku_keep_list_pd, on=['fdc_id', 'sku_id'])
            system_all_sku_retail_keep = system_all_sku_retail.merge(sku_keep_list_pd, on=['fdc_id', 'sku_id'])
            # 3、--------------------------- 计算 KPI ---------------------------
            sim_all_sku_retail_keep_kpi = calKpi(sim_all_sku_retail_keep, suffix='_sim' + suffix[i])
            system_all_sku_retail_keep_kpi = calKpi(system_all_sku_retail_keep, suffix='_system' + suffix[i])
            if i == 0:
                kpi_list.append(sim_all_sku_retail_keep_kpi)
                kpi_list.append(system_all_sku_retail_keep_kpi)
            else:
                kpi_list.append(sim_all_sku_retail_keep_kpi)
            sim_all_sku_retail_keep_kpi_band = calKpi_label(sim_all_sku_retail_keep, suffix='_sim' + suffix[i])
            system_all_sku_retail_keep_kpi_band = calKpi_label(system_all_sku_retail_keep, suffix='_system' + suffix[i])
            if i == 0:
                kpi_band_list.append(sim_all_sku_retail_keep_kpi_band)
                kpi_band_list.append(system_all_sku_retail_keep_kpi_band)
            else:
                kpi_band_list.append(sim_all_sku_retail_keep_kpi_band)
            printRunTime(t1, 'Calculate KPI')
        # 4、--------------------------- 合并 KPI ---------------------------
        kpi_list_1 = reduce(lambda x, y: x.merge(y, on=['fdc_id']), kpi_list)
        kpi_list_2 = reduce(lambda x, y: x.merge(y, on=['fdc_id', 'label']), kpi_band_list)
        need_columns = ['cr_his_sim{0}'.format(suffix[0])] + ['cr_sim_sim{0}'.format(x) for x in suffix] + [
            'cr_sim_system{0}'.format(suffix[0])] + \
                       ['ito_his_sim{0}'.format(suffix[0])] + ['ito_sim_sim{0}'.format(x) for x in suffix] + [
                           'ito_sim_system{0}'.format(suffix[0])] + \
                       ['ts_his_sim{0}'.format(suffix[0])] + ['ts_sim_sim{0}'.format(x) for x in suffix] + [
                           'ts_sim_system{0}'.format(suffix[0])] + \
                       ['ts_rate_sim{0}'.format(x) for x in suffix] + ['ts_rate_system{0}'.format(suffix[0])]
        # ['cr_his_new_0_sim{0}'.format(suffix[0]) for x in ['his'] ]
        kpi_list_1_keep = kpi_list_1.loc[:, ['fdc_id'] + need_columns]
        kpi_list_2_keep = kpi_list_2.loc[:, ['fdc_id', 'label'] + need_columns]
        # 5、--------------------------- 存储 KPI ---------------------------
        if add_true:
            kpi_list_1_keep.to_csv(analysis_path + os.sep + 'kpi_list_1_keep_add.csv', index=False)
            kpi_list_2_keep.to_csv(analysis_path + os.sep + 'kpi_list_2_keep_add.csv', index=False)
        else:
            kpi_list_1_keep.to_csv(analysis_path + os.sep + 'kpi_list_1_keep.csv', index=False)
            kpi_list_2_keep.to_csv(analysis_path + os.sep + 'kpi_list_2_keep.csv', index=False)
            # 6、new 分析
            # 'cr_his_new_0_sim_L_std', 'cr_sim_new_0_sim_L_std', 'cr_his_new_12_sim_L_std', 'cr_sim_new_12_sim_L_std'


    def allocationSimulation(self):
        rdc_fdc=self.fdc_list
        complete_sku=0
        starttime=datetime.now()
        print 'simulation....',len(self.sku_list)
        for self_sku in self.sku_list:
            self_sku=str(self_sku)
            for d in self.date_range:
                # 1.1 更新获取当天白名单`
                # self.logger.info('begin to deal with ' + d)
                # self.logger.info(u'标记当天新白名单信息,SKU属于当天白名单则对应的值标记为 1')
                self.gene_whitelist(self_sku,d)
                # 1.2 更新RDC库存，增
                # self.logger.info(u'更新当天rdc库存')
                self.cacl_rdc_inv(self_sku,d)
                # 1.3 计算每个SKU的调拨量
                # self.logger.info(u'计算每个SKU的调拨量')
                # 按照分配原则，分配顺序，调拨量取整等原则 对调拨量进行调整
                self.calc_sku_allocation(self_sku,d)
                # 更新FDC的调拨量
                for f in rdc_fdc:
                    # 更新FDC当天库存，增
                    # 并针对FDC进行调拨，仅更新调拨、在途、到达，并未减
                    # self.logger.info('begin to deal with :' + d + '...fdc:' + str(f))
                    self.calc_fdc_allocation(self_sku,d, f)

                    #----------------------更新SKU的库存信息------------------------------------------------------------------------------------------#
                    index = self.gene_index(f, self_sku, d)
                    rdc_index = self.gene_index('rdc', self_sku, d)
                    ###标记初始化库存
                    # print index,self.fdc_inv[index]['inv']
                    self.fdc_begin_inv[index]=self.fdc_inv[index]['inv']
                    ###标记完成
                    #FDC销量标记与总销量标记放在第一位，因为涉及到在途消耗，该尚未造成实际的消耗增加
                    self.fdc_sales_retail[index] = min(self.sales_retail[index],
                                               self.fdc_inv[index]['inv']+self.fdc_inv[index]['open_po']-self.fdc_inv[index]['cons_open_po'])
                    self.sim_sales_retail[index] = min(self.sales_retail[index],
                                              self.fdc_inv[index]['inv']+self.fdc_inv[index]['open_po']-self.fdc_inv[index]['cons_open_po']
                                              + self.rdc_inv[rdc_index])
                    # print self.sim_sales_retail[index],index,self.rdc_inv[rdc_index]
                    #记录消耗在途的数量
                    if self.sales_retail[index]>self.fdc_inv[index]['inv']:
                        #该递推公式保证了 self.fdc_inv[index]['cons_open_po'] 小于等于  self.fdc_inv[index]['open_po']
                        #同时 在途消耗为正值，s[1]>self.fdc_inv[index]['inv'] 保证了 第一项>0
                        self.fdc_inv[index]['cons_open_po']=self.fdc_inv[index]['cons_open_po']+min(self.sales_retail[index]-self.fdc_inv[index]['inv'],
                                                                                                    self.fdc_inv[index]['open_po']-self.fdc_inv[index]['cons_open_po'])
                    #库存放在最好此时的标记订单已经消耗实际库存
                    # 首先从fdc 发货 其次不够的从rdc补，需求>=库存，则fdc库存为0,否则为 剩余量
                    sku_gap = self.sales_retail[index] - self.fdc_inv[index]['inv']
                    self.fdc_inv[index]['inv'] = 0 if sku_gap >= 0 else abs(sku_gap)
                    # 在模拟中有些订单会不被满足，所以需要在0 和实际值之间取最大值，无效订单在simu_order里面会被标记
                    sku_gap = self.sales_retail[index] - (self.fdc_inv[index]['inv']+self.fdc_inv[index]['open_po']-self.fdc_inv[index]['cons_open_po'])
                    self.rdc_inv[rdc_index] = self.rdc_inv[rdc_index] if sku_gap < 0 else max(
                        self.rdc_inv[rdc_index] - sku_gap, 0)
          #----------------------------------------------------------------------------------------------------------------#


                # 更新下一天库存，将当天剩余库存标记为第二天库存,第二天到达库存会在开始增加上，将每天最后的在途消耗 更新为第二天的初始在途消耗，在第二天更新调拨的时候
                #在途消耗与第二天的到达量做运算，如果有到达，则在途消耗做减法运算，即 不入库直接发给用户
                for f in self.fdc_list:
                    format_date = '%Y-%m-%d'
                    date_tmp = datetime.strptime(d, format_date) + timedelta(1)
                    date_s_c = date_tmp.strftime('%Y-%m-%d')
                    index_next = self.gene_index(f, self_sku, date_s_c)
                    index = self.gene_index(f, self_sku, d)
                    self.fdc_inv[index_next]['inv'] = self.fdc_inv[index]['inv']
                    self.fdc_inv[index_next]['cons_open_po'] = self.fdc_inv[index]['cons_open_po']
                # 不仅仅更新白名单更新全量库存，如何获取全量list
                format_date = '%Y-%m-%d'
                date_tmp = datetime.strptime(d, format_date) + timedelta(1)
                date_s_c = date_tmp.strftime('%Y-%m-%d')
                index_next = self.gene_index('rdc', self_sku, date_s_c)
                index = self.gene_index('rdc', self_sku, d)
                self.rdc_inv[index_next] = self.rdc_inv[index]
            endtime = datetime.now()
            used_seconds = (endtime - starttime).total_seconds()
            complete_sku += 1
            self.logger.info( 'Finish SKU=' + str(complete_sku) + ' | ' + 'Used seconds=' +
                str(used_seconds))