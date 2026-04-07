"""
持仓服务单元测试
"""
import pytest
from datetime import date
from unittest.mock import Mock, MagicMock, patch

from backend.services.accounts.holdings_service import (
    HoldingsService,
    HoldingsError,
    POOL_MAX_SIZE,
    _pool_suggestion_cache,
    refresh_ai_batch_suggestions,
    _ai_batch_suggestions_cache,
    get_ai_batch_cache,
)


class TestHoldingsService:
    """持仓服务测试类"""

    def test_get_holdings_returns_correct_structure(self, mock_warehouse):
        """测试获取持仓返回正确的数据结构"""
        # Arrange
        mock_session = MagicMock()
        mock_warehouse.get_session.return_value = mock_session

        # 模拟持仓数据
        mock_holding = MagicMock()
        mock_holding.symbol = "000001"
        mock_holding.name = "平安银行"
        mock_holding.total_quantity = 100
        mock_holding.board_type = "short"
        mock_holding.status = "holding"

        mock_session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_holding]

        service = HoldingsService(mock_warehouse)

        # Act
        result = service.get_holdings(user_id=1)

        # Assert
        assert result["success"] is True
        assert "data" in result
        assert "count" in result
        assert result["pool_max_size"] == POOL_MAX_SIZE

    def test_create_holding_validates_symbol(self, mock_warehouse):
        """测试创建持仓时验证股票代码"""
        service = HoldingsService(mock_warehouse)

        with pytest.raises(HoldingsError) as exc_info:
            service.create_holding(symbol="", name="测试")

        assert exc_info.value.code == "bad_request"

    def test_create_holding_validates_name(self, mock_warehouse):
        """测试创建持仓时验证股票名称"""
        service = HoldingsService(mock_warehouse)

        with pytest.raises(HoldingsError) as exc_info:
            service.create_holding(symbol="000001", name="")

        assert exc_info.value.code == "bad_request"

    def test_pool_full_suggestion_when_pool_is_full(self, mock_warehouse):
        """测试当持仓池已满时的建议逻辑"""
        # Arrange
        service = HoldingsService(mock_warehouse)

        # 模拟持仓已满（包含规则选仓所需最小字段）
        mock_holdings = [
            {
                "id": i + 1,
                "symbol": f"00000{i}",
                "name": f"股票{i}",
                "is_leader": i == 0,
                "holding_days": i + 1,
                "below_ma5": True,
                "profit_rate": -float(i + 1),
                "chase_risk_score": i * 10,
                "change_pct": 0.0,
            }
            for i in range(POOL_MAX_SIZE)
        ]

        # Act
        suggestion = service._compute_pool_full_suggestion(None, mock_holdings, user_id=1)

        # Assert
        assert suggestion is not None
        assert "symbol" in suggestion
        assert "reason" in suggestion


class TestHoldingsUtils:
    """持仓工具函数测试"""

    def test_code_6_converts_ts_code_to_6_digit(self):
        """测试将Tushare代码转换为6位代码"""
        from backend.services.accounts.holdings_utils import code_6

        assert code_6("000001.SZ") == "000001"
        assert code_6("600000.SH") == "600000"
        assert code_6("000001") == "000001"

    def test_to_ts_code_converts_6_digit_to_ts_code(self):
        """测试将6位代码转换为Tushare代码"""
        from backend.services.accounts.holdings_utils import to_ts_code

        # 深市
        assert to_ts_code("000001") == "000001.SZ"
        assert to_ts_code("002001") == "002001.SZ"
        assert to_ts_code("300001") == "300001.SZ"

        # 沪市
        assert to_ts_code("600000") == "600000.SH"
        assert to_ts_code("688001") == "688001.SH"

        # 已经带有后缀的
        assert to_ts_code("000001.SZ") == "000001.SZ"


class TestCreateHolding:
    """创建持仓测试"""

    def test_create_existing_holding_adds_quantity(self, mock_warehouse):
        """对已有持仓加仓"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session

        existing = MagicMock()
        existing.total_quantity = 100.0
        existing.avg_cost_price = 10.0
        existing.status = "holding"
        mock_session.query.return_value.filter.return_value.first.return_value = existing

        service = HoldingsService(mock_warehouse)
        result = service.create_holding(symbol="000001", name="平安银行", user_id=1, buy_price=12.0, quantity=50)

        assert result["success"] is True
        assert existing.total_quantity == 150.0
        mock_session.commit.assert_called()

    def test_create_new_position_with_trading_rules_blocked(self, mock_warehouse):
        """新仓位被交易规则拦截"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.count.return_value = 1  # POOL 未满

        with patch("backend.services.accounts.trading_rules_checker.check_can_open_new_position") as mock_check:
            mock_check.return_value = (False, "当日亏损超限")
            service = HoldingsService(mock_warehouse)
            with pytest.raises(HoldingsError) as exc_info:
                service.create_holding(symbol="000001", name="平安银行", user_id=1)
            assert exc_info.value.code == "trading_rule"
            assert "亏损超限" in exc_info.value.message

    def test_create_new_position_bypass_rules(self, mock_warehouse):
        """bypass_trading_rules=true 跳过规则校验"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.count.return_value = 1

        service = HoldingsService(mock_warehouse)
        with patch("backend.services.accounts.trading_rules_checker.check_can_open_new_position") as mock_check:
            result = service.create_holding(symbol="000001", name="平安银行", user_id=1, bypass_trading_rules=True)
            mock_check.assert_not_called()
        assert result["success"] is True

    def test_create_pool_full_blocked(self, mock_warehouse):
        """持仓池已满时拦截"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.filter.return_value.count.return_value = POOL_MAX_SIZE

        with patch("backend.services.accounts.trading_rules_checker.check_can_open_new_position") as mock_check:
            mock_check.return_value = (True, "ok")
            service = HoldingsService(mock_warehouse)
            with pytest.raises(HoldingsError) as exc_info:
                service.create_holding(symbol="000001", name="平安银行", user_id=1)
            assert exc_info.value.code == "trading_rule"
            assert "已满" in exc_info.value.message


class TestUpdateHolding:
    """更新持仓测试"""

    def test_update_buy_success(self, mock_warehouse):
        """加仓成功"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        holding = MagicMock()
        holding.total_quantity = 100.0
        holding.avg_cost_price = 10.0
        mock_session.query.return_value.filter.return_value.first.return_value = holding

        service = HoldingsService(mock_warehouse)
        result = service.update_holding(holding_id=1, op_type="buy", price=12.0, quantity=50)

        assert result["success"] is True
        assert holding.total_quantity == 150.0

    def test_update_sell_closes_position(self, mock_warehouse):
        """减仓至0时清仓"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        holding = MagicMock()
        holding.total_quantity = 100.0
        holding.avg_cost_price = 10.0
        holding.current_price = 12.0
        mock_session.query.return_value.filter.return_value.first.return_value = holding

        with patch("backend.api.accounts.sold_stock.create_sold_stock_from_holding") as mock_sold:
            service = HoldingsService(mock_warehouse)
            result = service.update_holding(holding_id=1, op_type="sell", quantity=100)

            assert result["success"] is True
            assert holding.status == "closed"
            assert holding.realized_profit == 200.0
            mock_sold.assert_called_once()

    def test_update_edit_symbol_and_name(self, mock_warehouse):
        """编辑修改名称和代码"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        holding = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = holding

        service = HoldingsService(mock_warehouse)
        result = service.update_holding(holding_id=1, op_type="edit", name=" 新名字 ", symbol="000002")

        assert holding.name == "新名字"
        assert holding.symbol == "000002.SZ"

    def test_update_not_found(self, mock_warehouse):
        """更新不存在的持仓"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None

        service = HoldingsService(mock_warehouse)
        with pytest.raises(HoldingsError) as exc_info:
            service.update_holding(holding_id=999, op_type="edit")
        assert exc_info.value.code == "not_found"

    def test_update_unknown_op_type(self, mock_warehouse):
        """不支持的操作类型"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        holding = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = holding

        service = HoldingsService(mock_warehouse)
        with pytest.raises(HoldingsError) as exc_info:
            service.update_holding(holding_id=1, op_type="merge")
        assert exc_info.value.code == "bad_request"


class TestCloseHolding:
    """清仓测试"""

    def test_close_holding_success(self, mock_warehouse):
        """正常清仓"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        holding = MagicMock()
        holding.total_quantity = 100.0
        holding.avg_cost_price = 10.0
        holding.current_price = 12.0
        mock_session.query.return_value.filter.return_value.first.return_value = holding

        with patch("backend.api.accounts.sold_stock.create_sold_stock_from_holding") as mock_sold:
            service = HoldingsService(mock_warehouse)
            result = service.close_holding(holding_id=1, close_price=11.0)

            assert result["success"] is True
            assert holding.status == "closed"
            assert holding.realized_profit == 100.0
            mock_sold.assert_called_once()

    def test_close_holding_not_found(self, mock_warehouse):
        """清仓不存在的持仓"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None

        service = HoldingsService(mock_warehouse)
        with pytest.raises(HoldingsError) as exc_info:
            service.close_holding(holding_id=999)
        assert exc_info.value.code == "not_found"


class TestGetClosedHoldings:
    """历史持仓测试"""

    def test_get_closed_holdings(self, mock_warehouse):
        """获取已清仓记录"""
        mock_session = MagicMock()
        mock_warehouse.warehouse_service.get_session.return_value = mock_session

        mock_holding = MagicMock()
        mock_holding.symbol = "000001"
        mock_holding.name = "平安银行"
        mock_holding.status = "closed"
        mock_holding.buy_date = date(2023, 12, 1)
        mock_holding.close_date = date(2024, 1, 1)
        mock_holding.realized_profit = 100.0

        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_holding]

        with patch("backend.services.accounts.holdings_service.calculate_trading_days_diff", return_value=22):
            service = HoldingsService(mock_warehouse)
            result = service.get_closed_holdings(user_id=1)

        assert result["success"] is True
        assert result["count"] == 1
        assert result["data"][0]["symbol"] == "000001"


class TestPickWorstHoldingByRule:
    """规则选最建议清仓标的测试"""

    def test_picks_worst_loss_below_ma5(self, mock_warehouse):
        """选中亏损最深且破5日线的标的"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "A", "name": "A股", "profit_rate": -8.0, "below_ma5": True, "holding_days": 5, "chase_risk_score": 10, "change_pct": 0.0},
            {"symbol": "B", "name": "B股", "profit_rate": -2.0, "below_ma5": True, "holding_days": 5, "chase_risk_score": 10, "change_pct": 0.0},
            {"symbol": "C", "name": "C股", "profit_rate": 5.0, "below_ma5": True, "holding_days": 5, "chase_risk_score": 10, "change_pct": 0.0},
        ]
        worst, reason = service._pick_worst_holding_by_rule(holdings)
        assert worst["symbol"] == "A"
        assert "A股" in reason

    def test_excludes_today_buy(self, mock_warehouse):
        """今日买入不会被选中"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "A", "name": "A股", "profit_rate": -10.0, "below_ma5": True, "holding_days": 0, "chase_risk_score": 10, "change_pct": 0.0},
            {"symbol": "B", "name": "B股", "profit_rate": -3.0, "below_ma5": True, "holding_days": 2, "chase_risk_score": 10, "change_pct": 0.0},
        ]
        worst, reason = service._pick_worst_holding_by_rule(holdings)
        assert worst["symbol"] == "B"

    def test_excludes_not_below_ma5(self, mock_warehouse):
        """未破5日线不会被选中"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "A", "name": "A股", "profit_rate": -10.0, "below_ma5": False, "holding_days": 2, "chase_risk_score": 10, "change_pct": 0.0},
            {"symbol": "B", "name": "B股", "profit_rate": -3.0, "below_ma5": True, "holding_days": 2, "chase_risk_score": 10, "change_pct": 0.0},
        ]
        worst, reason = service._pick_worst_holding_by_rule(holdings)
        assert worst["symbol"] == "B"

    def test_protect_leader_first_3_days(self, mock_warehouse):
        """龙头前3天轻微回撤受保护"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "L", "name": "龙头", "profit_rate": -2.0, "below_ma5": True, "holding_days": 2, "chase_risk_score": 10, "is_leader": True, "change_pct": 0.0},
            {"symbol": "F", "name": "跟风", "profit_rate": -4.0, "below_ma5": True, "holding_days": 2, "chase_risk_score": 10, "sector_leader_role": "跟风", "change_pct": 0.0},
        ]
        worst, reason = service._pick_worst_holding_by_rule(holdings)
        assert worst["symbol"] == "F"

    def test_no_eligible_returns_none(self, mock_warehouse):
        """全部不适配时返回None"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "A", "name": "A股", "profit_rate": 5.0, "below_ma5": False, "holding_days": 0, "chase_risk_score": 10, "change_pct": 0.0},
        ]
        worst, reason = service._pick_worst_holding_by_rule(holdings)
        assert worst is None
        assert reason is None


class TestApplyAddQuota:
    """加仓配额测试"""

    def test_limits_add_count(self, mock_warehouse):
        """限制同时建议加仓的数量"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": f"00{i}", "today_action": "add", "add_score": i} for i in range(10)
        ]
        result = service._apply_add_quota(holdings)
        add_count = sum(1 for r in result if r["today_action"] == "add")
        assert add_count <= 3

    def test_keeps_non_add_unchanged(self, mock_warehouse):
        """非add操作不受影响"""
        service = HoldingsService(mock_warehouse)
        holdings = [
            {"symbol": "A", "today_action": "hold"},
            {"symbol": "B", "today_action": "add", "add_score": 10},
        ]
        result = service._apply_add_quota(holdings)
        assert result[0]["today_action"] == "hold"
        assert result[1]["today_action"] == "add"


class TestAIBatchSuggestions:
    """AI 建议缓存测试"""

    def test_get_ai_batch_suggestions_cache_hit(self, mock_warehouse):
        """缓存命中"""
        _ai_batch_suggestions_cache[1] = {
            "suggestions": [{"symbol": "000001"}],
            "updated_at": 9999999999.0,  # 未来时间确保未过期
        }
        try:
            service = HoldingsService(mock_warehouse)
            result = service._get_ai_batch_suggestions(user_id=1)
            assert result is not None
            assert len(result["suggestions"]) == 1
        finally:
            _ai_batch_suggestions_cache.pop(1, None)

    def test_get_ai_batch_suggestions_cache_miss(self, mock_warehouse):
        """缓存未命中"""
        service = HoldingsService(mock_warehouse)
        result = service._get_ai_batch_suggestions(user_id=99)
        assert result is None

    def test_refresh_ai_skips_non_trading_hours(self, mock_warehouse):
        """非交易时段不刷新"""
        with patch("backend.utils.trade_date_utils.is_trading_hours_cn") as mock_trading:
            mock_trading.return_value = False
            refresh_ai_batch_suggestions(mock_warehouse, user_id=1)
            mock_trading.assert_called_once()

    def test_refresh_ai_empty_holdings(self, mock_warehouse):
        """无持仓时缓存为空列表"""
        mock_warehouse.warehouse_service = MagicMock()
        original_cache = dict(_ai_batch_suggestions_cache)
        with patch("backend.utils.trade_date_utils.is_trading_hours_cn") as mock_trading, \
             patch("backend.utils.trade_date_utils.is_trade_date") as mock_trade_date, \
             patch.object(HoldingsService, "get_holdings", return_value={"success": True, "data": []}) as mock_get:
            mock_trading.return_value = True
            mock_trade_date.return_value = True
            _ai_batch_suggestions_cache.clear()
            try:
                refresh_ai_batch_suggestions(mock_warehouse, user_id=1)
                assert _ai_batch_suggestions_cache[1]["suggestions"] == []
            finally:
                _ai_batch_suggestions_cache.clear()
                _ai_batch_suggestions_cache.update(original_cache)

    def test_refresh_ai_success(self, mock_warehouse):
        """正常刷新并写入缓存"""
        mock_warehouse.warehouse_service = MagicMock()
        original_cache = dict(_ai_batch_suggestions_cache)
        with patch("backend.utils.trade_date_utils.is_trading_hours_cn") as mock_trading, \
             patch("backend.utils.trade_date_utils.is_trade_date") as mock_trade_date, \
             patch.object(HoldingsService, "get_holdings", return_value={
                 "success": True,
                 "data": [
                     {"symbol": "000001.SZ", "name": "平安银行", "profit_rate": 5.0, "today_action": "hold", "holding_days": 3, "is_leader": True}
                 ]
             }), \
             patch("backend.services.analysis.ai_analysis_service.AIAnalysisService") as MockAI:
            mock_trading.return_value = True
            mock_trade_date.return_value = True
            MockAI.return_value.batch_holding_actions.return_value = [
                {"symbol": "000001.SZ", "action": "hold"}
            ]
            _ai_batch_suggestions_cache.clear()
            try:
                refresh_ai_batch_suggestions(mock_warehouse, user_id=1)
                assert _ai_batch_suggestions_cache[1]["suggestions"][0]["name"] == "平安银行"
            finally:
                _ai_batch_suggestions_cache.clear()
                _ai_batch_suggestions_cache.update(original_cache)
