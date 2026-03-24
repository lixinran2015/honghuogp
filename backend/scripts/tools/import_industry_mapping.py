#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入用户提供的股票行业匹配数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import date
from sqlalchemy import create_engine, text
from data_warehouse.config import DATABASE_URL
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 用户提供的行业匹配数据
INDUSTRY_MAPPING = [
    {"code": "000034", "name": "神州数码", "ts_code": "000034.SZ", "sector_id": "BK0737"},
    {"code": "000039", "name": "中集集团", "ts_code": "000039.SZ", "sector_id": "BK0910"},
    {"code": "000338", "name": "潍柴动力", "ts_code": "000338.SZ", "sector_id": "BK0481"},
    {"code": "000519", "name": "中兵红箭", "ts_code": "000519.SZ", "sector_id": "BK0480"},
    {"code": "000533", "name": "顺钠股份", "ts_code": "000533.SZ", "sector_id": "BK0457"},
    {"code": "000536", "name": "华映科技", "ts_code": "000536.SZ", "sector_id": "BK1038"},
    {"code": "000559", "name": "万向钱潮", "ts_code": "000559.SZ", "sector_id": "BK0481"},
    {"code": "000566", "name": "海南海药", "ts_code": "000566.SZ", "sector_id": "BK0465"},
    {"code": "000572", "name": "海马汽车", "ts_code": "000572.SZ", "sector_id": "BK1029"},
    {"code": "000633", "name": "合金投资", "ts_code": "000633.SZ", "sector_id": "BK1027"},
    {"code": "000665", "name": "湖北广电", "ts_code": "000665.SZ", "sector_id": "BK0486"},
    {"code": "000686", "name": "东北证券", "ts_code": "000686.SZ", "sector_id": "BK0473"},
    {"code": "000688", "name": "国城矿业", "ts_code": "000688.SZ", "sector_id": "BK0478"},
    {"code": "000695", "name": "滨海能源", "ts_code": "000695.SZ", "sector_id": "BK0428"},
    {"code": "000753", "name": "漳州发展", "ts_code": "000753.SZ", "sector_id": "BK1028"},
    {"code": "000796", "name": "凯撒旅业", "ts_code": "000796.SZ", "sector_id": "BK0485"},
    {"code": "000905", "name": "厦门港务", "ts_code": "000905.SZ", "sector_id": "BK0450"},
    {"code": "000908", "name": "*ST景峰", "ts_code": "000908.SZ", "sector_id": "BK0465"},
    {"code": "000933", "name": "神火股份", "ts_code": "000933.SZ", "sector_id": "BK0437"},
    {"code": "000973", "name": "佛塑科技", "ts_code": "000973.SZ", "sector_id": "BK0454"},
    {"code": "001203", "name": "大中矿业", "ts_code": "001203.SZ", "sector_id": "BK1017"},
    {"code": "001298", "name": "好上好", "ts_code": "001298.SZ", "sector_id": "BK0438"},
    {"code": "001301", "name": "尚太科技", "ts_code": "001301.SZ", "sector_id": "BK1033"},
    {"code": "001309", "name": "德明利", "ts_code": "001309.SZ", "sector_id": "BK0459"},
    {"code": "002020", "name": "京新药业", "ts_code": "002020.SZ", "sector_id": "BK0465"},
    {"code": "002067", "name": "景兴纸业", "ts_code": "002067.SZ", "sector_id": "BK0470"},
    {"code": "002068", "name": "黑猫股份", "ts_code": "002068.SZ", "sector_id": "BK0538"},
    {"code": "002077", "name": "大港股份", "ts_code": "002077.SZ", "sector_id": "BK0451"},
    {"code": "002080", "name": "中材科技", "ts_code": "002080.SZ", "sector_id": "BK1032"},
    {"code": "002108", "name": "沧州明珠", "ts_code": "002108.SZ", "sector_id": "BK0454"},
    {"code": "002129", "name": "TCL中环", "ts_code": "002129.SZ", "sector_id": "BK1031"},
    {"code": "002163", "name": "海南发展", "ts_code": "002163.SZ", "sector_id": "BK0422"},
    {"code": "002175", "name": "东方智造", "ts_code": "002175.SZ", "sector_id": "BK1034"},
    {"code": "002176", "name": "江特电机", "ts_code": "002176.SZ", "sector_id": "BK1033"},
    {"code": "002196", "name": "方正电机", "ts_code": "002196.SZ", "sector_id": "BK1030"},
    {"code": "002208", "name": "合肥城建", "ts_code": "002208.SZ", "sector_id": "BK0451"},
    {"code": "002213", "name": "大为股份", "ts_code": "002213.SZ", "sector_id": "BK0458"},
    {"code": "002218", "name": "拓日新能", "ts_code": "002218.SZ", "sector_id": "BK1031"},
    {"code": "002227", "name": "奥 特 迅", "ts_code": "002227.SZ", "sector_id": "BK1034"},
    {"code": "002250", "name": "联化科技", "ts_code": "002250.SZ", "sector_id": "BK0538"},
    {"code": "002251", "name": "步步高", "ts_code": "002251.SZ", "sector_id": "BK0482"},
    {"code": "002255", "name": "海陆重工", "ts_code": "002255.SZ", "sector_id": "BK0545"},
    {"code": "002317", "name": "众生药业", "ts_code": "002317.SZ", "sector_id": "BK1040"},
    {"code": "002320", "name": "海峡股份", "ts_code": "002320.SZ", "sector_id": "BK0450"},
    {"code": "002326", "name": "永太科技", "ts_code": "002326.SZ", "sector_id": "BK0538"},
    {"code": "002370", "name": "亚太药业", "ts_code": "002370.SZ", "sector_id": "BK0465"},
    {"code": "002384", "name": "东山精密", "ts_code": "002384.SZ", "sector_id": "BK0459"},
    {"code": "002400", "name": "省广集团", "ts_code": "002400.SZ", "sector_id": "BK0447"},
    {"code": "002407", "name": "多氟多", "ts_code": "002407.SZ", "sector_id": "BK1033"},
    {"code": "002436", "name": "兴森科技", "ts_code": "002436.SZ", "sector_id": "BK0459"},
    {"code": "002451", "name": "摩恩电气", "ts_code": "002451.SZ", "sector_id": "BK0457"},
    {"code": "002459", "name": "晶澳科技", "ts_code": "002459.SZ", "sector_id": "BK1031"},
    {"code": "002497", "name": "雅化集团", "ts_code": "002497.SZ", "sector_id": "BK1033"},
    {"code": "002512", "name": "达华智能", "ts_code": "002512.SZ", "sector_id": "BK0448"},
    {"code": "002578", "name": "闽发铝业", "ts_code": "002578.SZ", "sector_id": "BK0478"},
    {"code": "002593", "name": "日上集团", "ts_code": "002593.SZ", "sector_id": "BK0479"},
    {"code": "002603", "name": "以岭药业", "ts_code": "002603.SZ", "sector_id": "BK1040"},
    {"code": "002611", "name": "东方精工", "ts_code": "002611.SZ", "sector_id": "BK0910"},
    {"code": "002639", "name": "雪人集团", "ts_code": "002639.SZ", "sector_id": "BK0545"},
    {"code": "002709", "name": "天赐材料", "ts_code": "002709.SZ", "sector_id": "BK1033"},
    {"code": "002728", "name": "特一药业", "ts_code": "002728.SZ", "sector_id": "BK1040"},
    {"code": "002756", "name": "永兴材料", "ts_code": "002756.SZ", "sector_id": "BK1015"},
    {"code": "002759", "name": "天际股份", "ts_code": "002759.SZ", "sector_id": "BK1033"},
    {"code": "002805", "name": "丰元股份", "ts_code": "002805.SZ", "sector_id": "BK1033"},
    {"code": "002812", "name": "恩捷股份", "ts_code": "002812.SZ", "sector_id": "BK1033"},
    {"code": "002846", "name": "英联股份", "ts_code": "002846.SZ", "sector_id": "BK0733"},
    {"code": "002864", "name": "盘龙药业", "ts_code": "002864.SZ", "sector_id": "BK1040"},
    {"code": "002897", "name": "意华股份", "ts_code": "002897.SZ", "sector_id": "BK0459"},
    {"code": "002927", "name": "泰永长征", "ts_code": "002927.SZ", "sector_id": "BK0457"},
    {"code": "002940", "name": "昂利康", "ts_code": "002940.SZ", "sector_id": "BK0465"},
    {"code": "300001", "name": "特锐德", "ts_code": "300001.SZ", "sector_id": "BK0457"},
    {"code": "300014", "name": "亿纬锂能", "ts_code": "300014.SZ", "sector_id": "BK1033"},
    {"code": "300035", "name": "中科电气", "ts_code": "300035.SZ", "sector_id": "BK1033"},
    {"code": "300037", "name": "新宙邦", "ts_code": "300037.SZ", "sector_id": "BK1033"},
    {"code": "300058", "name": "蓝色光标", "ts_code": "300058.SZ", "sector_id": "BK0447"},
    {"code": "300062", "name": "中能电气", "ts_code": "300062.SZ", "sector_id": "BK0457"},
    {"code": "300068", "name": "南都电源", "ts_code": "300068.SZ", "sector_id": "BK1033"},
    {"code": "300071", "name": "福石控股", "ts_code": "300071.SZ", "sector_id": "BK0738"},
    {"code": "300072", "name": "海新能科", "ts_code": "300072.SZ", "sector_id": "BK0728"},
    {"code": "300086", "name": "康芝药业", "ts_code": "300086.SZ", "sector_id": "BK0465"},
    {"code": "300118", "name": "东方日升", "ts_code": "300118.SZ", "sector_id": "BK1031"},
    {"code": "300173", "name": "福能东方", "ts_code": "300173.SZ", "sector_id": "BK1034"},
    {"code": "300179", "name": "四方达", "ts_code": "300179.SZ", "sector_id": "BK1020"},
    {"code": "300204", "name": "舒泰神", "ts_code": "300204.SZ", "sector_id": "BK1044"},
    {"code": "300223", "name": "北京君正", "ts_code": "300223.SZ", "sector_id": "BK1036"},
    {"code": "300235", "name": "方直科技", "ts_code": "300235.SZ", "sector_id": "BK0737"},
    {"code": "300255", "name": "常山药业", "ts_code": "300255.SZ", "sector_id": "BK0465"},
    {"code": "300274", "name": "阳光电源", "ts_code": "300274.SZ", "sector_id": "BK1031"},
    {"code": "300285", "name": "国瓷材料", "ts_code": "300285.SZ", "sector_id": "BK1020"},
    {"code": "300289", "name": "利德曼", "ts_code": "300289.SZ", "sector_id": "BK1044"},
    {"code": "300302", "name": "同有科技", "ts_code": "300302.SZ", "sector_id": "BK0735"},
    {"code": "300339", "name": "润和软件", "ts_code": "300339.SZ", "sector_id": "BK0737"},
    {"code": "300393", "name": "中来股份", "ts_code": "300393.SZ", "sector_id": "BK1031"},
    {"code": "300405", "name": "科隆股份", "ts_code": "300405.SZ", "sector_id": "BK0538"},
    {"code": "300427", "name": "红相股份", "ts_code": "300427.SZ", "sector_id": "BK0457"},
    {"code": "300432", "name": "富临精工", "ts_code": "300432.SZ", "sector_id": "BK1033"},
    {"code": "300437", "name": "清水源", "ts_code": "300437.SZ", "sector_id": "BK0728"},
    {"code": "300438", "name": "鹏辉能源", "ts_code": "300438.SZ", "sector_id": "BK1033"},
    {"code": "300444", "name": "双杰电气", "ts_code": "300444.SZ", "sector_id": "BK0457"},
    {"code": "300451", "name": "创业慧康", "ts_code": "300451.SZ", "sector_id": "BK0737"},
    {"code": "300455", "name": "航天智装", "ts_code": "300455.SZ", "sector_id": "BK0910"},
    {"code": "300456", "name": "赛微电子", "ts_code": "300456.SZ", "sector_id": "BK1036"},
    {"code": "300475", "name": "香农芯创", "ts_code": "300475.SZ", "sector_id": "BK0459"},
    {"code": "300483", "name": "首华燃气", "ts_code": "300483.SZ", "sector_id": "BK1028"},
    {"code": "300490", "name": "华自科技", "ts_code": "300490.SZ", "sector_id": "BK1034"},
    {"code": "300497", "name": "富祥药业", "ts_code": "300497.SZ", "sector_id": "BK0465"},
    {"code": "300520", "name": "科大国创", "ts_code": "300520.SZ", "sector_id": "BK0737"},
    {"code": "300539", "name": "横河精密", "ts_code": "300539.SZ", "sector_id": "BK0481"},
    {"code": "300560", "name": "中富通", "ts_code": "300560.SZ", "sector_id": "BK0736"},
    {"code": "300568", "name": "星源材质", "ts_code": "300568.SZ", "sector_id": "BK1033"},
    {"code": "300584", "name": "海辰药业", "ts_code": "300584.SZ", "sector_id": "BK0465"},
    {"code": "300598", "name": "诚迈科技", "ts_code": "300598.SZ", "sector_id": "BK0737"},
    {"code": "300626", "name": "华瑞股份", "ts_code": "300626.SZ", "sector_id": "BK1030"},
    {"code": "300648", "name": "星云股份", "ts_code": "300648.SZ", "sector_id": "BK0910"},
    {"code": "300672", "name": "国科微", "ts_code": "300672.SZ", "sector_id": "BK1036"},
    {"code": "300731", "name": "科创新源", "ts_code": "300731.SZ", "sector_id": "BK0454"},
    {"code": "300751", "name": "迈为股份", "ts_code": "300751.SZ", "sector_id": "BK1031"},
    {"code": "300763", "name": "锦浪科技", "ts_code": "300763.SZ", "sector_id": "BK1031"},
    {"code": "300769", "name": "德方纳米", "ts_code": "300769.SZ", "sector_id": "BK1033"},
    {"code": "300801", "name": "泰和科技", "ts_code": "300801.SZ", "sector_id": "BK0728"},
    {"code": "300806", "name": "斯迪克", "ts_code": "300806.SZ", "sector_id": "BK0538"},
    {"code": "300814", "name": "中富电路", "ts_code": "300814.SZ", "sector_id": "BK0459"},
    {"code": "300821", "name": "东岳硅材", "ts_code": "300821.SZ", "sector_id": "BK0538"},
    {"code": "300827", "name": "上能电气", "ts_code": "300827.SZ", "sector_id": "BK1031"},
    {"code": "300862", "name": "蓝盾光电", "ts_code": "300862.SZ", "sector_id": "BK1038"},
    {"code": "300867", "name": "圣元环保", "ts_code": "300867.SZ", "sector_id": "BK0728"},
    {"code": "300875", "name": "捷强装备", "ts_code": "300875.SZ", "sector_id": "BK0480"},
    {"code": "300902", "name": "国安达", "ts_code": "300902.SZ", "sector_id": "BK0910"},
    {"code": "300919", "name": "中伟股份", "ts_code": "300919.SZ", "sector_id": "BK1033"},
    {"code": "300975", "name": "商络电子", "ts_code": "300975.SZ", "sector_id": "BK0459"},
    {"code": "301012", "name": "扬电科技", "ts_code": "301012.SZ", "sector_id": "BK0457"},
    {"code": "301013", "name": "利和兴", "ts_code": "301013.SZ", "sector_id": "BK0910"},
    {"code": "301017", "name": "漱玉平民", "ts_code": "301017.SZ", "sector_id": "BK1042"},
    {"code": "301045", "name": "天禄科技", "ts_code": "301045.SZ", "sector_id": "BK1038"},
    {"code": "301150", "name": "中一科技", "ts_code": "301150.SZ", "sector_id": "BK1033"},
    {"code": "301152", "name": "天力锂能", "ts_code": "301152.SZ", "sector_id": "BK1033"},
    {"code": "301201", "name": "诚达药业", "ts_code": "301201.SZ", "sector_id": "BK0465"},
    {"code": "301213", "name": "观想科技", "ts_code": "301213.SZ", "sector_id": "BK0480"},
    {"code": "301217", "name": "铜冠铜箔", "ts_code": "301217.SZ", "sector_id": "BK1033"},
    {"code": "301292", "name": "海科新源", "ts_code": "301292.SZ", "sector_id": "BK1033"},
    {"code": "301308", "name": "江波龙", "ts_code": "301308.SZ", "sector_id": "BK1036"},
    {"code": "301357", "name": "北方长龙", "ts_code": "301357.SZ", "sector_id": "BK0481"},
    {"code": "301358", "name": "湖南裕能", "ts_code": "301358.SZ", "sector_id": "BK1033"},
    {"code": "301489", "name": "思泉新材", "ts_code": "301489.SZ", "sector_id": "BK0459"},
    {"code": "600006", "name": "东风股份", "ts_code": "600006.SH", "sector_id": "BK0733"},
    {"code": "600030", "name": "中信证券", "ts_code": "600030.SH", "sector_id": "BK0473"},
    {"code": "600031", "name": "三一重工", "ts_code": "600031.SH", "sector_id": "BK0739"},
    {"code": "600048", "name": "保利发展", "ts_code": "600048.SH", "sector_id": "BK0451"},
    {"code": "600050", "name": "中国联通", "ts_code": "600050.SH", "sector_id": "BK0736"},
    {"code": "600061", "name": "国投资本", "ts_code": "600061.SH", "sector_id": "BK0738"},
    {"code": "600062", "name": "华润双鹤", "ts_code": "600062.SH", "sector_id": "BK0465"},
    {"code": "600063", "name": "皖维高新", "ts_code": "600063.SH", "sector_id": "BK1019"},
    {"code": "600072", "name": "中船科技", "ts_code": "600072.SH", "sector_id": "BK0729"},
    {"code": "600079", "name": "人福医药", "ts_code": "600079.SH", "sector_id": "BK0465"},
    {"code": "600080", "name": "金花股份", "ts_code": "600080.SH", "sector_id": "BK0465"},
    {"code": "600085", "name": "同仁堂", "ts_code": "600085.SH", "sector_id": "BK1040"},
    {"code": "600089", "name": "特变电工", "ts_code": "600089.SH", "sector_id": "BK1034"},
    {"code": "600095", "name": "湘财股份", "ts_code": "600095.SH", "sector_id": "BK0473"},
    {"code": "600100", "name": "同方股份", "ts_code": "600100.SH", "sector_id": "BK0735"},
    {"code": "600104", "name": "上汽集团", "ts_code": "600104.SH", "sector_id": "BK1029"},
    {"code": "600110", "name": "诺德股份", "ts_code": "600110.SH", "sector_id": "BK1033"},
    {"code": "600114", "name": "东睦股份", "ts_code": "600114.SH", "sector_id": "BK0481"},
    {"code": "600120", "name": "浙江东方", "ts_code": "600120.SH", "sector_id": "BK0484"},
    {"code": "600126", "name": "杭钢股份", "ts_code": "600126.SH", "sector_id": "BK0479"},
    {"code": "600143", "name": "金发科技", "ts_code": "600143.SH", "sector_id": "BK0538"},
    {"code": "600152", "name": "维科技术", "ts_code": "600152.SH", "sector_id": "BK0436"},
    {"code": "600155", "name": "华创云信", "ts_code": "600155.SH", "sector_id": "BK0447"},
    {"code": "600172", "name": "黄河旋风", "ts_code": "600172.SH", "sector_id": "BK1020"},
    {"code": "600183", "name": "生益科技", "ts_code": "600183.SH", "sector_id": "BK0459"},
    {"code": "600184", "name": "光电股份", "ts_code": "600184.SH", "sector_id": "BK0480"},
    {"code": "600185", "name": "珠免集团", "ts_code": "600185.SH", "sector_id": "BK0484"},
    {"code": "600196", "name": "复星医药", "ts_code": "600196.SH", "sector_id": "BK1044"},
    {"code": "600201", "name": "生物股份", "ts_code": "600201.SH", "sector_id": "BK1044"},
    {"code": "600203", "name": "福日电子", "ts_code": "600203.SH", "sector_id": "BK1037"},
    {"code": "600210", "name": "紫江企业", "ts_code": "600210.SH", "sector_id": "BK0733"},
    {"code": "600211", "name": "西藏药业", "ts_code": "600211.SH", "sector_id": "BK1040"},
    {"code": "600219", "name": "南山铝业", "ts_code": "600219.SH", "sector_id": "BK0478"},
    {"code": "600222", "name": "太龙药业", "ts_code": "600222.SH", "sector_id": "BK1040"},
    {"code": "600246", "name": "万通发展", "ts_code": "600246.SH", "sector_id": "BK0451"},
    {"code": "600256", "name": "广汇能源", "ts_code": "600256.SH", "sector_id": "BK0437"},
    {"code": "600268", "name": "国电南自", "ts_code": "600268.SH", "sector_id": "BK0457"},
    {"code": "600272", "name": "开开实业", "ts_code": "600272.SH", "sector_id": "BK1042"},
    {"code": "600276", "name": "恒瑞医药", "ts_code": "600276.SH", "sector_id": "BK0465"},
    {"code": "600292", "name": "远达环保", "ts_code": "600292.SH", "sector_id": "BK0728"},
    {"code": "600309", "name": "万华化学", "ts_code": "600309.SH", "sector_id": "BK0538"},
    {"code": "600327", "name": "大东方", "ts_code": "600327.SH", "sector_id": "BK0482"},
    {"code": "600329", "name": "达仁堂", "ts_code": "600329.SH", "sector_id": "BK1040"},
    {"code": "600333", "name": "长春燃气", "ts_code": "600333.SH", "sector_id": "BK1028"},
    {"code": "600338", "name": "西藏珠峰", "ts_code": "600338.SH", "sector_id": "BK0478"},
    {"code": "600343", "name": "航天动力", "ts_code": "600343.SH", "sector_id": "BK0480"},
    {"code": "600352", "name": "浙江龙盛", "ts_code": "600352.SH", "sector_id": "BK0538"},
    {"code": "600376", "name": "首开股份", "ts_code": "600376.SH", "sector_id": "BK0451"},
    {"code": "600378", "name": "昊华科技", "ts_code": "600378.SH", "sector_id": "BK0538"},
    {"code": "600380", "name": "健康元", "ts_code": "600380.SH", "sector_id": "BK0465"},
    {"code": "600415", "name": "小商品城", "ts_code": "600415.SH", "sector_id": "BK0482"},
    {"code": "600436", "name": "片仔癀", "ts_code": "600436.SH", "sector_id": "BK1040"},
    {"code": "600438", "name": "通威股份", "ts_code": "600438.SH", "sector_id": "BK1031"},
    {"code": "600460", "name": "士兰微", "ts_code": "600460.SH", "sector_id": "BK1036"},
    {"code": "600475", "name": "华光环能", "ts_code": "600475.SH", "sector_id": "BK0728"},
    {"code": "600480", "name": "凌云股份", "ts_code": "600480.SH", "sector_id": "BK0481"},
    {"code": "600490", "name": "鹏欣资源", "ts_code": "600490.SH", "sector_id": "BK0478"},
    {"code": "600497", "name": "驰宏锌锗", "ts_code": "600497.SH", "sector_id": "BK0478"},
    {"code": "600499", "name": "科达制造", "ts_code": "600499.SH", "sector_id": "BK0910"},
    {"code": "600506", "name": "统一股份", "ts_code": "600506.SH", "sector_id": "BK0438"},
    {"code": "600513", "name": "联环药业", "ts_code": "600513.SH", "sector_id": "BK0465"},
    {"code": "600516", "name": "方大炭素", "ts_code": "600516.SH", "sector_id": "BK1020"},
    {"code": "600519", "name": "贵州茅台", "ts_code": "600519.SH", "sector_id": "BK0477"},
    {"code": "600521", "name": "华海药业", "ts_code": "600521.SH", "sector_id": "BK0465"},
    {"code": "600536", "name": "中国软件", "ts_code": "600536.SH", "sector_id": "BK0737"},
    {"code": "600550", "name": "保变电气", "ts_code": "600550.SH", "sector_id": "BK0457"},
    {"code": "600556", "name": "天下秀", "ts_code": "600556.SH", "sector_id": "BK0447"},
    {"code": "600557", "name": "康缘药业", "ts_code": "600557.SH", "sector_id": "BK1040"},
    {"code": "600570", "name": "恒生电子", "ts_code": "600570.SH", "sector_id": "BK0737"},
    {"code": "600576", "name": "祥源文旅", "ts_code": "600576.SH", "sector_id": "BK0485"},
    {"code": "600577", "name": "精达股份", "ts_code": "600577.SH", "sector_id": "BK1030"},
    {"code": "600580", "name": "卧龙电驱", "ts_code": "600580.SH", "sector_id": "BK1030"},
    {"code": "600584", "name": "长电科技", "ts_code": "600584.SH", "sector_id": "BK1036"},
    {"code": "600586", "name": "金晶科技", "ts_code": "600586.SH", "sector_id": "BK0546"},
    {"code": "600588", "name": "用友网络", "ts_code": "600588.SH", "sector_id": "BK0737"},
    {"code": "600592", "name": "龙溪股份", "ts_code": "600592.SH", "sector_id": "BK0481"},
    {"code": "600593", "name": "大连圣亚", "ts_code": "600593.SH", "sector_id": "BK0485"},
    {"code": "600595", "name": "中孚实业", "ts_code": "600595.SH", "sector_id": "BK0478"},
    {"code": "600629", "name": "华建集团", "ts_code": "600629.SH", "sector_id": "BK0726"},
    {"code": "600635", "name": "大众公用", "ts_code": "600635.SH", "sector_id": "BK1028"},
    {"code": "600681", "name": "百川能源", "ts_code": "600681.SH", "sector_id": "BK1028"},
    {"code": "600682", "name": "南京新百", "ts_code": "600682.SH", "sector_id": "BK1042"},
    {"code": "600683", "name": "京投发展", "ts_code": "600683.SH", "sector_id": "BK0451"},
    {"code": "600693", "name": "东百集团", "ts_code": "600693.SH", "sector_id": "BK0482"},
    {"code": "600721", "name": "百花医药", "ts_code": "600721.SH", "sector_id": "BK0465"},
    {"code": "600745", "name": "闻泰科技", "ts_code": "600745.SH", "sector_id": "BK1036"},
    {"code": "600773", "name": "西藏城投", "ts_code": "600773.SH", "sector_id": "BK1015"},
    {"code": "600829", "name": "人民同泰", "ts_code": "600829.SH", "sector_id": "BK1042"},
    {"code": "600875", "name": "东方电气", "ts_code": "600875.SH", "sector_id": "BK1034"},
    {"code": "600977", "name": "中国电影", "ts_code": "600977.SH", "sector_id": "BK0486"},
    {"code": "601012", "name": "隆基绿能", "ts_code": "601012.SH", "sector_id": "BK1031"},
    {"code": "601020", "name": "华钰矿业", "ts_code": "601020.SH", "sector_id": "BK0478"},
    {"code": "601116", "name": "三江购物", "ts_code": "601116.SH", "sector_id": "BK0482"},
    {"code": "601168", "name": "西部矿业", "ts_code": "601168.SH", "sector_id": "BK0478"},
    {"code": "601179", "name": "中国西电", "ts_code": "601179.SH", "sector_id": "BK0457"},
    {"code": "601360", "name": "三六零", "ts_code": "601360.SH", "sector_id": "BK0447"},
    {"code": "601600", "name": "中国铝业", "ts_code": "601600.SH", "sector_id": "BK0478"},
    {"code": "601606", "name": "长城军工", "ts_code": "601606.SH", "sector_id": "BK0480"},
    {"code": "601872", "name": "招商轮船", "ts_code": "601872.SH", "sector_id": "BK0450"},
    {"code": "601888", "name": "中国中免", "ts_code": "601888.SH", "sector_id": "BK0484"},
    {"code": "601969", "name": "海南矿业", "ts_code": "601969.SH", "sector_id": "BK1017"},
    {"code": "603026", "name": "石大胜华", "ts_code": "603026.SH", "sector_id": "BK1033"},
    {"code": "603099", "name": "长白山", "ts_code": "603099.SH", "sector_id": "BK0485"},
    {"code": "603119", "name": "浙江荣泰", "ts_code": "603119.SH", "sector_id": "BK0440"},
    {"code": "603131", "name": "上海沪工", "ts_code": "603131.SH", "sector_id": "BK0545"},
    {"code": "603185", "name": "弘元绿能", "ts_code": "603185.SH", "sector_id": "BK1031"},
    {"code": "603186", "name": "华正新材", "ts_code": "603186.SH", "sector_id": "BK0459"},
    {"code": "603222", "name": "济民健康", "ts_code": "603222.SH", "sector_id": "BK0727"},
    {"code": "603228", "name": "景旺电子", "ts_code": "603228.SH", "sector_id": "BK0459"},
    {"code": "603232", "name": "格尔软件", "ts_code": "603232.SH", "sector_id": "BK0737"},
    {"code": "603301", "name": "振德医疗", "ts_code": "603301.SH", "sector_id": "BK1041"},
    {"code": "603319", "name": "美湖股份", "ts_code": "603319.SH", "sector_id": "BK0481"},
    {"code": "603360", "name": "百傲化学", "ts_code": "603360.SH", "sector_id": "BK0538"},
    {"code": "603456", "name": "九洲药业", "ts_code": "603456.SH", "sector_id": "BK0465"},
    {"code": "603516", "name": "淳中科技", "ts_code": "603516.SH", "sector_id": "BK0735"},
    {"code": "603612", "name": "索通发展", "ts_code": "603612.SH", "sector_id": "BK0478"},
    {"code": "603628", "name": "清源股份", "ts_code": "603628.SH", "sector_id": "BK1031"},
    {"code": "603659", "name": "璞泰来", "ts_code": "603659.SH", "sector_id": "BK1033"},
    {"code": "603686", "name": "福龙马", "ts_code": "603686.SH", "sector_id": "BK0728"},
    {"code": "603778", "name": "国晟科技", "ts_code": "603778.SH", "sector_id": "BK1031"},
    {"code": "603817", "name": "海峡环保", "ts_code": "603817.SH", "sector_id": "BK0728"},
    {"code": "603906", "name": "龙蟠科技", "ts_code": "603906.SH", "sector_id": "BK1033"},
    {"code": "603909", "name": "建发合诚", "ts_code": "603909.SH", "sector_id": "BK0726"},
    {"code": "603948", "name": "建业股份", "ts_code": "603948.SH", "sector_id": "BK0538"},
    {"code": "603978", "name": "深圳新星", "ts_code": "603978.SH", "sector_id": "BK0538"},
    {"code": "605178", "name": "时空科技", "ts_code": "605178.SH", "sector_id": "BK0421"},
    {"code": "605255", "name": "天普股份", "ts_code": "605255.SH", "sector_id": "BK0424"},
    {"code": "605358", "name": "立昂微", "ts_code": "605358.SH", "sector_id": "BK1036"},
    {"code": "688005", "name": "容百科技", "ts_code": "688005.SH", "sector_id": "BK1033"},
    {"code": "688012", "name": "中微公司", "ts_code": "688012.SH", "sector_id": "BK1036"},
    {"code": "688031", "name": "星环科技-U", "ts_code": "688031.SH", "sector_id": "BK0737"},
    {"code": "688048", "name": "长光华芯", "ts_code": "688048.SH", "sector_id": "BK1038"},
    {"code": "688072", "name": "拓荆科技", "ts_code": "688072.SH", "sector_id": "BK1036"},
    {"code": "688116", "name": "天奈科技", "ts_code": "688116.SH", "sector_id": "BK1033"},
    {"code": "688147", "name": "微导纳米", "ts_code": "688147.SH", "sector_id": "BK1039"},
    {"code": "688195", "name": "腾景科技", "ts_code": "688195.SH", "sector_id": "BK1038"},
    {"code": "688205", "name": "德科立", "ts_code": "688205.SH", "sector_id": "BK1038"},
    {"code": "688233", "name": "神工股份", "ts_code": "688233.SH", "sector_id": "BK1036"},
    {"code": "688235", "name": "百济神州-U", "ts_code": "688235.SH", "sector_id": "BK1044"},
    {"code": "688275", "name": "万润新能", "ts_code": "688275.SH", "sector_id": "BK1033"},
    {"code": "688353", "name": "华盛锂电", "ts_code": "688353.SH", "sector_id": "BK1033"},
    {"code": "688388", "name": "嘉元科技", "ts_code": "688388.SH", "sector_id": "BK1033"},
    {"code": "688411", "name": "海博思创", "ts_code": "688411.SH", "sector_id": "BK1034"},
    {"code": "688416", "name": "恒烁股份", "ts_code": "688416.SH", "sector_id": "BK1036"},
    {"code": "688469", "name": "芯联集成-U", "ts_code": "688469.SH", "sector_id": "BK1036"},
    {"code": "688472", "name": "阿特斯", "ts_code": "688472.SH", "sector_id": "BK1031"},
    {"code": "688498", "name": "源杰科技", "ts_code": "688498.SH", "sector_id": "BK1038"},
    {"code": "688525", "name": "佰维存储", "ts_code": "688525.SH", "sector_id": "BK1036"},
    {"code": "688535", "name": "华海诚科", "ts_code": "688535.SH", "sector_id": "BK1033"},
    {"code": "688559", "name": "海目星", "ts_code": "688559.SH", "sector_id": "BK0910"},
    {"code": "688599", "name": "天合光能", "ts_code": "688599.SH", "sector_id": "BK1031"},
    {"code": "688602", "name": "康鹏科技", "ts_code": "688602.SH", "sector_id": "BK0538"},
    {"code": "688627", "name": "精智达", "ts_code": "688627.SH", "sector_id": "BK0910"},
    {"code": "688629", "name": "华丰科技", "ts_code": "688629.SH", "sector_id": "BK0459"},
    {"code": "688676", "name": "金盘科技", "ts_code": "688676.SH", "sector_id": "BK0457"},
    {"code": "688707", "name": "振华新材", "ts_code": "688707.SH", "sector_id": "BK1033"},
    {"code": "688720", "name": "艾森股份", "ts_code": "688720.SH", "sector_id": "BK1039"},
    {"code": "688766", "name": "普冉股份", "ts_code": "688766.SH", "sector_id": "BK1036"},
    {"code": "688779", "name": "五矿新能", "ts_code": "688779.SH", "sector_id": "BK1015"},
]


def import_industry_mapping():
    """导入行业匹配数据到数据库"""
    logger.info("=" * 60)
    logger.info("导入股票行业匹配数据")
    logger.info("=" * 60)
    logger.info(f"共 {len(INDUSTRY_MAPPING)} 条数据")
    
    engine = create_engine(DATABASE_URL, echo=False)
    today = date.today()
    
    # 准备数据
    stock_sector_rows = []
    for item in INDUSTRY_MAPPING:
        stock_sector_rows.append({
            "ts_code": item["ts_code"],
            "sector_id": item["sector_id"],
            "start_date": today,
            "end_date": None,
            "is_primary": True,
        })
    
    logger.info(f"准备导入 {len(stock_sector_rows)} 条股票-板块关联")
    
    # 批量入库
    if stock_sector_rows:
        with engine.connect() as conn:
            temp_table_name = 'temp_stock_sector_import'
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 创建临时表
            df_stock_sector = pd.DataFrame(stock_sector_rows)
            df_stock_sector.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=5000
            )
            conn.commit()
            
            # 批量插入（使用ON CONFLICT处理重复）
            insert_cols = ', '.join(df_stock_sector.columns)
            select_cols_list = []
            for col in df_stock_sector.columns:
                if col == 'end_date':
                    select_cols_list.append(f"NULLIF({col}, '')::DATE")
                else:
                    select_cols_list.append(col)
            select_cols = ', '.join(select_cols_list)
            
            sql = f"""
            INSERT INTO fact_stock_sector 
            ({insert_cols})
            SELECT {select_cols}
            FROM {temp_table_name}
            ON CONFLICT (ts_code, sector_id, start_date) 
            DO UPDATE SET
                is_primary = EXCLUDED.is_primary,
                end_date = EXCLUDED.end_date
            """
            
            result = conn.execute(text(sql))
            conn.commit()
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
        
        logger.info(f"✅ 成功导入 {len(stock_sector_rows)} 条关联数据")
    else:
        logger.warning("⚠️ 没有可导入的数据")
    
    # 验证导入结果
    logger.info("")
    logger.info("📊 验证导入结果...")
    with engine.connect() as conn:
        ts_codes = [item["ts_code"] for item in INDUSTRY_MAPPING]
        query = text("""
            SELECT COUNT(DISTINCT ts_code)
            FROM fact_stock_sector
            WHERE ts_code = ANY(:ts_codes)
              AND is_primary = TRUE
              AND (end_date IS NULL OR end_date > CURRENT_DATE)
        """)
        result = conn.execute(query, {'ts_codes': ts_codes})
        count = result.fetchone()[0]
        logger.info(f"✅ 验证成功: {count}/{len(ts_codes)} 只股票有行业关联")
    
    logger.info("=" * 60)
    logger.info("✅ 行业数据导入完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    import_industry_mapping()

