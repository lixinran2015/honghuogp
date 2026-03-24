"""
推荐效果追踪服务
每日追踪推荐股票的表现，计算胜率和收益统计
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, date, timedelta

from backend.utils.trade_date_utils import get_trade_date_or_latest, calculate_trading_days_diff
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TrackingRecord:
    """追踪记录"""
    recommendation_id: int
    ts_code: str
    name: str
    recommend_date: str
    entry_price: float
    current_price: float
    total_return_pct: float
    max_return_pct: float
    max_drawdown_pct: float
    holding_days: int
    hit_stop_loss: bool
    hit_target_1: bool
    hit_target_2: bool
    status: str


@dataclass
class PerformanceStats:
    """表现统计"""
    total_recommendations: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_return: float
    avg_win_return: float
    avg_loss_return: float
    max_win: float
    max_loss: float
    hit_target_rate: float
    hit_stop_loss_rate: float
    avg_holding_days: float
    profit_factor: float


class RecommendationTracker:
    """推荐效果追踪服务"""
    
    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()
        self._ensure_table()
    
    def _ensure_table(self):
        """确保追踪表存在"""
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                # 检查表是否存在
                result = session.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'fact_recommendation_tracking'
                    )
                """))
                exists = result.scalar()
                
                # 若表已存在，确保 holding_trading_days 列存在并回填历史数据
                if exists:
                    col_check = session.execute(text("""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'fact_recommendation_tracking' AND column_name = 'holding_trading_days'
                    """)).fetchone()
                    if not col_check:
                        session.execute(text("ALTER TABLE fact_recommendation_tracking ADD COLUMN holding_trading_days INTEGER"))
                        session.commit()
                        logger.info("✅ fact_recommendation_tracking 添加 holding_trading_days 列")
                    # 回填 holding_trading_days 为空的记录（基于 recommend_date 与 track_date 间的交易日数）
                    try:
                        r = session.execute(text("""
                            UPDATE fact_recommendation_tracking t
                            SET holding_trading_days = (
                                SELECT count(*)::integer FROM dim_trade_calendar c
                                WHERE c.trade_date > t.recommend_date AND c.trade_date <= t.track_date AND c.is_open = true
                            )
                            WHERE t.holding_trading_days IS NULL AND t.recommend_date <= t.track_date
                        """))
                        if r.rowcount and r.rowcount > 0:
                            session.commit()
                            logger.info(f"✅ 回填 holding_trading_days: {r.rowcount} 条")
                    except Exception as be:
                        logger.debug("回填 holding_trading_days 失败（可忽略）: %s", be)
                if not exists:
                    # 创建表
                    session.execute(text("""
                        CREATE TABLE IF NOT EXISTS fact_recommendation_tracking (
                            id SERIAL PRIMARY KEY,
                            recommendation_id INTEGER,
                            ts_code VARCHAR(10) NOT NULL,
                            
                            recommend_date DATE NOT NULL,
                            entry_price NUMERIC(10,2),
                            stop_loss_price NUMERIC(10,2),
                            target_price_1 NUMERIC(10,2),
                            target_price_2 NUMERIC(10,2),
                            
                            track_date DATE NOT NULL,
                            current_price NUMERIC(10,2),
                            daily_return_pct NUMERIC(10,2),
                            total_return_pct NUMERIC(10,2),
                            max_return_pct NUMERIC(10,2),
                            max_drawdown_pct NUMERIC(10,2),
                            
                            hit_stop_loss BOOLEAN DEFAULT FALSE,
                            hit_target_1 BOOLEAN DEFAULT FALSE,
                            hit_target_2 BOOLEAN DEFAULT FALSE,
                            holding_days INTEGER,
                            holding_trading_days INTEGER,
                            
                            is_closed BOOLEAN DEFAULT FALSE,
                            close_date DATE,
                            close_price NUMERIC(10,2),
                            final_return_pct NUMERIC(10,2),
                            close_reason VARCHAR(50),
                            
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(recommendation_id, track_date)
                        )
                    """))
                    
                    # 创建索引
                    session.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_tracking_ts_code 
                        ON fact_recommendation_tracking(ts_code)
                    """))
                    session.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_tracking_recommend_date 
                        ON fact_recommendation_tracking(recommend_date)
                    """))
                    
                    session.commit()
                    logger.info("✅ 创建 fact_recommendation_tracking 表成功")
                    
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"检查/创建追踪表失败: {e}")
    
    def track_daily(self, trade_date: Optional[str] = None) -> Dict:
        """
        每日收盘后更新所有活跃推荐的表现
        
        Args:
            trade_date: 交易日期
            
        Returns:
            Dict: 追踪结果统计
        """
        try:
            resolved = get_trade_date_or_latest(self.ws, trade_date)
            trade_date = resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
            
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                # 获取所有活跃推荐
                result = session.execute(text("""
                    SELECT id, ts_code, recommend_date, entry_price, 
                           stop_loss_price, target_price_1, target_price_2
                    FROM fact_recommended_stocks
                    WHERE status = 'active'
                """))
                active_recs = result.fetchall()
                
                if not active_recs:
                    return {'success': True, 'tracked': 0, 'message': '无活跃推荐'}
                
                tracked_count = 0
                auto_closed = 0
                
                for rec in active_recs:
                    rec_id, ts_code, recommend_date, entry_price, stop_loss, target_1, target_2 = rec
                    
                    # 获取当日收盘价
                    price_result = session.execute(text("""
                        SELECT close FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code AND trade_date = :trade_date
                    """), {'ts_code': ts_code, 'trade_date': trade_date})
                    price_row = price_result.fetchone()
                    
                    if not price_row:
                        continue
                    
                    current_price = float(price_row[0])
                    entry_price = float(entry_price) if entry_price else current_price
                    
                    # 计算收益率
                    total_return_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                    
                    # 获取历史最大涨幅和最大回撤
                    history_result = session.execute(text("""
                        SELECT MAX(max_return_pct), MIN(total_return_pct)
                        FROM fact_recommendation_tracking
                        WHERE recommendation_id = :rec_id
                    """), {'rec_id': rec_id})
                    history_row = history_result.fetchone()
                    
                    prev_max_return = float(history_row[0]) if history_row and history_row[0] else 0
                    prev_min_return = float(history_row[1]) if history_row and history_row[1] else 0
                    
                    max_return_pct = max(prev_max_return, total_return_pct)
                    max_drawdown_pct = min(prev_min_return, total_return_pct)
                    
                    # 持有天数：自然日 + 交易日（5日/10日收益按交易日计算）
                    recommend_date_obj = recommend_date if isinstance(recommend_date, date) else datetime.strptime(str(recommend_date), '%Y-%m-%d').date()
                    trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
                    holding_days = (trade_date_obj - recommend_date_obj).days
                    diff = calculate_trading_days_diff(session, recommend_date_obj, trade_date_obj)
                    holding_trading_days = max(0, diff) if diff is not None and diff >= 0 else 0
                    
                    # 检查是否触及止损/止盈
                    hit_stop_loss = float(stop_loss) > 0 and current_price <= float(stop_loss) if stop_loss else False
                    hit_target_1 = float(target_1) > 0 and current_price >= float(target_1) if target_1 else False
                    hit_target_2 = float(target_2) > 0 and current_price >= float(target_2) if target_2 else False
                    
                    # 插入或更新追踪记录
                    session.execute(text("""
                        INSERT INTO fact_recommendation_tracking 
                        (recommendation_id, ts_code, recommend_date, entry_price,
                         stop_loss_price, target_price_1, target_price_2,
                         track_date, current_price, total_return_pct,
                         max_return_pct, max_drawdown_pct, holding_days, holding_trading_days,
                         hit_stop_loss, hit_target_1, hit_target_2)
                        VALUES (:rec_id, :ts_code, :recommend_date, :entry_price,
                                :stop_loss, :target_1, :target_2,
                                :track_date, :current_price, :total_return,
                                :max_return, :max_drawdown, :holding_days, :holding_trading_days,
                                :hit_stop_loss, :hit_target_1, :hit_target_2)
                        ON CONFLICT (recommendation_id, track_date) 
                        DO UPDATE SET
                            current_price = EXCLUDED.current_price,
                            total_return_pct = EXCLUDED.total_return_pct,
                            max_return_pct = EXCLUDED.max_return_pct,
                            max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                            holding_days = EXCLUDED.holding_days,
                            holding_trading_days = EXCLUDED.holding_trading_days,
                            hit_stop_loss = EXCLUDED.hit_stop_loss,
                            hit_target_1 = EXCLUDED.hit_target_1,
                            hit_target_2 = EXCLUDED.hit_target_2
                    """), {
                        'rec_id': rec_id,
                        'ts_code': ts_code,
                        'recommend_date': recommend_date,
                        'entry_price': entry_price,
                        'stop_loss': stop_loss,
                        'target_1': target_1,
                        'target_2': target_2,
                        'track_date': trade_date,
                        'current_price': current_price,
                        'total_return': round(total_return_pct, 2),
                        'max_return': round(max_return_pct, 2),
                        'max_drawdown': round(max_drawdown_pct, 2),
                        'holding_days': holding_days,
                        'holding_trading_days': holding_trading_days,
                        'hit_stop_loss': hit_stop_loss,
                        'hit_target_1': hit_target_1,
                        'hit_target_2': hit_target_2
                    })
                    
                    # 更新推荐表的当前价格
                    session.execute(text("""
                        UPDATE fact_recommended_stocks
                        SET current_price = :price,
                            max_gain = GREATEST(COALESCE(max_gain, 0), :total_return),
                            max_drawdown = LEAST(COALESCE(max_drawdown, 0), :total_return)
                        WHERE id = :rec_id
                    """), {
                        'price': current_price,
                        'total_return': round(total_return_pct, 2),
                        'rec_id': rec_id
                    })
                    
                    tracked_count += 1
                
                session.commit()
                
                logger.info(f"✅ 追踪完成: 更新 {tracked_count} 条推荐")
                
                return {
                    'success': True,
                    'tracked': tracked_count,
                    'trade_date': trade_date
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"追踪失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}

    def track_backfill(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """
        回填历史追踪记录（用于补齐 5日/10日收益所需的 holding_trading_days=5/10 记录）
        对 [start_date, end_date] 内每个交易日执行一次 track_daily
        
        Args:
            start_date: 起始日期（YYYY-MM-DD），默认取活跃推荐的最早 recommend_date
            end_date: 结束日期，默认取最近交易日
            
        Returns:
            Dict: {success, days_processed, total_tracked, message}
        """
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                from data_warehouse.models.generated_models import DimTradeCalendar

                # 获取活跃推荐的最早 recommend_date
                rec_row = session.execute(text("""
                    SELECT MIN(recommend_date) FROM fact_recommended_stocks WHERE status = 'active'
                """)).fetchone()
                min_rec_date = rec_row[0] if rec_row and rec_row[0] else None
                if not min_rec_date:
                    return {'success': True, 'days_processed': 0, 'total_tracked': 0, 'message': '无活跃推荐'}

                # 确定日期范围
                min_rec = min_rec_date if isinstance(min_rec_date, date) else datetime.strptime(str(min_rec_date), '%Y-%m-%d').date()
                end_d = get_trade_date_or_latest(self.ws, end_date) if end_date else get_trade_date_or_latest(self.ws, None)
                start_d = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else min_rec
                if not end_d:
                    return {'success': False, 'error': '无法获取最近交易日'}
                if start_d > end_d:
                    return {'success': False, 'error': 'start_date 不能大于 end_date'}
                start_d = max(start_d, min_rec)

                # 获取 [start_d, end_d] 内所有交易日
                trade_dates = session.query(DimTradeCalendar.trade_date).filter(
                    DimTradeCalendar.trade_date >= start_d,
                    DimTradeCalendar.trade_date <= end_d,
                    DimTradeCalendar.is_open == True
                ).order_by(DimTradeCalendar.trade_date.asc()).all()
                trade_dates = [row[0] for row in trade_dates] if trade_dates else []

                if not trade_dates:
                    return {'success': True, 'days_processed': 0, 'total_tracked': 0, 'message': '范围内无交易日'}

                total_tracked = 0
                for d in trade_dates:
                    dt_str = d.strftime('%Y-%m-%d')
                    result = self.track_daily(dt_str)
                    if result.get('success'):
                        total_tracked += result.get('tracked', 0)

                logger.info(f"✅ 回填完成: {len(trade_dates)} 个交易日, 累计追踪 {total_tracked} 条")
                return {
                    'success': True,
                    'days_processed': len(trade_dates),
                    'total_tracked': total_tracked,
                    'message': f'已回填 {len(trade_dates)} 个交易日，5日/10日收益将可用'
                }
            finally:
                session.close()
        except Exception as e:
            logger.error(f"回填追踪失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}

    def auto_close(self, trade_date: Optional[str] = None) -> Dict:
        """
        自动平仓触及止损/止盈的推荐
        
        Args:
            trade_date: 交易日期
            
        Returns:
            Dict: 平仓结果
        """
        try:
            resolved = get_trade_date_or_latest(self.ws, trade_date)
            trade_date = resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
            
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                closed_count = 0
                
                # 获取触及止损的推荐
                result = session.execute(text("""
                    SELECT DISTINCT t.recommendation_id, t.ts_code, t.current_price, t.total_return_pct
                    FROM fact_recommendation_tracking t
                    JOIN fact_recommended_stocks r ON t.recommendation_id = r.id
                    WHERE r.status = 'active'
                      AND t.track_date = :trade_date
                      AND t.hit_stop_loss = TRUE
                """), {'trade_date': trade_date})
                
                for row in result.fetchall():
                    rec_id, ts_code, close_price, final_return = row
                    self._close_recommendation(
                        session, rec_id, trade_date, close_price, final_return, 'stop_loss'
                    )
                    closed_count += 1
                    logger.info(f"📉 止损平仓: {ts_code}, 收益率: {final_return:.1f}%")
                
                # 获取触及目标价2的推荐
                result = session.execute(text("""
                    SELECT DISTINCT t.recommendation_id, t.ts_code, t.current_price, t.total_return_pct
                    FROM fact_recommendation_tracking t
                    JOIN fact_recommended_stocks r ON t.recommendation_id = r.id
                    WHERE r.status = 'active'
                      AND t.track_date = :trade_date
                      AND t.hit_target_2 = TRUE
                """), {'trade_date': trade_date})
                
                for row in result.fetchall():
                    rec_id, ts_code, close_price, final_return = row
                    self._close_recommendation(
                        session, rec_id, trade_date, close_price, final_return, 'target_reached'
                    )
                    closed_count += 1
                    logger.info(f"📈 止盈平仓: {ts_code}, 收益率: {final_return:.1f}%")
                
                session.commit()
                
                return {
                    'success': True,
                    'closed': closed_count,
                    'trade_date': trade_date
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"自动平仓失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def _close_recommendation(
        self,
        session,
        rec_id: int,
        close_date: str,
        close_price: float,
        final_return: float,
        reason: str
    ):
        """关闭推荐"""
        from sqlalchemy import text
        
        # 更新推荐状态
        session.execute(text("""
            UPDATE fact_recommended_stocks
            SET status = 'closed'
            WHERE id = :rec_id
        """), {'rec_id': rec_id})
        
        # 更新追踪记录
        session.execute(text("""
            UPDATE fact_recommendation_tracking
            SET is_closed = TRUE,
                close_date = :close_date,
                close_price = :close_price,
                final_return_pct = :final_return,
                close_reason = :reason
            WHERE recommendation_id = :rec_id
              AND track_date = :close_date
        """), {
            'rec_id': rec_id,
            'close_date': close_date,
            'close_price': close_price,
            'final_return': final_return,
            'reason': reason
        })
    
    def close_recommendation(self, rec_id: int, reason: str = 'manual') -> Dict:
        """
        手动平仓推荐
        
        Args:
            rec_id: 推荐ID
            reason: 平仓原因
            
        Returns:
            Dict: 平仓结果
        """
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                # 获取最新追踪数据
                result = session.execute(text("""
                    SELECT current_price, total_return_pct, track_date
                    FROM fact_recommendation_tracking
                    WHERE recommendation_id = :rec_id
                    ORDER BY track_date DESC
                    LIMIT 1
                """), {'rec_id': rec_id})
                row = result.fetchone()
                
                if not row:
                    return {'success': False, 'error': '未找到追踪记录'}
                
                close_price, final_return, track_date = row
                
                self._close_recommendation(
                    session, rec_id, str(track_date), float(close_price), float(final_return), reason
                )
                
                session.commit()
                
                return {
                    'success': True,
                    'rec_id': rec_id,
                    'close_price': float(close_price),
                    'final_return': float(final_return),
                    'reason': reason
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"手动平仓失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def get_performance_stats(self, days: int = 30) -> Dict:
        """
        获取历史推荐表现统计（含已平仓 + 进行中，以最新收益计算）
        
        Args:
            days: 统计天数
            
        Returns:
            Dict: 表现统计
        """
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                start_date = (date.today() - timedelta(days=days)).isoformat()
                
                # 每只推荐取一条有效收益：已平仓用 final_return_pct，否则用最新 total_return_pct
                # 子查询：按 recommendation_id 取 is_closed 优先、再按 track_date 最新
                result = session.execute(text("""
                    WITH rec_list AS (
                        SELECT id, ts_code, recommend_date, entry_price
                        FROM fact_recommended_stocks
                        WHERE recommend_date >= :start_date
                    ),
                    eff_return AS (
                        SELECT DISTINCT ON (t.recommendation_id)
                            t.recommendation_id,
                            COALESCE(t.final_return_pct, t.total_return_pct) AS return_pct,
                            t.holding_days,
                            t.hit_target_1,
                            t.hit_target_2,
                            t.hit_stop_loss
                        FROM fact_recommendation_tracking t
                        INNER JOIN rec_list r ON t.recommendation_id = r.id
                        ORDER BY t.recommendation_id, t.is_closed DESC NULLS LAST, t.track_date DESC
                    )
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE e.return_pct > 0) as win_count,
                        COUNT(*) FILTER (WHERE e.return_pct <= 0) as loss_count,
                        AVG(e.return_pct) as avg_return,
                        AVG(e.return_pct) FILTER (WHERE e.return_pct > 0) as avg_win,
                        AVG(e.return_pct) FILTER (WHERE e.return_pct <= 0) as avg_loss,
                        MAX(e.return_pct) as max_win,
                        MIN(e.return_pct) as max_loss,
                        COUNT(*) FILTER (WHERE e.hit_target_1 OR e.hit_target_2) as hit_target_count,
                        COUNT(*) FILTER (WHERE e.hit_stop_loss) as hit_stop_count,
                        AVG(e.holding_days) as avg_holding_days
                    FROM rec_list r
                    LEFT JOIN eff_return e ON r.id = e.recommendation_id
                    WHERE e.return_pct IS NOT NULL
                """), {'start_date': start_date})
                row = result.fetchone()
                
                # 若无追踪数据，尝试用 fact_recommended_stocks + 最新价计算（无追踪时回退）
                total = row[0] or 0 if row else 0
                if total == 0:
                    fallback = session.execute(text("""
                        SELECT r.id, r.ts_code, r.entry_price
                        FROM fact_recommended_stocks r
                        WHERE r.recommend_date >= :start_date
                    """), {'start_date': start_date})
                    recs = fallback.fetchall()
                    if recs:
                        returns = []
                        for rec_id, ts_code, entry_price in recs:
                            entry = float(entry_price) if entry_price else None
                            if not entry or entry <= 0:
                                continue
                            # 取该股最新收盘价
                            pr = session.execute(text("""
                                SELECT close FROM fact_daily_price_qfq
                                WHERE ts_code = :ts_code
                                ORDER BY trade_date DESC LIMIT 1
                            """), {'ts_code': ts_code}).fetchone()
                            if pr and pr[0]:
                                ret = (float(pr[0]) - entry) / entry * 100
                                returns.append(ret)
                        if returns:
                            total = len(returns)
                            win_count = sum(1 for r in returns if r > 0)
                            loss_count = total - win_count
                            avg_return = sum(returns) / total
                            avg_win = sum(r for r in returns if r > 0) / win_count if win_count else 0
                            avg_loss = sum(r for r in returns if r <= 0) / loss_count if loss_count else 0
                            max_win = max(returns)
                            max_loss = min(returns)
                            hit_target = hit_stop = 0
                            avg_holding = 0
                            win_rate = (win_count / total * 100) if total > 0 else 0
                            hit_target_rate = hit_stop_rate = 0
                            profit_factor = (avg_win * win_count / abs(avg_loss * loss_count)) if loss_count > 0 and avg_loss < 0 else 0
                            stats = PerformanceStats(
                                total_recommendations=total,
                                win_count=win_count,
                                loss_count=loss_count,
                                win_rate=round(win_rate, 1),
                                avg_return=round(avg_return, 2),
                                avg_win_return=round(avg_win, 2),
                                avg_loss_return=round(avg_loss, 2),
                                max_win=round(max_win, 2),
                                max_loss=round(max_loss, 2),
                                hit_target_rate=0,
                                hit_stop_loss_rate=0,
                                avg_holding_days=0,
                                profit_factor=round(profit_factor, 2)
                            )
                            return {
                                'success': True,
                                'data': asdict(stats),
                                'period_days': days
                            }
                
                if not row or total == 0:
                    return {
                        'success': True,
                        'data': self._empty_stats().__dict__
                    }
                
                win_count = row[1] or 0
                loss_count = row[2] or 0
                avg_return = float(row[3]) if row[3] else 0
                avg_win = float(row[4]) if row[4] else 0
                avg_loss = float(row[5]) if row[5] else 0
                max_win = float(row[6]) if row[6] else 0
                max_loss = float(row[7]) if row[7] else 0
                hit_target = row[8] or 0
                hit_stop = row[9] or 0
                avg_holding = float(row[10]) if row[10] else 0
                
                win_rate = (win_count / total * 100) if total > 0 else 0
                hit_target_rate = (hit_target / total * 100) if total > 0 else 0
                hit_stop_rate = (hit_stop / total * 100) if total > 0 else 0
                profit_factor = (avg_win * win_count / abs(avg_loss * loss_count)) if loss_count > 0 and avg_loss < 0 else 0
                
                stats = PerformanceStats(
                    total_recommendations=total,
                    win_count=win_count,
                    loss_count=loss_count,
                    win_rate=round(win_rate, 1),
                    avg_return=round(avg_return, 2),
                    avg_win_return=round(avg_win, 2),
                    avg_loss_return=round(avg_loss, 2),
                    max_win=round(max_win, 2),
                    max_loss=round(max_loss, 2),
                    hit_target_rate=round(hit_target_rate, 1),
                    hit_stop_loss_rate=round(hit_stop_rate, 1),
                    avg_holding_days=round(avg_holding, 1),
                    profit_factor=round(profit_factor, 2)
                )
                
                return {
                    'success': True,
                    'data': asdict(stats),
                    'period_days': days
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取表现统计失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败',
                'data': self._empty_stats().__dict__
            }
    
    def get_tracking_detail(self, rec_id: int) -> Dict:
        """获取单只推荐的追踪详情"""
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                result = session.execute(text("""
                    SELECT t.*, r.recommend_reason, d.name
                    FROM fact_recommendation_tracking t
                    JOIN fact_recommended_stocks r ON t.recommendation_id = r.id
                    LEFT JOIN dim_stock d ON t.ts_code = d.ts_code
                    WHERE t.recommendation_id = :rec_id
                    ORDER BY t.track_date DESC
                """), {'rec_id': rec_id})
                
                rows = result.fetchall()
                if not rows:
                    return {'success': False, 'error': '未找到追踪记录'}
                
                # 转换为字典列表
                columns = result.keys()
                records = [dict(zip(columns, row)) for row in rows]
                
                return {
                    'success': True,
                    'data': records
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取追踪详情失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def get_active_recommendations(self) -> Dict:
        """获取活跃推荐列表"""
        try:
            session = self.ws.get_session()
            try:
                from sqlalchemy import text
                
                result = session.execute(text("""
                    SELECT r.id, r.ts_code, d.name, r.recommend_date, r.entry_price,
                           r.current_price, r.stop_loss_price, r.target_price_1,
                           r.target_price_2, r.recommend_reason, r.signal_strength,
                           r.risk_level,
                           CASE WHEN r.entry_price > 0 
                                THEN ((r.current_price - r.entry_price) / r.entry_price * 100)
                                ELSE 0 END as return_pct,
                           r.max_gain, r.max_drawdown
                    FROM fact_recommended_stocks r
                    LEFT JOIN dim_stock d ON r.ts_code = d.ts_code
                    WHERE r.status = 'active'
                    ORDER BY r.recommend_date DESC
                """))
                
                rows = result.fetchall()
                columns = result.keys()
                records = [dict(zip(columns, row)) for row in rows]
                
                return {
                    'success': True,
                    'data': records
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"获取活跃推荐失败: {e}", exc_info=True)
            return {'success': False, 'error': '操作失败'}
    
    def _empty_stats(self) -> PerformanceStats:
        """返回空统计"""
        return PerformanceStats(
            total_recommendations=0,
            win_count=0,
            loss_count=0,
            win_rate=0,
            avg_return=0,
            avg_win_return=0,
            avg_loss_return=0,
            max_win=0,
            max_loss=0,
            hit_target_rate=0,
            hit_stop_loss_rate=0,
            avg_holding_days=0,
            profit_factor=0
        )
