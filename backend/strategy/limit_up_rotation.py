"""
轮动打板策略
从热点板块中筛选打板候选股
"""

import logging
from typing import List, Dict, Optional
import pandas as pd
from sqlalchemy import text

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)


class LimitUpRotationStrategy:
    """
    轮动打板策略
    从热点板块中筛选打板候选股
    """
    
    def __init__(self):
        """初始化打板策略"""
        self.warehouse = PostgresWarehouse()
        self.warehouse_service = WarehouseService()
    
    def get_sector_stocks(self, sector_ids: List[str]) -> List[str]:
        """
        获取板块成分股
        
        Args:
            sector_ids: 板块ID列表
        
        Returns:
            List[str]: 股票代码列表（ts_code格式）
        """
        try:
            if not sector_ids:
                return []
            
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactStockSector
                
                stocks = session.query(FactStockSector.ts_code).filter(
                    FactStockSector.sector_id.in_(sector_ids),
                    FactStockSector.end_date.is_(None)  # 当前有效的关联
                ).distinct().all()
                
                ts_codes = [stock[0] for stock in stocks]
                logger.info(f"获取板块成分股: {len(ts_codes)}只（板块数: {len(sector_ids)}）")
                return ts_codes
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取板块成分股失败: {e}", exc_info=True)
            return []
    
    def filter_limit_up_candidates(
        self,
        sector_ids: List[str],
        min_turnover_rate: float = 3.0,
        min_change_pct: float = 5.0,
        min_amount: float = 1e8
    ) -> pd.DataFrame:
        """
        从指定板块中筛选打板候选股
        
        条件：
        1. 属于热点板块
        2. 换手率 > min_turnover_rate（默认3%）
        3. 涨幅 > min_change_pct（默认5%，接近涨停）
        4. 成交量放大（>5日均量1.5倍）
        5. 趋势向上（价格>MA20）
        6. 成交额 > min_amount（默认1亿）
        
        Args:
            sector_ids: 板块ID列表
            min_turnover_rate: 最低换手率
            min_change_pct: 最低涨幅
            min_amount: 最低成交额
        
        Returns:
            DataFrame: 候选股列表，包含评分
        """
        try:
            # 1. 获取板块成分股
            ts_codes = self.get_sector_stocks(sector_ids)
            
            if not ts_codes:
                logger.warning("板块成分股为空")
                return pd.DataFrame()
            
            # 2. 加载股票数据
            latest_date = self.warehouse.get_latest_stocks_date()
            if not latest_date:
                logger.warning("无法获取最新交易日期")
                return pd.DataFrame()
            
            stock_df = self.warehouse.load_stocks_data(latest_date, ts_codes)
            
            if stock_df is None or stock_df.empty:
                logger.warning("无法加载股票数据")
                return pd.DataFrame()
            
            logger.info(f"加载股票数据: {len(stock_df)}只")
            
            # 3. 应用过滤条件
            filtered_df = stock_df.copy()
            
            # 换手率过滤
            if 'turnover_rate' in filtered_df.columns:
                before = len(filtered_df)
                filtered_df = filtered_df[filtered_df['turnover_rate'] >= min_turnover_rate]
                logger.info(f"换手率过滤: {before} -> {len(filtered_df)}")
            
            # 涨幅过滤
            if 'change_pct' in filtered_df.columns or 'pct_chg' in filtered_df.columns:
                change_col = 'change_pct' if 'change_pct' in filtered_df.columns else 'pct_chg'
                before = len(filtered_df)
                filtered_df = filtered_df[filtered_df[change_col] >= min_change_pct]
                logger.info(f"涨幅过滤: {before} -> {len(filtered_df)}")
            
            # 成交额过滤
            if 'amount' in filtered_df.columns:
                before = len(filtered_df)
                filtered_df = filtered_df[filtered_df['amount'] >= min_amount]
                logger.info(f"成交额过滤: {before} -> {len(filtered_df)}")
            
            # 趋势过滤（价格>MA20）
            if 'ma20' in filtered_df.columns and 'close' in filtered_df.columns:
                before = len(filtered_df)
                filtered_df = filtered_df[
                    (filtered_df['close'] > filtered_df['ma20']) | 
                    filtered_df['ma20'].isna()
                ]
                logger.info(f"趋势过滤: {before} -> {len(filtered_df)}")
            
            # 4. 计算评分
            if not filtered_df.empty:
                filtered_df = self.calculate_limit_up_score(filtered_df, sector_ids)
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"筛选打板候选股失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def calculate_limit_up_score(
        self, 
        stock_df: pd.DataFrame,
        sector_ids: List[str]
    ) -> pd.DataFrame:
        """
        计算打板评分
        
        评分维度：
        1. 涨幅（40%）：越接近涨停越高
        2. 成交量（30%）：放量越大越高
        3. 板块热度（20%）：所属板块热度越高越高
        4. 技术形态（10%）：突破、金叉等
        
        Args:
            stock_df: 股票数据DataFrame
            sector_ids: 板块ID列表（用于计算板块热度）
        
        Returns:
            DataFrame: 带评分的候选股
        """
        try:
            df = stock_df.copy()
            
            # 初始化评分列
            df['limit_up_score'] = 0.0
            
            # 1. 涨幅评分（40%）
            change_col = 'change_pct' if 'change_pct' in df.columns else 'pct_chg'
            if change_col in df.columns:
                # 涨幅越高，评分越高，涨停（9.5%以上）得满分
                df['change_score'] = df[change_col].apply(
                    lambda x: min(100, (x / 9.5) * 100) if pd.notna(x) and x > 0 else 0
                )
                df['limit_up_score'] += df['change_score'] * 0.4
            
            # 2. 成交量评分（30%）
            # 需要计算量比（当前成交量/5日均量）
            if 'volume' in df.columns and 'avgVolume5' in df.columns:
                df['volume_ratio'] = df['volume'] / (df['avgVolume5'] + 1e-6)
                df['volume_score'] = df['volume_ratio'].apply(
                    lambda x: min(100, (x / 2.0) * 100) if pd.notna(x) and x > 0 else 0
                )
                df['limit_up_score'] += df['volume_score'] * 0.3
            elif 'volume_ratio' in df.columns:
                df['volume_score'] = df['volume_ratio'].apply(
                    lambda x: min(100, (x / 2.0) * 100) if pd.notna(x) and x > 0 else 0
                )
                df['limit_up_score'] += df['volume_score'] * 0.3
            
            # 3. 板块热度评分（20%）
            # 获取板块热度
            sector_heat = self._get_sector_heat(sector_ids)
            if sector_heat:
                # 为每只股票分配板块热度（简化：取最高热度）
                df['sector_heat_score'] = 50  # 默认值
                # 这里可以进一步优化，根据股票实际所属板块分配热度
                df['limit_up_score'] += df['sector_heat_score'] * 0.2
            
            # 4. 技术形态评分（10%）
            # 价格>MA20且MA20斜率>0
            if 'ma20' in df.columns and 'close' in df.columns and 'slope_ma20' in df.columns:
                df['tech_score'] = 0
                # 价格>MA20
                price_above_ma20 = (df['close'] > df['ma20']) & df['ma20'].notna()
                df.loc[price_above_ma20, 'tech_score'] += 50
                # MA20斜率>0
                slope_positive = (df['slope_ma20'] > 0) & df['slope_ma20'].notna()
                df.loc[slope_positive, 'tech_score'] += 50
                df['limit_up_score'] += df['tech_score'] * 0.1
            else:
                df['limit_up_score'] += 50 * 0.1  # 默认分
            
            # 排序
            df = df.sort_values('limit_up_score', ascending=False)
            
            logger.info(f"计算打板评分完成，最高分: {df['limit_up_score'].max():.2f}")
            
            return df
            
        except Exception as e:
            logger.error(f"计算打板评分失败: {e}", exc_info=True)
            return stock_df
    
    def _get_sector_heat(self, sector_ids: List[str]) -> Dict[str, float]:
        """
        获取板块热度
        
        Args:
            sector_ids: 板块ID列表
        
        Returns:
            Dict[str, float]: 板块ID到热度的映射
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactSectorDaily
                from sqlalchemy import func
                
                # 获取最新日期的板块数据
                latest_date = session.query(func.max(FactSectorDaily.trade_date)).scalar()
                
                if not latest_date:
                    return {}
                
                sectors = session.query(
                    FactSectorDaily.sector_id,
                    FactSectorDaily.heat_score,
                    FactSectorDaily.change_pct,
                    FactSectorDaily.num_limit_up
                ).filter(
                    FactSectorDaily.sector_id.in_(sector_ids),
                    FactSectorDaily.trade_date == latest_date
                ).all()
                
                heat_map = {}
                for sector_id, heat_score, change_pct, num_limit_up in sectors:
                    # 综合热度 = 热度评分 * 0.5 + 涨跌幅 * 5 + 涨停家数 * 10
                    heat = 0
                    if heat_score:
                        heat += float(heat_score) * 0.5
                    if change_pct:
                        heat += float(change_pct) * 5
                    if num_limit_up:
                        heat += float(num_limit_up) * 10
                    heat_map[sector_id] = heat
                
                return heat_map
                
            finally:
                session.close()
                
        except Exception as e:
            logger.debug(f"获取板块热度失败: {e}")
            return {}
    
    def get_limit_up_candidates_from_hot_sectors(
        self,
        hot_sectors: List[Dict],
        top_n: int = 20
    ) -> pd.DataFrame:
        """
        从热点板块中筛选打板候选股
        
        Args:
            hot_sectors: 热点板块列表（来自SectorRotationStrategy）
            top_n: 取前N个板块
        
        Returns:
            DataFrame: 打板候选股列表
        """
        try:
            # 取前N个板块
            top_sectors = hot_sectors[:top_n]
            sector_ids = [s['sector_id'] for s in top_sectors]
            
            logger.info(f"从{len(top_sectors)}个热点板块筛选打板候选股")
            
            # 筛选候选股
            candidates = self.filter_limit_up_candidates(sector_ids)
            
            # 添加板块信息
            if not candidates.empty and 'code' in candidates.columns:
                # 为每只股票添加所属板块信息
                candidates['sector_info'] = candidates['code'].apply(
                    lambda x: self._get_stock_sectors(x, sector_ids)
                )
            
            return candidates
            
        except Exception as e:
            logger.error(f"从热点板块筛选打板候选股失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _get_stock_sectors(self, ts_code: str, sector_ids: List[str]) -> List[str]:
        """
        获取股票所属的板块（在指定板块列表中）
        
        Args:
            ts_code: 股票代码
            sector_ids: 板块ID列表
        
        Returns:
            List[str]: 板块名称列表
        """
        try:
            session = self.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactStockSector
                from data_warehouse.models import DimSector
                
                # 标准化ts_code格式
                if not ts_code.endswith(('.SH', '.SZ', '.BJ')):
                    if ts_code.startswith('6'):
                        ts_code = f"{ts_code}.SH"
                    elif ts_code.startswith(('0', '3')):
                        ts_code = f"{ts_code}.SZ"
                
                sectors = session.query(DimSector.name).join(
                    FactStockSector,
                    FactStockSector.sector_id == DimSector.sector_id
                ).filter(
                    FactStockSector.ts_code == ts_code,
                    FactStockSector.sector_id.in_(sector_ids),
                    FactStockSector.end_date.is_(None)
                ).all()
                
                return [s[0] for s in sectors]
                
            finally:
                session.close()
                
        except Exception as e:
            logger.debug(f"获取股票板块失败 {ts_code}: {e}")
            return []

