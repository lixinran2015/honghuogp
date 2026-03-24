"""
股票池服务
管理可交易股票池的更新和维护
"""

import logging
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import text

from backend.services.stock.stock_universe_filter import StockUniverseFilter

logger = logging.getLogger(__name__)


def _normalize_trade_date(trade_date) -> Optional[str]:
    """将日期规范为 YYYY-MM-DD，修复双横线等格式问题"""
    if trade_date is None:
        return None
    if isinstance(trade_date, datetime):
        return trade_date.strftime('%Y-%m-%d')
    if hasattr(trade_date, 'strftime'):
        return trade_date.strftime('%Y-%m-%d')
    s = str(trade_date).strip()[:10]
    # 修复 2026--02-13 -> 2026-02-13
    while '--' in s:
        s = s.replace('--', '-')
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    return s if s else None


class StockUniverseService:
    """股票池服务"""
    
    def __init__(self):
        """初始化服务"""
        # 延迟导入避免循环依赖
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        self.warehouse = PostgresWarehouse()
        self.filter_service = StockUniverseFilter()
        # market_service 延迟获取，避免循环依赖
        self._market_service = None
    
    @property
    def market_service(self):
        """延迟获取 MarketDataService"""
        if self._market_service is None:
            from backend.services.market_data_service import MarketDataService
            self._market_service = MarketDataService()
        return self._market_service
    
    def create_universe_table(self):
        """创建股票池表"""
        try:
            if not self.warehouse.warehouse_service:
                logger.error("❌ WarehouseService未初始化")
                return
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                queries = [
                    text("""
                        CREATE TABLE IF NOT EXISTS dim_stock_universe (
                            ts_code VARCHAR(20) NOT NULL,
                            universe_type VARCHAR(20) NOT NULL,
                            trade_date DATE NOT NULL,
                            is_active BOOLEAN DEFAULT TRUE,
                            filter_reason TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (ts_code, universe_type, trade_date)
                        )
                    """),
                    text("""
                        CREATE INDEX IF NOT EXISTS idx_universe_type_date 
                        ON dim_stock_universe(universe_type, trade_date)
                    """),
                    text("""
                        CREATE INDEX IF NOT EXISTS idx_universe_code 
                        ON dim_stock_universe(ts_code)
                    """)
                ]
                
                for query in queries:
                    session.execute(query)
                
                session.commit()
                logger.info("✅ 股票池表创建成功")
                
            finally:
                session.close()
            
        except Exception as e:
            logger.error(f"❌ 创建股票池表失败: {e}", exc_info=True)
            raise
    
    def update_universe(
        self,
        universe_type: str = 'base',
        trade_date: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, int]:
        """
        更新股票池
        
        Args:
            universe_type: 股票池类型（'base', 's1', 's2', 's3'）
            trade_date: 交易日期（默认今天）
            force_refresh: 是否强制刷新（默认False，基础池会优先使用缓存）
        
        Returns:
            更新统计信息
        """
        try:
            if trade_date is None:
                trade_date = datetime.now().strftime('%Y-%m-%d')
            
            logger.info(f"📊 开始更新股票池: type={universe_type}, date={trade_date}")
            
            # 基础池优先从数据库读取（不经常变动）
            if universe_type == 'base' and not force_refresh:
                existing_stocks = self.get_universe_stocks('base', trade_date)
                if len(existing_stocks) > 100:  # 如果已有足够数据，直接返回
                    logger.info(f"  ✅ 基础池已存在 {len(existing_stocks)} 只股票，跳过重新计算")
                    return {'total': len(existing_stocks), 'filtered': len(existing_stocks), 'added': 0, 'cached': True}
            
            # 2. 应用过滤（从配置文件读取参数）
            from backend.config.universe_filter_config import (
                MAINBOARD_FILTER_CONFIG, BASE_FILTER_CONFIG, S1_FILTER_CONFIG, 
                S2_FILTER_CONFIG, S3_FILTER_CONFIG,
                HIGH_180D_FILTER_CONFIG
            )
            
            if universe_type == 'mainboard':
                # 主板池：从dim_stock全表获取所有股票
                logger.info("  📥 从dim_stock全表读取股票...")
                session = self.warehouse.warehouse_service.get_session()
                try:
                    result = session.execute(text("""
                        SELECT ts_code, symbol, name, industry, exchange 
                        FROM dim_stock 
                        WHERE ts_code IS NOT NULL AND delist_date IS NULL
                    """)).fetchall()
                    stock_data = pd.DataFrame(result, columns=['ts_code', 'symbol', 'name', 'industry', 'exchange'])
                    logger.info(f"  📥 从dim_stock读取到 {len(stock_data)} 只股票")
                finally:
                    session.close()
                
                filtered_data = self.filter_service.mainboard_universe_filter(
                    stock_data,
                    **MAINBOARD_FILTER_CONFIG
                )
            elif universe_type == 's1':
                # S1直接从基础池读取数据，不需要获取全部股票
                base_codes = self.get_universe_stocks('base', trade_date)
                if not base_codes:
                    logger.warning("⚠️ 基础池为空，请先刷新基础池")
                    return {'total': 0, 'filtered': 0, 'added': 0, 'error': '基础池为空'}
                
                logger.info(f"  📥 从基础池读取 {len(base_codes)} 只股票")
                
                # 获取基础池股票的实时数据（包含股价、成交额等）
                all_stocks = self.market_service.get_realtime_stocks(force_refresh=False)
                if all_stocks.empty:
                    logger.warning("⚠️ 无法获取实时数据")
                    return {'total': 0, 'filtered': 0, 'added': 0}
                
                # 只保留基础池中的股票
                code_col = self._get_code_column(all_stocks)
                if code_col is None:
                    logger.warning("⚠️ 无法找到股票代码列")
                    return {'total': 0, 'filtered': 0, 'added': 0}
                
                # 统一代码格式：将 base_codes 的 ts_code (如 300001.SZ) 转为纯数字 (300001)
                base_codes_clean = [code.split('.')[0] for code in base_codes]
                
                # 同时也将 all_stocks 的代码清理（去掉可能的后缀）
                all_stocks['_code_clean'] = all_stocks[code_col].astype(str).str.replace(r'\.(SH|SZ)$', '', regex=True)
                
                stock_data = all_stocks[all_stocks['_code_clean'].isin(base_codes_clean)].copy()
                stock_data = stock_data.drop(columns=['_code_clean'], errors='ignore')
                logger.info(f"  📥 匹配到 {len(stock_data)} 只基础池股票的实时数据")
                
                filtered_data = self.filter_service.s1_universe_filter(
                    stock_data,
                    **S1_FILTER_CONFIG
                )
            elif universe_type == 's2':
                # S2直接从历史S1筛选，不需要获取全量股票
                logger.info(f"  📥 S2直接从历史S1筛选")
                filtered_data = self.filter_service.s2_universe_filter(
                    pd.DataFrame(),
                    **S2_FILTER_CONFIG
                )
            else:
                # base需要从dim_stock全表获取所有股票（而不是物化视图）
                if universe_type == 'base' and force_refresh:
                    # 强制刷新时从dim_stock读取全部股票
                    logger.info("  📥 从dim_stock全表读取股票...")
                    session = self.warehouse.warehouse_service.get_session()
                    try:
                        result = session.execute(text("""
                            SELECT ts_code, symbol, name, industry, exchange 
                            FROM dim_stock 
                            WHERE ts_code IS NOT NULL
                        """)).fetchall()
                        stock_data = pd.DataFrame(result, columns=['ts_code', 'symbol', 'name', 'industry', 'exchange'])
                        logger.info(f"  📥 从dim_stock读取到 {len(stock_data)} 只股票")
                    finally:
                        session.close()
                else:
                    stock_data = self.market_service.get_realtime_stocks(force_refresh=False)
                
                if stock_data.empty:
                    logger.warning("⚠️ 无法获取股票数据")
                    return {'total': 0, 'filtered': 0, 'added': 0}
                
                original_count = len(stock_data)
                logger.info(f"  📥 获取到 {original_count} 只股票")
                
                if universe_type == 'base':
                    filtered_data = self.filter_service.base_universe_filter(
                        stock_data,
                        **BASE_FILTER_CONFIG
                    )
                elif universe_type == 's3':
                    filtered_data = self.filter_service.base_universe_filter(
                        stock_data,
                        **BASE_FILTER_CONFIG
                    )
                    filtered_data = self.filter_service.s3_universe_filter(
                        filtered_data,
                        **S3_FILTER_CONFIG
                    )
                elif universe_type == 'high_180d':
                    # 180日高点策略：使用主板池的固定代码列表，查询指定日期的实际数据
                    logger.info("  📥 获取主板池股票列表...")
                    
                    # 获取主板池的股票代码列表（固定范围，使用最新的主板池）
                    mainboard_codes = self.get_universe_stocks(
                        universe_type='mainboard',
                        trade_date=None,  # 使用最新的主板池（固定的股票范围）
                        active_only=True
                    )
                    
                    if not mainboard_codes:
                        logger.warning("⚠️ 主板池为空，请先刷新主板池")
                        return {'total': 0, 'filtered': 0, 'added': 0, 'error': '主板池为空'}
                    
                    logger.info(f"  📥 主板池股票列表: {len(mainboard_codes)} 只（固定范围）")
                    
                    # 使用主板池代码，查询指定日期的实际数据
                    from data_warehouse.service.warehouse_service import WarehouseService
                    
                    ws = WarehouseService()
                    session = ws.get_session()
                    
                    try:
                        # 从 fact_daily_price_qfq 表读取指定日期的主板池股票数据
                        query = text("""
                            SELECT 
                                f.ts_code,
                                d.name,
                                f.open,
                                f.high,
                                f.low,
                                f.close,
                                f.pre_close,
                                f.amount,
                                f.turnover_rate,
                                f.change_pct,
                                f.trade_date
                            FROM fact_daily_price_qfq f
                            JOIN dim_stock d ON f.ts_code = d.ts_code
                            WHERE f.trade_date = :trade_date
                              AND f.ts_code = ANY(:ts_codes)
                        """)
                        
                        result = session.execute(query, {
                            'trade_date': trade_date,  # 使用字符串格式，PostgreSQL会自动转换
                            'ts_codes': mainboard_codes
                        }).fetchall()
                        
                        if not result:
                            logger.warning(f"⚠️ {trade_date} 无主板股票数据")
                            return {'total': 0, 'filtered': 0, 'added': 0}
                        
                        # 转换为DataFrame（包含开盘价、前日收盘价，用于判断一字涨停板）
                        stock_data = pd.DataFrame(result, columns=[
                            'ts_code', 'name', 'open', 'high', 'low', 'close', 'pre_close', 'amount', 'turnover_rate', 'change_pct', 'trade_date'
                        ])
                        
                        logger.info(f"  📥 从qfq表获取到 {len(stock_data)} 只股票数据（日期: {trade_date}）")
                        
                    finally:
                        session.close()
                    
                    # 应用180日高点过滤（跳过基础过滤，因为主板池已经过滤过了）
                    filtered_data = self.filter_service.high_180d_universe_filter(
                        stock_data,
                        max_high_distance=HIGH_180D_FILTER_CONFIG['max_high_distance'],
                        min_price=HIGH_180D_FILTER_CONFIG['min_price'],
                        min_amount=HIGH_180D_FILTER_CONFIG['min_amount'],
                        max_change_180d=HIGH_180D_FILTER_CONFIG['max_change_180d'],
                        allowed_prefixes=None,
                        kline_data=None,
                        skip_basic_filter=True,  # 跳过代码前缀和ST过滤
                        target_date=trade_date,  # 传入目标日期，确保K线数据截止到该日期
                        strategy_name="180日高点"
                    )
                
                elif universe_type == 'high_60d':
                    # 60日新高策略：复用180日的逻辑，只是时间窗口和参数不同
                    logger.info("  📥 获取主板池股票列表...")
                    
                    # 获取主板池的股票代码列表（固定范围，使用最新的主板池）
                    mainboard_codes = self.get_universe_stocks(
                        universe_type='mainboard',
                        trade_date=None,  # 使用最新的主板池（固定的股票范围）
                        active_only=True
                    )
                    
                    if not mainboard_codes:
                        logger.warning("⚠️ 主板池为空，请先刷新主板池")
                        return {'total': 0, 'filtered': 0, 'added': 0, 'error': '主板池为空'}
                    
                    logger.info(f"  📥 主板池股票列表: {len(mainboard_codes)} 只（固定范围）")
                    
                    # 使用主板池代码，查询指定日期的实际数据
                    from data_warehouse.service.warehouse_service import WarehouseService
                    
                    ws = WarehouseService()
                    session = ws.get_session()
                    
                    try:
                        # 从 fact_daily_price_qfq 表读取指定日期的主板池股票数据
                        query = text("""
                            SELECT 
                                f.ts_code,
                                d.name,
                                f.open,
                                f.high,
                                f.low,
                                f.close,
                                f.pre_close,
                                f.amount,
                                f.turnover_rate,
                                f.change_pct,
                                f.trade_date
                            FROM fact_daily_price_qfq f
                            JOIN dim_stock d ON f.ts_code = d.ts_code
                            WHERE f.trade_date = :trade_date
                              AND f.ts_code = ANY(:ts_codes)
                        """)
                        
                        result = session.execute(query, {
                            'trade_date': trade_date,
                            'ts_codes': mainboard_codes
                        }).fetchall()
                        
                        if not result:
                            logger.warning(f"⚠️ {trade_date} 无主板股票数据")
                            return {'total': 0, 'filtered': 0, 'added': 0}
                        
                        # 转换为DataFrame
                        stock_data = pd.DataFrame(result, columns=[
                            'ts_code', 'name', 'open', 'high', 'low', 'close', 'pre_close', 'amount', 'turnover_rate', 'change_pct', 'trade_date'
                        ])
                        
                        logger.info(f"  📥 从qfq表获取到 {len(stock_data)} 只股票数据（日期: {trade_date}）")
                        
                    finally:
                        session.close()
                    
                    # 复用180日方法，但参数不同（60日策略只看成交额和距离，不看股价和涨幅）
                    from backend.config.universe_filter_config import HIGH_60D_FILTER_CONFIG
                    filtered_data = self.filter_service.high_180d_universe_filter(
                        stock_data,
                        max_high_distance=HIGH_60D_FILTER_CONFIG['max_high_distance'],
                        min_price=0,  # 60日策略不限制股价
                        min_amount=HIGH_60D_FILTER_CONFIG['min_amount'],
                        max_change_180d=9999,  # 60日策略不限制涨幅
                        allowed_prefixes=None,
                        kline_data=None,
                        skip_basic_filter=True,  # 跳过代码前缀和ST过滤
                        target_date=trade_date,  # 传入目标日期
                        strategy_name="60日新高"
                    )
                
                else:
                    logger.error(f"❌ 未知的股票池类型: {universe_type}")
                    return {'total': 0, 'filtered': 0, 'added': 0}
            
            filtered_count = len(filtered_data)
            # 计算原始数量（S2可能没有stock_data变量）
            try:
                original_count = len(stock_data) if 'stock_data' in locals() else filtered_count
            except NameError:
                original_count = filtered_count
            logger.info(f"  ✅ 过滤完成: {filtered_count} 只")
            
            # 3. 更新数据库
            if not self.warehouse.warehouse_service:
                logger.warning("⚠️ WarehouseService未初始化，跳过数据库更新")
                return {'total': original_count, 'filtered': filtered_count, 'added': 0}
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 删除策略：
                # - 基础池：删除所有旧数据（只保留最新）
                # - S1/S2/S3：删除当天的旧数据，保留历史数据
                if universe_type == 'base':
                    delete_old = text("""
                        DELETE FROM dim_stock_universe
                        WHERE universe_type = :universe_type
                    """)
                    session.execute(delete_old, {
                        'universe_type': universe_type
                    })
                    logger.debug(f"  🗑️ 删除 {universe_type} 所有旧数据（基础池只保留最新）")
                else:
                    # S1/S2/S3：删除当天的旧数据，保留历史数据
                    delete_today = text("""
                        DELETE FROM dim_stock_universe
                        WHERE universe_type = :universe_type
                          AND trade_date = :trade_date
                    """)
                    result = session.execute(delete_today, {
                        'universe_type': universe_type,
                        'trade_date': trade_date
                    })
                    logger.info(f"  🗑️ 删除 {universe_type} 当天({trade_date})旧数据: {result.rowcount} 条")
                
                # 插入新数据
                code_col = self._get_code_column(filtered_data)
                if code_col is None:
                    logger.warning("⚠️ 无法找到股票代码列")
                    return {'total': filtered_count, 'filtered': filtered_count, 'added': 0}
                
                added_count = 0
                
                for _, row in filtered_data.iterrows():
                    try:
                        code = row[code_col]
                        
                        # 因为已经删除了当天的旧数据，直接插入即可
                        # 但保留 ON CONFLICT 以防万一（如并发插入）
                        insert_query = text("""
                            INSERT INTO dim_stock_universe 
                                (ts_code, universe_type, trade_date, is_active, filter_reason)
                            VALUES (:ts_code, :universe_type, :trade_date, TRUE, :filter_reason)
                            ON CONFLICT (ts_code, universe_type, trade_date)
                            DO UPDATE SET
                                is_active = TRUE,
                                updated_at = CURRENT_TIMESTAMP,
                                filter_reason = EXCLUDED.filter_reason
                        """)
                        
                        session.execute(insert_query, {
                            'ts_code': code,
                            'universe_type': universe_type,
                            'trade_date': trade_date,
                            'filter_reason': f'{universe_type}策略筛选'
                        })
                        
                        added_count += 1
                        
                    except Exception as e:
                        logger.warning(f"插入股票 {code} 失败: {e}")
                        continue
                
                session.commit()
                
            finally:
                session.close()
            
            logger.info(f"✅ 股票池更新完成: {universe_type}, 新增 {added_count} 只")
            
            return {
                'total': filtered_count,
                'filtered': filtered_count,
                'added': added_count
            }
            
        except Exception as e:
            logger.error(f"❌ 更新股票池失败: {e}", exc_info=True)
            return {'total': 0, 'filtered': 0, 'added': 0}
    
    def update_all_universes(self, trade_date: Optional[str] = None) -> Dict[str, Dict]:
        """
        更新所有股票池
        
        Args:
            trade_date: 交易日期（默认今天）
        
        Returns:
            所有股票池的更新统计
        """
        results = {}
        
        for universe_type in ['mainboard', 'base', 's1', 's2', 'high_180d', 'high_60d']:  # S3已停用
            try:
                result = self.update_universe(universe_type, trade_date)
                results[universe_type] = result
            except Exception as e:
                logger.error(f"更新 {universe_type} 股票池失败: {e}")
                results[universe_type] = {'total': 0, 'filtered': 0, 'added': 0}
        
        return results
    
    def _get_code_column(self, df: pd.DataFrame) -> Optional[str]:
        """
        获取DataFrame中的股票代码列名
        
        Args:
            df: 股票数据DataFrame
        
        Returns:
            代码列名（'ts_code' 或 'code'），如果都不存在返回None
        """
        if 'ts_code' in df.columns:
            return 'ts_code'
        elif 'code' in df.columns:
            return 'code'
        return None
    
    def _get_latest_trade_date(self, session, universe_type: str) -> str:
        """
        获取指定股票池类型的最新交易日期
        
        Args:
            session: 数据库会话
            universe_type: 股票池类型
        
        Returns:
            最新交易日期字符串（YYYY-MM-DD），如果没有则返回今天
        """
        query_max_date = text("""
            SELECT MAX(trade_date)
            FROM dim_stock_universe
            WHERE universe_type = :universe_type
        """)
        max_date = session.execute(query_max_date, {
            'universe_type': universe_type
        }).scalar()
        if max_date:
            return _normalize_trade_date(max_date) or datetime.now().strftime('%Y-%m-%d')
        return datetime.now().strftime('%Y-%m-%d')
    
    def get_universe_stocks(
        self,
        universe_type: str = 'base',
        trade_date: Optional[str] = None,
        active_only: bool = True
    ) -> List[str]:
        """
        获取股票池中的股票代码列表
        
        Args:
            universe_type: 股票池类型（'base', 's1', 's2', 's3'）
            trade_date: 交易日期（默认使用最新可用日期）
            active_only: 是否只返回活跃股票
        
        Returns:
            股票代码列表
        """
        try:
            if not self.warehouse.warehouse_service:
                logger.warning("⚠️ WarehouseService未初始化")
                return []
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 如果没有指定日期，使用最新可用日期
                if trade_date is None:
                    trade_date = self._get_latest_trade_date(session, universe_type)
                else:
                    trade_date = _normalize_trade_date(trade_date) or trade_date
                
                # 查询指定日期的股票代码
                query = text("""
                    SELECT ts_code
                    FROM dim_stock_universe
                    WHERE universe_type = :universe_type
                        AND trade_date = :trade_date
                        AND (:active_only = FALSE OR is_active = TRUE)
                """)
                
                result = session.execute(query, {
                    'universe_type': universe_type,
                    'trade_date': trade_date,
                    'active_only': active_only
                })
                
                codes = [row[0] for row in result]
                
                # 如果指定日期没有数据，使用最新可用日期
                if not codes:
                    latest_date = self._get_latest_trade_date(session, universe_type)
                    if latest_date != trade_date:
                        logger.info(f"⚠️ {trade_date} 没有数据，使用最新日期 {latest_date}")
                        result = session.execute(query, {
                            'universe_type': universe_type,
                            'trade_date': latest_date,
                            'active_only': active_only
                        })
                        codes = [row[0] for row in result]
                        trade_date = latest_date  # 更新trade_date用于日志
            finally:
                session.close()
            logger.info(f"📊 获取 {universe_type} 股票池: {len(codes)} 只 (日期: {trade_date})")
            
            return codes
            
        except Exception as e:
            logger.error(f"❌ 获取股票池失败: {e}", exc_info=True)
            return []
    
    def get_universe_stats(self, trade_date: Optional[str] = None) -> Dict[str, int]:
        """
        获取股票池统计信息
        
        Args:
            trade_date: 交易日期（默认使用各股票池的最新可用日期）
        
        Returns:
            各股票池的股票数量
        """
        try:
            if not self.warehouse.warehouse_service:
                logger.warning("⚠️ WarehouseService未初始化")
                return {}
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                stats = {}
                
                # 如果没有指定日期，为每个股票池类型分别使用其最新可用日期
                if trade_date is None:
                    universe_types = ['mainboard', 'base', 's1', 's2', 'high_180d', 'high_60d']  # S3已停用
                    for universe_type in universe_types:
                        latest_date = self._get_latest_trade_date(session, universe_type)
                        query = text("""
                            SELECT COUNT(*) as count
                            FROM dim_stock_universe
                            WHERE universe_type = :universe_type
                                AND trade_date = :trade_date
                                AND is_active = TRUE
                        """)
                        result = session.execute(query, {
                            'universe_type': universe_type,
                            'trade_date': latest_date
                        }).fetchone()
                        if result:
                            stats[universe_type] = int(result[0])
                        else:
                            stats[universe_type] = 0
                else:
                    # 如果指定了日期，使用该日期查询所有股票池（先规范化格式）
                    trade_date = _normalize_trade_date(trade_date) or trade_date
                    query = text("""
                        SELECT universe_type, COUNT(*) as count
                        FROM dim_stock_universe
                        WHERE trade_date = :trade_date
                            AND is_active = TRUE
                        GROUP BY universe_type
                    """)
                    
                    result = session.execute(query, {'trade_date': trade_date})
                    
                    for row in result:
                        stats[row[0]] = int(row[1])
                
                logger.debug(f"📊 股票池统计: {stats}")
            finally:
                session.close()
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取股票池统计失败: {e}", exc_info=True)
            return {}
    
    def filter_stocks_by_universe(
        self,
        stock_data: pd.DataFrame,
        universe_type: str = 'base',
        trade_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        根据股票池过滤股票数据
        
        Args:
            stock_data: 股票数据DataFrame
            universe_type: 股票池类型
            trade_date: 交易日期
        
        Returns:
            过滤后的DataFrame（只包含股票池中的股票）
        """
        try:
            # 获取股票池代码
            universe_codes = self.get_universe_stocks(universe_type, trade_date)
            
            if not universe_codes:
                logger.warning(f"⚠️ {universe_type} 股票池为空")
                return pd.DataFrame()
            
            # 确定代码列
            code_col = self._get_code_column(stock_data)
            if code_col is None:
                logger.warning("⚠️ 无法找到股票代码列")
                return stock_data
            
            # 过滤
            filtered_data = stock_data[stock_data[code_col].isin(universe_codes)]
            
            logger.info(f"📊 股票池过滤: {len(stock_data)} -> {len(filtered_data)} 只")
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"❌ 股票池过滤失败: {e}", exc_info=True)
            return stock_data

