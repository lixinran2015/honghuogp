"""
股票数据快照服务
在四个时间点（09:15, 11:30, 13:00, 15:00）创建数据快照
"""

import sys
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, List
import logging
from datetime import datetime, date, time
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.models import FactStockSnapshot
from data_warehouse.db import get_shared_engine
from backend.services.market_data_service import MarketDataService
from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.sector.sector_enricher import SectorEnricher
from backend.services.data.financial_data_service import FinancialDataService

logger = logging.getLogger(__name__)


class StockSnapshotService:
    """股票数据快照服务"""
    
    def __init__(self):
        """初始化服务"""
        self.market_service = MarketDataService()
        self.universe_service = StockUniverseService()
        self.sector_enricher = SectorEnricher()
        self.financial_service = FinancialDataService()
        self.engine = get_shared_engine()
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def _convert_to_ts_code(self, code: str) -> Optional[str]:
        """将6位数字代码转换为ts_code格式"""
        code = str(code).strip().replace('sh', '').replace('sz', '').replace('bj', '').strip()
        if len(code) == 6:
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
            elif code.startswith('8') or code.startswith('4'):
                return f"{code}.BJ"
        return None
    
    def _calculate_ma(self, prices: pd.Series, period: int) -> float:
        """计算移动平均线"""
        if len(prices) < period:
            return 0.0
        return float(prices.tail(period).mean())
    
    def _calculate_ma20_slope(self, prices: pd.Series) -> float:
        """计算MA20斜率"""
        if len(prices) < 20:
            return 0.0
        ma20_values = prices.rolling(window=20).mean()
        if len(ma20_values) < 2:
            return 0.0
        recent_ma20 = ma20_values.tail(5)
        if len(recent_ma20) < 2:
            return 0.0
        slope = (recent_ma20.iloc[-1] - recent_ma20.iloc[0]) / recent_ma20.iloc[0] * 100
        return float(slope)
    
    def create_snapshot(self, trade_date: Optional[str] = None, snapshot_time: Optional[str] = None) -> int:
        """
        创建数据快照
        
        Args:
            trade_date: 交易日期（格式：YYYY-MM-DD），默认今天
            snapshot_time: 快照时间点（格式：HH:MM），如"09:15"、"11:30"等
            
        Returns:
            int: 创建的快照数量
        """
        try:
            if trade_date is None:
                trade_date = datetime.now().strftime('%Y-%m-%d')
            
            if snapshot_time is None:
                current_time = datetime.now().time()
                # 自动判断时间点
                if current_time < time(9, 30):
                    snapshot_time = "09:15"
                elif current_time < time(13, 0):
                    snapshot_time = "11:30"
                elif current_time < time(15, 0):
                    snapshot_time = "13:00"
                else:
                    snapshot_time = "15:00"
            
            logger.info(f"📸 开始创建数据快照: trade_date={trade_date}, snapshot_time={snapshot_time}")
            
            # 1. 获取S1新高策略股票池数据（只保存S1池股票，减少数据量）
            s1_codes = self.universe_service.get_universe_stocks('s1', trade_date)
            
            if not s1_codes:
                logger.warning("⚠️ S1股票池为空，跳过快照创建")
                return 0
            
            logger.info(f"📊 从S1池获取 {len(s1_codes)} 只股票")
            
            # 获取S1股票的实时数据
            stock_df = self.market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
            
            if stock_df.empty:
                logger.error("❌ 无法获取股票数据，快照创建失败")
                return 0
            
            # 只保留S1池中的股票
            code_col = 'code' if 'code' in stock_df.columns else 'ts_code'
            stock_df = stock_df[stock_df[code_col].astype(str).isin(s1_codes)]
            
            if stock_df.empty:
                logger.warning("⚠️ S1股票数据匹配为空，跳过快照创建")
                return 0
            
            logger.info(f"📊 获取到 {len(stock_df)} 只股票，开始创建快照...")
            
            # 2. 获取历史K线数据（用于计算MA等指标）
            codes = stock_df['code'].astype(str).tolist()[:100]  # 限制数量，避免超时
            historical_data = self.market_service.get_historical_kline(
                codes=codes,
                days=120,
                max_codes=100,
                use_warehouse=True
            )
            
            # 3. 解析快照时间
            snapshot_time_obj = datetime.strptime(snapshot_time, '%H:%M').time()
            
            # 4. 创建数据库会话
            session = self.SessionLocal()
            created_count = 0
            
            try:
                # 5. 为每只股票创建快照
                for idx, row in stock_df.iterrows():
                    try:
                        code = str(row.get('code', '')).strip()
                        ts_code = self._convert_to_ts_code(code)
                        
                        if not ts_code:
                            continue
                        
                        # 获取历史数据（用于计算MA）
                        historical_for_code = historical_data[historical_data['code'] == code] if not historical_data.empty else pd.DataFrame()
                        
                        # 计算历史指标
                        historical_dict = {}
                        if not historical_for_code.empty and 'close' in historical_for_code.columns:
                            date_col = 'trade_date' if 'trade_date' in historical_for_code.columns else historical_for_code.index
                            closes = historical_for_code.sort_values(date_col)['close'] if isinstance(date_col, str) else historical_for_code.sort_index()['close']
                            historical_dict = {
                                'ma5': self._calculate_ma(closes, 5),
                                'ma10': self._calculate_ma(closes, 10),
                                'ma20': self._calculate_ma(closes, 20),
                                'ma60': self._calculate_ma(closes, 60),
                                'ma20_slope': self._calculate_ma20_slope(closes),
                            }
                        
                        # 获取财务数据
                        financial_dict = {}
                        try:
                            financial = self.financial_service.get_stock_financial(ts_code)
                            if financial:
                                financial_dict = {
                                    'roe': financial.get('roe', 0),
                                    'gross_margin': financial.get('gross_margin', 0),
                                    'pe': financial.get('pe', 0),
                                    'pb': financial.get('pb', 0),
                                    'revenue_growth': financial.get('revenue_growth', 0),
                                    'profit_growth': financial.get('profit_growth', 0),
                                }
                        except Exception as e:
                            logger.debug(f"获取 {code} 财务数据失败: {e}")
                        
                        # 获取行业信息
                        sector_name = row.get('sector', '')
                        if not sector_name:
                            # 使用SectorEnricher获取行业信息
                            try:
                                sector_name = self.sector_enricher._fetch_sector_from_database(code)
                                if not sector_name:
                                    sector_name = self.sector_enricher._fetch_sector_from_akshare(code)
                            except Exception as e:
                                logger.debug(f"获取股票 {code} 行业信息失败: {e}")
                                sector_name = ''
                        
                        # 创建快照记录
                        snapshot = FactStockSnapshot(
                            ts_code=ts_code,
                            trade_date=datetime.strptime(trade_date, '%Y-%m-%d').date(),
                            snapshot_time=snapshot_time_obj,
                            pre_close=float(row.get('preClose', row.get('昨收', 0))),
                            open=float(row.get('open', row.get('今开', 0))),
                            high=float(row.get('high', row.get('最高', 0))),
                            low=float(row.get('low', row.get('最低', 0))),
                            close=float(row.get('lastPrice', row.get('最新价', 0))),
                            change_pct=float(row.get('changePct', row.get('涨跌幅', 0))),
                            vol=float(row.get('volume', row.get('成交量', 0))),
                            amount=float(row.get('amount', row.get('成交额', 0))),
                            turnover_rate=float(row.get('turnoverRate', row.get('换手率', 0))),
                            historical_data=historical_dict,
                            financial_data=financial_dict,
                            sector_name=sector_name,
                            concept_tags=row.get('concept_tags', []) if isinstance(row.get('concept_tags'), list) else []
                        )
                        
                        session.merge(snapshot)  # 使用merge避免重复
                        created_count += 1
                        
                        if created_count % 50 == 0:
                            logger.info(f"  📝 已处理 {created_count} 只股票...")
                            session.commit()  # 分批提交
                    
                    except Exception as e:
                        logger.warning(f"创建股票 {code} 快照失败: {e}")
                        continue
                
                # 最终提交
                session.commit()
                logger.info(f"✅ 数据快照创建完成: {created_count} 只股票")
                
                return created_count
                
            except Exception as e:
                session.rollback()
                logger.error(f"❌ 创建数据快照失败: {e}", exc_info=True)
                raise
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 创建数据快照异常: {e}", exc_info=True)
            raise
    
    def get_latest_snapshot(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取最新快照数据
        
        Args:
            trade_date: 交易日期（格式：YYYY-MM-DD），默认今天
            
        Returns:
            DataFrame: 快照数据
        """
        try:
            if trade_date is None:
                trade_date = datetime.now().strftime('%Y-%m-%d')
            
            session = self.SessionLocal()
            try:
                # 查询最新快照（按时间倒序）
                snapshots = session.query(FactStockSnapshot).filter(
                    FactStockSnapshot.trade_date == datetime.strptime(trade_date, '%Y-%m-%d').date()
                ).order_by(
                    FactStockSnapshot.snapshot_time.desc()
                ).all()
                
                if not snapshots:
                    logger.warning(f"⚠️ 未找到 {trade_date} 的快照数据")
                    return pd.DataFrame()
                
                # 转换为DataFrame
                data = []
                for snapshot in snapshots:
                    row = {
                        'ts_code': snapshot.ts_code,
                        'trade_date': snapshot.trade_date,
                        'snapshot_time': snapshot.snapshot_time,
                        'pre_close': float(snapshot.pre_close) if snapshot.pre_close else 0,
                        'open': float(snapshot.open) if snapshot.open else 0,
                        'high': float(snapshot.high) if snapshot.high else 0,
                        'low': float(snapshot.low) if snapshot.low else 0,
                        'close': float(snapshot.close) if snapshot.close else 0,
                        'change_pct': float(snapshot.change_pct) if snapshot.change_pct else 0,
                        'vol': float(snapshot.vol) if snapshot.vol else 0,
                        'amount': float(snapshot.amount) if snapshot.amount else 0,
                        'turnover_rate': float(snapshot.turnover_rate) if snapshot.turnover_rate else 0,
                        'sector_name': snapshot.sector_name or '',
                        'historical_data': snapshot.historical_data or {},
                        'financial_data': snapshot.financial_data or {},
                    }
                    data.append(row)
                
                return pd.DataFrame(data)
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 获取快照数据失败: {e}", exc_info=True)
            return pd.DataFrame()

