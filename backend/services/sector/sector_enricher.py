"""
板块信息增强服务
为股票数据添加板块/行业信息
"""

import logging
import pandas as pd
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class SectorEnricher:
    """板块信息增强器"""
    
    def __init__(self):
        """初始化板块信息增强器"""
        self._sector_cache = {}  # 缓存股票代码 -> 行业名称
        self._cache_size_limit = 10000  # 缓存大小限制
    
    def enrich_with_sector(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        为DataFrame添加板块/行业信息
        
        Args:
            df: 股票数据DataFrame，必须包含'代码'或'code'字段
        
        Returns:
            DataFrame: 添加了'sector'和'行业'字段的DataFrame
        """
        try:
            if df.empty:
                return df
            
            # 确定代码字段名
            code_field = None
            for field in ['code', '代码']:
                if field in df.columns:
                    code_field = field
                    break
            
            if code_field is None:
                logger.warning("无法找到股票代码字段，无法添加板块信息")
                return df
            
            # 检查是否已有板块字段
            if 'sector' in df.columns or '行业' in df.columns:
                logger.debug("数据已包含板块信息，跳过增强")
                return df
            
            # 获取需要查询的股票代码（去重）
            codes_to_query = df[code_field].dropna().unique().tolist()
            
            # 从缓存中获取已有的板块信息
            sector_map = {}
            codes_to_fetch = []
            
            for code in codes_to_query:
                # 清理代码格式（去除sh/sz前缀，统一为6位数字）
                clean_code = str(code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                
                if clean_code in self._sector_cache:
                    sector_map[code] = self._sector_cache[clean_code]
                else:
                    codes_to_fetch.append(clean_code)
            
            # 批量获取板块信息（限制数量，避免请求过多）
            if codes_to_fetch:
                logger.info(f"需要获取 {len(codes_to_fetch)} 只股票的板块信息（已缓存 {len(sector_map)} 只）")
                
                # 限制批量查询数量，避免超时
                max_fetch = min(100, len(codes_to_fetch))  # 最多查询100只
                fetched_count = 0
                
                for clean_code in codes_to_fetch[:max_fetch]:
                    try:
                        # 优先从数据库获取，如果失败再尝试akshare
                        sector = self._fetch_sector_from_database(clean_code)
                        if not sector:
                            sector = self._fetch_sector_from_akshare(clean_code)
                        
                        if sector:
                            # 找到对应的原始代码
                            for orig_code in codes_to_query:
                                orig_clean = str(orig_code).replace('sh', '').replace('sz', '').replace('SH', '').replace('SZ', '').strip()
                                if orig_clean == clean_code:
                                    sector_map[orig_code] = sector
                                    self._sector_cache[clean_code] = sector
                                    break
                            fetched_count += 1
                        
                        # 添加延迟，避免请求过快（仅对akshare请求）
                        if fetched_count % 10 == 0 and not sector:
                            time.sleep(0.1)  # 数据库查询不需要延迟，akshare需要
                    except Exception as e:
                        logger.debug(f"获取股票 {clean_code} 的板块信息失败: {e}")
                        continue
                
                logger.info(f"成功获取 {fetched_count} 只股票的板块信息")
            
            # 为DataFrame添加板块字段
            df = df.copy()
            df['行业'] = df[code_field].map(sector_map).fillna('未知')
            df['sector'] = df['行业']  # 同时添加英文字段名
            
            # 统计板块分布
            sector_counts = df['行业'].value_counts()
            logger.info(f"板块信息增强完成: {len(sector_counts)} 个不同板块，{len(df[df['行业'] != '未知'])} 只股票有板块信息")
            
            return df
            
        except Exception as e:
            logger.error(f"板块信息增强失败: {e}", exc_info=True)
            # 如果失败，至少添加空字段
            df = df.copy()
            if '行业' not in df.columns:
                df['行业'] = '未知'
            if 'sector' not in df.columns:
                df['sector'] = '未知'
            return df
    
    def _fetch_sector_from_database(self, code: str) -> Optional[str]:
        """
        从数据库获取单只股票的行业信息（优先方法）
        
        Args:
            code: 股票代码（6位数字，不带前缀）
        
        Returns:
            str: 行业名称，如果获取失败返回None
        """
        try:
            from sqlalchemy import create_engine, text
            from data_warehouse.config import DATABASE_URL
            
            # 转换代码格式：6位数字 -> ts_code格式
            if len(code) == 6:
                # 判断市场：6开头=上海，0/3开头=深圳，8开头=北交所
                if code.startswith('6'):
                    ts_code = f"{code}.SH"
                elif code.startswith('0') or code.startswith('3'):
                    ts_code = f"{code}.SZ"
                elif code.startswith('8') or code.startswith('4'):
                    ts_code = f"{code}.BJ"
                else:
                    ts_code = f"{code}.SZ"  # 默认深圳
            else:
                ts_code = code
            
            engine = create_engine(DATABASE_URL, echo=False)
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT DISTINCT ON (fss.ts_code)
                        ds.name as sector_name
                    FROM fact_stock_sector fss
                    JOIN dim_sector ds ON fss.sector_id = ds.sector_id
                    WHERE fss.ts_code = :ts_code
                      AND fss.is_primary = TRUE
                      AND (fss.end_date IS NULL OR fss.end_date > CURRENT_DATE)
                    ORDER BY fss.ts_code, fss.start_date DESC
                    LIMIT 1
                """), {'ts_code': ts_code})
                
                row = result.fetchone()
                if row and row[0]:
                    return str(row[0])
            
            return None
            
        except Exception as e:
            logger.debug(f"从数据库获取股票 {code} 的行业信息失败: {e}")
            return None
    
    def _fetch_sector_from_akshare(self, code: str) -> Optional[str]:
        """
        从akshare获取单只股票的行业信息（备用方法）
        
        Args:
            code: 股票代码（6位数字，不带前缀）
        
        Returns:
            str: 行业名称，如果获取失败返回None
        """
        try:
            import akshare as ak
            
            # 调用akshare接口
            info = ak.stock_individual_info_em(symbol=code)
            
            # 查找行业字段
            industry_row = info[info['item'] == '行业']
            if not industry_row.empty:
                industry = industry_row['value'].iloc[0]
                return str(industry)
            
            return None
            
        except Exception as e:
            logger.debug(f"从akshare获取股票 {code} 的行业信息失败: {e}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self._sector_cache.clear()
        logger.info("板块信息缓存已清空")

