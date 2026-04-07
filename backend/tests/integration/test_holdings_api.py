import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration


class TestGetHoldings:
    """获取持仓列表测试"""

    def test_get_holdings_success(self, integration_client):
        """正常获取持仓列表"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.get_holdings.return_value = {
                "success": True, "data": [{"symbol": "000001"}], "count": 1, "pool_max_size": 5
            }
            MockSvc.return_value = svc

            response = integration_client.get("/api/holdings/?user_id=1")
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["count"] == 1

    def test_get_holdings_service_error(self, integration_client):
        """服务返回失败时触发500"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.get_holdings.return_value = {"success": False, "error": "数据库错误"}
            MockSvc.return_value = svc

            response = integration_client.get("/api/holdings/?user_id=1")
            assert response.status_code == 500
            assert "数据库错误" in response.json()["detail"]


class TestCreateHolding:
    """创建持仓测试"""

    def test_create_holding_validation_missing_symbol(self, integration_client):
        """缺少symbol时返回422（Pydantic校验）"""
        response = integration_client.post("/api/holdings/", json={"name": "测试", "user_id": 1})
        assert response.status_code == 422

    def test_create_holding_success(self, integration_client):
        """正常创建持仓"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.create_holding.return_value = {"success": True, "id": 1}
            MockSvc.return_value = svc

            response = integration_client.post(
                "/api/holdings/",
                json={"symbol": "000001", "name": "平安银行", "user_id": 1}
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_create_holding_service_bad_request(self, integration_client):
        """HoldingsError bad_request 转为 400"""
        from backend.services.accounts.holdings_service import HoldingsError
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.create_holding.side_effect = HoldingsError(code="bad_request", message="代码非法")
            MockSvc.return_value = svc

            response = integration_client.post(
                "/api/holdings/",
                json={"symbol": "000001", "name": "平安银行", "user_id": 1}
            )
            assert response.status_code == 400
            assert "代码非法" in response.json()["detail"]


class TestUpdateHolding:
    """更新持仓测试"""

    def test_update_holding_success(self, integration_client):
        """正常更新持仓"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.update_holding.return_value = {"success": True, "id": 1}
            MockSvc.return_value = svc

            response = integration_client.put(
                "/api/holdings/1",
                json={"user_id": 1, "op_type": "edit", "name": "新名字"}
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_update_holding_not_found(self, integration_client):
        """更新不存在的持仓返回404"""
        from backend.services.accounts.holdings_service import HoldingsError
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.update_holding.side_effect = HoldingsError(code="not_found", message="持仓不存在")
            MockSvc.return_value = svc

            response = integration_client.put(
                "/api/holdings/999",
                json={"user_id": 1, "op_type": "edit"}
            )
            assert response.status_code == 404
            assert "持仓不存在" in response.json()["detail"]


class TestDeleteHolding:
    """删除/清仓持仓测试"""

    def test_delete_holding_success(self, integration_client):
        """正常清仓"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.close_holding.return_value = {"success": True}
            MockSvc.return_value = svc

            response = integration_client.delete("/api/holdings/1?user_id=1&close_price=10.5")
            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_delete_holding_not_found(self, integration_client):
        """清仓不存在的持仓返回404"""
        from backend.services.accounts.holdings_service import HoldingsError
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.close_holding.side_effect = HoldingsError(code="not_found", message="持仓不存在")
            MockSvc.return_value = svc

            response = integration_client.delete("/api/holdings/999?user_id=1")
            assert response.status_code == 404


class TestGetClosedHoldings:
    """获取历史记录测试"""

    def test_get_closed_holdings_success(self, integration_client):
        """正常获取历史记录"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.get_closed_holdings.return_value = {
                "success": True, "data": [], "count": 0
            }
            MockSvc.return_value = svc

            response = integration_client.get("/api/holdings/history?user_id=1")
            assert response.status_code == 200
            assert response.json()["count"] == 0


class TestUpdateCloseInfo:
    """更新清仓信息测试"""

    def test_update_close_info_success(self, integration_client):
        """正常更新清仓信息"""
        with patch("backend.api.accounts.holdings.HoldingsService") as MockSvc:
            svc = MagicMock()
            svc.update_close_info.return_value = {"success": True}
            MockSvc.return_value = svc

            response = integration_client.put(
                "/api/holdings/1/update-close",
                json={"user_id": 1, "close_price": 9.8, "close_date": "2024-01-01"}
            )
            assert response.status_code == 200


class TestRefreshAiSuggestions:
    """刷新AI建议测试"""

    def test_refresh_ai_suggestions_success(self, integration_client):
        """正常刷新AI建议"""
        with patch("backend.api.accounts.holdings.svc_refresh_ai_batch_suggestions") as mock_refresh, \
             patch("backend.api.accounts.holdings.get_ai_batch_cache") as mock_cache:
            mock_cache.return_value = {
                1: {"suggestions": [{"symbol": "000001"}], "updated_at": 1700000000.0}
            }

            # 确保清除可能存在的冷却时间
            from backend.api.accounts.holdings import _ai_refresh_timestamps
            _ai_refresh_timestamps.clear()

            response = integration_client.post("/api/holdings/ai-suggestions/refresh?user_id=1")
            assert response.status_code == 200
            assert response.json()["success"] is True
            assert response.json()["suggestions_count"] == 1
            mock_refresh.assert_called_once()
            _ai_refresh_timestamps.clear()

    def test_refresh_ai_suggestions_cooldown(self, integration_client):
        """冷却时间内重复请求返回429"""
        import time
        from backend.api.accounts.holdings import _ai_refresh_timestamps, _AI_REFRESH_COOLDOWN

        # 设置最近刷新时间
        _ai_refresh_timestamps[1] = time.time()

        response = integration_client.post("/api/holdings/ai-suggestions/refresh?user_id=1")
        assert response.status_code == 429
        assert "过于频繁" in response.json()["detail"]
        assert "Retry-After" in response.headers

        # 清理
        _ai_refresh_timestamps.clear()


class TestParseBuyImage:
    """解析买入截图测试"""

    def test_parse_buy_image_empty(self, integration_client):
        """空图片返回400"""
        response = integration_client.post(
            "/api/holdings/parse-buy-image",
            files={"file": ("empty.png", b"", "image/png")}
        )
        assert response.status_code == 400
        assert "为空" in response.json()["detail"]

    def test_parse_buy_image_success(self, integration_client):
        """正常解析图片"""
        with patch("backend.api.accounts.holdings.parse_buy_image") as mock_parse, \
             patch("utils.config_manager.ConfigManager") as MockConfig:
            mock_parse.return_value = {"success": True, "records": [{"symbol": "000001"}]}

            response = integration_client.post(
                "/api/holdings/parse-buy-image",
                files={"file": ("test.png", b"fake-image-content-x" * 10, "image/png")}
            )
            assert response.status_code == 200
            assert response.json()["success"] is True
            mock_parse.assert_called_once()
