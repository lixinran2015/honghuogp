"""
信号跟踪服务

负责：
1. 每日生成并记录Top推荐信号
2. 每日收盘后更新未平仓信号的后续表现与退出状态
"""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.models import ShortTermSignalTracking, FactDailyPriceQfq, FactMarketEmotionDaily
from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.leader_tracking.leader_tracking_pool_service import LeaderTrackingPoolService
from backend.services.leader_tracking.buy_signal_integration import get_buy_signals_for_pool
from backend.services.leader_tracking.emotion_cycle_analyzer import EmotionCycleAnalyzer

logger = logging.getLogger(__name__)


def _get_auto_emotion_cycle(trade_date: date, warehouse: PostgresWarehouse) -> str:
    """基于 FactMarketEmotionDaily 自动识别情绪周期"""
    if warehouse is None:
        return '震荡期'
    try:
        session = warehouse.warehouse_service.get_session()
        try:
            record = session.query(FactMarketEmotionDaily).filter(
                FactMarketEmotionDaily.trade_date == trade_date,
            ).first()
            if record:
                analyzer = EmotionCycleAnalyzer()
                market_data = {
                    'limit_up_count': record.total_limit_up or 0,
                    'limit_down_count': record.total_limit_down or 0,
                    'max_continuous_limit': record.highest_streak or 0,
                    'advance_decline_ratio': 1.0,
                    'volume_ratio': 1.0,
                }
                result = analyzer.analyze(market_data)
                return result.cycle
            record2 = session.query(FactMarketEmotionDaily.emotion_stage).filter(
                FactMarketEmotionDaily.trade_date == trade_date,
            ).scalar()
            if record2:
                mapping = {
                    '冰点': '冰点期',
                    '回暖': '低迷期',
                    '震荡': '震荡期',
                    '退潮': '退潮期',
                    '高潮': '高涨期',
                }
                return mapping.get(record2, '震荡期')
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"自动识别情绪周期失败: {e}")
    return '震荡期'


class SignalTrackingService:
    """信号跟踪服务"""

    def __init__(self):
        self.ws = WarehouseService()
        self.warehouse = PostgresWarehouse()

    def generate_signals(self, trade_date: date) -> int:
        """
        生成当日信号并写入 tracking 表
        Returns:
            新写入信号数量
        """
        # 1. 获取龙头池
        svc = LeaderTrackingPoolService(self.ws)
        pool_result = svc.get_pool(
            trade_date=trade_date,
            min_score=60,
            stage_filter='confirmed',
            stable_window_id='rolling_30d_v2',
            do_bootstrap=False,
            force_sync=False,
            catch_up_window_trading_days=0,
            catch_up_max_syncs=0,
        )
        if not pool_result or not pool_result.get('success') or not pool_result.get('pool'):
            logger.info(f"{trade_date} 龙头池为空，无信号可记录")
            return 0

        pool = pool_result['pool']
        td_str = pool_result.get('trade_date')

        # 2. 自动识别情绪周期
        emotion_cycle = _get_auto_emotion_cycle(trade_date, self.warehouse)

        # 3. 计算买点信号
        buy_signals = get_buy_signals_for_pool(
            pool,
            trade_date_str=td_str,
            warehouse=self.warehouse,
            emotion_cycle=emotion_cycle,
        )

        # 4. 过滤有买点的股票，并批量查询当日收盘价作为 entry_price
        candidates = []
        for stock in pool:
            tc = stock.get('ts_code')
            bs = buy_signals.get(tc)
            if bs:
                candidates.append({
                    'ts_code': tc,
                    'name': stock.get('name'),
                    'buy_point_type': bs.get('signal_type'),
                    'lstm_mab_score': stock.get('lstm_mab_score', {}).get('total_score'),
                    'grade': stock.get('lstm_mab_score', {}).get('grade'),
                    'prediction_id': stock.get('lstm_mab_score', {}).get('prediction_id'),
                })

        if not candidates:
            logger.info(f"{trade_date} 无股票触发买点，跳过记录")
            return 0

        # 查询当日收盘价
        entry_prices = self._get_close_prices(
            [c['ts_code'] for c in candidates],
            td_str or trade_date.isoformat(),
        )

        # 5. 写入数据库（忽略重复）
        session = self.ws.get_session()
        inserted = 0
        try:
            for cand in candidates:
                tc = cand['ts_code']
                signal_id = f"{tc}_{td_str}"
                exists = session.query(ShortTermSignalTracking).filter(
                    ShortTermSignalTracking.signal_id == signal_id
                ).first()
                if exists:
                    continue

                record = ShortTermSignalTracking(
                    signal_id=signal_id,
                    ts_code=tc,
                    signal_date=td_str or trade_date.isoformat(),
                    signal_type='leader',
                    buy_point_type=cand['buy_point_type'],
                    entry_price=entry_prices.get(tc),
                    lstm_mab_score=cand['lstm_mab_score'],
                    grade=cand['grade'],
                    emotion_cycle=emotion_cycle,
                    prediction_id=cand['prediction_id'],
                )
                session.add(record)
                inserted += 1
            session.commit()
            logger.info(f"信号记录完成：{trade_date} 新增 {inserted} 条")
        except Exception as e:
            logger.error(f"信号记录失败: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()

        return inserted

    def record_actual_trade(
        self,
        signal_id: str,
        actual_entry_price: Optional[float] = None,
        actual_quantity: Optional[int] = None,
    ) -> bool:
        """
        记录实盘成交信息。
        用于小仓位实盘验证，将实际成交价格/数量写入信号跟踪表。
        """
        session = self.ws.get_session()
        try:
            record = session.query(ShortTermSignalTracking).filter(
                ShortTermSignalTracking.signal_id == signal_id
            ).first()
            if not record:
                logger.warning(f"未找到信号记录: {signal_id}")
                return False

            if actual_entry_price is not None:
                record.actual_entry_price = actual_entry_price
            if actual_quantity is not None:
                record.actual_quantity = actual_quantity
            session.commit()
            logger.info(f"实盘成交已记录: {signal_id} 价格={actual_entry_price} 数量={actual_quantity}")
            return True
        except Exception as e:
            logger.error(f"记录实盘成交失败: {e}", exc_info=True)
            session.rollback()
            return False
        finally:
            session.close()

    def _get_close_prices(self, ts_codes: List[str], trade_date_str: str) -> Dict[str, float]:
        """批量查询收盘价"""
        prices = {}
        try:
            df = self.warehouse.load_stocks_data(trade_date_str, stock_codes=ts_codes)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = row.get('code') or row.get('ts_code', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    for tc in ts_codes:
                        if tc.startswith(code):
                            prices[tc] = float(row.get('close', 0) or 0)
                            break
        except Exception as e:
            logger.warning(f"查询收盘价失败: {e}")
        return prices

    def update_open_signals(self, trade_date: date) -> int:
        """
        更新所有未平仓信号的后续表现和退出状态
        Returns:
            更新记录数
        """
        session = self.ws.get_session()
        try:
            open_signals = session.query(ShortTermSignalTracking).filter(
                ShortTermSignalTracking.exit_date.is_(None)
            ).all()
            if not open_signals:
                logger.info("没有待更新的未平仓信号")
                return 0

            # 批量获取价格数据
            codes = list({s.ts_code for s in open_signals})
            min_date = min(s.signal_date for s in open_signals)
            df = self.warehouse.load_history_kline_batch(
                codes=[c.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') for c in codes],
                start_date=min_date.isoformat(),
                end_date=trade_date.isoformat(),
            )
            if df is None or df.empty:
                logger.warning("未获取到历史K线数据，无法更新信号表现")
                return 0

            # 构建查询表: {(ts_code, trade_date_str): row_dict}
            lookup: Dict[tuple, Any] = {}
            for _, row in df.iterrows():
                tc = row.get('ts_code', '')
                d = str(row.get('trade_date', ''))
                lookup[(tc, d)] = row

            updated = 0
            for sig in open_signals:
                updated += self._update_single_signal(sig, lookup, trade_date)

            session.commit()
            logger.info(f"信号表现更新完成：共更新 {updated} 条")
            return updated
        except Exception as e:
            logger.error(f"更新信号表现失败: {e}", exc_info=True)
            session.rollback()
            return 0
        finally:
            session.close()

    def _update_single_signal(self, sig: ShortTermSignalTracking, lookup: Dict[tuple, Any], trade_date: date) -> int:
        """更新单条信号的表现和退出状态"""
        tc = sig.ts_code
        signal_date = sig.signal_date
        if not signal_date:
            return 0

        # 获取signal_date之后的交易日列表（从lookup中筛选）
        future_rows = []
        for (code, d_str), row in lookup.items():
            if code == tc and d_str > str(signal_date):
                future_rows.append((d_str, row))
        future_rows.sort(key=lambda x: x[0])

        if not future_rows:
            return 0

        entry_price = float(sig.entry_price) if sig.entry_price else 0.0
        if entry_price <= 0:
            return 0

        highs = [float(r['high']) for _, r in future_rows]
        closes = [float(r['close']) for _, r in future_rows]
        lows = [float(r['low']) for _, r in future_rows]

        # 记录 day1 / day3 / day5 表现
        if len(highs) >= 1:
            sig.day1_high = highs[0]
            sig.day1_close = closes[0]
        if len(highs) >= 3:
            sig.day3_max = max(highs[:3])
            sig.day3_close = closes[2]
        if len(highs) >= 5:
            sig.day5_max = max(highs[:5])
            sig.day5_close = closes[4]

        # 计算最大回撤（从买入后最高价到当日最低价的回撤）
        max_price = max(highs) if highs else entry_price
        min_price_after_peak = min(lows[highs.index(max_price):]) if highs else entry_price
        if max_price > 0:
            sig.max_drawdown = round((min_price_after_peak - max_price) / max_price, 4)

        # 退出规则判定
        exit_triggered = False
        exit_price = None
        exit_reason = None
        holding_days = len(future_rows)

        # 1. 机械止损 -3%
        for i, close in enumerate(closes):
            if (close - entry_price) / entry_price <= -0.03:
                exit_triggered = True
                exit_price = close
                exit_reason = 'stop_loss'
                holding_days = i + 1
                break

        # 2. 动态止盈：从最高点回撤 5%
        if not exit_triggered:
            running_max = entry_price
            for i, (high, close) in enumerate(zip(highs, closes)):
                running_max = max(running_max, high)
                # 只有先盈利 >10% 才触发回撤止盈
                if (running_max - entry_price) / entry_price > 0.10:
                    if (close - running_max) / running_max <= -0.05:
                        exit_triggered = True
                        exit_price = close
                        exit_reason = 'take_profit'
                        holding_days = i + 1
                        break

        # 3. 时间卖点：最长持有3天（与v2设计一致）
        if not exit_triggered and len(closes) >= 3:
            exit_triggered = True
            exit_price = closes[2]
            exit_reason = 'time_exit'
            holding_days = 3

        # 如果有更多天数仍未触发，-trade_date 更新到今天，但不标记退出（继续跟踪到5天）
        # 但短线一般只跟踪5天，5天后强制标记退出
        if not exit_triggered and len(closes) >= 5:
            exit_triggered = True
            exit_price = closes[4]
            exit_reason = 'time_exit'
            holding_days = 5

        if exit_triggered and exit_price is not None:
            sig.exit_price = round(exit_price, 2)
            sig.exit_date = future_rows[holding_days - 1][0] if holding_days <= len(future_rows) else future_rows[-1][0]
            if isinstance(sig.exit_date, str):
                sig.exit_date = date.fromisoformat(sig.exit_date)
            sig.exit_reason = exit_reason
            sig.total_return = round((exit_price - entry_price) / entry_price, 4)
            sig.holding_days = holding_days

        return 1
