"""
涨停缩量回测服务
对涨停缩量策略进行历史回测，计算收益率和统计指标
"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models.generated_models import FactDailyPriceQfq, DimTradeCalendar
from data_warehouse.models.limit_up_volume_shrink import FactLimitUpVolumeShrink
from data_warehouse.models.limit_up_volume_shrink_backtest import FactLimitUpVolumeShrinkBacktest
from data_warehouse.models.orm_classes import DimStock
from data_warehouse.models.tonghuashun_limit_up import FactTonghuashunLimitUp

logger = logging.getLogger(__name__)


class LimitUpVolumeShrinkBacktestService:
    """涨停缩量回测服务"""
    
    # 交易成本参数（基于A股实际交易成本）
    BUY_COMMISSION_RATE = 0.0003  # 买入手续费：0.03%
    SELL_COMMISSION_RATE = 0.0003  # 卖出手续费：0.03%
    STAMP_TAX_RATE = 0.001  # 印花税：0.1%（仅卖出时收取）
    
    def __init__(self):
        self.warehouse = WarehouseService()
    
    def backtest_strategy(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        profit_target: float = 0.20,
        stop_loss: float = -0.10,
        max_hold_days: int = 5,
        sell_strategy: str = 'profit_stop',  # 'profit_stop': 止盈止损策略, 'ma5_loss': 破跌5日线或亏损5%策略, 'ma5_loss_5pct': 破跌5日线或亏损5%策略, 'ma5_rising': 上涨过程中不破5日线不卖或亏损5%策略
        strategy_type: str = 'mainboard_limit_up'  # 'mainboard_limit_up': 主板涨停缩量, 'cyb_rise_shrink': 创业板科创板涨幅缩量
    ) -> Dict:
        """
        执行回测策略
        
        Args:
            start_date: 回测开始日期，如果为None则使用1年前
            end_date: 回测结束日期，如果为None则使用今天
            profit_target: 目标收益率（如0.20表示20%）
            stop_loss: 止损比例（如-0.10表示-10%）
            max_hold_days: 最大持有天数
        
        Returns:
            Dict: 回测结果，包含统计指标和交易明细
        """
        session = self.warehouse.get_session()
        try:
            # 确定回测日期范围
            if end_date is None:
                end_date = date.today()
            
            if start_date is None:
                # 默认回测最近1年
                start_date = end_date - timedelta(days=365)
            
            logger.info(f"开始回测：{start_date} 至 {end_date}, "
                       f"卖出策略={sell_strategy}, 止盈={profit_target*100}%, 止损={stop_loss*100}%, 最大持有={max_hold_days}天")
            
            # 1. 获取信号数据（涨停缩量股票）
            logger.info(f"步骤1: 开始获取信号数据（策略类型：{strategy_type}）...")
            signals = self._get_signals(session, start_date, end_date, strategy_type)
            logger.info(f"✅ 步骤1完成：找到 {len(signals)} 个信号")
            
            # 1.1. 过滤ST股票和退市股票
            logger.info("步骤1.1: 开始过滤ST股票和退市股票...")
            signals = self._filter_st_and_delisted_stocks(session, signals, start_date, end_date)
            logger.info(f"✅ 步骤1.1完成：过滤后剩余 {len(signals)} 个信号")
            
            if not signals:
                return {
                    'success': True,
                    'backtest_period': {
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat()
                    },
                    'parameters': {
                        'profit_target': profit_target,
                        'stop_loss': stop_loss,
                        'max_hold_days': max_hold_days,
                        'sell_strategy': sell_strategy
                    },
                    'statistics': {},
                    'trades': []
                }
            
            # 2. 按信号日期排序，确保按时间顺序处理
            signals = sorted(signals, key=lambda x: x['signal_date'])
            logger.info(f"信号已按日期排序，最早信号: {signals[0]['signal_date'] if signals else 'N/A'}, 最晚信号: {signals[-1]['signal_date'] if signals else 'N/A'}")
            
            # 3. 批量获取价格数据
            logger.info("步骤2: 开始获取价格数据...")
            ts_codes = list(set([s['ts_code'] for s in signals]))
            logger.info(f"需要获取 {len(ts_codes)} 只股票的价格数据")
            price_data = self._get_price_data(session, ts_codes, start_date, end_date + timedelta(days=max_hold_days + 10))
            logger.info(f"✅ 步骤2完成：获取到 {len(price_data)} 只股票的价格数据")
            
            # 4. 资金管理：根据策略类型设置不同参数
            initial_capital = 300000.0  # 初始本金30万
            if strategy_type == 'cyb_rise_shrink':
                # 创业板策略：每天最多买5只，每只6万
                max_stocks_per_day = 5  # 每天最多买5只
                capital_per_stock = 60000.0  # 每只股票买6万
            else:
                # 主板策略：每天最多买10只，每只3万
                max_stocks_per_day = 10  # 每天最多买10只
                capital_per_stock = 30000.0  # 每只股票买3万
            
            # 5. 按时间顺序模拟交易，并应用资金管理
            logger.info("步骤3: 开始模拟交易（按时间顺序，应用资金管理）...")
            trades = []
            processed_count = 0
            
            # 记录每日买入的股票数量
            daily_buy_count = {}  # key: 买入日期, value: 当日已买入数量
            # 记录持仓（买入日期 -> 持仓列表）
            holdings = {}  # key: 买入日期, value: List[Dict] 持仓信息
            # 当前可用资金
            available_capital = initial_capital
            # 总资产（可用资金 + 持仓市值）
            total_assets = initial_capital
            
            # 最大回撤计算相关变量（基于实际资金管理）
            max_total_assets = initial_capital  # 历史最高总资产
            max_drawdown = 0.0  # 最大回撤
            daily_assets_history = []  # 记录每日资产变化（用于计算回撤）
            
            # 连续亏损统计（仅用于统计，不再用于暂停交易）
            consecutive_losses = 0  # 连续亏损次数
            
            # 风险控制统计
            risk_control_stats = {
                'consecutive_losses_triggered': False,  # 是否触发连续亏损保护（仅用于统计）
                'drawdown_reduction_triggered': False,  # 是否触发回撤降仓
                'monthly_loss_pause_triggered': False,  # 是否触发月度亏损暂停（仅用于统计）
                'reduced_position_days': 0  # 降仓交易的天数
            }
            
            # 记录每月盈亏（用于月度亏损检查）
            monthly_pnl = {}  # key: 'YYYY-MM', value: 累计盈亏金额
            
            # 统计信息
            skipped_no_trade_result = 0  # 模拟交易返回None的数量
            skipped_daily_limit = 0  # 因每日上限而跳过的数量
            skipped_no_capital = 0  # 因资金不足而跳过的数量
            successful_trades = 0  # 成功交易的次数
            
            for i, signal in enumerate(signals):
                if (i + 1) % 50 == 0:
                    logger.info(f"  处理进度: {i + 1}/{len(signals)}，已成功交易: {successful_trades}，已跳过: {skipped_no_trade_result + skipped_daily_limit + skipped_no_capital}")
                
                # 模拟交易
                trade_result = self._simulate_trade(
                    signal,
                    price_data,
                    profit_target,
                    stop_loss,
                    max_hold_days,
                    session,
                    sell_strategy,
                    strategy_type
                )
                
                # 记录交易结果为None的情况（用于调试）
                if not trade_result:
                    skipped_no_trade_result += 1
                    if skipped_no_trade_result <= 10:  # 只记录前10个，避免日志过多
                        logger.debug(f"信号 {signal['ts_code']}（信号日期: {signal.get('signal_date')}）模拟交易返回None，可能原因：无法找到买入日期/没有价格数据/买入价格无效/买入价低于涨停价90%/停牌")
                
                if trade_result:
                    # 获取买入日期
                    buy_date_str = trade_result.get('buy_date')
                    if buy_date_str:
                        buy_date = datetime.strptime(buy_date_str, '%Y-%m-%d').date() if isinstance(buy_date_str, str) else buy_date_str
                        
                        # 风险控制检查1：连续亏损保护（仅用于统计，不再暂停交易）
                        if consecutive_losses >= 3:
                            if not risk_control_stats['consecutive_losses_triggered']:
                                risk_control_stats['consecutive_losses_triggered'] = True
                                logger.info(f"⚠️ 连续亏损{consecutive_losses}次（仅记录，不暂停交易）")
                        
                        # 风险控制检查2：总回撤超过15%后降低仓位
                        current_drawdown = (max_total_assets - total_assets) / max_total_assets if max_total_assets > 0 else 0
                        if current_drawdown >= 0.15 and not risk_control_stats['drawdown_reduction_triggered']:
                            risk_control_stats['drawdown_reduction_triggered'] = True
                            logger.warning(f"⚠️ 风险控制触发：总回撤{current_drawdown*100:.2f}%超过15%，降低仓位（每只股票买入金额减半）")
                        
                        # 风险控制检查3：单月亏损超过10%（仅用于统计，不再暂停交易）
                        signal_date = signal.get('signal_date')
                        if signal_date:
                            if isinstance(signal_date, str):
                                signal_date = datetime.strptime(signal_date, '%Y-%m-%d').date()
                            month_key = signal_date.strftime('%Y-%m')
                            
                            if month_key not in monthly_pnl:
                                monthly_pnl[month_key] = 0.0
                            
                            # 计算当月累计盈亏（基于已完成的交易）
                            monthly_loss_pct = abs(monthly_pnl[month_key]) / initial_capital if initial_capital > 0 else 0
                            if monthly_loss_pct >= 0.10 and not risk_control_stats['monthly_loss_pause_triggered']:
                                risk_control_stats['monthly_loss_pause_triggered'] = True
                                logger.info(f"⚠️ {month_key}月亏损{monthly_loss_pct*100:.2f}%超过10%（仅记录，不暂停交易）")
                        
                        # 检查当日是否还能买入（每天最多10只）
                        if buy_date not in daily_buy_count:
                            daily_buy_count[buy_date] = 0
                        
                        # 如果回撤超过15%，降低每日买入上限（从10只降到5只）
                        effective_max_stocks = max_stocks_per_day
                        if risk_control_stats['drawdown_reduction_triggered']:
                            effective_max_stocks = max_stocks_per_day // 2  # 减半
                            risk_control_stats['reduced_position_days'] += 1
                        
                        if daily_buy_count[buy_date] >= effective_max_stocks:
                            logger.debug(f"跳过信号 {signal['ts_code']}（{buy_date}）：当日已买入 {daily_buy_count[buy_date]} 只股票，达到上限（降仓后: {effective_max_stocks}只）")
                            processed_count += 1
                            continue
                        
                        # 检查可用资金是否足够
                        # 如果回撤超过15%，降低每只股票的买入金额（从3万降到1.5万）
                        effective_capital_per_stock = capital_per_stock
                        if risk_control_stats['drawdown_reduction_triggered']:
                            effective_capital_per_stock = capital_per_stock // 2  # 减半
                        
                        if available_capital < effective_capital_per_stock:
                            skipped_no_capital += 1
                            if skipped_no_capital <= 10:  # 只记录前10个
                                logger.debug(f"跳过信号 {signal['ts_code']}（{buy_date}）：可用资金不足（当前: {available_capital:.2f}, 需要: {effective_capital_per_stock:.2f}）")
                            processed_count += 1
                            continue
                        
                        # 计算买入金额和数量
                        buy_price = trade_result.get('buy_price', 0)
                        if buy_price > 0:
                            # 买入金额（如果回撤超过15%，则减半）
                            buy_amount = effective_capital_per_stock
                            # 计算买入数量（股数，按100股取整）
                            buy_quantity = int(buy_amount / buy_price / 100) * 100  # 按100股取整
                            if buy_quantity < 100:
                                buy_quantity = 100  # 最少100股
                            
                            # 实际买入金额（考虑取整）
                            gross_buy_amount = buy_quantity * buy_price
                            # 买入手续费
                            buy_commission = gross_buy_amount * self.BUY_COMMISSION_RATE
                            # 实际买入成本（包含手续费）
                            actual_buy_amount = gross_buy_amount + buy_commission
                            
                            # 计算卖出金额和盈亏
                            sell_price = trade_result.get('sell_price', 0)
                            gross_sell_amount = buy_quantity * sell_price if sell_price > 0 else 0
                            # 卖出手续费
                            sell_commission = gross_sell_amount * self.SELL_COMMISSION_RATE if gross_sell_amount > 0 else 0
                            # 印花税（仅卖出时收取）
                            stamp_tax = gross_sell_amount * self.STAMP_TAX_RATE if gross_sell_amount > 0 else 0
                            # 实际卖出金额（扣除手续费和印花税）
                            sell_amount = gross_sell_amount - sell_commission - stamp_tax if gross_sell_amount > 0 else 0
                            
                            # 计算盈亏（使用扣除交易成本后的实际金额）
                            profit_loss = sell_amount - actual_buy_amount
                            profit_loss_pct = (profit_loss / actual_buy_amount * 100) if actual_buy_amount > 0 else 0
                            
                            # 计算总交易成本（用于统计）
                            total_trading_cost = buy_commission + sell_commission + stamp_tax
                            
                            # 更新交易结果，添加资金管理相关字段
                            trade_result['buy_amount'] = actual_buy_amount  # 实际买入成本（含手续费）
                            trade_result['gross_buy_amount'] = gross_buy_amount  # 买入金额（不含手续费）
                            trade_result['buy_commission'] = buy_commission  # 买入手续费
                            trade_result['buy_quantity'] = buy_quantity
                            trade_result['sell_amount'] = sell_amount  # 实际卖出金额（扣除手续费和印花税）
                            trade_result['gross_sell_amount'] = gross_sell_amount  # 卖出金额（不含手续费和印花税）
                            trade_result['sell_commission'] = sell_commission  # 卖出手续费
                            trade_result['stamp_tax'] = stamp_tax  # 印花税
                            trade_result['total_trading_cost'] = total_trading_cost  # 总交易成本
                            trade_result['profit_loss'] = profit_loss
                            trade_result['profit_loss_pct'] = profit_loss_pct
                            
                            # 更新可用资金和持仓
                            available_capital -= actual_buy_amount
                            daily_buy_count[buy_date] += 1
                            
                            # 记录持仓（买入时）
                            if buy_date not in holdings:
                                holdings[buy_date] = []
                            holdings[buy_date].append({
                                'ts_code': trade_result['ts_code'],
                                'buy_price': buy_price,
                                'buy_quantity': buy_quantity,
                                'buy_amount': actual_buy_amount,
                                'buy_date': buy_date
                            })
                            
                            # 卖出时，更新可用资金
                            sell_date_str = trade_result.get('sell_date')
                            if sell_date_str:
                                sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date() if isinstance(sell_date_str, str) else sell_date_str
                                available_capital += sell_amount
                                
                                # 从持仓中移除
                                if buy_date in holdings:
                                    holdings[buy_date] = [h for h in holdings[buy_date] if h['ts_code'] != trade_result['ts_code']]
                            
                            # 计算当前总资产（用于最大回撤计算）
                            # 计算当前持仓市值（使用当前价格）
                            current_holdings_value = 0.0
                            # 使用卖出日期（如果已卖出）或买入日期作为当前日期
                            current_date = sell_date if sell_date_str else buy_date
                            
                            # 遍历所有持仓，计算当前市值
                            for h_buy_date, holding_list in holdings.items():
                                for holding in holding_list:
                                    h_ts_code = holding['ts_code']
                                    h_buy_quantity = holding['buy_quantity']
                                    # 获取当前价格
                                    if h_ts_code in price_data:
                                        stock_prices = price_data[h_ts_code]
                                        if not stock_prices.empty:
                                            # 找到当前日期之前的最新价格
                                            current_price = None
                                            for idx in range(len(stock_prices) - 1, -1, -1):
                                                row = stock_prices.iloc[idx]
                                                if row['trade_date'] <= current_date:
                                                    current_price = row['close']
                                                    break
                                            
                                            if current_price and not pd.isna(current_price) and current_price > 0:
                                                current_holdings_value += h_buy_quantity * current_price
                            
                            # 计算当前总资产
                            current_total_assets = available_capital + current_holdings_value
                            
                            # 更新历史最高资产
                            if current_total_assets > max_total_assets:
                                max_total_assets = current_total_assets
                            
                            # 计算当前回撤
                            if max_total_assets > 0:
                                current_drawdown = (current_total_assets - max_total_assets) / max_total_assets
                                if current_drawdown < max_drawdown:
                                    max_drawdown = current_drawdown
                            
                            # 记录每日资产变化（用于调试）
                            daily_assets_history.append({
                                'date': current_date.isoformat() if isinstance(current_date, date) else str(current_date),
                                'available_capital': available_capital,
                                'holdings_value': current_holdings_value,
                                'total_assets': current_total_assets,
                                'max_total_assets': max_total_assets,
                                'drawdown': current_drawdown if max_total_assets > 0 else 0.0
                            })
                            
                            trades.append(trade_result)
                            successful_trades += 1
                            logger.debug(f"✅ 成功买入 {signal['ts_code']}（买入日期: {buy_date}, 买入价格: {buy_price:.2f}）")
                            
                            # 更新连续亏损计数和月度盈亏（在交易完成后）
                            if sell_date_str:  # 如果已卖出
                                # 更新连续亏损计数
                                if profit_loss < 0:
                                    consecutive_losses += 1
                                else:
                                    # 盈利后重置连续亏损计数
                                    consecutive_losses = 0
                                
                                # 更新月度盈亏
                                if sell_date:
                                    month_key = sell_date.strftime('%Y-%m')
                                    if month_key not in monthly_pnl:
                                        monthly_pnl[month_key] = 0.0
                                    monthly_pnl[month_key] += profit_loss
                        else:
                            logger.warning(f"交易 {signal['ts_code']} 买入价格为0，跳过")
                    else:
                        # 如果没有买入日期，仍然添加交易记录（但不计入资金管理）
                        trades.append(trade_result)
                        logger.debug(f"⚠️ 交易 {signal['ts_code']} 没有买入日期，添加交易记录但不计入资金管理")
                
                processed_count += 1
            
            logger.info(f"✅ 步骤3完成：处理了 {processed_count} 个信号，完成 {len(trades)} 笔交易模拟")
            logger.info(f"📊 交易统计详情：")
            logger.info(f"  总信号数: {len(signals)}")
            logger.info(f"  成功交易: {successful_trades}")
            logger.info(f"  模拟交易返回None: {skipped_no_trade_result}（可能原因：停牌/开盘涨停/价格数据缺失）")
            logger.info(f"  因每日上限跳过: {skipped_daily_limit}")
            logger.info(f"  因资金不足跳过: {skipped_no_capital}")
            logger.info(f"  当前连续亏损次数: {consecutive_losses}")
            
            # 计算最终总资产（可用资金 + 所有持仓市值）
            # 注意：这里需要计算所有未卖出持仓的市值
            total_holdings_value = 0.0
            for buy_date, holding_list in holdings.items():
                for holding in holding_list:
                    ts_code = holding['ts_code']
                    buy_quantity = holding['buy_quantity']
                    # 获取最新价格（使用回测结束日期）
                    if ts_code in price_data:
                        stock_prices = price_data[ts_code]
                        if not stock_prices.empty:
                            # 找到回测结束日期之前的最新价格
                            latest_price = None
                            for idx in range(len(stock_prices) - 1, -1, -1):
                                row = stock_prices.iloc[idx]
                                if row['trade_date'] <= end_date:
                                    latest_price = row['close']
                                    break
                            
                            if latest_price and not pd.isna(latest_price) and latest_price > 0:
                                total_holdings_value += buy_quantity * latest_price
            
            total_assets = available_capital + total_holdings_value
            total_profit_loss = total_assets - initial_capital
            total_profit_loss_pct = (total_profit_loss / initial_capital * 100) if initial_capital > 0 else 0
            
            # 计算总交易成本（用于日志）
            total_buy_commission_log = sum([t.get('buy_commission', 0) or 0 for t in trades])
            total_sell_commission_log = sum([t.get('sell_commission', 0) or 0 for t in trades])
            total_stamp_tax_log = sum([t.get('stamp_tax', 0) or 0 for t in trades])
            total_trading_cost_log = total_buy_commission_log + total_sell_commission_log + total_stamp_tax_log
            
            logger.info(f"💰 资金管理统计：")
            logger.info(f"  初始本金: {initial_capital:.2f} 元")
            logger.info(f"  最终可用资金: {available_capital:.2f} 元")
            logger.info(f"  持仓市值: {total_holdings_value:.2f} 元")
            logger.info(f"  总资产: {total_assets:.2f} 元")
            logger.info(f"  总盈亏: {total_profit_loss:.2f} 元 ({total_profit_loss_pct:.2f}%)")
            logger.info(f"  历史最高资产: {max_total_assets:.2f} 元")
            logger.info(f"  最大回撤（基于实际资金管理）: {max_drawdown:.2%}")
            logger.info(f"  交易成本统计：")
            logger.info(f"    买入手续费: {total_buy_commission_log:.2f} 元")
            logger.info(f"    卖出手续费: {total_sell_commission_log:.2f} 元")
            logger.info(f"    印花税: {total_stamp_tax_log:.2f} 元")
            logger.info(f"    总交易成本: {total_trading_cost_log:.2f} 元 (占初始本金 {total_trading_cost_log/initial_capital*100:.2f}%)")
            logger.info(f"  风险控制统计：")
            logger.info(f"    连续亏损保护触发: {risk_control_stats['consecutive_losses_triggered']}")
            logger.info(f"    回撤降仓触发: {risk_control_stats['drawdown_reduction_triggered']}")
            logger.info(f"    月度亏损暂停触发: {risk_control_stats['monthly_loss_pause_triggered']}")
            logger.info(f"    降仓交易天数: {risk_control_stats['reduced_position_days']}")
            
            # 6. 保存交易记录到数据库
            logger.info("步骤4: 开始保存交易记录到数据库...")
            saved_count = self._save_trades_to_db(session, trades, profit_target, stop_loss, max_hold_days, sell_strategy, strategy_type)
            logger.info(f"✅ 步骤4完成：保存了 {saved_count} 条交易记录")
            
            # 7. 计算统计指标
            logger.info("步骤5: 开始计算统计指标...")
            statistics = self._calculate_statistics(
                trades, 
                max_drawdown=max_drawdown,
                start_date=start_date,
                end_date=end_date,
                total_profit_loss_pct=total_profit_loss_pct
            )
            
            # 计算总交易成本统计
            total_buy_commission = sum([t.get('buy_commission', 0) or 0 for t in trades])
            total_sell_commission = sum([t.get('sell_commission', 0) or 0 for t in trades])
            total_stamp_tax = sum([t.get('stamp_tax', 0) or 0 for t in trades])
            total_trading_cost = total_buy_commission + total_sell_commission + total_stamp_tax
            
            # 添加资金管理统计信息
            statistics['capital_management'] = {
                'initial_capital': initial_capital,
                'final_available_capital': available_capital,
                'holdings_value': total_holdings_value,
                'total_assets': total_assets,
                'total_profit_loss': total_profit_loss,
                'total_profit_loss_pct': total_profit_loss_pct,
                'max_stocks_per_day': max_stocks_per_day,
                'capital_per_stock': capital_per_stock,
                # 交易成本统计
                'total_buy_commission': total_buy_commission,
                'total_sell_commission': total_sell_commission,
                'total_stamp_tax': total_stamp_tax,
                'total_trading_cost': total_trading_cost,
                'trading_cost_ratio': (total_trading_cost / initial_capital * 100) if initial_capital > 0 else 0,  # 交易成本占初始本金的比例
                # 风险控制统计
                'risk_control': risk_control_stats
            }
            
            logger.info(f"✅ 步骤5完成：统计指标计算完成")
            
            logger.info(f"✅ 回测完成：共处理 {len(signals)} 个信号，完成 {len(trades)} 笔交易")
            
            # 建立信号和交易记录的映射关系
            # 使用 (signal_date, ts_code) 作为唯一键
            signal_trade_map = {}  # key: (signal_date, ts_code), value: trade
            for trade in trades:
                signal_date = trade.get('signal_date')
                ts_code = trade.get('ts_code')
                if signal_date and ts_code:
                    # 确保signal_date是字符串格式（统一格式）
                    if isinstance(signal_date, date):
                        signal_date_str = signal_date.isoformat()
                    else:
                        signal_date_str = str(signal_date)
                    key = (signal_date_str, ts_code)
                    signal_trade_map[key] = trade
            
            # 为每个信号添加对应的交易记录
            signals_with_trades = []
            for signal in signals:
                signal_date = signal.get('signal_date')
                ts_code = signal.get('ts_code')
                # 统一转换为字符串格式
                if isinstance(signal_date, date):
                    signal_date_str = signal_date.isoformat()
                elif isinstance(signal_date, str):
                    signal_date_str = signal_date
                else:
                    signal_date_str = str(signal_date) if signal_date else ''
                
                key = (signal_date_str, ts_code)
                trade = signal_trade_map.get(key)
                
                # 构建信号数据（确保日期格式统一）
                signal_with_trade = {
                    **signal,
                    'signal_date': signal_date_str,  # 统一为字符串格式
                    'trade': trade,  # 对应的交易记录，如果没有则为None
                    'has_trade': trade is not None  # 是否有交易记录
                }
                signals_with_trades.append(signal_with_trade)
            
            return {
                'success': True,
                'backtest_period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'parameters': {
                    'profit_target': profit_target,
                    'stop_loss': stop_loss,
                    'max_hold_days': max_hold_days,
                    'sell_strategy': sell_strategy
                },
                'statistics': statistics,
                'trades': trades,
                'signals': signals_with_trades  # 信号列表，每个信号包含对应的交易记录
            }
            
        except Exception as e:
            logger.error(f"回测失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败'
            }
        finally:
            session.close()
    
    def _get_signals(self, session: Session, start_date: date, end_date: date, strategy_type: str = 'mainboard_limit_up') -> List[Dict]:
        """获取信号数据"""
        try:
            # 构建查询条件
            filters = [
                FactLimitUpVolumeShrink.trade_date >= start_date,
                FactLimitUpVolumeShrink.trade_date <= end_date,
                FactLimitUpVolumeShrink.strategy_type == strategy_type  # 根据策略类型过滤
            ]
            
            # 主板策略：限制 limit_up_days_ago 范围（排除当天涨停且缩量的股票，只考虑最近5个交易日内有涨停的股票）
            # 创业板策略：不限制 limit_up_days_ago 范围
            if strategy_type == 'mainboard_limit_up':
                filters.append(FactLimitUpVolumeShrink.limit_up_days_ago > 0)  # 排除当天涨停且缩量的股票（limit_up_days_ago == 0）
                filters.append(FactLimitUpVolumeShrink.limit_up_days_ago <= 4)  # 只考虑最近5个交易日内有涨停的股票
            
            query = session.query(FactLimitUpVolumeShrink).filter(*filters).order_by(FactLimitUpVolumeShrink.trade_date)
            
            records = query.all()
            
            # 基于 limit_up_date 和 ts_code 去重，保留最早的 trade_date（信号日期）
            # 同一个涨停日期应该只产生一个信号
            signals_dict = {}  # key: (ts_code, limit_up_date), value: signal
            duplicate_count = 0
            
            for record in records:
                if not record.limit_up_date:
                    # 如果没有涨停日期，使用 trade_date 作为唯一标识
                    key = (record.ts_code, record.trade_date)
                else:
                    # 使用涨停日期和股票代码作为唯一标识
                    key = (record.ts_code, record.limit_up_date)
                
                if key not in signals_dict:
                    # 第一次出现，保存
                    signals_dict[key] = {
                        'signal_date': record.trade_date,
                        'ts_code': record.ts_code,
                        'stock_name': record.stock_name or '',
                        'signal_close': float(record.today_close) if record.today_close else None,
                        'limit_up_date': record.limit_up_date,
                        'volume_ratio': float(record.volume_ratio) if record.volume_ratio else None,
                        'today_change_pct': float(record.today_change_pct) if record.today_change_pct else None,
                        'today_amount': float(record.today_amount) if record.today_amount else None
                    }
                else:
                    # 已存在，保留更早的 trade_date（信号日期）
                    duplicate_count += 1
                    existing_signal = signals_dict[key]
                    if record.trade_date < existing_signal['signal_date']:
                        # 如果当前记录的 trade_date 更早，更新为更早的信号
                        signals_dict[key] = {
                            'signal_date': record.trade_date,
                            'ts_code': record.ts_code,
                            'stock_name': record.stock_name or '',
                            'signal_close': float(record.today_close) if record.today_close else None,
                            'limit_up_date': record.limit_up_date,
                            'volume_ratio': float(record.volume_ratio) if record.volume_ratio else None,
                            'today_change_pct': float(record.today_change_pct) if record.today_change_pct else None,
                            'today_amount': float(record.today_amount) if record.today_amount else None
                        }
            
            signals = list(signals_dict.values())
            
            # 过滤非止跌日的信号（仅主板策略：信号日期必须是上涨的，涨幅 > 0）
            # 注意：today_change_pct 存储的是百分比形式（如 -0.7 表示 -0.7%，0.5 表示 0.5%）
            # 创业板策略：不限制涨幅范围
            filtered_signals_by_change = []
            excluded_not_up_day_count = 0
            for signal in signals:
                signal_change_pct = signal.get('today_change_pct')
                ts_code = signal['ts_code']
                stock_name = signal.get('stock_name', '')
                signal_date = signal.get('signal_date')
                
                if signal_change_pct is None:
                    excluded_not_up_day_count += 1
                    logger.debug(f"排除信号（涨幅数据缺失）: {ts_code} {stock_name} (信号日期: {signal_date})")
                    continue
                
                # 确保是数值类型
                try:
                    signal_change_pct = float(signal_change_pct)
                except (ValueError, TypeError):
                    excluded_not_up_day_count += 1
                    logger.warning(f"排除信号（涨幅数据格式错误）: {ts_code} {stock_name} (信号日期: {signal_date}, 涨幅值: {signal_change_pct})")
                    continue
                
                # 主板策略：判断是否是止跌日（涨幅必须 > 0）
                # 创业板策略：不限制涨幅
                if strategy_type == 'mainboard_limit_up':
                    if signal_change_pct <= 0:
                        excluded_not_up_day_count += 1
                        logger.debug(f"排除信号（非止跌日，涨幅: {signal_change_pct:.4f}%）: {ts_code} {stock_name} (信号日期: {signal_date})")
                        continue
                    
                    # 判断信号日最高涨幅是否过大：最高涨幅不能 > 5%（仅主板策略）
                    # 需要查询信号日期的最高价，计算最高涨幅 = (最高价 - 前一日收盘价) / 前一日收盘价 * 100
                    try:
                        if isinstance(signal_date, str):
                            signal_date_parsed = datetime.strptime(signal_date, '%Y-%m-%d').date()
                        else:
                            signal_date_parsed = signal_date
                        
                        # 查询信号日期的最高价和前一日收盘价
                        price_query = session.query(
                            FactDailyPriceQfq.high,
                            FactDailyPriceQfq.pre_close
                        ).filter(
                            FactDailyPriceQfq.ts_code == ts_code,
                            FactDailyPriceQfq.trade_date == signal_date_parsed
                        ).first()
                        
                        if price_query and price_query.high and price_query.pre_close:
                            high_price = float(price_query.high)
                            pre_close = float(price_query.pre_close)
                            
                            if pre_close > 0:
                                max_change_pct = (high_price - pre_close) / pre_close * 100
                                
                                if max_change_pct > 5.0:
                                    excluded_not_up_day_count += 1
                                    logger.debug(f"排除信号（最高涨幅过大，最高涨幅: {max_change_pct:.4f}%）: {ts_code} {stock_name} (信号日期: {signal_date}, 最高价: {high_price:.2f}, 前收盘: {pre_close:.2f})")
                                    continue
                    except Exception as e:
                        logger.warning(f"查询信号日期最高价失败: {ts_code} {stock_name} (信号日期: {signal_date}), 错误: {e}，继续处理")
                
                filtered_signals_by_change.append(signal)
            
            if excluded_not_up_day_count > 0:
                if strategy_type == 'mainboard_limit_up':
                    logger.info(f"过滤信号：排除了 {excluded_not_up_day_count} 个信号（涨幅 <= 0 或涨幅 > 5% 或数据缺失）")
                else:
                    logger.info(f"过滤信号：排除了 {excluded_not_up_day_count} 个信号（数据缺失）")
            
            signals = filtered_signals_by_change
            
            # 过滤股价低于3元的股票
            filtered_signals_by_price = []
            excluded_low_price_count = 0
            for signal in signals:
                signal_close = signal.get('signal_close')
                ts_code = signal['ts_code']
                stock_name = signal.get('stock_name', '')
                signal_date = signal.get('signal_date')
                
                if signal_close is None:
                    excluded_low_price_count += 1
                    logger.debug(f"排除信号（收盘价数据缺失）: {ts_code} {stock_name} (信号日期: {signal_date})")
                    continue
                
                # 确保是数值类型
                try:
                    signal_close = float(signal_close)
                except (ValueError, TypeError):
                    excluded_low_price_count += 1
                    logger.warning(f"排除信号（收盘价数据格式错误）: {ts_code} {stock_name} (信号日期: {signal_date}, 收盘价: {signal.get('signal_close')})")
                    continue
                
                # 判断股价是否低于3元
                if signal_close < 3.0:
                    excluded_low_price_count += 1
                    logger.debug(f"排除信号（股价低于3元，收盘价: {signal_close:.2f}元）: {ts_code} {stock_name} (信号日期: {signal_date})")
                    continue
                
                filtered_signals_by_price.append(signal)
            
            if excluded_low_price_count > 0:
                logger.info(f"过滤低价股：排除了 {excluded_low_price_count} 个信号（股价 < 3元）")
            
            signals = filtered_signals_by_price
            
            # 过滤信号日出现死叉的信号（5日线 < 10日线）
            filtered_signals_by_dead_cross = []
            excluded_dead_cross_count = 0
            for signal in signals:
                ts_code = signal['ts_code']
                stock_name = signal.get('stock_name', '')
                signal_date = signal.get('signal_date')
                
                try:
                    # 解析信号日期
                    if isinstance(signal_date, str):
                        signal_date_parsed = datetime.strptime(signal_date, '%Y-%m-%d').date()
                    else:
                        signal_date_parsed = signal_date
                    
                    # 查询信号日的5日线和10日线数据
                    ma_query = session.query(
                        FactDailyPriceQfq.ma5,
                        FactDailyPriceQfq.ma10
                    ).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == signal_date_parsed
                    ).first()
                    
                    if ma_query and ma_query.ma5 is not None and ma_query.ma10 is not None:
                        ma5 = float(ma_query.ma5)
                        ma10 = float(ma_query.ma10)
                        
                        # 死叉判断：5日线 < 10日线（5日线在10日线下方）
                        if ma5 < ma10:
                            excluded_dead_cross_count += 1
                            logger.debug(f"排除信号（信号日出现死叉，5日线: {ma5:.2f} < 10日线: {ma10:.2f}）: {ts_code} {stock_name} (信号日期: {signal_date})")
                            continue
                    elif ma_query is None:
                        # 如果查询不到数据，记录警告但保留信号（保守策略）
                        logger.warning(f"信号日MA数据查询失败（无数据）: {ts_code} {stock_name} (信号日期: {signal_date})，保留信号")
                    elif ma_query.ma5 is None or ma_query.ma10 is None:
                        # 如果MA数据缺失，记录警告但保留信号（保守策略）
                        logger.warning(f"信号日MA数据缺失: {ts_code} {stock_name} (信号日期: {signal_date}, ma5={ma_query.ma5}, ma10={ma_query.ma10})，保留信号")
                except Exception as e:
                    logger.warning(f"查询信号日MA数据失败: {ts_code} {stock_name} (信号日期: {signal_date}), 错误: {e}，保留信号")
                
                filtered_signals_by_dead_cross.append(signal)
            
            if excluded_dead_cross_count > 0:
                logger.info(f"过滤死叉信号：排除了 {excluded_dead_cross_count} 个信号（信号日出现死叉：5日线 < 10日线）")
            
            signals = filtered_signals_by_dead_cross
            
            # 过滤信号日期当天是跌停的股票
            from data_warehouse.models.tonghuashun_limit_up import FactTonghuashunLimitUp
            filtered_signals = []
            excluded_signal_date_limit_down_count = 0
            
            for signal in signals:
                signal_date = signal['signal_date']
                ts_code = signal['ts_code']
                
                # 检查信号日期当天是否是跌停
                # 注意：只有在明确确认是跌停时才排除，如果查询不到数据则保留（保守策略）
                is_signal_date_limit_down = False
                
                # 方法1：通过同花顺的 up_and_down_status 检查
                limit_down_query = session.query(
                    FactTonghuashunLimitUp.up_and_down_status,
                    FactTonghuashunLimitUp.change_pct
                ).filter(
                    FactTonghuashunLimitUp.ts_code == ts_code,
                    FactTonghuashunLimitUp.trade_date == signal_date
                ).first()
                
                if limit_down_query:
                    # 查询到了数据，检查是否是跌停
                    status = limit_down_query.up_and_down_status
                    change_pct_val = limit_down_query.change_pct
                    
                    # 优先使用状态字段判断
                    if status:
                        status_str = str(status).strip()
                        # 明确判断：只有状态值完全等于"跌停"或"-1"时才判断为跌停
                        # 注意："非涨跌停"包含"跌停"关键词，但不应该被判断为跌停
                        if status_str == '跌停' or status_str == '-1':
                            is_signal_date_limit_down = True
                        # 如果状态值以"跌停"开头或结尾（排除"非涨跌停"这种情况）
                        elif status_str.startswith('跌停') or status_str.endswith('跌停'):
                            # 但要排除"非涨跌停"这种情况
                            if '非涨跌停' not in status_str and '非跌停' not in status_str:
                                is_signal_date_limit_down = True
                    
                    # 如果状态字段没有明确标识跌停，再通过涨跌幅判断
                    if not is_signal_date_limit_down and change_pct_val is not None:
                        try:
                            change_pct_float = float(change_pct_val)
                            code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                            is_cyb = code_part.startswith('300') or code_part.startswith('688')
                            limit_down_threshold = -19.5 if is_cyb else -9.5
                            if change_pct_float <= limit_down_threshold:
                                is_signal_date_limit_down = True
                        except (ValueError, TypeError):
                            # 如果转换失败，忽略（不排除）
                            pass
                # 如果查询不到数据（limit_down_query 为 None），不排除（保守策略）
                
                if is_signal_date_limit_down:
                    excluded_signal_date_limit_down_count += 1
                    logger.debug(f"排除信号（信号日期当天跌停）: {ts_code} {signal.get('stock_name', '')} "
                               f"(信号日期: {signal_date}, 状态: {limit_down_query.up_and_down_status if limit_down_query else 'N/A'}, "
                               f"涨跌幅: {limit_down_query.change_pct if limit_down_query else 'N/A'}%)")
                    continue
                
                # 调试日志：记录前几个信号的状态（用于排查问题）
                if len(filtered_signals) < 5 and limit_down_query:
                    logger.debug(f"保留信号（非跌停）: {ts_code} {signal.get('stock_name', '')} "
                               f"(信号日期: {signal_date}, 状态: {limit_down_query.up_and_down_status}, "
                               f"涨跌幅: {limit_down_query.change_pct}%)")
                
                filtered_signals.append(signal)
            
            signals = filtered_signals
            
            if duplicate_count > 0:
                logger.info(f"获取到 {len(records)} 个原始信号，去重后剩余 {len(signals_dict)} 个信号（基于涨停日期去重，排除了 {duplicate_count} 个重复信号）")
            else:
                logger.info(f"获取到 {len(signals_dict)} 个原始信号")
            
            if excluded_signal_date_limit_down_count > 0:
                logger.info(f"排除 {excluded_signal_date_limit_down_count} 个信号（信号日期当天跌停），最终剩余 {len(signals)} 个信号")
            else:
                if strategy_type == 'mainboard_limit_up':
                    logger.info(f"最终剩余 {len(signals)} 个信号（已排除 limit_up_days_ago == 0 的数据，且只保留 limit_up_days_ago <= 4 的数据）")
                else:
                    logger.info(f"最终剩余 {len(signals)} 个信号（创业板策略：不限制 limit_up_days_ago 范围）")
            
            return signals
        except Exception as e:
            logger.error(f"获取信号数据失败: {e}", exc_info=True)
            return []
    
    def _filter_st_and_delisted_stocks(
        self, 
        session: Session, 
        signals: List[Dict], 
        start_date: date, 
        end_date: date
    ) -> List[Dict]:
        """
        过滤ST股票和退市股票
        
        Args:
            session: 数据库会话
            signals: 信号列表
            start_date: 回测开始日期
            end_date: 回测结束日期
        
        Returns:
            List[Dict]: 过滤后的信号列表
        """
        if not signals:
            return signals
        
        try:
            # 获取所有股票代码
            ts_codes = list(set([s['ts_code'] for s in signals]))
            
            # 查询股票基本信息
            stocks = session.query(
                DimStock.ts_code,
                DimStock.name,
                DimStock.delist_date
            ).filter(
                DimStock.ts_code.in_(ts_codes)
            ).all()
            
            # 构建股票信息字典
            stock_info = {}
            for stock in stocks:
                stock_info[stock.ts_code] = {
                    'name': stock.name,
                    'delist_date': stock.delist_date
                }
            
            # 过滤信号
            filtered_signals = []
            st_count = 0
            delisted_count = 0
            
            for signal in signals:
                ts_code = signal['ts_code']
                signal_date = signal['signal_date']
                
                # 确保signal_date是date对象
                if isinstance(signal_date, str):
                    signal_date = datetime.strptime(signal_date, '%Y-%m-%d').date()
                elif not isinstance(signal_date, date):
                    signal_date = signal_date  # 假设已经是date对象
                
                # 检查股票信息
                if ts_code not in stock_info:
                    # 如果查询不到股票信息，保留（可能是新股票）
                    filtered_signals.append(signal)
                    continue
                
                stock_name = stock_info[ts_code]['name']
                delist_date = stock_info[ts_code]['delist_date']
                
                # 检查是否为ST股票（名称包含ST或*ST）
                # 同时检查DimStock表中的名称和信号数据中的名称
                is_st = False
                signal_stock_name = signal.get('stock_name', '')  # 信号数据中的股票名称
                
                # 检查DimStock表中的名称
                if stock_name:
                    stock_name_upper = stock_name.upper()
                    if 'ST' in stock_name_upper or '*ST' in stock_name_upper:
                        is_st = True
                
                # 检查信号数据中的名称（可能DimStock表中没有ST前缀，但信号数据中有）
                if not is_st and signal_stock_name:
                    signal_stock_name_upper = signal_stock_name.upper()
                    if 'ST' in signal_stock_name_upper or '*ST' in signal_stock_name_upper:
                        is_st = True
                
                if is_st:
                    st_count += 1
                    logger.debug(f"过滤ST股票: {ts_code} DimStock名称={stock_name}, 信号名称={signal_stock_name} (信号日期: {signal_date})")
                
                # 检查是否已退市或即将退市
                is_delisted = False
                if stock_name:
                    # 方法1：检查股票名称是否包含"退市"关键词（包括"退"字）
                    stock_name_upper = stock_name.upper()
                    # 检查是否包含"退市"、"DELIST"或单独的"退"字（在股票名称末尾，如"XX退"）
                    if ('退市' in stock_name or 'DELIST' in stock_name_upper or 
                        stock_name.endswith('退') or stock_name.endswith('退市')):
                        is_delisted = True
                        delisted_count += 1
                        logger.debug(f"过滤退市股票（名称包含退市）: {ts_code} {stock_name} (信号日期: {signal_date})")
                
                # 方法2：检查退市日期
                if not is_delisted and delist_date:
                    # 如果退市日期在信号日期之前，或者在信号日期之后60天内，则过滤
                    if delist_date <= signal_date:
                        # 退市日期在信号日期之前，肯定要过滤
                        is_delisted = True
                        delisted_count += 1
                        logger.debug(f"过滤退市股票（已退市）: {ts_code} {stock_name} (退市日期: {delist_date}, 信号日期: {signal_date})")
                    elif (delist_date - signal_date).days <= 60:
                        # 退市日期在信号日期之后60天内，也要过滤（即将退市）
                        is_delisted = True
                        delisted_count += 1
                        logger.debug(f"过滤退市股票（即将退市）: {ts_code} {stock_name} (退市日期: {delist_date}, 信号日期: {signal_date}, 距离{delist_date - signal_date}天)")
                
                # 只保留非ST且未退市的股票
                if not is_st and not is_delisted:
                    filtered_signals.append(signal)
            
            if st_count > 0 or delisted_count > 0:
                logger.info(f"过滤结果：ST股票 {st_count} 只，退市股票 {delisted_count} 只")
            
            return filtered_signals
            
        except Exception as e:
            logger.error(f"过滤ST和退市股票失败: {e}", exc_info=True)
            # 如果过滤失败，返回原始信号列表（避免影响回测）
            return signals
    
    def _get_price_data(self, session: Session, ts_codes: List[str], start_date: date, end_date: date) -> Dict[str, pd.DataFrame]:
        """批量获取价格数据"""
        try:
            logger.info(f"开始查询价格数据：{len(ts_codes)} 只股票，日期范围：{start_date} 至 {end_date}")
            query = session.query(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date,
                FactDailyPriceQfq.open,
                FactDailyPriceQfq.close,
                FactDailyPriceQfq.high,
                FactDailyPriceQfq.low,
                FactDailyPriceQfq.is_suspended,
                FactDailyPriceQfq.ma5,
                FactDailyPriceQfq.ma10,
                FactDailyPriceQfq.ma20,
                FactDailyPriceQfq.ma60,
                FactDailyPriceQfq.change_pct
            ).filter(
                FactDailyPriceQfq.ts_code.in_(ts_codes),
                FactDailyPriceQfq.trade_date >= start_date,
                FactDailyPriceQfq.trade_date <= end_date
            ).order_by(
                FactDailyPriceQfq.ts_code,
                FactDailyPriceQfq.trade_date
            )
            
            logger.info("执行价格数据查询...")
            rows = query.all()
            logger.info(f"查询完成，获取到 {len(rows)} 条价格记录")
            
            # 转换为DataFrame并按股票代码分组
            logger.info("开始处理价格数据...")
            data_dict = {}
            for row in rows:
                ts_code = row.ts_code
                if ts_code not in data_dict:
                    data_dict[ts_code] = []
                
                data_dict[ts_code].append({
                    'trade_date': row.trade_date,
                    'open': float(row.open) if row.open else None,
                    'close': float(row.close) if row.close else None,
                    'high': float(row.high) if row.high else None,
                    'low': float(row.low) if row.low else None,
                    'is_suspended': bool(row.is_suspended) if row.is_suspended is not None else False,
                    'ma5': float(row.ma5) if row.ma5 else None,
                    'ma10': float(row.ma10) if row.ma10 else None,
                    'ma20': float(row.ma20) if row.ma20 else None,
                    'ma60': float(row.ma60) if row.ma60 else None,
                    'change_pct': float(row.change_pct) if row.change_pct is not None else None  # 涨跌幅
                })
            
            # 转换为DataFrame
            logger.info("转换为DataFrame...")
            price_data = {}
            for ts_code, records in data_dict.items():
                df = pd.DataFrame(records)
                df = df.sort_values('trade_date').reset_index(drop=True)
                price_data[ts_code] = df
            
            logger.info(f"价格数据处理完成，共 {len(price_data)} 只股票")
            return price_data
            
        except Exception as e:
            logger.error(f"获取价格数据失败: {e}", exc_info=True)
            return {}
    
    def _check_break_ma5_optimized(
        self,
        current_close: float,
        ma5_today: float,
        ma5_yesterday: Optional[float],
        ma10_today: Optional[float],
        volume: float,
        avg_volume: float,
        buy_price: float,
        consecutive_days_below_ma5: int,
        config: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """
        优化后的破5日线判断逻辑
        
        Args:
            current_close: 当前收盘价
            ma5_today: 今日5日均线
            ma5_yesterday: 昨日5日均线（可为None）
            ma10_today: 今日10日均线（可为None）
            volume: 当前成交量
            avg_volume: 平均成交量（如5日平均）
            buy_price: 买入价
            consecutive_days_below_ma5: 连续破5日线天数
            config: 配置参数
            
        Returns:
            (是否卖出, 退出原因)
        """
        if config is None:
            config = {}
        
        # 检查是否破5日线
        is_below_ma5 = current_close < ma5_today
        
        if not is_below_ma5:
            return False, 'not_below_ma5'
        
        # 获取配置参数
        enable_optimization = config.get('enable_optimization', False)  # 默认关闭优化，使用保守策略
        consecutive_threshold = config.get('consecutive_days_threshold', 2)
        volume_expand_ratio = config.get('volume_expand_ratio', 1.5)
        volume_shrink_ratio = config.get('volume_shrink_ratio', 0.8)
        profit_protect_threshold = config.get('profit_protect_threshold', 0.0)
        
        # 如果未启用优化，使用保守策略：破5日线就卖出
        if not enable_optimization:
            return True, 'break_ma5_conservative'
        
        # 以下为优化逻辑（仅在enable_optimization=True时启用）
        # 条件1：5日线是否仍在上升
        ma5_rising = False
        if ma5_yesterday is not None and not pd.isna(ma5_yesterday):
            ma5_rising = ma5_today > ma5_yesterday
        
        # 条件2：是否连续N天破5日线
        consecutive = consecutive_days_below_ma5 >= consecutive_threshold
        
        # 条件3：成交量是否放大
        volume_expanded = False
        volume_shrunk = False
        if avg_volume > 0:
            volume_expanded = volume > avg_volume * volume_expand_ratio
            volume_shrunk = volume < avg_volume * volume_shrink_ratio
        
        # 条件4：是否仍在盈利
        profit_pct = (current_close - buy_price) / buy_price
        still_profitable = profit_pct > profit_protect_threshold
        
        # 条件5：是否跌破10日均线
        below_ma10 = False
        if ma10_today is not None and not pd.isna(ma10_today):
            below_ma10 = current_close < ma10_today
        
        # 卖出条件（按优先级）：
        
        # 1. 连续N天破5日线，且5日线下降（确认趋势反转）
        if consecutive and not ma5_rising:
            return True, 'break_ma5_consecutive_trend_down'
        
        # 2. 破5日线且成交量放大（真破位）
        if volume_expanded:
            return True, 'break_ma5_volume_expanded'
        
        # 3. 破5日线且跌破10日均线（中期趋势转弱）
        if below_ma10:
            return True, 'break_ma5_below_ma10'
        
        # 4. 破5日线且已亏损超过-3%（保护本金）
        if not still_profitable and profit_pct < -0.03:
            return True, 'break_ma5_loss_protection'
        
        # 5. 如果仍在盈利，且成交量萎缩，可能是洗盘，继续持有
        if still_profitable and volume_shrunk:
            return False, 'hold_ma5_volume_shrunk'
        
        # 6. 如果5日线仍在上升，且只是单日破5日线，且仍在盈利，继续持有
        if ma5_rising and consecutive_days_below_ma5 == 1 and still_profitable:
            return False, 'hold_ma5_rising'
        
        # 7. 如果连续破位但5日线仍在上升，且仍在盈利，继续持有
        if consecutive and ma5_rising and still_profitable:
            return False, 'hold_ma5_rising_consecutive'
        
        # 默认：如果已亏损，单日破5日线就卖出（保守策略，避免亏损扩大）
        if not still_profitable:
            return True, 'break_ma5_loss_default'
        
        # 如果仍在盈利但其他条件不满足，单日破5日线也卖出（保守策略）
        return True, 'break_ma5_profit_default'
    
    def _calculate_trailing_stop_loss(
        self,
        buy_price: float,
        current_price: float,
        initial_stop_loss_pct: float = -0.10,
        config: Optional[Dict] = None
    ) -> float:
        """
        计算移动止损价
        
        Args:
            buy_price: 买入价
            current_price: 当前价格
            initial_stop_loss_pct: 初始止损比例（如-0.10表示-10%）
            config: 配置参数
            
        Returns:
            止损价
        """
        if config is None:
            config = {}
        
        # 获取配置参数
        profit_thresholds = config.get('profit_thresholds', [0.05, 0.10, 0.15, 0.20, 0.30])
        stop_loss_protections = config.get('stop_loss_protections', [0.0, 0.05, 0.08, 0.12, 0.20])
        
        # 计算当前盈利比例
        profit_pct = (current_price - buy_price) / buy_price
        
        # 根据盈利情况确定止损保护比例
        stop_loss_protection = initial_stop_loss_pct  # 默认-10%
        
        for i, threshold in enumerate(profit_thresholds):
            if profit_pct >= threshold:
                if i < len(stop_loss_protections):
                    stop_loss_protection = stop_loss_protections[i]
        
        # 计算止损价
        stop_loss_price = buy_price * (1 + stop_loss_protection)
        
        # 重要：确保止损价不会高于当前价格（止损价应该低于当前价）
        # 但如果当前价格已经低于止损价，说明已经触发止损，止损价应该保持原值
        if stop_loss_price > current_price and profit_pct < 0:
            # 如果当前亏损，止损价不应该高于当前价格
            # 保持原始止损价（-10%）
            stop_loss_price = buy_price * (1 + initial_stop_loss_pct)
        elif stop_loss_price >= current_price and profit_pct >= 0:
            # 如果当前盈利，止损价不应该高于当前价格
            stop_loss_price = current_price * 0.99  # 至少1%的安全边际
        
        return stop_loss_price
    
    def _update_trailing_stop_loss(
        self,
        buy_price: float,
        current_price: float,
        previous_stop_loss_price: float,
        initial_stop_loss_pct: float = -0.10,
        config: Optional[Dict] = None
    ) -> float:
        """
        更新移动止损价（只上移不下移）
        
        Args:
            buy_price: 买入价
            current_price: 当前价格
            previous_stop_loss_price: 之前的止损价
            initial_stop_loss_pct: 初始止损比例
            config: 配置参数
            
        Returns:
            新的止损价
        """
        # 计算新的止损价
        new_stop_loss_price = self._calculate_trailing_stop_loss(
            buy_price, current_price, initial_stop_loss_pct, config
        )
        
        # 止损价只上移不下移
        if new_stop_loss_price > previous_stop_loss_price:
            return new_stop_loss_price
        else:
            return previous_stop_loss_price
    
    def _calculate_max_hold_days(
        self,
        current_profit_pct: float,
        base_max_hold_days: int = 5,
        config: Optional[Dict] = None
    ) -> int:
        """
        根据盈利情况计算最大持有天数
        
        Args:
            current_profit_pct: 当前盈利比例
            base_max_hold_days: 基础最大持有天数
            config: 配置参数
            
        Returns:
            最大持有天数
        """
        if config is None:
            config = {}
        
        # 获取配置参数
        profit_thresholds = config.get('profit_thresholds', [0.03, 0.08, 0.15])
        extended_days = config.get('extended_days', [2, 5, 10])
        max_hold_days_limit = config.get('max_hold_days_limit', 15)
        
        # 根据盈利情况确定延长天数
        extended_days_count = 0
        
        for i, threshold in enumerate(profit_thresholds):
            if current_profit_pct >= threshold:
                if i < len(extended_days):
                    extended_days_count = extended_days[i]
        
        # 计算最大持有天数
        max_hold_days = base_max_hold_days + extended_days_count
        
        # 不超过上限
        return min(max_hold_days, max_hold_days_limit)
    
    def _get_next_trading_date(self, session: Session, trade_date: date, max_days: int = 10) -> Optional[date]:
        """获取下一个交易日"""
        try:
            query = session.query(DimTradeCalendar.trade_date).filter(
                DimTradeCalendar.trade_date > trade_date,
                DimTradeCalendar.is_open == True
            ).order_by(
                DimTradeCalendar.trade_date
            ).limit(1)
            
            result = query.first()
            if result:
                return result[0]
            
            # 降级：简单计算（跳过周末）
            current = trade_date
            for _ in range(max_days):
                current += timedelta(days=1)
                if current.weekday() < 5:  # 周一到周五
                    return current
            
            return None
        except Exception as e:
            logger.warning(f"获取下一个交易日失败: {e}")
            # 降级：简单计算
            current = trade_date
            for _ in range(max_days):
                current += timedelta(days=1)
                if current.weekday() < 5:
                    return current
            return None
    
    def analyze_stop_loss_stocks(self, stocks: List[Dict]) -> Dict:
        """
        分析止损股票的共同特征，找出可以规避风险的方法
        
        Args:
            stocks: 止损股票列表，每个元素包含 ts_code 和 signal_date（实际是卖出日期）
        
        Returns:
            Dict: 分析结果
        """
        session = self.warehouse.get_session()
        result = {
            'total_stocks': len(stocks),
            'analysis': [],
            'common_features': {},
            'suggestions': []
        }
        
        try:
            all_features = []
            
            for stock_info in stocks:
                ts_code = stock_info.get('ts_code')
                sell_date_str = stock_info.get('signal_date')  # 实际是卖出日期
                
                if not ts_code or not sell_date_str:
                    continue
                
                try:
                    sell_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
                except:
                    continue
                
                # 方法1：从回测交易记录表中查找（更准确）
                # 支持多种退出原因：stop_loss, break_ma5_conservative 等
                trade_record = session.query(FactLimitUpVolumeShrinkBacktest).filter(
                    FactLimitUpVolumeShrinkBacktest.ts_code == ts_code,
                    FactLimitUpVolumeShrinkBacktest.sell_date == sell_date,
                    FactLimitUpVolumeShrinkBacktest.strategy_type == 'cyb_rise_shrink'
                ).first()
                
                # 如果没找到，尝试只匹配股票代码（可能日期有误差）
                if not trade_record:
                    trade_record = session.query(FactLimitUpVolumeShrinkBacktest).filter(
                        FactLimitUpVolumeShrinkBacktest.ts_code == ts_code,
                        FactLimitUpVolumeShrinkBacktest.strategy_type == 'cyb_rise_shrink'
                    ).order_by(FactLimitUpVolumeShrinkBacktest.sell_date.desc()).first()
                
                if trade_record:
                    # 从交易记录中获取数据
                    signal_date = trade_record.signal_date
                    buy_date = trade_record.buy_date
                    buy_price = float(trade_record.buy_price) if trade_record.buy_price else None
                    
                    # 获取信号数据
                    signal_query = session.query(FactLimitUpVolumeShrink).filter(
                        FactLimitUpVolumeShrink.ts_code == ts_code,
                        FactLimitUpVolumeShrink.trade_date == signal_date,
                        FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
                    ).first()
                    
                    # 获取买入日数据
                    buy_query = session.query(
                        FactDailyPriceQfq.open,
                        FactDailyPriceQfq.close,
                        FactDailyPriceQfq.high,
                        FactDailyPriceQfq.low,
                        FactDailyPriceQfq.change_pct,
                        FactDailyPriceQfq.vol,
                        FactDailyPriceQfq.amount,
                        FactDailyPriceQfq.ma5,
                        FactDailyPriceQfq.ma10,
                        FactDailyPriceQfq.ma20
                    ).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == buy_date
                    ).first()
                    
                    # 获取止损日数据
                    stop_loss_query = session.query(
                        FactDailyPriceQfq.close,
                        FactDailyPriceQfq.change_pct,
                        FactDailyPriceQfq.ma5
                    ).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == sell_date
                    ).first()
                    
                    if buy_query and stop_loss_query and signal_query:
                        # 计算持有天数
                        days_to_stop_loss = trade_record.hold_days if trade_record.hold_days else None
                        
                        stop_loss_close = float(stop_loss_query.close) if stop_loss_query.close else None
                        stop_loss_change = float(stop_loss_query.change_pct) if stop_loss_query.change_pct else None
                        stop_loss_ma5 = float(stop_loss_query.ma5) if stop_loss_query.ma5 else None
                        
                        features = {
                            'ts_code': ts_code,
                            'signal_date': signal_date.isoformat() if signal_date else sell_date_str,
                            'buy_date': buy_date.isoformat() if buy_date else None,
                            'stop_loss_date': sell_date.isoformat(),
                            'days_to_stop_loss': days_to_stop_loss,
                            # 信号特征
                            'signal_volume_ratio': float(signal_query.volume_ratio) if signal_query.volume_ratio else None,
                            'signal_change_pct': float(signal_query.today_change_pct) if signal_query.today_change_pct else None,
                            'signal_close': float(signal_query.today_close) if signal_query.today_close else None,
                            # 买入日特征
                            'buy_open': float(buy_query.open) if buy_query.open else None,
                            'buy_close': float(buy_query.close) if buy_query.close else None,
                            'buy_change_pct': float(buy_query.change_pct) if buy_query.change_pct else None,
                            'buy_vol': float(buy_query.vol) if buy_query.vol else None,
                            'buy_ma5': float(buy_query.ma5) if buy_query.ma5 else None,
                            'buy_ma10': float(buy_query.ma10) if buy_query.ma10 else None,
                            'buy_ma20': float(buy_query.ma20) if buy_query.ma20 else None,
                            # 止损日特征
                            'stop_loss_close': stop_loss_close,
                            'stop_loss_change_pct': stop_loss_change,
                            'stop_loss_ma5': stop_loss_ma5,
                            # 计算特征
                            'buy_price_vs_signal_close_pct': ((float(buy_query.open) - float(signal_query.today_close)) / float(signal_query.today_close) * 100) if buy_query.open and signal_query.today_close else None,
                            'buy_below_ma5': float(buy_query.open) < float(buy_query.ma5) if buy_query.open and buy_query.ma5 else None,
                            'buy_below_ma10': float(buy_query.open) < float(buy_query.ma10) if buy_query.open and buy_query.ma10 else None,
                            'buy_below_ma20': float(buy_query.open) < float(buy_query.ma20) if buy_query.open and buy_query.ma20 else None,
                        }
                        all_features.append(features)
                        continue
                
                # 方法2：如果交易记录表中找不到，尝试从信号日期查找（兼容旧逻辑）
                try:
                    signal_date = datetime.strptime(sell_date_str, '%Y-%m-%d').date()
                except:
                    continue
                
                # 获取买入日期（信号日期的下一个交易日）
                buy_date = self._get_next_trading_date(session, signal_date)
                if not buy_date:
                    continue
                
                # 获取信号数据
                signal_query = session.query(FactLimitUpVolumeShrink).filter(
                    FactLimitUpVolumeShrink.ts_code == ts_code,
                    FactLimitUpVolumeShrink.trade_date == signal_date,
                    FactLimitUpVolumeShrink.strategy_type == 'cyb_rise_shrink'
                ).first()
                
                if not signal_query:
                    continue
                
                # 获取买入日数据
                buy_query = session.query(
                    FactDailyPriceQfq.open,
                    FactDailyPriceQfq.close,
                    FactDailyPriceQfq.high,
                    FactDailyPriceQfq.low,
                    FactDailyPriceQfq.change_pct,
                    FactDailyPriceQfq.vol,
                    FactDailyPriceQfq.amount,
                    FactDailyPriceQfq.ma5,
                    FactDailyPriceQfq.ma10,
                    FactDailyPriceQfq.ma20
                ).filter(
                    FactDailyPriceQfq.ts_code == ts_code,
                    FactDailyPriceQfq.trade_date == buy_date
                ).first()
                
                if not buy_query:
                    continue
                
                # 获取买入后5天的数据，查找止损日期
                current_date = buy_date
                days_count = 0
                for i in range(10):  # 最多查找10天
                    current_date = self._get_next_trading_date(session, current_date)
                    if not current_date:
                        break
                    
                    days_count += 1
                    
                    day_query = session.query(
                        FactDailyPriceQfq.close,
                        FactDailyPriceQfq.change_pct,
                        FactDailyPriceQfq.ma5
                    ).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == current_date
                    ).first()
                    
                    if day_query and buy_query and buy_query.open:
                        day_close = float(day_query.close) if day_query.close else None
                        if day_close:
                            profit_pct = (day_close - float(buy_query.open)) / float(buy_query.open) * 100
                            
                            # 如果亏损达到-10%，且日期匹配，记录这一天
                            if profit_pct <= -10.0 and current_date == sell_date:
                                day_change = float(day_query.change_pct) if day_query.change_pct else None
                                day_ma5 = float(day_query.ma5) if day_query.ma5 else None
                                
                                features = {
                                    'ts_code': ts_code,
                                    'signal_date': signal_date.isoformat(),
                                    'buy_date': buy_date.isoformat(),
                                    'stop_loss_date': current_date.isoformat(),
                                    'days_to_stop_loss': days_count,
                                    # 信号特征
                                    'signal_volume_ratio': float(signal_query.volume_ratio) if signal_query.volume_ratio else None,
                                    'signal_change_pct': float(signal_query.today_change_pct) if signal_query.today_change_pct else None,
                                    'signal_close': float(signal_query.today_close) if signal_query.today_close else None,
                                    # 买入日特征
                                    'buy_open': float(buy_query.open) if buy_query.open else None,
                                    'buy_close': float(buy_query.close) if buy_query.close else None,
                                    'buy_change_pct': float(buy_query.change_pct) if buy_query.change_pct else None,
                                    'buy_vol': float(buy_query.vol) if buy_query.vol else None,
                                    'buy_ma5': float(buy_query.ma5) if buy_query.ma5 else None,
                                    'buy_ma10': float(buy_query.ma10) if buy_query.ma10 else None,
                                    'buy_ma20': float(buy_query.ma20) if buy_query.ma20 else None,
                                    # 止损日特征
                                    'stop_loss_close': day_close,
                                    'stop_loss_change_pct': day_change,
                                    'stop_loss_ma5': day_ma5,
                                    # 计算特征
                                    'buy_price_vs_signal_close_pct': ((float(buy_query.open) - float(signal_query.today_close)) / float(signal_query.today_close) * 100) if buy_query.open and signal_query.today_close else None,
                                    'buy_below_ma5': float(buy_query.open) < float(buy_query.ma5) if buy_query.open and buy_query.ma5 else None,
                                    'buy_below_ma10': float(buy_query.open) < float(buy_query.ma10) if buy_query.open and buy_query.ma10 else None,
                                    'buy_below_ma20': float(buy_query.open) < float(buy_query.ma20) if buy_query.open and buy_query.ma20 else None,
                                }
                                all_features.append(features)
                                break
            
            if not all_features:
                result['message'] = '未找到相关数据'
                return result
            
            # 分析共同特征
            result['analysis'] = all_features
            
            # 统计共同特征
            common_features = {
                'avg_days_to_stop_loss': np.mean([f['days_to_stop_loss'] for f in all_features]),
                'avg_signal_volume_ratio': np.mean([f['signal_volume_ratio'] for f in all_features if f['signal_volume_ratio']]),
                'avg_signal_change_pct': np.mean([f['signal_change_pct'] for f in all_features if f['signal_change_pct']]),
                'avg_buy_change_pct': np.mean([f['buy_change_pct'] for f in all_features if f['buy_change_pct']]),
                'avg_buy_price_vs_signal_close_pct': np.mean([f['buy_price_vs_signal_close_pct'] for f in all_features if f['buy_price_vs_signal_close_pct']]),
                'buy_below_ma5_count': sum([1 for f in all_features if f.get('buy_below_ma5')]),
                'buy_below_ma10_count': sum([1 for f in all_features if f.get('buy_below_ma10')]),
                'buy_below_ma20_count': sum([1 for f in all_features if f.get('buy_below_ma20')]),
            }
            
            result['common_features'] = common_features
            
            # 生成规避建议
            suggestions = []
            
            # 建议1：买入价低于均线
            if common_features['buy_below_ma5_count'] / len(all_features) > 0.5:
                suggestions.append({
                    'type': '买入时机',
                    'priority': '高',
                    'description': f"{common_features['buy_below_ma5_count']}/{len(all_features)}只股票买入价低于5日均线",
                    'suggestion': '买入前检查：如果买入价低于5日均线，跳过买入（趋势可能转弱）'
                })
            
            if common_features['buy_below_ma10_count'] / len(all_features) > 0.5:
                suggestions.append({
                    'type': '买入时机',
                    'priority': '高',
                    'description': f"{common_features['buy_below_ma10_count']}/{len(all_features)}只股票买入价低于10日均线",
                    'suggestion': '买入前检查：如果买入价低于10日均线，跳过买入（中期趋势转弱）'
                })
            
            # 建议2：买入日跌幅过大
            avg_buy_change = common_features['avg_buy_change_pct']
            if avg_buy_change < -2.0:
                suggestions.append({
                    'type': '买入时机',
                    'priority': '高',
                    'description': f'平均买入日跌幅: {avg_buy_change:.2f}%',
                    'suggestion': '买入前检查：如果买入日跌幅超过-2%，跳过买入（可能继续下跌）'
                })
            
            # 建议3：买入价相对信号日收盘价过高
            avg_buy_vs_signal = common_features['avg_buy_price_vs_signal_close_pct']
            if avg_buy_vs_signal > 3.0:
                suggestions.append({
                    'type': '买入价格',
                    'priority': '中',
                    'description': f'平均买入价相对信号日收盘价涨幅: {avg_buy_vs_signal:.2f}%',
                    'suggestion': '买入前检查：如果买入价超过信号日收盘价3%，跳过买入（买入点过高）'
                })
            
            # 建议4：止损时间过短
            avg_days = common_features['avg_days_to_stop_loss']
            if avg_days < 2.0:
                suggestions.append({
                    'type': '持有时间',
                    'priority': '中',
                    'description': f'平均{avg_days:.1f}天就止损',
                    'suggestion': '这些股票买入后很快止损，建议：1) 买入前更严格筛选 2) 考虑更早的止损（如-5%）'
                })
            
            # 建议5：信号日涨幅过大
            avg_signal_change = common_features['avg_signal_change_pct']
            if avg_signal_change > 15.0:
                suggestions.append({
                    'type': '信号质量',
                    'priority': '中',
                    'description': f'平均信号日涨幅: {avg_signal_change:.2f}%',
                    'suggestion': '信号日涨幅过大可能不是好的买入时机，建议：如果信号日涨幅>15%，跳过买入'
                })
            
            result['suggestions'] = suggestions
            
            return result
            
        except Exception as e:
            logger.error(f"分析止损股票失败: {e}", exc_info=True)
            result['error'] = '分析失败'
            return result
        finally:
            session.close()
    
    def _simulate_trade(
        self,
        signal: Dict,
        price_data: Dict[str, pd.DataFrame],
        profit_target: float,
        stop_loss: float,
        max_hold_days: int,
        session: Session,
        sell_strategy: str = 'profit_stop',
        strategy_type: str = 'mainboard_limit_up'
    ) -> Optional[Dict]:
        """
        模拟单只股票交易
        
        Args:
            signal: 信号数据
            price_data: 价格数据字典
            profit_target: 目标收益率
            stop_loss: 止损比例
            max_hold_days: 最大持有天数
            session: 数据库会话
        
        Returns:
            Dict: 交易结果，如果无法完成交易则返回None
        """
        ts_code = signal['ts_code']
        signal_date = signal['signal_date']
        
        # 获取下一个交易日作为买入日期
        buy_date = self._get_next_trading_date(session, signal_date)
        if not buy_date:
            logger.debug(f"{ts_code} 无法找到买入日期（信号日期: {signal_date}）")
            return None
        
        # 获取该股票的价格数据
        if ts_code not in price_data:
            logger.debug(f"{ts_code} 没有价格数据")
            return None
        
        stock_prices = price_data[ts_code]
        
        # 找到买入日期的价格（可能需要延后，如果买入日开盘涨停或开盘价无效或涨幅不在2%-6%范围内）
        # 注意：如果买入日停牌，直接跳过，不延后
        # 买入日涨幅必须在2%-6%之间，优先选择涨幅接近2%的日期
        max_retry_days = 10  # 最多延后10个交易日（因为需要找到涨幅在2%-6%范围内的日期）
        best_buy_row = None  # 记录涨幅最接近2%的买入日期
        best_buy_date = None
        best_change_diff = float('inf')  # 记录与2%的最小差值
        
        current_check_date = buy_date
        for retry in range(max_retry_days):
            if retry > 0:
                current_check_date = self._get_next_trading_date(session, current_check_date)
                if not current_check_date:
                    break
            
            buy_row = stock_prices[stock_prices['trade_date'] == current_check_date]
            
            if buy_row.empty:
                logger.debug(f"{ts_code} 买入日期 {current_check_date} 没有价格数据，尝试延后")
                continue
            
            buy_row_data = buy_row.iloc[0]
            
            # 检查是否停牌（如果停牌，直接跳过，不延后）
            if buy_row_data.get('is_suspended', False):
                logger.info(f"{ts_code} 买入日期 {current_check_date} 停牌，跳过买入（不延后）")
                return None
            
            # 检查开盘价是否有效
            buy_price = buy_row_data['open']
            if pd.isna(buy_price) or buy_price <= 0:
                logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘价无效: {buy_price}，延后到下一个交易日")
                continue
            
            # 检查是否开盘涨停（开盘价等于或接近涨停价，可能买不到）
            # 获取前一日收盘价用于判断涨停
            prev_close = None
            buy_idx = buy_row.index[0]
            if buy_idx > 0:
                # 向前查找上一个交易日
                for prev_idx in range(buy_idx - 1, -1, -1):
                    prev_row = stock_prices.iloc[prev_idx]
                    if not prev_row.get('is_suspended', False):
                        prev_close_val = prev_row.get('close')
                        if not pd.isna(prev_close_val) and prev_close_val > 0:
                            prev_close = prev_close_val
                            break
            
            # 如果找到前一日收盘价，判断是否开盘涨停
            if prev_close and prev_close > 0:
                code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                is_cyb = code_part.startswith('300') or code_part.startswith('688')
                limit_up_threshold = 0.195 if is_cyb else 0.095  # 19.5% 或 9.5%
                
                # 计算开盘价相对前一日收盘价的涨幅
                open_change_pct = (buy_price - prev_close) / prev_close
                
                # 如果开盘涨幅接近或达到涨停（>= 涨停阈值 - 0.1%，考虑精度问题）
                if open_change_pct >= (limit_up_threshold - 0.001):
                    logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘涨停（开盘价: {buy_price:.2f}, 前收盘: {prev_close:.2f}, 涨幅: {open_change_pct*100:.2f}%），可能买不到，延后到下一个交易日")
                    continue
            
            # 买入日涨幅检查：买入日涨幅必须在2%-6%之间，优先选择涨幅接近2%的日期
            # 注意：这里检查的是"盘中涨幅"，而不是收盘涨幅
            # 由于只有日线数据，我们检查：
            # 1. 开盘涨幅（开盘价相对前收盘的涨幅）- 如果开盘涨幅在2%-6%之间，可以在开盘时买入
            # 2. 盘中最低涨幅（最低价相对前收盘的涨幅）- 如果盘中曾经到过2%-6%的范围，说明有机会买入
            
            if prev_close and prev_close > 0:
                # 计算开盘涨幅
                open_change_pct_val = (buy_price - prev_close) / prev_close * 100
                
                # 计算盘中最低涨幅（通过最低价）
                buy_low = buy_row_data.get('low')
                low_change_pct_val = None
                if not pd.isna(buy_low) and buy_low > 0:
                    low_change_pct_val = (buy_low - prev_close) / prev_close * 100
                
                # 判断是否符合买入条件
                # 条件1：开盘涨幅在2%-6%之间（最优情况，开盘就可以买入）
                # 条件2：开盘涨幅 < 2%，但盘中最低涨幅在2%-6%之间（说明盘中曾经到过2%，可以在2%时买入）
                # 条件3：开盘涨幅 > 6%，但盘中最低涨幅在2%-6%之间（说明盘中曾经到过这个范围，可以在最低价附近买入）
                
                can_buy = False
                buy_change_pct_for_calc = None  # 用于计算与2%的差值
                
                if 2.0 <= open_change_pct_val <= 6.0:
                    # 开盘涨幅在范围内，最优情况
                    can_buy = True
                    buy_change_pct_for_calc = open_change_pct_val
                    logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘涨幅 {open_change_pct_val:.2f}% 在2%-6%范围内，符合买入条件")
                elif open_change_pct_val < 2.0 and low_change_pct_val is not None and 2.0 <= low_change_pct_val <= 6.0:
                    # 开盘涨幅 < 2%，但盘中最低涨幅在范围内（说明盘中曾经到过2%，可以在2%时买入）
                    can_buy = True
                    buy_change_pct_for_calc = low_change_pct_val
                    logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘涨幅 {open_change_pct_val:.2f}%，盘中最低涨幅 {low_change_pct_val:.2f}% 在2%-6%范围内，符合买入条件")
                elif open_change_pct_val > 6.0 and low_change_pct_val is not None and 2.0 <= low_change_pct_val <= 6.0:
                    # 开盘涨幅 > 6%，但盘中最低涨幅在范围内（说明盘中曾经到过这个范围）
                    can_buy = True
                    buy_change_pct_for_calc = low_change_pct_val
                    logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘涨幅 {open_change_pct_val:.2f}%，盘中最低涨幅 {low_change_pct_val:.2f}% 在2%-6%范围内，符合买入条件")
                
                if can_buy and buy_change_pct_for_calc is not None:
                    current_diff = abs(buy_change_pct_for_calc - 2.0)
                    # 如果这个日期涨幅更接近2%，更新最佳买入日期
                    if current_diff < best_change_diff:
                        best_buy_row = buy_row_data
                        best_buy_date = current_check_date
                        best_change_diff = current_diff
                        logger.debug(f"{ts_code} 找到符合条件的买入日期 {current_check_date}，涨幅 {buy_change_pct_for_calc:.2f}%（距离2%的差值: {current_diff:.2f}%）")
                    # 继续查找，看是否有更接近2%的日期（最多查找10天）
                    continue
                else:
                    # 如果涨幅不在范围内，继续查找
                    low_change_str = f"{low_change_pct_val:.2f}%" if low_change_pct_val is not None else "N/A"
                    logger.debug(f"{ts_code} 买入日期 {current_check_date} 开盘涨幅 {open_change_pct_val:.2f}%，盘中最低涨幅 {low_change_str}，不在2%-6%范围内，继续查找")
                    continue
            else:
                # 如果前收盘价缺失，无法计算涨幅，继续查找
                logger.debug(f"{ts_code} 买入日期 {current_check_date} 前收盘价缺失，无法计算涨幅，继续查找")
                continue
        
        # 如果找到了符合条件的买入日期（涨幅在2%-6%范围内），使用最佳日期
        if best_buy_row is not None and best_buy_date is not None:
            # 重新从stock_prices中获取完整的DataFrame行
            buy_row = stock_prices[stock_prices['trade_date'] == best_buy_date]
            buy_date_final = best_buy_date
            
            # 计算最终买入时的涨幅（用于日志显示）
            # 获取前收盘价
            buy_idx_final = buy_row.index[0]
            prev_close_final = None
            if buy_idx_final > 0:
                for prev_idx in range(buy_idx_final - 1, -1, -1):
                    prev_row = stock_prices.iloc[prev_idx]
                    if not prev_row.get('is_suspended', False):
                        prev_close_val = prev_row.get('close')
                        if not pd.isna(prev_close_val) and prev_close_val > 0:
                            prev_close_final = prev_close_val
                            break
            
            if prev_close_final and prev_close_final > 0:
                buy_price_final = buy_row.iloc[0]['open']
                final_open_change_pct = (buy_price_final - prev_close_final) / prev_close_final * 100
                logger.info(f"{ts_code} 最终选择买入日期 {best_buy_date}，开盘涨幅 {final_open_change_pct:.2f}%（最接近2%的买入点）")
            else:
                logger.info(f"{ts_code} 最终选择买入日期 {best_buy_date}（涨幅在2%-6%范围内）")
        else:
            # 如果没有找到符合条件的日期，返回None
            logger.info(f"{ts_code} 在 {max_retry_days} 个交易日内未找到涨幅在2%-6%范围内的买入日期，跳过买入")
            return None
        
        if buy_row is None or buy_row.empty:
            logger.debug(f"{ts_code} 无法找到合适的买入日期")
            return None
        
        # 使用最终确定的买入日期和价格
        buy_date = buy_date_final
        buy_price = buy_row.iloc[0]['open']
        
        # 再次确认买入价格有效（双重检查）
        if pd.isna(buy_price) or buy_price <= 0:
            logger.debug(f"{ts_code} 买入价格无效: {buy_price}")
            return None
        
        # 买入前再次检查ST股票（双重保险，防止信号生成时股票名称还没有ST前缀）
        try:
            stock_info = session.query(
                DimStock.name
            ).filter(
                DimStock.ts_code == ts_code
            ).first()
            
            if stock_info and stock_info.name:
                stock_name_upper = stock_info.name.upper()
                # 检查是否为ST股票（名称包含ST或*ST）
                if 'ST' in stock_name_upper or '*ST' in stock_name_upper:
                    logger.debug(f"{ts_code} 买入前检查发现ST股票（名称: {stock_info.name}），跳过买入")
                    return None
        except Exception as e:
            logger.warning(f"{ts_code} 买入前检查ST股票失败: {e}，继续执行买入逻辑")
        
        # 买入逻辑：如果开盘价高于昨日收盘价3%，则不买入（以低吸为主）
        # 【已注释】去掉排除开盘价>3%的股票的限制
        # signal_close = signal.get('signal_close')
        # if signal_close and signal_close > 0:
        #     max_buy_price = signal_close * 1.03  # 昨日收盘价的103%
        #     if buy_price > max_buy_price:
        #         logger.debug(f"{ts_code} 开盘价 {buy_price:.2f} 高于昨日收盘价 {signal_close:.2f} 的3%（{max_buy_price:.2f}），跳过买入")
        #         return None
        
        # 买入逻辑：根据策略类型分别处理
        signal_close = signal.get('signal_close')
        if signal_close and signal_close > 0:
            if strategy_type == 'cyb_rise_shrink':
                # 创业板策略买入逻辑
                # 买入价格不能超过信号日收盘价的5%
                max_buy_price_from_signal = signal_close * 1.05  # 信号日收盘价的105%
                if buy_price > max_buy_price_from_signal:
                    logger.info(f"{ts_code} 买入价 {buy_price:.2f} 超过信号日收盘价 {signal_close:.2f} 的5%（{max_buy_price_from_signal:.2f}），买入点过高，跳过买入")
                    return None
                
                # 风险规避1：买入价超过信号日收盘价3%时跳过（根据止损股票分析）
                if buy_price > signal_close * 1.03:
                    logger.info(f"{ts_code} 买入价 {buy_price:.2f} 超过信号日收盘价 {signal_close:.2f} 的3%，买入点过高，跳过买入（风险规避）")
                    return None
                
                # 注意：创业板策略不检查买入价低于信号日收盘价95%的条件（允许低开）
            else:
                # 主板策略买入逻辑
                # 如果买入日开盘价低于信号日收盘价的95%（即低开超过5%），说明买入日大幅低开，跳过买入
                min_buy_price_from_signal = signal_close * 0.95
                if buy_price < min_buy_price_from_signal:
                    logger.info(f"{ts_code} 买入价 {buy_price:.2f} 低于信号日收盘价 {signal_close:.2f} 的95%（{min_buy_price_from_signal:.2f}），买入日大幅低开，跳过买入")
                    return None
        
        # 获取信号中的涨停日期和信号日期（用于后续筛选）
        limit_up_date = signal.get('limit_up_date')
        signal_date = signal.get('signal_date')
        
        # 买入筛选优化1：检查信号日期是否是止跌日（仅主板策略：信号日期涨幅必须 > 0）
        # 创业板策略：不限制涨幅范围
        signal_change_pct = signal.get('today_change_pct')
        if signal_change_pct is None:
            logger.info(f"{ts_code} 信号日期涨幅数据缺失，跳过买入")
            return None
        
        # 主板策略：止跌日判断（涨幅必须 > 0）
        if strategy_type == 'mainboard_limit_up':
            if signal_change_pct <= 0:
                logger.info(f"{ts_code} 信号日期不是止跌日（涨幅: {signal_change_pct:.2f}%，未上涨），跳过买入")
                return None
            
            # 买入筛选优化2：检查信号日期涨幅是否过大（如果信号日期涨幅>5%，可能不是好的买入时机）
            if signal_change_pct > 5.0:
                logger.info(f"{ts_code} 信号日期涨幅过大({signal_change_pct:.2f}%)，跳过买入")
                return None
        
        # 买入时机优化2：风险规避检查（根据止损股票分析结果）
        # 重新获取买入日的数据（确保使用最终确定的买入日期）
        buy_row_final = stock_prices[stock_prices['trade_date'] == buy_date]
        if not buy_row_final.empty:
            buy_row_data = buy_row_final.iloc[0]
            buy_day_ma5 = buy_row_data.get('ma5')
            buy_day_ma10 = buy_row_data.get('ma10')
            buy_day_ma20 = buy_row_data.get('ma20')
            buy_day_change_pct = buy_row_data.get('change_pct')
            
            # 风险规避1：买入价低于5日均线（趋势可能转弱）
            if strategy_type == 'cyb_rise_shrink':
                if not pd.isna(buy_day_ma5) and buy_day_ma5 > 0 and not pd.isna(buy_price) and buy_price > 0:
                    if buy_price < buy_day_ma5:
                        logger.info(f"{ts_code} 买入价 {buy_price:.2f} 低于5日均线 {buy_day_ma5:.2f}，趋势可能转弱，跳过买入（风险规避）")
                        return None
                
                # 风险规避2：买入价低于10日均线（中期趋势转弱）
                if not pd.isna(buy_day_ma10) and buy_day_ma10 > 0 and not pd.isna(buy_price) and buy_price > 0:
                    if buy_price < buy_day_ma10:
                        logger.info(f"{ts_code} 买入价 {buy_price:.2f} 低于10日均线 {buy_day_ma10:.2f}，中期趋势转弱，跳过买入（风险规避）")
                        return None
                
                # 风险规避3：买入日跌幅超过-2%（可能继续下跌）
                if not pd.isna(buy_day_change_pct):
                    if buy_day_change_pct < -2.0:
                        logger.info(f"{ts_code} 买入日跌幅 {buy_day_change_pct:.2f}% 超过-2%，可能继续下跌，跳过买入（风险规避）")
                        return None
            
            # 检查20日线数据是否有效（主板策略）
            if pd.isna(buy_day_ma20) or buy_day_ma20 is None or buy_day_ma20 <= 0:
                # 20日线数据缺失或无效，跳过买入（必须要有20日线数据才能买入）
                logger.info(f"{ts_code} 买入日({buy_date})20日线数据缺失或无效(ma20={buy_day_ma20})，无法进行20日线检查，跳过买入")
                return None
            elif (not pd.isna(buy_price) and buy_price > 0):
                # 20日线数据有效，进行检查
                if buy_price < buy_day_ma20:
                    logger.info(f"{ts_code} 买入日({buy_date})开盘价({buy_price:.2f})低于20日线({buy_day_ma20:.2f})，中期趋势转弱，跳过买入")
                    return None
                else:
                    logger.debug(f"{ts_code} 买入日({buy_date})开盘价({buy_price:.2f})高于20日线({buy_day_ma20:.2f})，通过20日线检查")
            else:
                logger.warning(f"{ts_code} 买入日({buy_date})买入价无效(buy_price={buy_price})，无法进行20日线检查")
                return None
        else:
            logger.warning(f"{ts_code} 买入日({buy_date})价格数据缺失，无法检查20日线")
            return None
        
        # 买入筛选：检查买入价是否低于涨停价的80%（仅主板策略）
        # 如果买入价低于涨停价的80%，说明价格下跌过多，可能趋势转弱，跳过买入
        # 注意：创业板策略不检查此条件
        if strategy_type == 'mainboard_limit_up':
            limit_up_date = signal.get('limit_up_date')
            if limit_up_date:
                try:
                    # 解析涨停日期
                    if isinstance(limit_up_date, str):
                        limit_up_date_parsed = datetime.strptime(limit_up_date, '%Y-%m-%d').date()
                    else:
                        limit_up_date_parsed = limit_up_date
                    
                    # 查询涨停日的收盘价（涨停价）
                    limit_up_price_query = session.query(
                        FactDailyPriceQfq.close
                    ).filter(
                        FactDailyPriceQfq.ts_code == ts_code,
                        FactDailyPriceQfq.trade_date == limit_up_date_parsed
                    ).first()
                    
                    if limit_up_price_query and limit_up_price_query.close:
                        limit_up_price = float(limit_up_price_query.close)
                        
                        # 计算买入价相对于涨停价的比例
                        min_buy_price_from_limit_up = limit_up_price * 0.80
                        
                        if buy_price < min_buy_price_from_limit_up:
                            logger.info(f"{ts_code} 买入价({buy_price:.2f})低于涨停价({limit_up_price:.2f})的80%({min_buy_price_from_limit_up:.2f})，价格下跌过多，跳过买入")
                            return None
                        else:
                            logger.debug(f"{ts_code} 买入价({buy_price:.2f})高于涨停价({limit_up_price:.2f})的80%({min_buy_price_from_limit_up:.2f})，通过涨停价检查")
                    else:
                        # 如果查询不到涨停价，记录警告但保留信号（保守策略）
                        logger.warning(f"{ts_code} 无法查询涨停日({limit_up_date_parsed})的收盘价，跳过涨停价检查，保留信号")
                except Exception as e:
                    logger.warning(f"{ts_code} 查询涨停价失败（涨停日期: {limit_up_date}），错误: {e}，跳过涨停价检查，保留信号")
        
        # 从买入日期开始模拟交易
        buy_idx = buy_row.index[0]
        hold_days = 0
        trading_days_held = 0
        
        # 用于炸板判断：记录买入后出现的涨停价
        # 炸板的正确逻辑：买入后如果某天涨停了，之后价格跌破这个涨停价，才判断为炸板
        post_buy_limit_up_price = None  # 买入后出现的涨停价
        
        # 初始化移动止损价（用于策略1）
        trailing_stop_loss_price = None
        
        for i in range(buy_idx + 1, len(stock_prices)):
            current_row = stock_prices.iloc[i]
            current_date = current_row['trade_date']
            
            # 跳过停牌日
            if current_row.get('is_suspended', False):
                continue
            
            trading_days_held += 1
            
            current_high = current_row['high']
            current_low = current_row['low']
            current_close = current_row['close']
            current_open = current_row['open']
            current_change_pct = current_row.get('change_pct')  # 涨跌幅
            
            # 检查买入后是否出现涨停（用于炸板判断）
            # 判断是否涨停：涨跌幅 >= 9.5%（主板）或 >= 19.5%（创业板/科创板）
            if not pd.isna(current_change_pct) and current_change_pct is not None:
                code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                is_cyb = code_part.startswith('300') or code_part.startswith('688')
                limit_up_threshold = 19.5 if is_cyb else 9.5
                
                # 如果当天涨停，记录涨停价（收盘价）
                if current_change_pct >= limit_up_threshold:
                    if not pd.isna(current_close) and current_close > 0:
                        post_buy_limit_up_price = float(current_close)
                        logger.debug(f"{ts_code} 买入后涨停（日期: {current_date}, 涨停价: {post_buy_limit_up_price:.2f}, 涨跌幅: {current_change_pct:.2f}%）")
            
            # 卖出原则：涨停后炸板就立马卖掉（优先检查，最高优先级）
            # 只有当买入后出现过涨停，且当前价格跌破涨停价时，才判断为炸板
            if post_buy_limit_up_price and post_buy_limit_up_price > 0:
                # 如果当前收盘价跌破买入后的涨停价，说明炸板了，立即卖出
                if not pd.isna(current_close) and current_close > 0:
                    if current_close < post_buy_limit_up_price:
                        sell_date = current_date
                        sell_price = current_close
                        exit_reason = 'limit_up_broken'  # 炸板
                        logger.debug(f"{ts_code} 炸板卖出（买入后涨停价: {post_buy_limit_up_price:.2f}, 当前收盘价: {current_close:.2f}）")
                        break
            
            # 根据卖出策略执行不同的卖出逻辑
            if sell_strategy == 'ma5_loss':
                # 策略2：破跌5日线或亏损5%，从第三天开始如果没有涨停就退出，涨停就继续持有
                current_ma5 = current_row.get('ma5')
                
                # 检查是否亏损5%（优先检查，因为这是硬止损，必须在所有其他检查之前）
                # 计算止损价格（买入价的95%）
                stop_loss_price = buy_price * 0.95
                
                # 检查收盘价是否低于止损价（如果收盘价已经低于止损价，说明亏损超过10%）
                if not pd.isna(current_close) and current_close > 0:
                    if current_close <= stop_loss_price:
                        sell_date = current_date
                        # 使用止损价格卖出，确保亏损不超过止损线
                        sell_price = stop_loss_price
                        exit_reason = 'loss_5pct'
                        logger.debug(f"{ts_code} 亏损5%止损（买入价: {buy_price:.2f}, 止损价: {stop_loss_price:.2f}, 收盘价: {current_close:.2f}）")
                        break
                
                # 也检查当日最低价是否触及止损价（如果最低价触及止损价，也应该止损）
                if not pd.isna(current_low) and current_low > 0:
                    if current_low <= stop_loss_price:
                        sell_date = current_date
                        # 使用止损价格卖出，确保亏损不超过止损线
                        sell_price = stop_loss_price
                        exit_reason = 'loss_5pct'
                        logger.debug(f"{ts_code} 亏损5%止损（买入价: {buy_price:.2f}, 止损价: {stop_loss_price:.2f}, 最低价: {current_low:.2f}）")
                        break
                
                # 从第三天开始检查：如果涨停就继续持有，如果未涨停但持续上涨也继续持有，否则卖出
                if trading_days_held >= 2:  # 买入后第三天开始（买入日是第0天，买入后第一天是第1天，买入后第二天是第2天）
                    # 获取昨日收盘价（用于判断是否持续上涨）
                    prev_close = None
                    prev_idx = i - 1
                    while prev_idx >= buy_idx:
                        prev_row = stock_prices.iloc[prev_idx]
                        if not prev_row.get('is_suspended', False):
                            prev_close_val = prev_row.get('close')
                            if not pd.isna(prev_close_val) and prev_close_val > 0:
                                prev_close = prev_close_val
                                break
                        prev_idx -= 1
                    
                    if prev_close is None:
                        buy_row_close = stock_prices.iloc[buy_idx].get('close')
                        if not pd.isna(buy_row_close) and buy_row_close > 0:
                            prev_close = buy_row_close
                    
                    # 判断是否涨停
                    is_limit_up = False
                    current_change_pct = current_row.get('change_pct')
                    
                    if current_change_pct is not None:
                        # 判断是否创业板/科创板（300开头或688开头）
                        code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                        is_cyb = code_part.startswith('300') or code_part.startswith('688')
                        
                        # 涨停判断：主板 >= 9.5%，创业板/科创板 >= 19.5%
                        limit_up_threshold = 19.5 if is_cyb else 9.5
                        if current_change_pct >= limit_up_threshold:
                            is_limit_up = True
                            logger.debug(f"{ts_code} 买入后第{trading_days_held + 1}天涨停（涨幅{current_change_pct:.2f}%），继续持有")
                    else:
                        # 如果没有涨跌幅数据，通过昨日收盘价和今日收盘价计算
                        if prev_close and prev_close > 0 and not pd.isna(current_close) and current_close > 0:
                            change_pct_calc = ((current_close - prev_close) / prev_close) * 100
                            code_part = ts_code.split('.')[0] if '.' in ts_code else ts_code
                            is_cyb = code_part.startswith('300') or code_part.startswith('688')
                            limit_up_threshold = 19.5 if is_cyb else 9.5
                            
                            if change_pct_calc >= limit_up_threshold:
                                is_limit_up = True
                                logger.debug(f"{ts_code} 买入后第{trading_days_held + 1}天涨停（涨幅{change_pct_calc:.2f}%），继续持有")
                    
                    # 如果未涨停，检查是否持续上涨
                    if not is_limit_up:
                        # 持续上涨的判断：今日收盘价 > 昨日收盘价
                        is_rising = False
                        if prev_close is not None and prev_close > 0 and not pd.isna(current_close) and current_close > 0:
                            if current_close > prev_close:
                                is_rising = True
                                logger.debug(f"{ts_code} 买入后第{trading_days_held + 1}天未涨停，但持续上涨（昨日收盘: {prev_close:.2f}, 今日收盘: {current_close:.2f}），继续持有")
                        
                        if not is_rising:
                            # 未涨停且未持续上涨，卖出
                            sell_date = current_date
                            sell_price = current_close
                            exit_reason = 'day3_no_limit_up'
                            logger.debug(f"{ts_code} 买入后第{trading_days_held + 1}天未涨停且未持续上涨，卖出")
                            break
                
                # 检查是否破跌5日线（收盘价跌破5日均线，且今日收盘价低于昨日收盘价）
                # 需要确保有5日均线数据
                if not pd.isna(current_close) and current_close > 0:
                    if not pd.isna(current_ma5) and current_ma5 > 0:
                        # 获取昨日收盘价（前一个交易日的收盘价）
                        prev_close = None
                        # 向前查找上一个交易日（跳过停牌日）
                        prev_idx = i - 1
                        while prev_idx >= buy_idx:
                            prev_row = stock_prices.iloc[prev_idx]
                            if not prev_row.get('is_suspended', False):
                                prev_close_val = prev_row.get('close')
                                if not pd.isna(prev_close_val) and prev_close_val > 0:
                                    prev_close = prev_close_val
                                break
                            prev_idx -= 1
                        
                        # 如果没找到前一个交易日，使用买入日的收盘价作为昨日收盘价
                        if prev_close is None:
                            buy_row_close = stock_prices.iloc[buy_idx].get('close')
                            if not pd.isna(buy_row_close) and buy_row_close > 0:
                                prev_close = buy_row_close
                        
                        # 破跌5日线的条件：1) 收盘价跌破5日均线 2) 今日收盘价低于昨日收盘价（下跌）
                        if current_close < current_ma5:
                            # 如果昨日收盘价存在，需要今日收盘价低于昨日收盘价
                            if prev_close is not None and prev_close > 0:
                                if current_close < prev_close:
                                    # 持股第1天特殊处理：如果跌幅不超过5%，破5日线可以忽略，继续持有
                                    if trading_days_held == 1:
                                        # 计算跌幅（相对于买入价）
                                        decline_pct = ((current_close - buy_price) / buy_price) * 100
                                        if decline_pct > -5.0:  # 跌幅不超过5%（即跌幅小于等于5%）
                                            logger.debug(f"{ts_code} 持股第1天破5日线，但跌幅{decline_pct:.2f}%不超过5%，继续持有")
                                            # 不卖出，继续持有，跳过破5日线检查
                                            continue  # 跳过当前循环，继续下一个交易日
                                        else:
                                            # 跌幅超过5%，执行破5日线卖出
                                            sell_date = current_date
                                            sell_price = current_close
                                            exit_reason = 'break_ma5'
                                            logger.debug(f"{ts_code} 持股第1天破5日线，跌幅{decline_pct:.2f}%超过5%，卖出")
                                            break
                                    else:
                                        # 持股第2天及以后，正常执行破5日线卖出
                                        sell_date = current_date
                                        sell_price = current_close
                                        exit_reason = 'break_ma5'
                                        break
                            else:
                                # 如果没有昨日收盘价数据
                                # 持股第1天特殊处理：如果跌幅不超过5%，破5日线可以忽略，继续持有
                                if trading_days_held == 1:
                                    decline_pct = ((current_close - buy_price) / buy_price) * 100
                                    if decline_pct > -5.0:  # 跌幅不超过5%
                                        logger.debug(f"{ts_code} 持股第1天破5日线（无昨日收盘价），但跌幅{decline_pct:.2f}%不超过5%，继续持有")
                                        # 不卖出，继续持有，跳过破5日线检查
                                        continue  # 跳过当前循环，继续下一个交易日
                                    else:
                                        # 跌幅超过5%，执行破5日线卖出
                                        sell_date = current_date
                                        sell_price = current_close
                                        exit_reason = 'break_ma5'
                                        logger.debug(f"{ts_code} 持股第1天破5日线（无昨日收盘价），跌幅{decline_pct:.2f}%超过5%，卖出")
                                        break
                                else:
                                    # 持股第2天及以后，仍然执行破跌5日线卖出（容错处理）
                                    sell_date = current_date
                                    sell_price = current_close
                                    exit_reason = 'break_ma5'
                                    break
                    # 如果5日均线数据不存在，跳过该检查（继续持有）
            elif sell_strategy == 'ma5_loss_5pct':
                # 策略3：破跌5日线或亏损5%或最大持仓5天
                current_ma5 = current_row.get('ma5')
                
                # 检查是否达到最大持有天数（5天）
                if trading_days_held >= 5:
                    sell_date = current_date
                    sell_price = current_row['close']
                    exit_reason = 'time_limit'
                    break
                
                # 检查是否亏损5%（优先检查，因为这是硬止损）
                # 计算止损价格（买入价的95%）
                stop_loss_price = buy_price * 0.95
                
                if not pd.isna(current_low) and current_low > 0:
                    # 如果当日最低价触及或跌破止损价，则止损
                    if current_low <= stop_loss_price:
                        sell_date = current_date
                        # 使用止损价格卖出，确保亏损不超过止损线
                        # 止损单应该在止损价执行，即使开盘价更低，也应该在止损价卖出
                        sell_price = stop_loss_price
                        exit_reason = 'loss_5pct'
                        break
                
                # 检查是否破跌5日线（收盘价跌破5日均线，且今日收盘价低于昨日收盘价）
                # 需要确保有5日均线数据
                if not pd.isna(current_close) and current_close > 0:
                    if not pd.isna(current_ma5) and current_ma5 > 0:
                        # 获取昨日收盘价（前一个交易日的收盘价）
                        prev_close = None
                        # 向前查找上一个交易日（跳过停牌日）
                        prev_idx = i - 1
                        while prev_idx >= buy_idx:
                            prev_row = stock_prices.iloc[prev_idx]
                            if not prev_row.get('is_suspended', False):
                                prev_close_val = prev_row.get('close')
                                if not pd.isna(prev_close_val) and prev_close_val > 0:
                                    prev_close = prev_close_val
                                break
                            prev_idx -= 1
                        
                        # 如果没找到前一个交易日，使用买入日的收盘价作为昨日收盘价
                        if prev_close is None:
                            buy_row_close = stock_prices.iloc[buy_idx].get('close')
                            if not pd.isna(buy_row_close) and buy_row_close > 0:
                                prev_close = buy_row_close
                        
                        # 破跌5日线的条件：1) 收盘价跌破5日均线 2) 今日收盘价低于昨日收盘价（下跌）
                        if current_close < current_ma5:
                            # 如果昨日收盘价存在，需要今日收盘价低于昨日收盘价
                            if prev_close is not None and prev_close > 0:
                                if current_close < prev_close:
                                    # 持股第1天特殊处理：如果跌幅不超过5%，破5日线可以忽略，继续持有
                                    if trading_days_held == 1:
                                        # 计算跌幅（相对于买入价）
                                        decline_pct = ((current_close - buy_price) / buy_price) * 100
                                        if decline_pct > -5.0:  # 跌幅不超过5%（即跌幅小于等于5%）
                                            logger.debug(f"{ts_code} 持股第1天破5日线（策略3），但跌幅{decline_pct:.2f}%不超过5%，继续持有")
                                            # 不卖出，继续持有
                                        else:
                                            # 跌幅超过5%，执行破5日线卖出
                                            sell_date = current_date
                                            sell_price = current_close
                                            exit_reason = 'break_ma5'
                                            logger.debug(f"{ts_code} 持股第1天破5日线（策略3），跌幅{decline_pct:.2f}%超过5%，卖出")
                                            break
                                    else:
                                        # 持股第2天及以后，正常执行破5日线卖出
                                        sell_date = current_date
                                        sell_price = current_close
                                        exit_reason = 'break_ma5'
                                        break
                            else:
                                # 如果没有昨日收盘价数据
                                # 持股第1天特殊处理：如果跌幅不超过5%，破5日线可以忽略，继续持有
                                if trading_days_held == 1:
                                    decline_pct = ((current_close - buy_price) / buy_price) * 100
                                    if decline_pct > -5.0:  # 跌幅不超过5%
                                        logger.debug(f"{ts_code} 持股第1天破5日线（策略3，无昨日收盘价），但跌幅{decline_pct:.2f}%不超过5%，继续持有")
                                        # 不卖出，继续持有
                                    else:
                                        # 跌幅超过5%，执行破5日线卖出
                                        sell_date = current_date
                                        sell_price = current_close
                                        exit_reason = 'break_ma5'
                                        logger.debug(f"{ts_code} 持股第1天破5日线（策略3，无昨日收盘价），跌幅{decline_pct:.2f}%超过5%，卖出")
                                        break
                                else:
                                    # 持股第2天及以后，仍然执行破跌5日线卖出（容错处理）
                                    sell_date = current_date
                                    sell_price = current_close
                                    exit_reason = 'break_ma5'
                                    break
                    # 如果5日均线数据不存在，跳过该检查（继续持有）
            elif sell_strategy == 'ma5_rising':
                # 策略4：上涨过程中不破5日线不卖，止损-5%
                current_ma5 = current_row.get('ma5')
                
                # 检查是否亏损5%（优先检查，因为这是硬止损，必须在所有其他检查之前）
                # 计算止损价格（买入价的95%）
                stop_loss_price = buy_price * 0.95
                
                # 检查收盘价是否低于止损价（如果收盘价已经低于止损价，说明亏损超过5%）
                if not pd.isna(current_close) and current_close > 0:
                    if current_close <= stop_loss_price:
                        sell_date = current_date
                        # 使用止损价格卖出，确保亏损不超过止损线
                        sell_price = stop_loss_price
                        exit_reason = 'loss_5pct'
                        logger.debug(f"{ts_code} 亏损5%止损（买入价: {buy_price:.2f}, 止损价: {stop_loss_price:.2f}, 收盘价: {current_close:.2f}）")
                        break
                
                # 也检查当日最低价是否触及止损价（如果最低价触及止损价，也应该止损）
                if not pd.isna(current_low) and current_low > 0:
                    if current_low <= stop_loss_price:
                        sell_date = current_date
                        # 使用止损价格卖出，确保亏损不超过止损线
                        sell_price = stop_loss_price
                        exit_reason = 'loss_5pct'
                        logger.debug(f"{ts_code} 亏损5%止损（买入价: {buy_price:.2f}, 止损价: {stop_loss_price:.2f}, 最低价: {current_low:.2f}）")
                        break
                
                # 检查是否破5日线（收盘价跌破5日均线）
                # 需要确保有5日均线数据
                if not pd.isna(current_close) and current_close > 0:
                    if not pd.isna(current_ma5) and current_ma5 > 0:
                        # 获取昨日收盘价（用于判断是否上涨）
                        prev_close = None
                        # 向前查找上一个交易日（跳过停牌日）
                        prev_idx = i - 1
                        while prev_idx >= buy_idx:
                            prev_row = stock_prices.iloc[prev_idx]
                            if not prev_row.get('is_suspended', False):
                                prev_close_val = prev_row.get('close')
                                if not pd.isna(prev_close_val) and prev_close_val > 0:
                                    prev_close = prev_close_val
                                    break
                            prev_idx -= 1
                        
                        # 如果没找到前一个交易日，使用买入日的收盘价作为昨日收盘价
                        if prev_close is None:
                            buy_row_close = stock_prices.iloc[buy_idx].get('close')
                            if not pd.isna(buy_row_close) and buy_row_close > 0:
                                prev_close = buy_row_close
                        
                        # 判断是否上涨：当前收盘价 > 昨日收盘价
                        is_rising = False
                        if prev_close is not None and prev_close > 0:
                            if current_close > prev_close:
                                is_rising = True
                        
                        # 判断是否破5日线：当前收盘价 < 5日均线
                        is_below_ma5 = current_close < current_ma5
                        
                        # 卖出条件：破5日线（无论是否上涨）
                        if is_below_ma5:
                            sell_date = current_date
                            sell_price = current_close
                            exit_reason = 'break_ma5'
                            prev_close_str = f"{prev_close:.2f}" if prev_close else "None"
                            logger.debug(f"{ts_code} 破5日线卖出（当前收盘: {current_close:.2f}, 5日线: {current_ma5:.2f}, 昨日收盘: {prev_close_str}, 是否上涨: {is_rising}）")
                            break
                        else:
                            # 不破5日线，继续持有（无论是否上涨）
                            prev_close_str = f"{prev_close:.2f}" if prev_close else "None"
                            logger.debug(f"{ts_code} 未破5日线，继续持有（当前收盘: {current_close:.2f}, 5日线: {current_ma5:.2f}, 昨日收盘: {prev_close_str}, 是否上涨: {is_rising}）")
                    else:
                        # 如果5日均线数据不存在，跳过该检查（继续持有）
                        logger.debug(f"{ts_code} 5日均线数据缺失，继续持有")
            else:
                # 策略1：优化后的止盈止损策略（有最大持有天数限制）
                # 重要：检查顺序必须是：止损 > 破5日线 > 止盈 > 时间限制
                # 这样才能确保止损优先于时间限制触发
                
                # 优化配置参数
                trailing_stop_config = {
                    'profit_thresholds': [0.05, 0.10, 0.15, 0.20, 0.30],
                    'stop_loss_protections': [0.0, 0.05, 0.08, 0.12, 0.20]
                }
                
                break_ma5_config = {
                    'consecutive_days_threshold': 2,
                    'volume_expand_ratio': 1.5,
                    'volume_shrink_ratio': 0.8,
                    'profit_protect_threshold': 0.0,
                    'enable_optimization': False  # 默认关闭优化，使用保守策略（破5日线就卖）
                }
                
                extend_hold_config = {
                    'profit_thresholds': [0.03, 0.08, 0.15],
                    'extended_days': [2, 5, 10],
                    'max_hold_days_limit': 15
                }
                
                # 计算当前盈利比例（用于移动止损和延长持有）
                current_profit_pct = (current_close - buy_price) / buy_price if not pd.isna(current_close) and current_close > 0 else 0.0
                
                # 动态计算最大持有天数（盈利后延长持有）
                # 如果未启用优化，使用原始最大持有天数
                if extend_hold_config.get('enable_optimization', False):
                    dynamic_max_hold_days = self._calculate_max_hold_days(
                        current_profit_pct, max_hold_days, extend_hold_config
                    )
                else:
                    dynamic_max_hold_days = max_hold_days  # 使用原始最大持有天数
                
                # 1. 优先检查是否触发止损（最重要，必须最先检查）
                # 使用移动止损：根据盈利情况动态调整止损价（默认关闭，使用原始止损）
                use_trailing_stop = trailing_stop_config.get('enable_optimization', False)  # 默认关闭
                
                if use_trailing_stop:
                    # 使用移动止损
                    if trailing_stop_loss_price is None:
                        # 第一次循环，初始化止损价
                        trailing_stop_loss_price = self._calculate_trailing_stop_loss(
                            buy_price, current_close, stop_loss, trailing_stop_config
                        )
                    else:
                        # 更新移动止损价（只上移不下移）
                        trailing_stop_loss_price = self._update_trailing_stop_loss(
                            buy_price, current_close, trailing_stop_loss_price, stop_loss, trailing_stop_config
                        )
                else:
                    # 使用原始止损（固定-10%）
                    trailing_stop_loss_price = buy_price * (1 + stop_loss)
                
                # 优先检查收盘价是否低于止损价
                if not pd.isna(current_close) and current_close > 0:
                    if current_close <= trailing_stop_loss_price:
                        sell_date = current_date
                        sell_price = trailing_stop_loss_price
                        exit_reason = 'stop_loss'
                        logger.debug(f"{ts_code} 移动止损卖出（买入价: {buy_price:.2f}, 止损价: {trailing_stop_loss_price:.2f}, 收盘价: {current_close:.2f}, 盈利: {current_profit_pct*100:.2f}%）")
                        break
                
                # 也检查当日最低价是否触及止损价
                if not pd.isna(current_low) and current_low > 0:
                    if current_low <= trailing_stop_loss_price:
                        sell_date = current_date
                        sell_price = trailing_stop_loss_price
                        exit_reason = 'stop_loss'
                        logger.debug(f"{ts_code} 移动止损卖出（买入价: {buy_price:.2f}, 止损价: {trailing_stop_loss_price:.2f}, 最低价: {current_low:.2f}, 盈利: {current_profit_pct*100:.2f}%）")
                        break
                
                # 2. 检查是否破5日线（优化后的逻辑）
                current_ma5 = current_row.get('ma5')
                current_ma10 = current_row.get('ma10')
                current_volume = current_row.get('vol', 0)
                
                # 计算平均成交量（买入后5日平均，用于成交量确认）
                avg_volume = 0.0
                if i > buy_idx:
                    volume_sum = 0.0
                    volume_count = 0
                    # 计算买入后到当前日期的平均成交量（最多5天）
                    start_idx = max(buy_idx + 1, i - 4)  # 从买入后第一天或当前日期前4天开始
                    for j in range(start_idx, i + 1):  # 包含当前日期
                        if j < len(stock_prices):
                            vol_val = stock_prices.iloc[j].get('vol', 0)
                            if not pd.isna(vol_val) and vol_val > 0:
                                volume_sum += float(vol_val)
                                volume_count += 1
                    if volume_count > 0:
                        avg_volume = volume_sum / volume_count
                
                # 获取昨日5日均线
                ma5_yesterday = None
                if i > buy_idx + 1:
                    prev_row = stock_prices.iloc[i - 1]
                    ma5_yesterday_val = prev_row.get('ma5')
                    if not pd.isna(ma5_yesterday_val) and ma5_yesterday_val > 0:
                        ma5_yesterday = float(ma5_yesterday_val)
                
                # 统计连续破5日线天数（从当前日期向前连续查找）
                consecutive_days_below_ma5 = 0
                if not pd.isna(current_ma5) and current_ma5 > 0 and current_close < current_ma5:
                    # 从当前日期向前查找，统计连续破5日线的天数
                    for j in range(i, buy_idx, -1):  # 从当前日期向前查找到买入日
                        if j < len(stock_prices) and j >= buy_idx + 1:
                            row = stock_prices.iloc[j]
                            close_val = row.get('close')
                            ma5_val = row.get('ma5')
                            if not pd.isna(close_val) and not pd.isna(ma5_val) and close_val < ma5_val:
                                consecutive_days_below_ma5 += 1
                            else:
                                break  # 如果某天没有破5日线，停止统计
                
                if not pd.isna(current_close) and current_close > 0:
                    if not pd.isna(current_ma5) and current_ma5 > 0:
                        # 使用优化后的破5日线判断逻辑
                        should_sell, exit_reason_ma5 = self._check_break_ma5_optimized(
                            current_close,
                            float(current_ma5),
                            ma5_yesterday,
                            float(current_ma10) if not pd.isna(current_ma10) and current_ma10 > 0 else None,
                            float(current_volume) if not pd.isna(current_volume) and current_volume > 0 else 0.0,
                            avg_volume,
                            buy_price,
                            consecutive_days_below_ma5,
                            break_ma5_config
                        )
                        
                        if should_sell:
                            sell_date = current_date
                            sell_price = current_close
                            exit_reason = exit_reason_ma5
                            logger.debug(f"{ts_code} 优化破5日线卖出（收盘价: {current_close:.2f}, 5日均线: {current_ma5:.2f}, 原因: {exit_reason_ma5}）")
                            break
                
                # 3. 检查是否触发止盈（使用最高价）
                if not pd.isna(current_high) and current_high > 0:
                    return_pct_high = (current_high - buy_price) / buy_price
                    if return_pct_high >= profit_target:
                        sell_date = current_date
                        sell_price = current_high  # 假设在最高价止盈
                        exit_reason = 'profit_target'
                        break
                
                # 4. 最后检查是否达到最大持有天数（动态调整）
                if trading_days_held >= dynamic_max_hold_days:
                    sell_date = current_date
                    sell_price = current_row['close']
                    exit_reason = 'time_limit'
                    logger.debug(f"{ts_code} 时间限制卖出（持有{trading_days_held}天，动态最大持有{dynamic_max_hold_days}天，盈利: {current_profit_pct*100:.2f}%）")
                    break
            
            # 如果都没有触发，继续持有
            hold_days += 1
        
        else:
            # 如果循环正常结束（没有break），说明持有到最后一天
            if sell_strategy == 'ma5_loss':
                # 策略2：如果数据结束但未触发卖出条件，使用最后一天的价格卖出
                if len(stock_prices) == 0:
                    logger.debug(f"{ts_code} 价格数据不足，无法完成交易")
                    return None
                last_row = stock_prices.iloc[-1]
                sell_date = last_row['trade_date']
                sell_price = last_row['close']
                exit_reason = 'data_end'  # 数据结束
            elif sell_strategy == 'ma5_loss_5pct':
                # 策略3：如果数据结束但未触发卖出条件，检查是否达到最大持有天数
                if len(stock_prices) == 0:
                    logger.debug(f"{ts_code} 价格数据不足，无法完成交易")
                    return None
                # 策略3有最大持有5天限制，如果数据结束但未达到5天，使用最后一天的价格卖出
                if trading_days_held < 5:
                    logger.debug(f"{ts_code} 价格数据不足，无法完成交易（持有{trading_days_held}天，需要5天）")
                    return None
                last_row = stock_prices.iloc[-1]
                sell_date = last_row['trade_date']
                sell_price = last_row['close']
                exit_reason = 'time_limit'  # 时间限制
            elif sell_strategy == 'ma5_rising':
                # 策略4：如果数据结束但未触发卖出条件，使用最后一天的价格卖出
                if len(stock_prices) == 0:
                    logger.debug(f"{ts_code} 价格数据不足，无法完成交易")
                    return None
                last_row = stock_prices.iloc[-1]
                sell_date = last_row['trade_date']
                sell_price = last_row['close']
                exit_reason = 'data_end'  # 数据结束
            else:
                # 策略1：检查是否达到最小持有天数要求
                if trading_days_held < max_hold_days:
                    # 数据不足，无法完成交易
                    logger.debug(f"{ts_code} 价格数据不足，无法完成交易（持有{trading_days_held}天）")
                    return None
                
                # 使用最后一天的价格卖出
                last_row = stock_prices.iloc[-1]
                sell_date = last_row['trade_date']
                sell_price = last_row['close']
                exit_reason = 'time_limit'
        
        # 计算收益率（使用实际卖出价）
        if pd.isna(sell_price) or sell_price <= 0:
            logger.debug(f"{ts_code} 卖出价格无效: {sell_price}")
            return None
        
        # 计算理论收益率（基于价格，不含交易成本）
        price_return_pct = (sell_price - buy_price) / buy_price
        
        # 注意：实际收益率会在资金管理部分计算，因为需要考虑交易成本
        # 这里先返回价格收益率，实际收益率会在扣除交易成本后计算
        return_pct = price_return_pct
        
        # 计算持有天数（交易日）
        hold_days = trading_days_held
        
        return {
            'ts_code': ts_code,
            'stock_name': signal['stock_name'],
            'signal_date': signal_date.isoformat(),
            'buy_date': buy_date.isoformat(),
            'buy_price': float(buy_price),
            'sell_date': sell_date.isoformat(),
            'sell_price': float(sell_price),
            'return_pct': float(return_pct),
            'hold_days': hold_days,
            'exit_reason': exit_reason,
            'is_profitable': bool(return_pct > 0)  # 转换为 Python bool，避免 numpy.bool_ 序列化错误
        }
    
    def _calculate_statistics(
        self, 
        trades: List[Dict], 
        max_drawdown: Optional[float] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        total_profit_loss_pct: Optional[float] = None
    ) -> Dict:
        """计算统计指标"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'mean_return': 0.0,
                'sharpe_ratio': 0.0,
                'annual_return': 0.0,
                'max_drawdown': 0.0
            }
        
        returns = [t['return_pct'] for t in trades]
        profitable_trades = [t for t in trades if t['is_profitable']]
        loss_trades = [t for t in trades if not t['is_profitable']]
        
        # 基础统计
        total_trades = len(trades)
        win_count = len(profitable_trades)
        loss_count = len(loss_trades)
        win_rate = win_count / total_trades if total_trades > 0 else 0.0
        
        # 收益率统计
        mean_return = np.mean(returns)
        median_return = np.median(returns)
        std_return = np.std(returns)
        
        # 盈利和亏损统计
        profit_returns = [t['return_pct'] for t in profitable_trades] if profitable_trades else []
        loss_returns = [t['return_pct'] for t in loss_trades] if loss_trades else []
        
        mean_profit = np.mean(profit_returns) if profit_returns else 0.0
        mean_loss = np.mean(loss_returns) if loss_returns else 0.0
        profit_loss_ratio = abs(mean_profit / mean_loss) if mean_loss != 0 else 0.0
        
        # 最大回撤
        if max_drawdown is not None:
            # 使用传入的最大回撤（基于实际资金管理计算）
            max_drawdown = float(max_drawdown)
            logger.debug(f"最大回撤（基于实际资金管理）：{max_drawdown:.2%}")
        else:
            # 降级：基于等权重投资组合的累计净值曲线（兼容旧逻辑）
            # 使用稳健的方法：逐笔计算累计净值，避免数值精度问题
            cumulative_net_value = 1.0  # 初始净值
            max_net_value = 1.0  # 历史最高净值
            max_drawdown = 0.0  # 最大回撤
            
            for ret in returns:
                # 确保收益率在合理范围内（单笔最大亏损不超过止损）
                if ret < -1.0:  # 如果收益率异常（<-100%），限制为-100%
                    ret = -1.0
                cumulative_net_value *= (1 + ret)
                # 更新历史最高净值
                if cumulative_net_value > max_net_value:
                    max_net_value = cumulative_net_value
                # 计算当前回撤
                if max_net_value > 0:
                    current_drawdown = (cumulative_net_value - max_net_value) / max_net_value
                    if current_drawdown < max_drawdown:
                        max_drawdown = current_drawdown
            
            max_drawdown = float(max_drawdown)
            
            # 记录计算信息（用于调试）
            logger.debug(f"最大回撤计算（等权重方式）：最终净值={cumulative_net_value:.4f}, 历史最高净值={max_net_value:.4f}, 最大回撤={max_drawdown:.2%}")
        
        # 计算平均持有天数（用于统计输出）
        avg_hold_days = np.mean([t['hold_days'] for t in trades]) if trades else 0.0
        
        # 年化收益率计算
        # 方式1：基于实际回测期间和总收益率（更准确）
        if start_date and end_date and total_profit_loss_pct is not None:
            # 计算实际回测天数（自然日）
            days_diff = (end_date - start_date).days
            if days_diff <= 0:
                days_diff = 1  # 避免除零
            
            # 估算交易日数（一年约252个交易日，365个自然日）
            trading_days = int(days_diff * 252 / 365)
            if trading_days <= 0:
                trading_days = 1  # 避免除零
            
            # 使用复利公式计算年化收益率
            # 年化收益率 = (1 + 总收益率)^(252/实际交易天数) - 1
            total_return = total_profit_loss_pct / 100.0  # 转换为小数形式（如5.79% -> 0.0579）
            if total_return > -1:  # 避免负数开方
                annual_return = (1 + total_return) ** (252 / trading_days) - 1
            else:
                annual_return = -1.0  # 如果亏损超过100%，年化收益率为-100%
            
            # 计算periods_per_year用于夏普比率计算
            periods_per_year = 252 / trading_days if trading_days > 0 else 50
            
            logger.debug(f"年化收益率计算（基于实际回测期间）：总收益率={total_profit_loss_pct:.2f}%, 回测自然日={days_diff}天, 估算交易日={trading_days}天, 年化收益率={annual_return*100:.2f}%")
        else:
            # 方式2：降级方案（基于平均持有天数，假设连续交易）
            # 注意：这种方式不准确，因为它假设所有交易都是连续进行的，没有考虑实际回测期间
            periods_per_year = 252 / avg_hold_days if avg_hold_days > 0 else 50
            annual_return = mean_return * periods_per_year
            logger.debug(f"年化收益率计算（降级方案）：平均持有天数={avg_hold_days:.2f}天, 年化收益率={annual_return*100:.2f}%")
        
        # 夏普比率（假设无风险利率为0，年化）
        # 年化收益率和年化波动率
        annual_return_sharpe = mean_return * periods_per_year
        annual_volatility = std_return * np.sqrt(periods_per_year)
        sharpe_ratio = annual_return_sharpe / annual_volatility if annual_volatility > 0 else 0.0
        
        # 退出原因统计
        exit_reasons = {}
        for trade in trades:
            reason = trade.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': float(win_rate),
            'mean_return': float(mean_return),
            'median_return': float(median_return),
            'std_return': float(std_return),
            'mean_profit': float(mean_profit),
            'mean_loss': float(mean_loss),
            'profit_loss_ratio': float(profit_loss_ratio),
            'max_drawdown': float(max_drawdown),
            'sharpe_ratio': float(sharpe_ratio),
            'annual_return': float(annual_return),
            'exit_reasons': exit_reasons,
            'avg_hold_days': float(avg_hold_days)
        }
    
    def _save_trades_to_db(
        self,
        session: Session,
        trades: List[Dict],
        profit_target: float,
        stop_loss: float,
        max_hold_days: int,
        sell_strategy: str,
        strategy_type: str = 'mainboard_limit_up'
    ) -> int:
        """
        保存交易记录到数据库
        
        Args:
            session: 数据库会话
            trades: 交易记录列表
            profit_target: 目标收益率
            stop_loss: 止损比例
            max_hold_days: 最大持有天数
            sell_strategy: 卖出策略
        
        Returns:
            int: 保存的记录数
        """
        try:
            saved_count = 0
            updated_count = 0
            batch_size = 100  # 每批处理100条
            error_count = 0
            
            for i in range(0, len(trades), batch_size):
                batch = trades[i:i + batch_size]
                try:
                    # 准备批量插入数据
                    insert_values = []
                    for trade in batch:
                        insert_values.append({
                            'signal_date': datetime.strptime(trade['signal_date'], '%Y-%m-%d').date(),
                            'ts_code': trade['ts_code'],
                            'stock_name': trade.get('stock_name', ''),
                            'buy_date': datetime.strptime(trade['buy_date'], '%Y-%m-%d').date(),
                            'buy_price': trade['buy_price'],
                            'sell_date': datetime.strptime(trade['sell_date'], '%Y-%m-%d').date() if trade.get('sell_date') else None,
                            'sell_price': trade.get('sell_price'),
                            'return_pct': trade['return_pct'],
                            'hold_days': trade['hold_days'],
                            'exit_reason': trade.get('exit_reason', ''),
                            # 资金管理字段（只保存数据库模型中存在的字段）
                            'buy_amount': trade.get('buy_amount'),
                            'buy_quantity': trade.get('buy_quantity'),
                            'sell_amount': trade.get('sell_amount'),
                            'profit_loss': trade.get('profit_loss'),
                            'profit_loss_pct': trade.get('profit_loss_pct'),
                            'profit_target': profit_target,
                            'stop_loss': stop_loss,
                            'max_hold_days': max_hold_days,
                            'sell_strategy': sell_strategy,
                            'strategy_type': strategy_type
                        })
                    
                    # 去重逻辑：先查询已存在的记录，然后只插入不存在的
                    # 基于 signal_date, ts_code, buy_date, sell_strategy, strategy_type 判断是否重复
                    # 构建查询条件：检查是否存在相同的 signal_date, ts_code, buy_date, sell_strategy, strategy_type
                    signal_dates = [datetime.strptime(t['signal_date'], '%Y-%m-%d').date() for t in batch]
                    ts_codes = [t['ts_code'] for t in batch]
                    buy_dates = [datetime.strptime(t['buy_date'], '%Y-%m-%d').date() for t in batch]
                    
                    # 查询已存在的记录
                    existing_records = session.query(
                        FactLimitUpVolumeShrinkBacktest.signal_date,
                        FactLimitUpVolumeShrinkBacktest.ts_code,
                        FactLimitUpVolumeShrinkBacktest.buy_date,
                        FactLimitUpVolumeShrinkBacktest.sell_strategy,
                        FactLimitUpVolumeShrinkBacktest.strategy_type
                    ).filter(
                        FactLimitUpVolumeShrinkBacktest.signal_date.in_(signal_dates),
                        FactLimitUpVolumeShrinkBacktest.ts_code.in_(ts_codes),
                        FactLimitUpVolumeShrinkBacktest.buy_date.in_(buy_dates),
                        FactLimitUpVolumeShrinkBacktest.sell_strategy == sell_strategy,
                        FactLimitUpVolumeShrinkBacktest.strategy_type == strategy_type
                    ).all()
                    
                    existing_set = set((r.signal_date, r.ts_code, r.buy_date, r.sell_strategy, r.strategy_type) for r in existing_records)
                    
                    # 只插入不存在的记录
                    new_insert_values = []
                    for trade in batch:
                        signal_date = datetime.strptime(trade['signal_date'], '%Y-%m-%d').date()
                        buy_date = datetime.strptime(trade['buy_date'], '%Y-%m-%d').date()
                        ts_code = trade['ts_code']
                        key = (signal_date, ts_code, buy_date, sell_strategy, strategy_type)
                        
                        if key not in existing_set:
                            new_insert_values.append({
                                'signal_date': signal_date,
                                'ts_code': ts_code,
                                'stock_name': trade.get('stock_name', ''),
                                'buy_date': buy_date,
                                'buy_price': trade['buy_price'],
                                'sell_date': datetime.strptime(trade['sell_date'], '%Y-%m-%d').date() if trade.get('sell_date') else None,
                                'sell_price': trade.get('sell_price'),
                                'return_pct': trade['return_pct'],
                                'hold_days': trade['hold_days'],
                                'exit_reason': trade.get('exit_reason', ''),
                                # 资金管理字段（只保存数据库模型中存在的字段）
                                'buy_amount': trade.get('buy_amount'),
                                'buy_quantity': trade.get('buy_quantity'),
                                'sell_amount': trade.get('sell_amount'),
                                'profit_loss': trade.get('profit_loss'),
                                'profit_loss_pct': trade.get('profit_loss_pct'),
                                'profit_target': profit_target,
                                'stop_loss': stop_loss,
                                'max_hold_days': max_hold_days,
                                'sell_strategy': sell_strategy,
                                'strategy_type': strategy_type
                            })
                        else:
                            updated_count += 1
                    
                    # 批量插入新记录
                    if new_insert_values:
                        for values in new_insert_values:
                            backtest_record = FactLimitUpVolumeShrinkBacktest(**values)
                            session.add(backtest_record)
                        session.commit()
                        saved_count += len(new_insert_values)
                    
                    if (i + batch_size) % 500 == 0:
                        logger.info(f"已保存 {saved_count}/{len(trades)} 条交易记录，跳过 {updated_count} 条重复记录")
                        
                except Exception as e:
                    session.rollback()
                    error_count += len(batch)
                    # 如果是字段不存在的错误，记录详细信息
                    if 'does not exist' in str(e) or 'UndefinedColumn' in str(e):
                        logger.error(f"数据库表缺少字段，请执行 ALTER TABLE 脚本: {e}")
                        logger.error(f"需要添加的字段: sell_strategy VARCHAR(50)")
                    else:
                        logger.warning(f"批量保存失败（第 {i//batch_size + 1} 批）: {e}")
                    # 继续处理下一批
                    continue
            
            if error_count > 0:
                logger.warning(f"保存完成：成功 {saved_count} 条，跳过 {updated_count} 条重复记录，失败 {error_count} 条")
            else:
                logger.info(f"成功保存 {saved_count} 条交易记录到数据库，跳过 {updated_count} 条重复记录")
            return saved_count
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存交易记录到数据库失败: {e}", exc_info=True)
            return 0
