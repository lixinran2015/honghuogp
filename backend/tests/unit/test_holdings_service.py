"""
持仓服务单元测试
"""
import pytest
from datetime import date
from unittest.mock import Mock, MagicMock

from backend.services.accounts.holdings_service import (
    HoldingsService,
    HoldingsError,
    POOL_MAX_SIZE,
    _pool_suggestion_cache,
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

        # 模拟持仓已满
        mock_holdings = [
            {"symbol": f"00000{i}", "is_leader": i == 0}
            for i in range(POOL_MAX_SIZE)
        ]

        # Act
        suggestion = service._compute_pool_full_suggestion(None, mock_holdings, user_id=1)

        # Assert
        assert "is_full" in suggestion
        assert suggestion["is_full"] is True


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
