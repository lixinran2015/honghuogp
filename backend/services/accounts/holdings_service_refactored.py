"""
持仓服务 - 重构后的模块化结构

将原有的单一大文件拆分为多个职责单一的模块：
- holdings_service.py: 主服务类和公开API
- holdings_calculations.py: 计算逻辑
- holdings_data_fetcher.py: 数据获取
- holdings_enrichment.py: 数据补充和增强
- holdings_recommendations.py: 建议和推荐逻辑

这种结构提高了：
1. 可维护性 - 每个文件职责单一
2. 可测试性 - 可以独立测试各个模块
3. 可读性 - 代码量减少，逻辑更清晰
4. 可扩展性 - 新增功能更容易
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Any

from backend.services.accounts.holdings_types import HoldingsError, POOL_MAX_SIZE, MAX_LEADER_HOLDINGS
from backend.services.accounts.holdings_repository import HoldingsRepository
from backend.services.accounts.holdings_calculations import (
    calculate_portfolio_context,
    calculate_holding_result,
    compute_today_realized,
    compute_today_total_pnl,
)
from backend.services.accounts.holdings_enrichment import (
    enrich_sector_leader,
    enrich_mainline,
    enrich_strength_score,
)
from backend.services.accounts.holdings_recommendations import (
    compute_pool_full_suggestion,
    get_ai_batch_suggestions,
    refresh_ai_batch_suggestions,
)
from backend.services.accounts.holdings_data_fetcher import HoldingsDataFetcher
from backend.services.data.postgres_warehouse import PostgresWarehouse


class HoldingsService:
    """
    持仓业务服务 - 重构后的主类

    职责：
    1. 协调各个子模块完成业务逻辑
    2. 提供对外API接口
    3. 管理事务和异常处理

    将具体实现委托给：
    - HoldingsRepository: 数据访问
    - HoldingsDataFetcher: 外部数据获取
    - holdings_calculations: 计算逻辑
    - holdings_enrichment: 数据增强
    - holdings_recommendations: 建议生成
    """

    def __init__(self, warehouse: PostgresWarehouse):
        self.warehouse = warehouse
        self.repository = HoldingsRepository(warehouse)
        self.data_fetcher = HoldingsDataFetcher()

    # ========== 查询接口 ==========

    def get_holdings(
        self,
        user_id: int = 1,
        board_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取持仓列表（主入口）

        流程：
        1. 从数据库获取持仓基础数据
        2. 并行获取实时行情和K线
        3. 构建持仓结果（包含盈亏、建议等）
        4. 补充龙头、主线等附加信息
        5. 计算池满建议和AI建议
        """
        # 1. 获取持仓基础数据
        holdings = self.repository.get_active_holdings(user_id, board_type)
        if not holdings:
            return self._empty_holdings_response()

        stock_codes = [h.symbol for h in holdings]

        # 2. 并行获取行情数据（使用data_fetcher模块）
        realtime_data, kline_data = self.data_fetcher.fetch_market_data(
            stock_codes, self.repository.get_session()
        )

        # 3. 获取龙头信息
        leader_map = self.data_fetcher.fetch_leader_map(
            stock_codes, self.repository.get_session()
        )

        # 4. 计算账户级上下文
        portfolio_context = calculate_portfolio_context(holdings, realtime_data)

        # 5. 构建持仓结果
        results = []
        for holding in holdings:
            item = calculate_holding_result(
                holding=holding,
                realtime_data=realtime_data,
                kline_data=kline_data,
                leader_map=leader_map,
                portfolio_context=portfolio_context,
                session=self.repository.get_session(),
            )
            if item:
                results.append(item)

        # 6. 数据增强
        self._enrich_results(results, stock_codes)

        # 7. 计算建议
        pool_suggestion = compute_pool_full_suggestion(
            results, user_id, self.warehouse
        )
        ai_suggestions = get_ai_batch_suggestions(user_id)
        today_realized = compute_today_realized(self.repository.get_session(), user_id)

        # 8. 统计信息
        leader_count = sum(1 for r in results if r.get("is_leader"))

        return {
            "success": True,
            "data": results,
            "count": len(results),
            "pool_max_size": POOL_MAX_SIZE,
            "leader_max_size": MAX_LEADER_HOLDINGS,
            "leader_count": leader_count,
            "pool_full_suggestion": pool_suggestion,
            "ai_batch_suggestions": ai_suggestions,
            "today_realized": today_realized,
        }

    def _empty_holdings_response(self) -> Dict[str, Any]:
        """返回空持仓响应"""
        return {
            "success": True,
            "data": [],
            "count": 0,
            "pool_max_size": POOL_MAX_SIZE,
            "leader_max_size": MAX_LEADER_HOLDINGS,
            "leader_count": 0,
            "pool_full_suggestion": None,
            "ai_batch_suggestions": None,
            "today_realized": 0.0,
        }

    def _enrich_results(self, results: List[Dict], stock_codes: List[str]) -> None:
        """增强持仓结果数据"""
        session = self.repository.get_session()
        try:
            enrich_sector_leader(session, results, stock_codes)
            enrich_mainline(session, results, stock_codes)
            enrich_strength_score(results)
        finally:
            session.close()

    # ========== CRUD 接口 ==========

    def create_holding(
        self,
        symbol: str,
        name: str,
        user_id: int = 1,
        board_type: Optional[str] = None,
        buy_price: Optional[float] = None,
        quantity: Optional[float] = None,
        buy_date: Optional[str] = None,
        bypass_trading_rules: bool = False,
    ) -> Dict[str, Any]:
        """
        创建新持仓或加仓

        流程：
        1. 验证输入参数
        2. 检查交易规则（如未跳过）
        3. 创建或更新持仓记录
        4. 刷新价格信息
        """
        # 1. 参数验证
        self._validate_holding_input(symbol, name)

        # 2. 获取现有持仓
        existing = self.repository.find_holding_by_symbol(user_id, symbol)

        if existing:
            # 加仓逻辑
            return self._add_to_existing_holding(
                existing, buy_price, quantity, buy_date
            )

        # 3. 新开仓 - 检查交易规则
        if not bypass_trading_rules:
            self._validate_trading_rules(user_id, symbol)

        # 4. 创建新持仓
        holding = self.repository.create_holding(
            user_id=user_id,
            symbol=symbol,
            name=name,
            board_type=board_type or "other",
            buy_price=buy_price,
            quantity=quantity,
            buy_date=buy_date,
        )

        # 5. 刷新价格
        self._refresh_holding_price(holding, symbol)

        return {
            "success": True,
            "data": self._holding_to_dict(holding),
        }

    def _validate_holding_input(self, symbol: str, name: str) -> None:
        """验证持仓输入参数"""
        if not symbol or not str(symbol).strip():
            raise HoldingsError("股票代码不能为空", "bad_request")
        if not name or not str(name).strip():
            raise HoldingsError("股票名称不能为空", "bad_request")

    def _validate_trading_rules(self, user_id: int, symbol: str) -> None:
        """验证交易规则"""
        from backend.services.accounts.trading_rules_checker import (
            check_can_open_new_position,
        )

        session = self.repository.get_session()
        try:
            # 检查亏损空仓规则
            today_total_pnl = compute_today_total_pnl(session, user_id, self.data_fetcher)
            allowed, reason = check_can_open_new_position(
                session, user_id, symbol,
                is_new_position=True,
                today_total_pnl=today_total_pnl,
            )
            if not allowed:
                raise HoldingsError(reason, "trading_rule")

            # 检查持仓池容量
            open_count = self.repository.count_active_holdings(user_id)
            if open_count >= POOL_MAX_SIZE:
                raise HoldingsError(
                    f"操作池已满（最多 {POOL_MAX_SIZE} 只）",
                    "trading_rule",
                )

            # 检查龙头数量限制
            self._validate_leader_limit(user_id, symbol)
        finally:
            session.close()

    def _validate_leader_limit(self, user_id: int, symbol: str) -> None:
        """验证龙头数量限制"""
        try:
            current_symbols = self.repository.get_active_symbols(user_id)
            leader_count = self._count_leader_holdings(current_symbols)

            if self._is_leader(symbol) and leader_count >= MAX_LEADER_HOLDINGS:
                raise HoldingsError(
                    f"龙头持仓已达上限（最多 {MAX_LEADER_HOLDINGS} 只龙头）",
                    "trading_rule",
                )
        except HoldingsError:
            raise
        except Exception:
            pass  # 龙头查询异常不阻断交易

    def _count_leader_holdings(self, symbols: List[str]) -> int:
        """统计持仓中的龙头数量"""
        if not symbols:
            return 0

        leader_map = self.data_fetcher.fetch_leader_map(
            symbols, self.repository.get_session()
        )
        return sum(
            1 for sym in symbols
            if leader_map.get(sym) or leader_map.get(self._to_ts_code(sym))
        )

    def _is_leader(self, symbol: str) -> bool:
        """判断股票是否为龙头"""
        leader_map = self.data_fetcher.fetch_leader_map(
            [symbol], self.repository.get_session()
        )
        return bool(leader_map.get(symbol) or leader_map.get(self._to_ts_code(symbol)))

    @staticmethod
    def _to_ts_code(symbol: str) -> str:
        """转换为Tushare代码格式"""
        from backend.services.accounts.holdings_utils import to_ts_code
        return to_ts_code(symbol)

    def _add_to_existing_holding(
        self,
        existing: Any,
        buy_price: Optional[float],
        quantity: Optional[float],
        buy_date: Optional[str],
    ) -> Dict[str, Any]:
        """加仓到现有持仓"""
        updated = self.repository.add_to_holding(
            existing, buy_price, quantity, buy_date
        )
        self._refresh_holding_price(updated, updated.symbol)
        return {
            "success": True,
            "data": self._holding_to_dict(updated),
        }

    def _refresh_holding_price(self, holding: Any, symbol: str) -> None:
        """刷新持仓价格信息"""
        self.repository.refresh_holding_price(holding, symbol)

    @staticmethod
    def _holding_to_dict(holding: Any) -> Dict[str, Any]:
        """将持仓对象转换为字典"""
        return {
            "id": holding.id,
            "symbol": holding.symbol,
            "name": holding.name,
            "board_type": holding.board_type,
            "total_quantity": float(holding.total_quantity or 0),
            "avg_cost_price": float(holding.avg_cost_price or 0),
            "current_price": float(holding.current_price or 0),
        }

    # ... 其他方法（update_holding, close_holding, get_closed_holdings 等）
    # 保持与原始文件相同的逻辑，但委托给 repository
