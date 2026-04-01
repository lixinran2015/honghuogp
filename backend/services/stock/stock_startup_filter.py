"""
股票启动筛选器（包装类）
提供简化的接口，内部组装所有组件

两阶段并行处理说明：
1. 阶段1：并行检查金叉（只计算，不保存数据库）
   - 使用 ThreadPoolExecutor 并行处理所有股票
   - 调用 check_golden_cross_only，只进行金叉计算
   - 不涉及数据库写操作，可以充分利用 CPU 多核
   
2. 阶段2：串行处理有金叉的股票（保存数据库并检查条件）
   - 对阶段1发现的有金叉的股票，串行处理
   - 在 _process_stock_with_golden_cross 中：
     a. 先保存金叉记录（20分，stage='golden_cross'）
     b. 然后调用 check_conditions 检查核心/辅助/风险条件
     c. check_conditions 会更新刚才保存的记录（如果条件满足）
   
保存时机：
- 金叉记录在阶段2的 _process_stock_with_golden_cross 方法中保存
- 然后 check_conditions 会根据 golden_cross_date 查找记录并更新

PRODUCT_LINE: S  启动龙头产品线核心模块
"""

import logging
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import os

from backend.services.stock.startup.data import StockDataLoader, IndicatorCalculator
from backend.services.stock.startup.conditions import (
    BasicConditionChecker,
    CoreConditionChecker,
    AssistConditionChecker,
    RiskConditionChecker
)
from backend.services.stock.startup.state import StartupStateManager, CandidateRepository
from backend.services.stock.startup.filter.startup_filter import StartupFilter

logger = logging.getLogger(__name__)


class StockStartupFilter:
    """股票启动筛选器（包装类，提供简化接口）"""
    
    def __init__(self, warehouse_service):
        """
        初始化筛选器
        
        Args:
            warehouse_service: 数据仓库服务实例
        """
        self.warehouse = warehouse_service
        
        # 初始化所有组件
        self.data_loader = StockDataLoader(warehouse_service)
        self.indicator_calculator = IndicatorCalculator()
        self.basic_checker = BasicConditionChecker()
        self.core_checker = CoreConditionChecker()
        self.assist_checker = AssistConditionChecker()
        self.risk_checker = RiskConditionChecker()
        self.state_manager = StartupStateManager()
        self.repository = CandidateRepository(warehouse_service)
        
        # 创建核心筛选器实例
        self.filter = StartupFilter(
            data_loader=self.data_loader,
            indicator_calculator=self.indicator_calculator,
            basic_checker=self.basic_checker,
            core_checker=self.core_checker,
            assist_checker=self.assist_checker,
            risk_checker=self.risk_checker,
            state_manager=self.state_manager,
            repository=self.repository
        )
    
    def _get_stock_indicators(self, ts_code: str, trade_date: str, force_realtime: bool = False, fallback_to_latest_if_no_data: bool = False) -> Optional[Dict]:
        """
        获取股票的完整指标数据
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期（格式：YYYY-MM-DD）
            force_realtime: 是否强制使用实时数据
            fallback_to_latest_if_no_data: 仅龙头诊断用。请求日无K线时是否用该股最新可用数据
        
        Returns:
            Dict: 包含所有指标的数据字典，如果获取失败返回 None
        """
        try:
            # 加载股票数据
            stock_data = self.data_loader.load_stock_data(
                ts_code=ts_code,
                trade_date=trade_date,
                force_realtime=force_realtime,
                fallback_to_latest_if_no_data=fallback_to_latest_if_no_data
            )
            
            if not stock_data:
                return None
            
            # 计算技术指标
            indicators = self.indicator_calculator.calculate_all(
                kline_df=stock_data.get('kline_df'),
                stock_info=stock_data.get('stock_info'),
                today_data=stock_data.get('today_data')
            )
            
            # 合并数据（带上实际使用的交易日期，便于请求日无数据时使用最新数据后仍能正确展示）
            result = {
                'ts_code': ts_code,
                'trade_date': stock_data.get('trade_date', trade_date),
                **indicators
            }
            
            return result
            
        except Exception as e:
            logger.error(f"获取股票指标失败 {ts_code} {trade_date}: {e}", exc_info=True)
            return None
    
    def batch_filter_startups(
        self,
        stock_codes: List[str],
        trade_date: Optional[str] = None,
        enable_prefilter: bool = True,
        max_workers: Optional[int] = None
    ) -> pd.DataFrame:
        """
        批量筛选启动股票（两阶段并行处理）
        
        阶段1：并行检查金叉（只计算，不保存数据库）
        阶段2：串行处理有金叉的股票（保存数据库并检查条件）
        
        Args:
            stock_codes: 股票代码列表
            trade_date: 交易日期（格式：YYYY-MM-DD），如果为None则使用今天
            enable_prefilter: 是否启用预过滤（批量检查价格数据是否存在）
            max_workers: 最大并发数，默认使用CPU核心数（最多16）
        
        Returns:
            pd.DataFrame: 筛选结果DataFrame，包含所有得分≥20的股票
        """
        if not trade_date:
            from datetime import date
            trade_date = date.today().strftime('%Y-%m-%d')
        
        logger.info(f"开始批量筛选启动股票: {len(stock_codes)} 只股票, 日期: {trade_date}")
        
        # 预过滤：批量检查哪些股票有价格数据
        if enable_prefilter:
            filtered_codes = self._batch_check_price_data_exists(stock_codes, trade_date)
            logger.info(f"预过滤后剩余 {len(filtered_codes)} 只股票（有价格数据）")
        else:
            filtered_codes = stock_codes
        
        if not filtered_codes:
            logger.warning("预过滤后没有股票需要处理")
            return pd.DataFrame()
        
        # 确定并发数
        if max_workers is None:
            cpu_count = os.cpu_count() or 4
            max_workers = min(cpu_count, 16)  # 最多16个线程
        
        if max_workers <= 1:
            max_workers = 1
        
        # ====================================
        # 阶段1：并行检查金叉（只计算，不保存数据库）
        # ====================================
        # 重置统计计数器
        from backend.services.stock.startup.conditions.basic_condition_checker import BasicConditionChecker
        BasicConditionChecker._stats = {
            'strict_golden_cross_count': 0,
            'bullish_arrangement_count': 0,
            'total_checked': 0
        }

        logger.info(f"阶段1：并行检查金叉（{max_workers} 个线程）")
        golden_cross_stocks = []
        
        def _check_golden_cross_only(ts_code: str) -> Optional[Dict]:
            """检查单个股票是否有金叉（不保存数据库）"""
            try:
                stock_data = self._get_stock_indicators(ts_code, trade_date)
                if not stock_data:
                    return None
                
                result = self.filter.check_golden_cross_only(stock_data, trade_date)
                if result.get('passed'):
                    return {
                        'ts_code': ts_code,
                        'stock_data': stock_data,
                        'golden_cross_date': result.get('golden_cross_date')
                    }
                return None
            except Exception as e:
                logger.error(f"检查金叉失败 {ts_code}: {e}", exc_info=True)
                return None
        
        # 并行执行阶段1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(_check_golden_cross_only, ts_code): ts_code
                for ts_code in filtered_codes
            }
            
            completed = 0
            for future in as_completed(future_to_code):
                completed += 1
                if completed % 500 == 0:
                    logger.debug(f"阶段1进度: {completed}/{len(filtered_codes)}")
                
                result = future.result()
                if result:
                    golden_cross_stocks.append(result)
        
        logger.info(f"阶段1完成：发现 {len(golden_cross_stocks)} 只股票有金叉")

        # 输出金叉/多头排列统计
        stats = BasicConditionChecker._stats
        logger.info(f"[金叉统计总结] 总计检查:{stats['total_checked']} "
                   f"严格金叉:{stats['strict_golden_cross_count']} "
                   f"多头排列:{stats['bullish_arrangement_count']}")

        if not golden_cross_stocks:
            return pd.DataFrame()
        
        # ====================================
        # 阶段2：串行处理有金叉的股票（保存数据库并检查条件）
        # ====================================
        logger.info(f"阶段2：串行处理 {len(golden_cross_stocks)} 只有金叉的股票")
        results = []
        
        for i, item in enumerate(golden_cross_stocks, 1):
            ts_code = item['ts_code']
            stock_data = item['stock_data']
            golden_cross_date = item['golden_cross_date']
            
            if i % 500 == 0:
                logger.debug(f"阶段2进度: {i}/{len(golden_cross_stocks)}")
            
            try:
                # 处理有金叉的股票（保存记录并检查条件）
                result = self._process_stock_with_golden_cross(
                    ts_code=ts_code,
                    stock_data=stock_data,
                    trade_date=trade_date,
                    golden_cross_date=golden_cross_date
                )
                
                if result:
                    results.append(result)
                    
            except Exception as e:
                logger.error(f"处理股票失败 {ts_code}: {e}", exc_info=True)
                continue
        
        logger.info(f"阶段2完成：处理了 {len(results)} 只股票")
        
        # 转换为DataFrame
        if results:
            df = pd.DataFrame(results)
            return df
        else:
            return pd.DataFrame()
    
    def _batch_check_price_data_exists(self, ts_codes: List[str], trade_date: str) -> List[str]:
        """
        批量检查哪些股票在指定日期有价格数据
        
        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期（格式：YYYY-MM-DD）
        
        Returns:
            List[str]: 有价格数据的股票代码列表
        """
        try:
            from datetime import datetime
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            from sqlalchemy import func
            
            trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
            session = self.warehouse.get_session()
            
            try:
                # 批量查询
                query = session.query(
                    FactDailyPriceQfq.ts_code
                ).filter(
                    FactDailyPriceQfq.trade_date == trade_date_obj,
                    FactDailyPriceQfq.ts_code.in_(ts_codes)
                ).distinct()
                
                codes_with_data = [row[0] for row in query.all()]
                return codes_with_data
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"批量检查价格数据失败: {e}", exc_info=True)
            # 出错时返回所有股票，让后续处理来处理
            return ts_codes
    
    def _process_stock_with_golden_cross(
        self,
        ts_code: str,
        stock_data: Dict,
        trade_date: Optional[str],
        golden_cross_date: Optional[str]
    ) -> Optional[Dict]:
        """
        处理有金叉的股票（检查核心条件、辅助条件、风险条件）
        
        优化后的保存逻辑：
        - 先检查是否已有7天内的记录，如果有，使用已有记录的 golden_cross_date
        - 直接调用 check_conditions，让它处理所有保存逻辑
        - check_conditions 内部会：
          1. 先保存金叉记录（如果 is_in_golden_cross_pool=False）
          2. 调用 check_core_conditions，如果核心条件未通过，会保存记录（20-50分）
          3. 如果核心条件通过，继续检查辅助条件，如果未通过，会保存记录（50分）
          4. 如果辅助条件通过，继续检查风险条件，如果未通过，会保存记录（60-80分）
          5. 如果所有条件都通过，会保存完全启动记录（100分）
        
        Args:
            ts_code: 股票代码
            stock_data: 股票数据字典
            trade_date: 交易日期
            golden_cross_date: 金叉日期（可能是当天的 trade_date，需要在保存时确定实际的金叉日期）
        
        Returns:
            处理结果字典，如果不符合条件返回 None
        """
        try:
            # ✅ 修复：检查是否已有7天内的记录（观察期内）
            # 如果已有记录，应该使用已有记录的 golden_cross_date，并设置 is_in_golden_cross_pool=True
            # 这样就不会重复创建新记录
            from datetime import datetime
            from backend.utils.trade_date_utils import calculate_trading_days_diff
            
            is_in_golden_cross_pool = False
            actual_golden_cross_date = golden_cross_date
            
            if trade_date and golden_cross_date:
                trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
                session = self.warehouse.get_session()
                try:
                    from data_warehouse.models.startup_candidate import FactStockStartupCandidate
                    
                    # 查找最近7天内的记录
                    recent_record = session.query(FactStockStartupCandidate).filter(
                        FactStockStartupCandidate.ts_code == ts_code,
                        FactStockStartupCandidate.golden_cross_date.isnot(None),
                        FactStockStartupCandidate.golden_cross_date <= trade_date_obj
                    ).order_by(
                        FactStockStartupCandidate.golden_cross_date.desc()
                    ).first()
                    
                    if recent_record and recent_record.golden_cross_date:
                        # 计算距离上次金叉的天数
                        days_diff = calculate_trading_days_diff(
                            session, recent_record.golden_cross_date, trade_date_obj, return_none_on_invalid=True
                        )
                        
                        # 如果7天内有记录，使用已有记录的 golden_cross_date
                        if days_diff is not None and 0 <= days_diff <= 7:
                            actual_golden_cross_date = recent_record.golden_cross_date.strftime('%Y-%m-%d')
                            is_in_golden_cross_pool = True
                            logger.debug(f"  {ts_code}: 7天内有记录，使用已有记录的 golden_cross_date={actual_golden_cross_date}（当前检查日期={trade_date}，距离{days_diff}个交易日）")
                finally:
                    session.close()
            
            # ✅ 优化：直接调用 check_conditions，让它统一处理保存逻辑
            # check_conditions 会根据条件检查结果，在适当的时机保存记录
            result = self.filter.check_conditions(
                stock_data,
                trade_date,
                is_in_golden_cross_pool=is_in_golden_cross_pool,  # 如果7天内有记录，设为True，不会重复保存金叉记录
                golden_cross_date=actual_golden_cross_date  # 使用实际的金叉日期（可能是已有记录的日期）
            )
            
            if result and result.get('is_started') or result.get('score', 0) >= 20:
                # 返回结果用于构建DataFrame
                return {
                    'ts_code': ts_code,
                    'trade_date': trade_date,
                    'score': result.get('score', 0),
                    'stage': result.get('stage', ''),
                    'is_started': result.get('is_started', False),
                    'signals': result.get('signals', []),
                    'risks': result.get('risks', [])
                }
            
            return None
            
        except Exception as e:
            logger.error(f"处理有金叉的股票失败 {ts_code}: {e}", exc_info=True)
            return None
    
    def check_conditions(
        self,
        stock_data: Dict,
        trade_date: Optional[str] = None,
        is_in_golden_cross_pool: bool = False,
        golden_cross_date: Optional[str] = None
    ) -> Dict:
        """
        检查股票是否符合条件（核心条件、辅助确认、风险排除）
        
        这是对 StartupFilter.check_conditions 的包装方法
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期（可选）
            is_in_golden_cross_pool: 是否已在金叉候选池中
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Dict: 检查结果
        """
        return self.filter.check_conditions(
            stock_data,
            trade_date,
            is_in_golden_cross_pool,
            golden_cross_date
        )
    
    def check_core_conditions(
        self,
        stock_data: Dict,
        trade_date: Optional[str] = None,
        is_in_golden_cross_pool: bool = False,
        golden_cross_date: Optional[str] = None
    ) -> Optional[Dict]:
        """
        检查核心条件（突破+放量+多头）
        
        这是对 StartupFilter.check_core_conditions 的包装方法
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期（可选）
            is_in_golden_cross_pool: 是否已在金叉候选池中
            golden_cross_date: 金叉日期（如果已在金叉候选池中）
        
        Returns:
            Optional[Dict]: 检查结果
        """
        return self.filter.check_core_conditions(
            stock_data,
            trade_date,
            is_in_golden_cross_pool,
            golden_cross_date
        )
    
    def check_assist_conditions(
        self,
        stock_data: Dict,
        trade_date: Optional[str] = None,
        signals: Optional[List[str]] = None,
        golden_cross_date: Optional[str] = None
    ) -> Optional[Dict]:
        """
        检查辅助确认条件
        
        这是对 StartupFilter.check_assist_conditions 的包装方法
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期（可选）
            signals: 已通过的核心条件信号列表
            golden_cross_date: 金叉日期
        
        Returns:
            Optional[Dict]: 检查结果
        """
        return self.filter.check_assist_conditions(
            stock_data,
            trade_date,
            signals,
            golden_cross_date
        )
    
    def check_risk_conditions(
        self,
        stock_data: Dict,
        trade_date: Optional[str] = None,
        signals: Optional[List[str]] = None,
        assist_count: int = 0,
        golden_cross_date: Optional[str] = None
    ) -> Optional[Dict]:
        """
        检查风险排除条件
        
        这是对 StartupFilter.check_risk_conditions 的包装方法
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期（可选）
            signals: 已通过的信号列表
            assist_count: 辅助条件通过数量
            golden_cross_date: 金叉日期
        
        Returns:
            Optional[Dict]: 检查结果
        """
        return self.filter.check_risk_conditions(
            stock_data,
            trade_date,
            signals,
            assist_count,
            golden_cross_date
        )
    
    def is_just_started(self, stock_data: Dict, trade_date: Optional[str] = None) -> Dict:
        """
        判断股票是否启动（主流程入口）
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期（可选）
        
        Returns:
            Dict: 启动判断结果
        """
        return self.filter.is_just_started(stock_data, trade_date)
    
    def _save_fully_started_record(
        self, 
        stock_data: Dict, 
        trade_date: Optional[str], 
        signals: List[str], 
        assist_count: int, 
        golden_cross_date: Optional[str]
    ) -> Dict:
        """
        保存完全启动记录（所有条件满足）
        
        这是对 StartupFilter._save_fully_started_record 的包装方法
        
        Args:
            stock_data: 股票数据字典
            trade_date: 交易日期
            signals: 通过的信号列表
            assist_count: 辅助条件通过数量
            golden_cross_date: 金叉日期
        
        Returns:
            Dict: 启动结果字典
        """
        return self.filter._save_fully_started_record(
            stock_data,
            trade_date,
            signals,
            assist_count,
            golden_cross_date
        )
