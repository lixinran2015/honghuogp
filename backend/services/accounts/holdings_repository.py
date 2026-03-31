"""
持仓服务 - 数据访问层（Repository模式）

职责：
1. 封装所有数据库访问逻辑
2. 提供清晰的CRUD接口
3. 管理数据库会话生命周期

这种设计使得：
- 业务逻辑与数据访问解耦
- 便于单元测试（可以mock repository）
- 数据库变更不影响业务层
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Any, Dict

from sqlalchemy import or_, func

from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.accounts.holdings_types import HoldingsError
from data_warehouse.db import SessionContext

logger = logging.getLogger(__name__)


class HoldingsRepository:
    """
    持仓数据仓库

    封装所有与FactUserHolding表相关的数据库操作
    """

    def __init__(self, warehouse: PostgresWarehouse):
        self.warehouse = warehouse

    def get_session(self):
        """获取数据库会话（向后兼容）"""
        if not self.warehouse.warehouse_service:
            raise HoldingsError("数据仓库未初始化", "error")
        return self.warehouse.warehouse_service.get_session()

    def session_scope(self, autocommit: bool = True):
        """获取会话上下文管理器（推荐使用）"""
        return SessionContext(autocommit=autocommit)

    # ========== 查询操作 ==========

    def get_active_holdings(
        self,
        user_id: int,
        board_type: Optional[str] = None,
    ) -> List[Any]:
        """
        获取用户的活跃持仓

        Args:
            user_id: 用户ID
            board_type: 可选的板块类型筛选

        Returns:
            持仓对象列表
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            query = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                or_(
                    FactUserHolding.status == "holding",
                    FactUserHolding.status.is_(None)
                ),
            )

            if board_type:
                query = query.filter(FactUserHolding.board_type == board_type)

            # 需要 detach 对象，因为会话会在with块结束时关闭
            results = query.order_by(FactUserHolding.updated_at.desc()).all()
            for r in results:
                session.expunge(r)
            return results

    def find_holding_by_symbol(self, user_id: int, symbol: str) -> Optional[Any]:
        """
        根据股票代码查找活跃持仓

        Args:
            user_id: 用户ID
            symbol: 股票代码（支持6位或带后缀格式）

        Returns:
            持仓对象或None
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            # 标准化代码格式
            normalized_symbol = self._normalize_symbol(symbol)

            result = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.symbol == normalized_symbol,
                or_(
                    FactUserHolding.status == "holding",
                    FactUserHolding.status.is_(None)
                ),
            ).first()

            if result:
                session.expunge(result)
            return result

    def get_holding_by_id(self, holding_id: int, user_id: int) -> Optional[Any]:
        """
        根据ID获取持仓

        Args:
            holding_id: 持仓ID
            user_id: 用户ID（用于权限验证）

        Returns:
            持仓对象或None
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            result = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()

            if result:
                session.expunge(result)
            return result

    def count_active_holdings(self, user_id: int) -> int:
        """
        统计用户活跃持仓数量

        Args:
            user_id: 用户ID

        Returns:
            持仓数量
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            return session.query(FactUserHolding.id).filter(
                FactUserHolding.user_id == user_id,
                or_(
                    FactUserHolding.status == "holding",
                    FactUserHolding.status.is_(None)
                ),
            ).count()

    def get_active_symbols(self, user_id: int) -> List[str]:
        """
        获取用户所有活跃持仓的股票代码

        Args:
            user_id: 用户ID

        Returns:
            股票代码列表
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            rows = session.query(FactUserHolding.symbol).filter(
                FactUserHolding.user_id == user_id,
                or_(
                    FactUserHolding.status == "holding",
                    FactUserHolding.status.is_(None)
                ),
            ).all()
            return [row[0] for row in rows if row[0]]

    def get_closed_holdings(self, user_id: int) -> List[Any]:
        """
        获取用户已清仓的持仓

        Args:
            user_id: 用户ID

        Returns:
            已清仓持仓列表
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=False) as session:
            results = session.query(FactUserHolding).filter(
                FactUserHolding.user_id == user_id,
                FactUserHolding.status == "closed",
            ).order_by(FactUserHolding.close_date.desc()).all()

            session.expunge_all()
            return results

    # ========== 写入操作 ==========

    def create_holding(
        self,
        user_id: int,
        symbol: str,
        name: str,
        board_type: str,
        buy_price: Optional[float],
        quantity: Optional[float],
        buy_date: Optional[str],
    ) -> Any:
        """
        创建新持仓记录

        Args:
            user_id: 用户ID
            symbol: 股票代码
            name: 股票名称
            board_type: 板块类型
            buy_price: 买入价格
            quantity: 买入数量
            buy_date: 买入日期字符串（YYYY-MM-DD）

        Returns:
            创建的持仓对象
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=True) as session:
            # 解析买入日期
            parsed_buy_date = self._parse_buy_date(buy_date)

            holding = FactUserHolding(
                user_id=user_id,
                symbol=symbol,
                name=name,
                board_type=board_type,
                total_quantity=quantity or 0,
                avg_cost_price=buy_price or 0,
                buy_date=parsed_buy_date,
                current_price=0,
                market_value=0,
                profit_amount=0,
                profit_rate=0,
                chase_risk_level="low",
                chase_risk_score=0,
                chase_risk_reason="",
                today_action="hold",
                today_action_reason="",
                status="holding",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            session.add(holding)
            session.commit()
            session.refresh(holding)
            # 分离对象以便在会话外使用
            session.expunge(holding)
            return holding

    def add_to_holding(
        self,
        existing: Any,
        buy_price: Optional[float],
        quantity: Optional[float],
        buy_date: Optional[str],
    ) -> Optional[Any]:
        """
        加仓到现有持仓

        Args:
            existing: 现有持仓对象
            buy_price: 加仓价格
            quantity: 加仓数量
            buy_date: 加仓日期

        Returns:
            更新后的持仓对象或None（如果持仓不存在）
        """
        from data_warehouse.models import FactUserHolding

        if not existing or not existing.id:
            return None

        with self.session_scope(autocommit=True) as session:
            # 重新获取持仓对象到当前会话
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == existing.id
            ).first()

            if not holding:
                return None

            if buy_price is not None and quantity is not None:
                old_total = float(holding.total_quantity or 0)
                old_cost = float(holding.avg_cost_price or 0)
                new_total = old_total + quantity

                if new_total > 0:
                    new_avg_cost = (old_total * old_cost + quantity * buy_price) / new_total
                    holding.total_quantity = new_total
                    holding.avg_cost_price = new_avg_cost

            if buy_date:
                parsed = self._parse_buy_date(buy_date)
                if not holding.buy_date or parsed >= holding.buy_date:
                    holding.buy_date = parsed

            holding.status = "holding"
            holding.updated_at = datetime.now()

            session.commit()
            session.refresh(holding)
            # 分离对象并更新传入的对象引用
            session.expunge(holding)
            return holding

    def update_holding(
        self,
        holding_id: int,
        user_id: int,
        updates: Dict[str, Any],
    ) -> Optional[Any]:
        """
        更新持仓信息

        Args:
            holding_id: 持仓ID
            user_id: 用户ID
            updates: 要更新的字段字典

        Returns:
            更新后的持仓对象或None
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=True) as session:
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()

            if not holding:
                return None

            # 应用更新
            for key, value in updates.items():
                if hasattr(holding, key) and value is not None:
                    setattr(holding, key, value)

            holding.updated_at = datetime.now()
            session.commit()
            session.refresh(holding)
            session.expunge(holding)
            return holding

    def close_holding(
        self,
        holding_id: int,
        user_id: int,
        close_price: float,
        realized_profit: float,
    ) -> Optional[Any]:
        """
        清仓持仓

        Args:
            holding_id: 持仓ID
            user_id: 用户ID
            close_price: 清仓价格
            realized_profit: 实现盈亏

        Returns:
            更新后的持仓对象或None
        """
        from data_warehouse.models import FactUserHolding

        with self.session_scope(autocommit=True) as session:
            holding = session.query(FactUserHolding).filter(
                FactUserHolding.id == holding_id,
                FactUserHolding.user_id == user_id,
            ).first()

            if not holding:
                return None

            holding.status = "closed"
            holding.close_date = date.today()
            holding.close_price = close_price
            holding.realized_profit = realized_profit
            holding.updated_at = datetime.now()

            session.commit()
            session.refresh(holding)
            session.expunge(holding)
            return holding

    def refresh_holding_price(self, holding: Any, symbol: str) -> None:
        """
        从数据库刷新持仓的最新价格

        Args:
            holding: 持仓对象
            symbol: 股票代码
        """
        from sqlalchemy import text
        from data_warehouse.models import FactUserHolding

        if not holding or not holding.id:
            return

        with self.session_scope(autocommit=True) as session:
            ts_code = self._to_ts_code(symbol)

            try:
                row = session.execute(
                    text("""
                        SELECT close
                        FROM fact_daily_price_qfq
                        WHERE ts_code = :ts_code
                        AND trade_date = (
                            SELECT MAX(trade_date)
                            FROM fact_daily_price_qfq
                        )
                    """),
                    {"ts_code": ts_code}
                ).fetchone()

                if row and row[0]:
                    current_price = float(row[0])

                    # 重新获取对象到当前会话进行更新
                    db_holding = session.query(FactUserHolding).filter(
                        FactUserHolding.id == holding.id
                    ).first()

                    if db_holding:
                        db_holding.current_price = current_price

                        if db_holding.avg_cost_price and db_holding.avg_cost_price > 0:
                            total_qty = float(db_holding.total_quantity or 0)
                            db_holding.market_value = total_qty * current_price
                            db_holding.profit_amount = (
                                current_price - float(db_holding.avg_cost_price)
                            ) * total_qty
                            db_holding.profit_rate = (
                                (current_price - float(db_holding.avg_cost_price))
                                / float(db_holding.avg_cost_price) * 100
                            )

                        session.commit()
                        # 同步更新传入的对象
                        holding.current_price = db_holding.current_price
                        holding.market_value = db_holding.market_value
                        holding.profit_amount = db_holding.profit_amount
                        holding.profit_rate = db_holding.profit_rate
            except Exception as e:
                logger.warning("更新实时价格失败: %s", e)
                # 不在会话上下文中抛出异常，确保连接正确关闭

    # ========== 辅助方法 ==========

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """标准化股票代码格式"""
        return str(symbol).strip().upper()

    @staticmethod
    def _to_ts_code(symbol: str) -> str:
        """转换为Tushare代码格式"""
        from backend.services.accounts.holdings_utils import to_ts_code
        return to_ts_code(symbol)

    @staticmethod
    def _parse_buy_date(buy_date: Optional[str]) -> date:
        """解析买入日期字符串"""
        if not buy_date:
            return date.today()

        try:
            return datetime.strptime(buy_date, "%Y-%m-%d").date()
        except ValueError:
            return date.today()
