"""
股票启动策略回测服务

PRODUCT_LINE: S  启动龙头产品线核心模块
"""

from typing import Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
from collections import defaultdict
import logging
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.factors.factor_calculator import FactorCalculator
from backend.services.stock.trade_plan_utils import compute_trade_plan

logger = logging.getLogger(__name__)


class StartupBacktestService:
    """股票启动策略回测服务"""
    
    # 交易成本配置
    BUY_COMMISSION_RATE = 0.0003  # 买入手续费：万三
    SELL_COMMISSION_RATE = 0.0003  # 卖出手续费：万三
    STAMP_TAX_RATE = 0.001  # 印花税：千一（仅卖出时收取）
    
    def __init__(self, warehouse_service):
        self.warehouse_service = warehouse_service
    
    def backtest_strategy(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        initial_capital: float = 300000.0,  # 初始资金30万
        capital_per_stock: float = 30000.0,  # 每只股票3万
        max_stocks_per_day: int = 10,  # 每天最多10只
        max_hold_days: int = 5,  # 最多持有5天
        stop_loss: float = -0.10,  # 止损10%
        min_score: int = 60,  # 最低得分
        risk_passed: Optional[bool] = None,  # 是否必须通过风险排除（None表示不检查，与单票诊断逻辑一致）
        force_recalculate: bool = False  # 是否强制重新计算（即使数据库已有数据也重新计算）
    ) -> Dict:
        """
        执行回测策略
        
        Args:
            start_date: 回测开始日期
            end_date: 回测结束日期
            initial_capital: 初始资金
            capital_per_stock: 每只股票分配资金
            max_stocks_per_day: 每天最多买入数量
            max_hold_days: 最大持有天数（交易日）
            stop_loss: 止损比例（负数，如-0.10表示-10%）
            min_score: 最低得分
            risk_passed: 是否必须通过风险排除（None表示不检查，与单票诊断逻辑一致）
            force_recalculate: 是否强制重新计算（即使数据库已有数据也重新计算）
        
        Returns:
            回测结果字典
        """
        session = self.warehouse_service.get_session()
        
        try:
            # 如果没有指定日期，使用默认范围
            if not end_date:
                end_date = datetime.now().date()
            if not start_date:
                start_date = end_date - timedelta(days=365)
            
            logger.info(f"开始回测：{start_date} 至 {end_date}")
            logger.info(f"参数：初始资金={initial_capital}，每只股票={capital_per_stock}，每天最多={max_stocks_per_day}只，最多持有={max_hold_days}天，止损={stop_loss*100}%")
            
            # 1. 获取符合条件的信号
            signals = self._get_signals(session, start_date, end_date, min_score, risk_passed, force_recalculate)
            logger.info(f"找到 {len(signals)} 个符合条件的信号")
            
            if not signals:
                return {
                    'success': False,
                    'message': '没有找到符合条件的信号',
                    'stats': {}
                }
            
            # 2. 执行回测
            trades = []
            positions = {}  # 当前持仓 {ts_code: trade_info}
            daily_cash = initial_capital  # 可用资金
            daily_positions_count = defaultdict(int)  # 每天持仓数量
            
            # 按日期排序信号
            signals_sorted = sorted(signals, key=lambda x: x['trade_date'])
            
            # 获取所有交易日
            trading_dates = self._get_trading_dates(session, start_date, end_date)
            
            # 按交易日处理
            for current_date in trading_dates:
                # 检查持仓，看是否需要卖出
                positions_to_sell = []
                for ts_code, position in list(positions.items()):
                    # 检查是否达到最大持有天数
                    hold_days = self._calculate_trading_days_diff(
                        session, position['buy_date'], current_date
                    )
                    
                    if hold_days >= max_hold_days:
                        positions_to_sell.append((ts_code, 'max_hold_days', current_date))
                        continue
                    
                    # 检查是否触发止损
                    current_price = self._get_price(session, ts_code, current_date, 'close')
                    if current_price and current_price > 0:
                        profit_loss_pct = (current_price - position['buy_price']) / position['buy_price']
                        if profit_loss_pct <= stop_loss:
                            positions_to_sell.append((ts_code, 'stop_loss', current_date))
                            continue
                
                # 执行卖出
                for ts_code, exit_reason, sell_date in positions_to_sell:
                    position = positions.pop(ts_code)
                    trade = self._execute_sell(
                        session, position, sell_date, exit_reason
                    )
                    if trade:
                        trades.append(trade)
                        daily_cash += trade['sell_amount']  # 回收资金
                        logger.debug(f"卖出 {ts_code}: {exit_reason}, 收益率={trade['profit_loss_pct']:.2f}%")
                
                # 检查当天是否有新信号可以买入
                # 注意：信号日期是入选日期，买入日期应该是信号日期的下一个交易日
                day_signals = [s for s in signals_sorted if s['trade_date'] == current_date]
                
                if day_signals:
                    # 获取下一个交易日作为买入日期
                    next_trading_day = self._get_next_trading_day(session, current_date)
                    if not next_trading_day:
                        continue
                    
                    # 检查当天持仓数量（买入后不能超过限制）
                    current_positions_count = len(positions)
                    available_slots = max_stocks_per_day - current_positions_count
                    
                    if available_slots > 0:
                        # 按得分排序，优先买入得分高的
                        day_signals_sorted = sorted(day_signals, key=lambda x: x['score'], reverse=True)
                        
                        for signal in day_signals_sorted[:available_slots]:
                            # 检查资金是否足够
                            if daily_cash < capital_per_stock:
                                break
                            
                            # 检查是否已经持有该股票
                            if signal['ts_code'] in positions:
                                continue
                            
                            # 执行买入（使用下一个交易日的开盘价）
                            trade = self._execute_buy(
                                session, signal, next_trading_day, capital_per_stock
                            )
                            
                            if trade:
                                positions[signal['ts_code']] = trade
                                trades.append(trade)
                                daily_cash -= trade['actual_buy_amount']  # 扣除资金
                                logger.debug(f"买入 {signal['ts_code']}: 价格={trade['buy_price']:.2f}, 数量={trade['buy_quantity']}")
            
            # 3. 处理剩余持仓（按最后一天价格卖出）
            final_date = trading_dates[-1] if trading_dates else end_date
            for ts_code, position in list(positions.items()):
                trade = self._execute_sell(
                    session, position, final_date, 'end_of_backtest'
                )
                if trade:
                    trades.append(trade)
                    daily_cash += trade['sell_amount']
            
            # 4. 计算统计信息
            stats = self._calculate_statistics(trades, initial_capital, daily_cash)

            # 5. 计算按因子分组的统计（例如 20 日动量分组）
            try:
                factor_stats = self._calculate_factor_buckets(trades)
                if factor_stats:
                    stats["factor_buckets"] = factor_stats
            except Exception as e:
                logger.warning("计算因子分组统计失败（不影响回测结果）: %s", e, exc_info=True)
            
            logger.info(f"回测完成：总交易数={len(trades)}，最终资金={daily_cash:.2f}，总收益率={stats['total_return_pct']:.2f}%")
            
            return {
                'success': True,
                'trades': trades,
                'stats': stats,
                'params': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'initial_capital': initial_capital,
                    'capital_per_stock': capital_per_stock,
                    'max_stocks_per_day': max_stocks_per_day,
                    'max_hold_days': max_hold_days,
                    'stop_loss': stop_loss,
                    'min_score': min_score,
                    'risk_passed': risk_passed
                }
            }
            
        finally:
            session.close()

    def _calculate_factor_buckets(self, trades: List[Dict]) -> Dict:
        """
        按因子分组统计表现（当前仅实现 mom_20d 分组）。

        逻辑：
        - 对每笔交易，在买入日计算 mom_20d（20 日动量）
        - 分组：low(<0)、mid(0~20)、high(>=20)
        - 统计：每组的笔数、平均收益率、胜率
        """
        if not trades:
            return {}

        # 先为每笔交易计算 mom_20d（在买入日的因子）
        calc = FactorCalculator(self.warehouse_service)
        for t in trades:
            ts_code = t.get("ts_code")
            buy_date = t.get("buy_date")
            if not ts_code or not buy_date:
                continue
            try:
                factors = calc.calculate_factors([ts_code], buy_date)
                f = factors.get(ts_code)
                if f and f.get("mom_20d") is not None:
                    t["mom_20d"] = f["mom_20d"]
            except Exception as e:
                logger.debug("为 %s 计算 mom_20d 因子失败（买入日=%s）: %s", ts_code, buy_date, e)

        # 分桶统计
        buckets = {
            "mom_20d": {
                "low": {"label": "<0%", "trades": [], "count": 0},
                "mid": {"label": "0~20%", "trades": [], "count": 0},
                "high": {"label": ">=20%", "trades": [], "count": 0},
            }
        }

        for t in trades:
            m20 = t.get("mom_20d")
            ret = t.get("profit_loss_pct")
            if m20 is None or ret is None:
                continue
            try:
                v = float(m20)
                r = float(ret)
            except (TypeError, ValueError):
                continue

            if v < 0:
                bucket = buckets["mom_20d"]["low"]
            elif v < 20:
                bucket = buckets["mom_20d"]["mid"]
            else:
                bucket = buckets["mom_20d"]["high"]

            bucket["trades"].append(r)

        # 汇总每个桶的表现
        for factor_name, factor_buckets in buckets.items():
            for key, info in factor_buckets.items():
                vals = info["trades"]
                count = len(vals)
                info["count"] = count
                if count > 0:
                    avg_ret = sum(vals) / count
                    win_rate = len([v for v in vals if v > 0]) / count * 100
                else:
                    avg_ret = 0.0
                    win_rate = 0.0
                info["avg_return_pct"] = round(avg_ret, 2)
                info["win_rate"] = round(win_rate, 2)
                # 去掉明细 trades，避免响应过大
                info.pop("trades", None)

        return buckets
    
    def _get_signals(
        self,
        session: Session,
        start_date: date,
        end_date: date,
        min_score: int,
        risk_passed: Optional[bool],
        force_recalculate: bool = False
    ) -> List[Dict]:
        """
        获取符合条件的信号（回测专用）
        
        业务逻辑：直接使用入选日期（score>=60的日期）作为买入信号点，不使用金叉日期分组
        - 买入日期 = 入选日期的下一个交易日的开盘价
        
        Args:
            force_recalculate: 是否强制重新计算（即使数据库已有数据也重新计算）
        
        如果 force_recalculate=False：
            优先使用数据库中的记录，如果数据库中没有记录，则实时计算
        如果 force_recalculate=True：
            忽略数据库中的记录，强制重新计算所有信号
        """
        from data_warehouse.models.startup_candidate import FactStockStartupCandidate
        from data_warehouse.models.generated_models import DimTradeCalendar, FactDailyPriceQfq
        from data_warehouse.models.orm_classes import DimStock
        from backend.services.stock.stock_startup_filter import StockStartupFilter
        
        # 1. 先从数据库查询已有记录（如果不需要强制重新计算）
        existing_signals = set()  # {(ts_code, trade_date)} 用于去重
        signals = []
        
        if not force_recalculate:
            # 查询 score >= min_score 的记录（直接使用入选日期，不基于金叉日期）
            query = session.query(FactStockStartupCandidate).filter(
                FactStockStartupCandidate.trade_date >= start_date,
                FactStockStartupCandidate.trade_date <= end_date,
                FactStockStartupCandidate.score >= min_score
            )
            
            # 如果指定了 risk_passed，则添加该条件
            if risk_passed is not None:
                query = query.filter(FactStockStartupCandidate.risk_passed == risk_passed)
            
            query = query.order_by(
                FactStockStartupCandidate.trade_date.asc(),
                FactStockStartupCandidate.ts_code.asc(),
                FactStockStartupCandidate.score.desc()
            )
            
            db_results = query.all()
            
            # 直接使用入选日期作为信号点（每个入选日期都是一个独立的买入信号）
            for candidate in db_results:
                signal_key = (candidate.ts_code, candidate.trade_date)
                
                # 去重：同一股票同一日期只保留一条记录
                if signal_key not in existing_signals:
                    signal = {
                        'ts_code': candidate.ts_code,
                        'trade_date': candidate.trade_date,  # 入选日期（买入信号点）
                        'score': candidate.score,
                        'stage': candidate.stage,
                        'entry_price': float(candidate.latest_price) if candidate.latest_price else None
                    }
                    signals.append(signal)
                    existing_signals.add(signal_key)
            
            logger.info(f"从数据库找到 {len(signals)} 个符合条件的信号（基于入选日期）")
        else:
            logger.info("强制重新计算模式：忽略数据库中的记录，将重新计算所有信号")
        
        # 2. 获取所有交易日，检查是否有缺失的信号（实时计算）
        trading_dates_query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date >= start_date,
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        )
        
        trading_dates = [row[0] for row in trading_dates_query.all()]
        
        # 3. 对每个交易日，检查是否有缺失的信号（实时计算）
        if force_recalculate or len(existing_signals) < len(trading_dates) * 10:  # 如果信号数量明显不足，进行实时计算
            logger.info(f"开始实时计算缺失的信号（交易日数: {len(trading_dates)}）")
            
            filter_service = StockStartupFilter(warehouse_service=self.warehouse_service)
            realtime_count = 0
            
            for trade_date in trading_dates:
                # 跳过已有信号的日期（如果不需要强制重新计算）
                if not force_recalculate:
                    # 检查该日期是否已有足够的信号（简单判断：如果该日期已有信号，跳过实时计算）
                    date_signals = [s for s in signals if s['trade_date'] == trade_date]
                    if len(date_signals) > 0:
                        continue
                
                # 获取该交易日有价格数据的股票
                stocks_with_data = session.query(
                    func.distinct(FactDailyPriceQfq.ts_code)
                ).filter(
                    FactDailyPriceQfq.trade_date == trade_date
                ).all()
                
                for (ts_code,) in stocks_with_data:
                    # 检查是否已有该日期的信号
                    signal_key = (ts_code, trade_date)
                    if signal_key in existing_signals:
                        continue
                    
                    # 实时计算该股票在该日期的得分
                    try:
                        stock_data = filter_service._get_stock_indicators(
                            ts_code,
                            trade_date.strftime('%Y-%m-%d'),
                            force_realtime=False
                        )
                        
                        if not stock_data:
                            continue
                        
                        # 检查是否有金叉（基础条件）
                        from backend.services.stock.startup.conditions import BasicConditionChecker
                        basic_checker = BasicConditionChecker()
                        basic_checks = basic_checker.check(stock_data, skip_golden_cross=False)
                        
                        if not basic_checks['passed']:
                            continue
                        
                        # 检查核心条件（与单票诊断逻辑一致）
                        from backend.services.stock.startup.conditions import CoreConditionChecker
                        core_checker = CoreConditionChecker()
                        core_checks = core_checker.check(stock_data)
                        
                        # 如果3个核心条件全部通过，得分60分（与单票诊断一致）
                        if core_checks['passed'] and len(core_checks['passed_signals']) == 3:
                            score = 60
                            stage = 'confirmed'
                        else:
                            # 核心条件不满足，跳过
                            continue
                        
                        # 检查是否符合回测条件（只检查 score，不强制要求 risk_passed）
                        if score >= min_score:
                            # 获取入选日收盘价
                            entry_price_query = session.query(FactDailyPriceQfq.close).filter(
                                FactDailyPriceQfq.ts_code == ts_code,
                                FactDailyPriceQfq.trade_date == trade_date
                            ).first()
                            
                            entry_price = float(entry_price_query[0]) if entry_price_query and entry_price_query[0] else None
                            
                            # 创建新信号
                            signals.append({
                                'ts_code': ts_code,
                                'trade_date': trade_date,  # 入选日期（买入信号点）
                                'score': score,
                                'stage': stage,
                                'entry_price': entry_price
                            })
                            
                            existing_signals.add(signal_key)
                            realtime_count += 1
                            
                            if realtime_count % 10 == 0:
                                logger.debug(f"已实时计算 {realtime_count} 个信号...")
                    
                    except Exception as e:
                        logger.warning(f"实时计算信号失败 {ts_code} {trade_date}: {e}")
                        continue
            
            if realtime_count > 0:
                logger.info(f"实时计算了 {realtime_count} 个缺失的信号")
        
        # 按交易日期和股票代码排序
        signals.sort(key=lambda x: (
            x['trade_date'],
            x['ts_code'],
            -x['score']
        ))
        
        logger.info(f"信号处理完成：共 {len(signals)} 个信号（基于入选日期，每个入选日期都是一个独立的买入信号）")
        
        return signals
    
    def _get_trading_dates(self, session: Session, start_date: date, end_date: date) -> List[date]:
        """获取交易日列表"""
        from data_warehouse.models.generated_models import DimTradeCalendar
        
        query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date >= start_date,
            DimTradeCalendar.trade_date <= end_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        )
        
        results = query.all()
        return [row[0] for row in results]
    
    def _get_next_trading_day(self, session: Session, current_date: date) -> Optional[date]:
        """获取下一个交易日"""
        from data_warehouse.models.generated_models import DimTradeCalendar
        
        query = session.query(DimTradeCalendar.trade_date).filter(
            DimTradeCalendar.trade_date > current_date,
            DimTradeCalendar.is_open == True
        ).order_by(
            DimTradeCalendar.trade_date.asc()
        ).limit(1)
        
        result = query.first()
        return result[0] if result else None
    
    def _calculate_trading_days_diff(self, session: Session, start_date: date, end_date: date) -> int:
        """计算两个日期之间的交易日差"""
        trading_dates = self._get_trading_dates(session, start_date, end_date)
        if start_date in trading_dates and end_date in trading_dates:
            return trading_dates.index(end_date) - trading_dates.index(start_date)
        return (end_date - start_date).days
    
    def _get_price(self, session: Session, ts_code: str, trade_date: date, price_type: str = 'close') -> Optional[float]:
        """获取价格数据"""
        from data_warehouse.models.generated_models import FactDailyPriceQfq
        
        query = session.query(FactDailyPriceQfq).filter(
            FactDailyPriceQfq.ts_code == ts_code,
            FactDailyPriceQfq.trade_date == trade_date
        ).first()
        
        if not query:
            return None
        
        if price_type == 'open':
            return float(query.open) if query.open else None
        elif price_type == 'close':
            return float(query.close) if query.close else None
        elif price_type == 'high':
            return float(query.high) if query.high else None
        elif price_type == 'low':
            return float(query.low) if query.low else None
        
        return None
    
    def _execute_buy(
        self,
        session: Session,
        signal: Dict,
        buy_date: date,
        capital_per_stock: float
    ) -> Optional[Dict]:
        """执行买入"""
        # 获取买入价格（开盘价）
        buy_price = self._get_price(session, signal['ts_code'], buy_date, 'open')
        
        if not buy_price or buy_price <= 0:
            logger.warning(f"{signal['ts_code']} {buy_date} 无开盘价数据")
            return None
        
        # 计算买入数量（按100股取整）
        buy_quantity = int(capital_per_stock / buy_price / 100) * 100
        if buy_quantity < 100:
            buy_quantity = 100  # 最少100股
        
        # 实际买入金额
        gross_buy_amount = buy_quantity * buy_price
        
        # 买入手续费
        buy_commission = gross_buy_amount * self.BUY_COMMISSION_RATE
        
        # 实际买入成本（包含手续费）
        actual_buy_amount = gross_buy_amount + buy_commission

        # 基于买入价的简化交易计划（不额外查高点数据，仅用默认比例）
        trade_plan = compute_trade_plan(buy_price, stock_data=None)
        
        return {
            'ts_code': signal['ts_code'],
            'signal_date': signal['trade_date'],
            'buy_date': buy_date,
            'buy_price': buy_price,
            'buy_quantity': buy_quantity,
            'gross_buy_amount': gross_buy_amount,
            'buy_commission': buy_commission,
            'actual_buy_amount': actual_buy_amount,
            'stop_loss_price': trade_plan.get('stop_loss_price'),
            'take_profit_price': trade_plan.get('take_profit_price'),
            'score': signal['score'],
            'stage': signal['stage']
        }
    
    def _execute_sell(
        self,
        session: Session,
        position: Dict,
        sell_date: date,
        exit_reason: str
    ) -> Optional[Dict]:
        """执行卖出"""
        # 获取卖出价格（收盘价）
        sell_price = self._get_price(session, position['ts_code'], sell_date, 'close')
        
        if not sell_price or sell_price <= 0:
            logger.warning(f"{position['ts_code']} {sell_date} 无收盘价数据")
            return None
        
        buy_quantity = position['buy_quantity']
        buy_price = position['buy_price']
        
        # 卖出金额
        gross_sell_amount = buy_quantity * sell_price
        
        # 卖出手续费
        sell_commission = gross_sell_amount * self.SELL_COMMISSION_RATE
        
        # 印花税（仅卖出时收取）
        stamp_tax = gross_sell_amount * self.STAMP_TAX_RATE
        
        # 实际卖出金额（扣除手续费和印花税）
        sell_amount = gross_sell_amount - sell_commission - stamp_tax
        
        # 计算盈亏
        profit_loss = sell_amount - position['actual_buy_amount']
        profit_loss_pct = (profit_loss / position['actual_buy_amount']) * 100
        
        # 计算持有天数
        hold_days = self._calculate_trading_days_diff(
            session, position['buy_date'], sell_date
        )
        
        return {
            **position,
            'sell_date': sell_date,
            'sell_price': sell_price,
            'gross_sell_amount': gross_sell_amount,
            'sell_commission': sell_commission,
            'stamp_tax': stamp_tax,
            'sell_amount': sell_amount,
            'profit_loss': profit_loss,
            'profit_loss_pct': profit_loss_pct,
            'hold_days': hold_days,
            'exit_reason': exit_reason
        }
    
    def _calculate_statistics(
        self,
        trades: List[Dict],
        initial_capital: float,
        final_cash: float
    ) -> Dict:
        """计算统计信息（含按计划交易 vs 实际结果的对比）"""
        if not trades:
            return {
                'total_trades': 0,
                'total_return_pct': 0,
                'final_capital': initial_capital
            }
        
        # 基础统计
        total_trades = len(trades)
        profitable_trades = [t for t in trades if t.get('profit_loss_pct', 0) > 0]
        losing_trades = [t for t in trades if t.get('profit_loss_pct', 0) < 0]
        
        # 收益率统计
        total_return = final_cash - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        # 胜率
        win_rate = (len(profitable_trades) / total_trades * 100) if total_trades > 0 else 0
        
        # 平均收益率
        avg_return_pct = sum(t.get('profit_loss_pct', 0) for t in trades) / total_trades if total_trades > 0 else 0
        
        # 平均盈利和平均亏损
        avg_profit = sum(t.get('profit_loss_pct', 0) for t in profitable_trades) / len(profitable_trades) if profitable_trades else 0
        avg_loss = sum(t.get('profit_loss_pct', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        # 盈亏比
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else 0
        
        # 最大单笔盈利和亏损
        max_profit = max((t.get('profit_loss_pct', 0) for t in trades), default=0)
        max_loss = min((t.get('profit_loss_pct', 0) for t in trades), default=0)
        
        # 平均持有天数
        avg_hold_days = sum(t.get('hold_days', 0) for t in trades) / total_trades if total_trades > 0 else 0
        
        # 按退出原因统计
        exit_reasons = defaultdict(int)
        exit_reasons_return = defaultdict(list)
        for trade in trades:
            reason = trade.get('exit_reason', 'unknown')
            exit_reasons[reason] += 1
            exit_reasons_return[reason].append(trade.get('profit_loss_pct', 0))
        
        exit_reasons_stats: Dict[str, Dict] = {}
        for reason, count in exit_reasons.items():
            returns = exit_reasons_return[reason]
            exit_reasons_stats[reason] = {
                'count': count,
                'avg_return_pct': sum(returns) / len(returns) if returns else 0,
                'win_rate': (len([r for r in returns if r > 0]) / len(returns) * 100) if returns else 0
            }

        # 按统一交易计划（止损/目标价）与实际结果做简单对比
        plan_vs_actual = self._calculate_plan_vs_actual(trades)

        return {
            'total_trades': total_trades,
            'profitable_trades': len(profitable_trades),
            'losing_trades': len(losing_trades),
            'win_rate': round(win_rate, 2),
            'total_return': round(total_return, 2),
            'total_return_pct': round(total_return_pct, 2),
            'final_capital': round(final_cash, 2),
            'avg_return_pct': round(avg_return_pct, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'max_profit': round(max_profit, 2),
            'max_loss': round(max_loss, 2),
            'avg_hold_days': round(avg_hold_days, 2),
            'exit_reasons': exit_reasons_stats,
            'plan_vs_actual': plan_vs_actual,
        }

    def _calculate_plan_vs_actual(self, trades: List[Dict]) -> Dict:
        """
        对比「统一交易计划」与实际卖出结果的简单统计。

        设计思路（不做复杂路径重建，只比较最终卖出结果 vs 计划价位）：
        - 使用买入价 + 计划止损价 + 计划目标价，计算：
          - expected_return_pct: 计划第一目标收益
          - stop_loss_pct: 计划止损跌幅
        - 将每笔实际收益 profit_loss_pct 归类到 4 个桶：
          1) target_or_above: 实际 >= 计划目标收益（按计划拿满或超额）
          2) positive_but_below_target: 0 < 实际 < 计划目标收益（中途就走，没拿满）
          3) loss_better_than_stop: 计划止损 < 实际 <= 0（亏损但好于计划止损）
          4) worse_than_plan_stop: 实际 <= 计划止损（比计划止损还差）
        """
        if not trades:
            return {}

        buckets = {
            "target_or_above": [],
            "positive_but_below_target": [],
            "loss_better_than_stop": [],
            "worse_than_plan_stop": [],
        }
        expected_returns: List[float] = []
        stop_losses: List[float] = []

        for t in trades:
            buy_price = t.get("buy_price")
            stop_loss_price = t.get("stop_loss_price")
            take_profit_price = t.get("take_profit_price")
            actual_ret = t.get("profit_loss_pct")

            # 计划价或实际收益缺失时跳过
            if (
                buy_price is None
                or stop_loss_price is None
                or take_profit_price is None
                or actual_ret is None
            ):
                continue

            try:
                buy = float(buy_price)
                stop = float(stop_loss_price)
                target = float(take_profit_price)
                actual = float(actual_ret)
            except (TypeError, ValueError):
                continue

            if buy <= 0:
                continue

            expected_ret = (target / buy - 1.0) * 100.0
            stop_ret = (stop / buy - 1.0) * 100.0

            expected_returns.append(expected_ret)
            stop_losses.append(stop_ret)

            if actual >= expected_ret:
                buckets["target_or_above"].append(actual)
            elif actual > 0:
                buckets["positive_but_below_target"].append(actual)
            elif actual > stop_ret:
                buckets["loss_better_than_stop"].append(actual)
            else:
                buckets["worse_than_plan_stop"].append(actual)

        total_with_plan = sum(len(v) for v in buckets.values())
        if total_with_plan == 0:
            return {}

        def _summary(vals: List[float]) -> Dict:
            count = len(vals)
            if count == 0:
                return {"count": 0, "ratio": 0.0, "avg_return_pct": 0.0}
            avg_ret = sum(vals) / count
            return {
                "count": count,
                "ratio": round(count / total_with_plan * 100.0, 2),
                "avg_return_pct": round(avg_ret, 2),
            }

        return {
            "total_with_plan": total_with_plan,
            "expected_return_pct_avg": round(sum(expected_returns) / len(expected_returns), 2) if expected_returns else 0.0,
            "stop_loss_pct_avg": round(sum(stop_losses) / len(stop_losses), 2) if stop_losses else 0.0,
            "target_or_above": _summary(buckets["target_or_above"]),
            "positive_but_below_target": _summary(buckets["positive_but_below_target"]),
            "loss_better_than_stop": _summary(buckets["loss_better_than_stop"]),
            "worse_than_plan_stop": _summary(buckets["worse_than_plan_stop"]),
        }

