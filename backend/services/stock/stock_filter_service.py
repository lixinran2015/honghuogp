"""
统一股票筛选服务
整合四个筛选器：短线强势股、短线低吸股、波段低吸、达尔文长期
实现统一的数据缺失处理机制
"""

from typing import Dict, List, Optional
import logging
import pandas as pd
from datetime import datetime

from backend.models.stock_data import StockData
from backend.models.strategy_result import StrategyResult
from backend.strategy.short_term_limit_up import ShortTermLimitUpFilter
from backend.strategy.short_term_reversal import ShortTermReversalFilter
from backend.strategy.swing_pullback import SwingPullbackFilter
from backend.strategy.darwin_long_term import DarwinLongTermFilter
from backend.strategy.new_high_pullback import NewHighPullbackFilter
from backend.services.trading_validation import (
    is_mid_trend_up, mid_trend_score, is_valid_pullback,
    is_short_momentum_ok, short_momentum_score, sector_heat_factor
)

logger = logging.getLogger(__name__)


class StockFilterService:
    """统一股票筛选服务"""
    
    def __init__(self):
        """初始化筛选服务"""
        self.limit_up_filter = ShortTermLimitUpFilter()
        self.reversal_filter = ShortTermReversalFilter()
        self.pullback_filter = SwingPullbackFilter()
        self.darwin_filter = DarwinLongTermFilter()
        self.new_high_filter = NewHighPullbackFilter()
    
    def filter_all_strategies(
        self,
        stock_data: List[StockData],
        historical_data: Optional[pd.DataFrame] = None,
        financial_data: Optional[Dict[str, Dict]] = None,
        limit: int = 10
    ) -> Dict[str, StrategyResult]:
        """
        执行所有策略筛选
        
        Args:
            stock_data: 股票数据模型列表
            historical_data: 历史数据DataFrame（可选）
            financial_data: 财务数据字典（可选）
            limit: 每种策略返回数量限制
        
        Returns:
            Dict[str, StrategyResult]: {
                "limit_up": StrategyResult,  # 短线强势股（打板策略）
                "reversal": StrategyResult,  # 短线低吸股（反转策略）
                "pullback": StrategyResult,  # 波段低吸
                "darwin": StrategyResult,    # 达尔文长期
            }
        """
        try:
            results = {}
            
            # 1. 短线强势股（打板策略）- 已停用
            # try:
            #     limit_up_result = self.limit_up_filter.filter_limit_up_candidates(
            #         stock_data,
            #         limit=limit,
            #         min_samples=3
            #     )
            #     results["limit_up"] = limit_up_result
            # except Exception as e:
            #     logger.error(f"打板策略筛选失败: {e}", exc_info=True)
            #     results["limit_up"] = StrategyResult(
            #         candidates=[],
            #         warning="筛选过程出错，请稍后重试",
            #         filter_steps={}
            #     )
            logger.info("⏸️ 短线动量策略（打板策略）已停用")
            results["limit_up"] = StrategyResult(
                candidates=[],
                warning="策略已停用",
                filter_steps={}
            )
            
            # 2. 短线低吸股（反转策略）- 已停用
            # try:
            #     reversal_result = self.reversal_filter.filter_reversal_candidates(
            #         stock_data,
            #         historical_data=historical_data,
            #         limit=limit,
            #         min_samples=3
            #     )
            #     results["reversal"] = reversal_result
            # except Exception as e:
            #     logger.error(f"反转策略筛选失败: {e}", exc_info=True)
            #     results["reversal"] = StrategyResult(
            #         candidates=[],
            #         warning="筛选过程出错，请稍后重试",
            #         filter_steps={}
            #     )
            logger.info("⏸️ 反转策略已停用")
            results["reversal"] = StrategyResult(
                candidates=[],
                warning="策略已停用",
                filter_steps={}
            )
            
            # 3. 波段低吸 - 已停用
            # try:
            #     pullback_result = self.pullback_filter.filter_pullback_candidates(
            #         stock_data,
            #         historical_data=historical_data,
            #         limit=limit,
            #         min_samples=3
            #     )
            #     results["pullback"] = pullback_result
            # except Exception as e:
            #     logger.error(f"波段低吸筛选失败: {e}", exc_info=True)
            #     results["pullback"] = StrategyResult(
            #         candidates=[],
            #         warning="筛选过程出错，请稍后重试",
            #         filter_steps={}
            #     )
            logger.info("⏸️ 波段低吸策略已停用")
            results["pullback"] = StrategyResult(
                candidates=[],
                warning="策略已停用",
                filter_steps={}
            )
            
            # 4. 达尔文长期 - 已停用
            # try:
            #     darwin_result = self.darwin_filter.filter_darwin_companies(
            #         stock_data,
            #         financial_data=financial_data,
            #         limit=limit,
            #         min_samples=3
            #     )
            #     results["darwin"] = darwin_result
            # except Exception as e:
            #     logger.error(f"达尔文筛选失败: {e}", exc_info=True)
            #     results["darwin"] = StrategyResult(
            #         darwin_core=[],
            #         darwin_watch=[],
            #         warning="筛选过程出错，请稍后重试",
            #         filter_steps={}
            #     )
            logger.info("⏸️ 达尔文长期策略已停用")
            results["darwin"] = StrategyResult(
                darwin_core=[],
                darwin_watch=[],
                warning="策略已停用",
                filter_steps={}
            )
            
            # 5. 新高回踩策略（300/688开头）
            try:
                new_high_result = self.new_high_filter.filter_new_high_pullback(
                    stock_data,
                    historical_data=historical_data,
                    limit=limit,
                    min_samples=3
                )
                results["new_high"] = new_high_result
            except Exception as e:
                logger.error(f"新高回踩筛选失败: {e}", exc_info=True)
                results["new_high"] = StrategyResult(
                    candidates=[],
                    warning="筛选过程出错，请稍后重试",
                    filter_steps={}
                )
            
            return results
            
        except Exception as e:
            logger.error(f"统一筛选失败: {e}", exc_info=True)
            return {
                "limit_up": StrategyResult(candidates=[], warning="统一筛选失败，请稍后重试", filter_steps={}),
                "reversal": StrategyResult(candidates=[], warning="统一筛选失败，请稍后重试", filter_steps={}),
                "pullback": StrategyResult(candidates=[], warning="统一筛选失败，请稍后重试", filter_steps={}),
                "darwin": StrategyResult(darwin_core=[], darwin_watch=[], warning="统一筛选失败，请稍后重试", filter_steps={}),
                "new_high": StrategyResult(candidates=[], warning="统一筛选失败，请稍后重试", filter_steps={})
            }
    
    def check_required_data(
        self,
        stock_data: pd.DataFrame,
        strategy_type: str
    ) -> Dict[str, bool]:
        """
        检查必需数据是否完整
        
        Args:
            stock_data: 股票数据DataFrame
            strategy_type: 策略类型（'limit_up', 'reversal', 'pullback', 'darwin'）
        
        Returns:
            Dict: {
                "has_required": bool,
                "missing_fields": List[str],
                "can_proceed": bool
            }
        """
        try:
            required_fields_map = {
                'limit_up': ['code', 'change_pct', 'amount', 'turnover_rate'],
                'reversal': ['code', 'change_pct', 'volume'],
                'pullback': ['code', 'close', 'change_pct'],
                'darwin': ['code']
            }
            
            required_fields = required_fields_map.get(strategy_type, [])
            missing_fields = []
            
            # 检查字段是否存在（支持中英文字段名）
            field_mapping = {
                'code': ['code', '代码'],
                'change_pct': ['pct_chg', 'changePct', '涨跌幅'],
                'amount': ['amount', '成交额'],
                'turnover_rate': ['turnover_rate', '换手率'],
                'volume': ['volume', '成交量'],
                'close': ['close', 'lastPrice', '当前价']
            }
            
            for field in required_fields:
                possible_names = field_mapping.get(field, [field])
                found = False
                for name in possible_names:
                    if name in stock_data.columns:
                        found = True
                        break
                if not found:
                    missing_fields.append(field)
            
            has_required = len(missing_fields) == 0
            can_proceed = has_required  # 必需数据缺失时不能继续
            
            return {
                "has_required": has_required,
                "missing_fields": missing_fields,
                "can_proceed": can_proceed
            }
            
        except Exception as e:
            logger.error(f"检查必需数据失败: {e}", exc_info=True)
            return {
                "has_required": False,
                "missing_fields": [],
                "can_proceed": False
            }
    
    def filter_limit_up_stocks(
        self,
        stock_data: pd.DataFrame,
        limit: int = 10
    ) -> Dict:
        """
        筛选短线强势股（打板策略）
        
        Args:
            stock_data: 当日股票数据DataFrame
            limit: 返回数量限制
        
        Returns:
            Dict: {
                "candidates": List[Dict],
                "warning": Optional[str],
                "filter_steps": Dict
            }
        """
        try:
            result = self.limit_up_filter.filter_limit_up_candidates(
                stock_data.copy(),
                limit=limit,
                min_samples=3
            )
            return result
        except Exception as e:
            logger.error(f"打板策略筛选失败: {e}", exc_info=True)
            return {
                "candidates": [],
                "warning": "筛选过程出错，请稍后重试",
                "filter_steps": {}
            }
    
    def filter_reversal_stocks(
        self,
        stock_data: pd.DataFrame,
        historical_data: Optional[pd.DataFrame] = None,
        limit: int = 10
    ) -> Dict:
        """
        筛选短线低吸股（反转策略）
        
        Args:
            stock_data: 当日股票数据DataFrame
            historical_data: 历史数据DataFrame（可选）
            limit: 返回数量限制
        
        Returns:
            Dict: {
                "candidates": List[Dict],
                "warning": Optional[str],
                "filter_steps": Dict
            }
        """
        try:
            result = self.reversal_filter.filter_reversal_candidates(
                stock_data.copy(),
                historical_data=historical_data,
                limit=limit,
                min_samples=3
            )
            return result
        except Exception as e:
            logger.error(f"反转策略筛选失败: {e}", exc_info=True)
            return {
                "candidates": [],
                "warning": "筛选过程出错，请稍后重试",
                "filter_steps": {}
            }
    
    def filter_pullback_stocks(
        self,
        stock_data: pd.DataFrame,
        historical_data: Optional[pd.DataFrame] = None,
        limit: int = 10
    ) -> Dict:
        """
        筛选波段低吸股票
        
        Args:
            stock_data: 当日股票数据DataFrame
            historical_data: 历史数据DataFrame（可选）
            limit: 返回数量限制
        
        Returns:
            Dict: {
                "candidates": List[Dict],
                "warning": Optional[str],
                "filter_steps": Dict
            }
        """
        try:
            result = self.pullback_filter.filter_pullback_candidates(
                stock_data.copy(),
                historical_data=historical_data,
                limit=limit,
                min_samples=3
            )
            return result
        except Exception as e:
            logger.error(f"波段低吸筛选失败: {e}", exc_info=True)
            return {
                "candidates": [],
                "warning": "筛选过程出错，请稍后重试",
                "filter_steps": {}
            }
    
    def filter_darwin_long_term_stocks(
        self,
        stock_data: pd.DataFrame,
        financial_data: Optional[Dict[str, Dict]] = None,
        limit: int = 20
    ) -> Dict:
        """
        筛选达尔文公司长期持仓股票
        
        Args:
            stock_data: 股票数据DataFrame
            financial_data: 财务数据字典（可选）
            limit: 返回数量限制
        
        Returns:
            Dict: {
                "darwin_core": List[Dict],
                "darwin_watch": List[Dict],
                "warning": Optional[str],
                "filter_steps": Dict
            }
        """
        try:
            result = self.darwin_filter.filter_darwin_companies(
                stock_data.copy(),
                financial_data=financial_data,
                limit=limit,
                min_samples=3
            )
            return result
        except Exception as e:
            logger.error(f"达尔文筛选失败: {e}", exc_info=True)
            return {
                "darwin_core": [],
                "darwin_watch": [],
                "warning": "筛选过程出错，请稍后重试",
                "filter_steps": {}
            }
    
    def _get_stock_sector_code(self, stock_code: str) -> Optional[str]:
        """
        从股票代码获取板块代码（sector_id）
        
        Args:
            stock_code: 股票代码（ts_code格式或6位数字）
        
        Returns:
            Optional[str]: 板块代码，如果获取失败返回None
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactStockSector
            
            # 标准化代码格式
            if not stock_code.endswith(('.SH', '.SZ', '.BJ')):
                if stock_code.startswith('6'):
                    ts_code = f"{stock_code}.SH"
                elif stock_code.startswith(('0', '3')):
                    ts_code = f"{stock_code}.SZ"
                else:
                    ts_code = stock_code
            else:
                ts_code = stock_code
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            try:
                # 获取主行业板块
                stock_sector = session.query(FactStockSector).filter(
                    FactStockSector.ts_code == ts_code,
                    FactStockSector.is_primary == True,
                    FactStockSector.end_date.is_(None)
                ).order_by(FactStockSector.start_date.desc()).first()
                
                if stock_sector:
                    return stock_sector.sector_id
                return None
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"获取股票 {stock_code} 的板块代码失败: {e}")
            return None
    
    def _get_sector_heat_snapshot(self, sector_code: str, window_id: str = 'rolling_30d_v2'):
        """
        获取板块热度快照
        
        Args:
            sector_code: 板块代码
            window_id: 时间窗口ID，默认'rolling_30d_v2'
        
        Returns:
            FactSectorHeatSnapshot对象或None
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactSectorHeatSnapshot
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            try:
                snapshot = session.query(FactSectorHeatSnapshot).filter(
                    FactSectorHeatSnapshot.window_id == window_id,
                    FactSectorHeatSnapshot.sector_code == sector_code
                ).first()
                return snapshot
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"获取板块 {sector_code} 的热度快照失败: {e}")
            return None
    
    def _get_sector_heat_batch(self, sector_codes: list, window_id: str = 'rolling_30d_v2') -> dict:
        """
        批量获取多个板块的热度快照
        
        Args:
            sector_codes: 板块代码列表
            window_id: 时间窗口ID，默认'rolling_30d_v2'
        
        Returns:
            dict: {sector_code: FactSectorHeatSnapshot} 映射
        """
        result = {}
        if not sector_codes:
            return result
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactSectorHeatSnapshot
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            try:
                snapshots = session.query(FactSectorHeatSnapshot).filter(
                    FactSectorHeatSnapshot.window_id == window_id,
                    FactSectorHeatSnapshot.sector_code.in_(sector_codes)
                ).all()
                for snapshot in snapshots:
                    result[snapshot.sector_code] = snapshot
                return result
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"批量获取板块热度失败: {e}")
            return result
    
    def _get_stock_leader_role(self, stock_code: str, sector_code: str, window_id: str = 'rolling_30d_v2') -> Optional[str]:
        """
        获取股票在板块中的龙头角色
        
        Args:
            stock_code: 股票代码（ts_code格式）
            sector_code: 板块代码
            window_id: 时间窗口ID，默认'rolling_30d_v2'
        
        Returns:
            Optional[str]: 龙头角色（'leader'/'sub_leader'/'follow'），如果获取失败返回None
        """
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models import FactSectorLeaderSnapshot
            
            # 标准化代码格式
            if not stock_code.endswith(('.SH', '.SZ', '.BJ')):
                if stock_code.startswith('6'):
                    ts_code = f"{stock_code}.SH"
                elif stock_code.startswith(('0', '3')):
                    ts_code = f"{stock_code}.SZ"
                else:
                    ts_code = stock_code
            else:
                ts_code = stock_code
            
            warehouse_service = WarehouseService()
            session = warehouse_service.get_session()
            try:
                leader = session.query(FactSectorLeaderSnapshot).filter(
                    FactSectorLeaderSnapshot.window_id == window_id,
                    FactSectorLeaderSnapshot.sector_code == sector_code,
                    FactSectorLeaderSnapshot.ts_code == ts_code
                ).first()
                
                if leader:
                    # 映射 leader_type 到 role
                    leader_type = getattr(leader, 'leader_type', 'follower')
                    if leader_type in ('absolute_leader', 'rel_strength'):
                        return 'leader'
                    elif leader_type in ('catch_up', 'resilient'):
                        return 'sub_leader'
                    else:
                        return 'follow'
                return None
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"获取股票 {stock_code} 的龙头角色失败: {e}")
            return None
    
    def refine_darwin_candidates(
        self,
        candidates: List[StockData],
        kline_map: Dict[str, pd.DataFrame],
        sector_map: Dict[str, any],
        max_count: int = 20,
        allow_no_kline: bool = False,
    ) -> List[Dict]:
        """
        精炼达尔文公司候选：加入趋势验证和板块热度加权
        
        Args:
            candidates: 达尔文筛选后的候选股票列表
            kline_map: 股票代码到K线数据的映射
            sector_map: 板块代码到FactSectorHeatSnapshot的映射
            max_count: 最大返回数量
            allow_no_kline: 是否允许没有K线数据的股票通过（给默认趋势分数）
        
        Returns:
            List[Dict]: 精炼后的候选列表，每个包含stock、final_score、trend_score、sector_heat
        """
        refined = []
        
        for stock in candidates:
            try:
                kline = kline_map.get(stock.code)
                
                # 获取板块代码和热度
                sector_code = self._get_stock_sector_code(stock.code)
                sector = sector_map.get(sector_code) if sector_code else None
                
                # 趋势验证（达尔文策略：无K线数据直接过滤，返回None）
                trend_s = None
                if kline is not None and len(kline) >= 60:
                    # 检查K线数据列名
                    if 'close' not in kline.columns:
                        logger.warning(f"股票 {stock.code} 的K线数据缺少'close'列，可用列: {kline.columns.tolist()}")
                        # 对于达尔文策略，无K线数据直接过滤
                        if not allow_no_kline:
                            logger.info(f"[darwin] 无趋势数据，过滤掉: {stock.code}")
                            continue
                        trend_s = None  # 标记为无数据
                    else:
                        # 有K线数据，正常计算趋势
                        try:
                            trend_ok = is_mid_trend_up(kline)
                            trend_s = mid_trend_score(kline)
                            
                            # 调试输出
                            if trend_s > 0.99:
                                logger.debug(f"股票 {stock.code} 趋势分数异常高: {trend_s:.3f}, K线数据长度: {len(kline)}, close列: {'close' in kline.columns}")
                            
                            # 如果趋势非常差，对于达尔文推荐（allow_no_kline=True），不直接过滤
                            # 但保持原始计算的趋势分，不设置默认值
                            if not trend_ok and trend_s < 0.3:
                                if not allow_no_kline:
                                    # 不允许没有K线数据，且趋势很差，直接过滤
                                    continue
                                # 允许通过，保持原始计算的趋势分（即使很低），让财务分占主导
                                logger.debug(f"股票 {stock.code} 趋势较差（trend_score={trend_s:.2f}），但保留原始分数")
                        except Exception as e:
                            logger.warning(f"股票 {stock.code} 计算趋势分数失败: {e}")
                            if not allow_no_kline:
                                logger.info(f"[darwin] 无趋势数据，过滤掉: {stock.code}")
                                continue
                            trend_s = None  # 标记为无数据
                elif kline is not None and len(kline) < 60:
                    # K线数据不足60天，对于达尔文策略直接过滤
                    if not allow_no_kline:
                        logger.info(f"[darwin] 无趋势数据（K线不足60天），过滤掉: {stock.code}")
                        continue
                    trend_s = None  # 标记为无数据
                else:
                    # 完全没有K线数据，对于达尔文策略直接过滤
                    if not allow_no_kline:
                        logger.info(f"[darwin] 无趋势数据，过滤掉: {stock.code}")
                        continue
                    trend_s = None  # 标记为无数据
                
                # 如果trend_s为None，说明无K线数据
                # 对于达尔文评分，如果没有K线数据，保持None，不设置默认值（避免误导）
                if trend_s is None:
                    if allow_no_kline:
                        # 保持None，不设置默认值，让前端显示"--"
                        logger.debug(f"股票 {stock.code} 无K线数据，趋势分保持为None")
                    else:
                        continue
                
                # 板块热度因子（用于计算得分，0-1）
                sector_s = sector_heat_factor(sector)
                
                # 板块热度原始值（用于返回给前端，0-20）
                if sector:
                    if hasattr(sector, 'swing_heat_score') and sector.swing_heat_score is not None:
                        sector_heat_raw = float(sector.swing_heat_score)
                    elif hasattr(sector, 'heat_score') and sector.heat_score is not None:
                        sector_heat_raw = float(sector.heat_score)
                    else:
                        sector_heat_raw = 0.0
                else:
                    sector_heat_raw = 0.0
                
                # base_score: 达尔文财务评分
                base_score = getattr(stock, 'darwin_score', getattr(stock, 'darwinScore', 60))
                if isinstance(base_score, (int, float)):
                    base_score_norm = base_score / 100.0
                else:
                    base_score_norm = 0.6
                
                # 最终得分：复盘建议强化趋势确认，趋势30% + 财务55% + 板块15%
                if trend_s is not None:
                    final_score = (
                        base_score_norm * 0.55 +
                        trend_s * 0.30 +
                        sector_s * 0.15
                    )
                else:
                    # 没有趋势分时，财务占70%，板块占30%
                    final_score = (
                        base_score_norm * 0.7 +
                        sector_s * 0.3
                    )
                
                # 调试：记录前3只股票的详细信息
                if len(refined) < 3:
                    trend_s_str = f"{trend_s:.3f}" if trend_s is not None else "None"
                    logger.debug(f"📊 精炼股票 {stock.code}: final_score={final_score:.3f}, trend_score={trend_s_str}, sector_heat={sector_heat_raw:.3f}, base_score={base_score_norm:.3f}")
                
                refined.append({
                    "stock": stock,
                    "final_score": final_score,
                    "trend_score": trend_s,
                    "sector_heat": sector_heat_raw,  # 返回原始热度值（0-20），而不是因子（0-1）
                })
            except Exception as e:
                logger.warning(f"精炼达尔文候选 {stock.code} 失败: {e}")
                continue
        
        refined.sort(key=lambda x: x["final_score"], reverse=True)
        return refined[:max_count]
    
    def refine_swing_candidates(
        self,
        candidates: List[StockData],
        kline_map: Dict[str, pd.DataFrame],
        sector_map: Dict[str, any],
        max_count: int = 10,
    ) -> List[Dict]:
        """
        精炼波段候选：要求上升趋势中的回踩，且来自热度较高的板块
        
        Args:
            candidates: 波段筛选后的候选股票列表
            kline_map: 股票代码到K线数据的映射
            sector_map: 板块代码到FactSectorHeatSnapshot的映射
            max_count: 最大返回数量
        
        Returns:
            List[Dict]: 精炼后的候选列表
        """
        refined = []
        
        logger.info(f"📊 开始精炼 {len(candidates)} 只波段候选股票")
        logger.info(f"📊 K线数据覆盖: {len(kline_map)}/{len(candidates)} 只股票")
        logger.info(f"📊 板块热度数据: {len(sector_map)} 个板块")
        
        filtered_reasons = {
            'no_kline': 0,
            'low_sector_heat': 0,
            'low_trend': 0,
            'invalid_pullback': 0,
            'low_amount': 0,
            'passed': 0
        }
        
        for stock in candidates:
            try:
                kline = kline_map.get(stock.code)
                if kline is None:
                    filtered_reasons['no_kline'] += 1
                    logger.debug(f"股票 {stock.code} 没有K线数据")
                    continue
                
                # 获取板块代码和热度
                sector_code = self._get_stock_sector_code(stock.code)
                sector = sector_map.get(sector_code) if sector_code else None
                
                # 1. 板块热度限制（swing_heat_score >= 8，如果没有板块数据则允许通过）
                swing_heat = getattr(sector, 'swing_heat_score', 0) if sector else 0
                if sector and swing_heat < 8:  # 从10降低到8，如果没有板块数据则允许通过
                    filtered_reasons['low_sector_heat'] += 1
                    logger.info(f"❌ 股票 {stock.code} 板块热度不足: sector={sector_code}, swing_heat={swing_heat:.2f} < 8")
                    continue
                
                # 2. 趋势 + 回踩结构（趋势分数要求降低到0.3）
                trend_s = mid_trend_score(kline)
                if trend_s < 0.3:  # 从0.5降低到0.3
                    filtered_reasons['low_trend'] += 1
                    logger.info(f"❌ 股票 {stock.code} 趋势分数不足: {trend_s:.2f} < 0.3")
                    continue
                
                if not is_valid_pullback(kline):
                    filtered_reasons['invalid_pullback'] += 1
                    logger.info(f"❌ 股票 {stock.code} 不是有效的回踩结构")
                    continue
                
                # 3. 成交额过滤（日均成交额 >= 5000万，如果没有数据则允许通过）
                if stock.amount and stock.amount < 5e7:
                    filtered_reasons['low_amount'] += 1
                    logger.info(f"❌ 股票 {stock.code} 成交额不足: {stock.amount/1e8:.2f}亿 < 0.5亿")
                    continue
                
                filtered_reasons['passed'] += 1
                logger.info(f"✅ 股票 {stock.code} 通过所有筛选条件: trend={trend_s:.2f}, sector_heat={swing_heat:.2f}")
                
                # 基础波段得分
                base_swing_score = getattr(stock, 'swing_score', 0.5)
                if not isinstance(base_swing_score, (int, float)):
                    base_swing_score = 0.5
                
                # 最终得分：波段50% + 趋势30% + 板块20%
                final_score = (
                    base_swing_score * 0.5 +
                    trend_s * 0.3 +
                    sector_heat_factor(sector, strategy_type="swing") * 0.2
                )
                
                refined.append({
                    "stock": stock,
                    "final_score": final_score,
                    "trend_score": trend_s,
                    "sector_heat": getattr(sector, 'swing_heat_score', 0),
                })
            except Exception as e:
                logger.warning(f"精炼波段候选 {stock.code} 失败: {e}")
                continue
        
        refined.sort(key=lambda x: x["final_score"], reverse=True)
        return refined[:max_count]
    
    def refine_short_candidates(
        self,
        candidates: List[StockData],
        kline_map: Dict[str, pd.DataFrame],
        sector_map: Dict[str, any],
        leaders_map: Dict[str, Dict[str, str]],
        max_count: int = 10,
    ) -> List[Dict]:
        """
        精炼短线候选：要求来自热门板块的龙头或强势票
        
        Args:
            candidates: 短线筛选后的候选股票列表
            kline_map: 股票代码到K线数据的映射
            sector_map: 板块代码到FactSectorHeatSnapshot的映射
            leaders_map: 板块代码到{股票代码: 龙头角色}的映射
            max_count: 最大返回数量
        
        Returns:
            List[Dict]: 精炼后的候选列表
        """
        refined = []
        
        logger.info(f"📊 开始精炼 {len(candidates)} 只短线候选股票")
        logger.info(f"📊 K线数据覆盖: {len(kline_map)}/{len(candidates)} 只股票")
        logger.info(f"📊 板块热度数据: {len(sector_map)} 个板块")
        logger.info(f"📊 龙头数据: {len(leaders_map)} 个板块")
        
        filtered_reasons = {
            'no_kline': 0,
            'no_sector': 0,
            'low_sector_heat': 0,
            'low_momentum': 0,
            'passed': 0
        }
        
        for stock in candidates:
            try:
                kline = kline_map.get(stock.code)
                if kline is None:
                    filtered_reasons['no_kline'] += 1
                    logger.debug(f"股票 {stock.code} 没有K线数据")
                    continue
                
                # 获取板块代码和热度
                sector_code = self._get_stock_sector_code(stock.code)
                sector = sector_map.get(sector_code) if sector_code else None
                
                # 1. 板块短线热度（统一阈值 >= 10，无板块数据时允许通过）
                short_heat = getattr(sector, 'short_heat_score', None) if sector else None
                if short_heat is None:
                    # 无板块数据，允许通过（兜底逻辑）
                    filtered_reasons['no_sector'] += 1
                    logger.warning(f"[short] 无板块热度数据，允许兜底通过: {stock.code}")
                    # 继续处理，不跳过
                    short_heat = None  # 明确标记为None，用于后续判断
                elif short_heat < 10:  # 统一阈值：>= 10（包括0.0的情况）
                    filtered_reasons['low_sector_heat'] += 1
                    logger.info(f"❌ 股票 {stock.code} 板块短线热度不足: sector={sector_code}, short_heat={short_heat:.2f} < 10")
                    continue
                
                # 2. 短线动能
                if not is_short_momentum_ok(kline):
                    filtered_reasons['low_momentum'] += 1
                    logger.info(f"❌ 股票 {stock.code} 短线动能不足")
                    continue
                
                # 3. 龙头加分
                sector_leaders = leaders_map.get(sector_code, {})
                role = sector_leaders.get(stock.code)
                
                if role == 'leader':
                    leader_bonus = 1.0
                elif role == 'sub_leader':
                    leader_bonus = 0.7
                else:
                    leader_bonus = 0.3
                
                # 基础短线得分
                base_short_score = getattr(stock, 'short_score', 0.5)
                if not isinstance(base_short_score, (int, float)):
                    base_short_score = 0.5
                
                momentum_s = short_momentum_score(kline)
                
                # 最终得分：基础40% + 动能30% + 板块20% + 龙头10%
                final_score = (
                    base_short_score * 0.4 +
                    momentum_s * 0.3 +
                    sector_heat_factor(sector, strategy_type="short") * 0.2 +
                    leader_bonus * 0.1
                )
                
                filtered_reasons['passed'] += 1
                logger.info(f"✅ 股票 {stock.code} 通过所有筛选条件: momentum={momentum_s:.2f}, sector_heat={short_heat if short_heat is not None else '无数据'}, leader_role={role}")
                
                refined.append({
                    "stock": stock,
                    "final_score": final_score,
                    "momentum_score": momentum_s,
                    "sector_heat": short_heat,  # 保持None或实际值，不转换为0
                    "leader_role": role,
                })
            except Exception as e:
                logger.warning(f"精炼短线候选 {stock.code} 失败: {e}")
                continue
        
        refined.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 输出过滤统计
        logger.info(f"📊 短线精炼统计:")
        logger.info(f"  - 无K线数据: {filtered_reasons['no_kline']} 只")
        logger.info(f"  - 无板块数据: {filtered_reasons['no_sector']} 只")
        logger.info(f"  - 板块热度不足: {filtered_reasons['low_sector_heat']} 只")
        logger.info(f"  - 短线动能不足: {filtered_reasons['low_momentum']} 只")
        logger.info(f"  - 通过筛选: {filtered_reasons['passed']} 只")
        logger.info(f"  - 最终返回: {len(refined)} 只")
        
        return refined[:max_count]

