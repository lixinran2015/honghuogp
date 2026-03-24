"""
行业分位数计算服务
用于计算行业内指标的分位数阈值
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IndustryPercentileService:
    """行业分位数计算服务"""
    
    def __init__(self, tushare_service=None, cache_ttl_hours: int = 24):
        """
        初始化行业分位数服务
        
        Args:
            tushare_service: TushareService实例，如果为None则自动创建
            cache_ttl_hours: 缓存有效期（小时），默认24小时
        """
        if tushare_service is None:
            from backend.services.tushare_service import TushareService
            self.tushare_service = TushareService()
        else:
            self.tushare_service = tushare_service
        
        self.cache_ttl_hours = cache_ttl_hours
        self._cache: Dict[str, Dict] = {}  # {cache_key: {value: float, timestamp: datetime}}
    
    def _get_cache_key(self, industry_name: str, indicator: str, percentile: float) -> str:
        """生成缓存键"""
        return f"{industry_name}_{indicator}_{percentile}"
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """检查缓存是否有效"""
        if 'timestamp' not in cache_entry:
            return False
        
        elapsed_hours = (datetime.now() - cache_entry['timestamp']).total_seconds() / 3600
        return elapsed_hours < self.cache_ttl_hours
    
    def get_percentile(
        self,
        industry_name: str,
        indicator: str,
        percentile: float = 0.5,  # 0.5=中位数, 0.75=75分位
        industry_level: str = 'L1'  # 'L1'一级行业, 'L2'二级行业
    ) -> float:
        """
        获取行业内指标的分位数阈值
        
        Args:
            industry_name: 行业名称（如"医药生物"、"计算机"）
            indicator: 指标名称（如'roe', 'grossprofit_margin'）
            percentile: 分位数（0.5=中位数, 0.75=75分位）
            industry_level: 行业级别（'L1'一级, 'L2'二级）
        
        Returns:
            float: 行业分位数阈值
        """
        # 检查缓存
        cache_key = self._get_cache_key(industry_name, indicator, percentile)
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if self._is_cache_valid(cache_entry):
                logger.debug(f"使用缓存的分位数: {industry_name} {indicator} {percentile*100}分位 = {cache_entry['value']:.2f}")
                return cache_entry['value']
        
        if not self.tushare_service.available:
            logger.warning(f"Tushare服务不可用，使用默认阈值: {indicator}")
            return self._get_default_threshold(indicator)
        
        try:
            # 1. 获取行业所有股票列表
            stock_basic = None
            try:
                stock_basic = self.tushare_service.pro.stock_basic(
                    exchange='',
                    list_status='L',
                    fields='ts_code,symbol,name,industry,list_date'
                )
            except Exception as e:
                logger.error(f"获取股票列表失败: {e}", exc_info=True)
                return self._get_default_threshold(indicator)
            
            if stock_basic is None or stock_basic.empty:
                logger.warning(f"未获取到股票列表")
                return self._get_default_threshold(indicator)
            
            # 筛选行业股票
            if industry_level == 'L1':
                # 申万一级行业（简化处理：使用industry字段）
                industry_stocks = stock_basic[stock_basic['industry'] == industry_name]['ts_code'].tolist()
            else:
                # 申万二级行业（需要从sw_industry表获取，这里简化处理）
                industry_stocks = stock_basic[stock_basic['industry'] == industry_name]['ts_code'].tolist()
            
            if not industry_stocks:
                logger.warning(f"未找到行业股票: {industry_name}")
                return self._get_default_threshold(indicator)
            
            # 2. 排除次新股（上市不足1年）
            current_date = datetime.now()
            valid_stocks = []
            for ts_code in industry_stocks:
                stock_info = stock_basic[stock_basic['ts_code'] == ts_code]
                if stock_info.empty:
                    continue
                
                list_date_str = str(stock_info.iloc[0]['list_date'])
                if len(list_date_str) == 8:  # YYYYMMDD格式
                    try:
                        list_date = datetime.strptime(list_date_str, '%Y%m%d')
                        listing_years = (current_date - list_date).days / 365.0
                        if listing_years >= 1.0:
                            valid_stocks.append(ts_code)
                    except:
                        # 日期解析失败，保留该股票
                        valid_stocks.append(ts_code)
                else:
                    valid_stocks.append(ts_code)
            
            if not valid_stocks:
                logger.warning(f"行业 {industry_name} 没有符合条件的股票（排除次新股后）")
                return self._get_default_threshold(indicator)
            
            # 3. 批量获取财务指标（限制数量，避免请求过多）
            max_stocks = 200  # 限制最多200只股票
            valid_stocks = valid_stocks[:max_stocks]
            
            indicator_values = []
            success_count = 0
            
            for idx, ts_code in enumerate(valid_stocks):
                try:
                    # 获取最新一期财务指标
                    fina_df = self.tushare_service.pro.fina_indicator(
                        ts_code=ts_code,
                        period='',  # 最新一期
                        fields=f'ts_code,end_date,{indicator}'
                    )
                    
                    if fina_df is not None and not fina_df.empty:
                        value = fina_df.iloc[0][indicator]
                        if pd.notna(value) and not np.isinf(value):
                            value_float = float(value)
                            # 如果值>1，认为是百分比，需要除以100
                            if value_float > 1 and indicator in ['roe', 'grossprofit_margin', 'netprofit_margin', 'debt_to_assets']:
                                value_float = value_float / 100
                            indicator_values.append(value_float)
                            success_count += 1
                    
                    # 限速，避免请求过快（每10只股票延迟1秒）
                    if (idx + 1) % 10 == 0:
                        import time
                        time.sleep(1)
                    
                except Exception as e:
                    logger.debug(f"获取财务指标失败 {ts_code}: {e}")
                    continue
            
            if not indicator_values:
                logger.warning(f"未获取到有效的指标数据: {industry_name} {indicator}")
                return self._get_default_threshold(indicator)
            
            # 4. 计算分位数
            percentile_value = np.percentile(indicator_values, percentile * 100)
            
            # 存入缓存
            self._cache[cache_key] = {
                'value': float(percentile_value),
                'timestamp': datetime.now()
            }
            
            logger.info(f"✅ 行业 {industry_name} 指标 {indicator} {percentile*100}分位: {percentile_value:.2f} (样本数: {success_count})")
            
            return float(percentile_value)
            
        except Exception as e:
            logger.error(f"计算行业分位数失败: {e}", exc_info=True)
            return self._get_default_threshold(indicator)
    
    def _get_default_threshold(self, indicator: str) -> float:
        """获取默认阈值（当行业分位数计算失败时使用）"""
        defaults = {
            'roe': 12.0,
            'grossprofit_margin': 20.0,
            'netprofit_margin': 5.0,
            'debt_to_assets': 0.6,
            'revenue_yoy': 0.0,
            'net_profit_yoy': 0.0,
        }
        return defaults.get(indicator, 0.0)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("已清空行业分位数缓存")
