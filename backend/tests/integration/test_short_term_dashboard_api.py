import pytest
from unittest.mock import MagicMock, patch
from datetime import date

pytestmark = pytest.mark.integration


class MockSignal:
    """模拟短线信号对象"""
    def __init__(self, type_, level, ts_code, name, message, score, trade_date, extra_data):
        self.type = MagicMock()
        self.type.value = type_
        self.level = MagicMock()
        self.level.value = level
        self.ts_code = ts_code
        self.name = name
        self.message = message
        self.score = score
        self.trade_date = trade_date
        self.extra_data = extra_data


def test_signals_invalid_date(integration_client):
    """日期格式错误返回 400"""
    response = integration_client.get("/api/short-term/dashboard/signals?trade_date=bad-date")
    assert response.status_code == 400
    assert "格式错误" in response.json()["detail"]


def test_signals_success(integration_client):
    """正常获取所有信号"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_all_signals.return_value = {
            "leader": [
                MockSignal("leader", "strong", "000001.SZ", "平安银行", "龙头信号", 85, date(2026, 4, 5), {"role": "空间"})
            ],
            "limit_up": [
                MockSignal("limit_up", "medium", "000002.SZ", "万科A", "涨停缩量", 70, date(2026, 4, 5), {"volume_ratio": 0.5})
            ],
            "startup": [
                MockSignal("startup", "watch", "000003.SZ", "测试股", "启动", 60, date(2026, 4, 5), {"stage": "early"})
            ],
            "timestamp": 1234567890,
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/signals?min_level=watch")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 3
        assert "leader" in data["data"]
        assert data["data"]["leader"][0]["score"] == 85


def test_signals_filter_by_level(integration_client):
    """按级别过滤信号"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_all_signals.return_value = {
            "leader": [
                MockSignal("leader", "strong", "000001.SZ", "A", "msg", 90, date(2026, 4, 5), {}),
                MockSignal("leader", "watch", "000002.SZ", "B", "msg", 50, date(2026, 4, 5), {}),
            ],
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/signals?min_level=strong")
        data = response.json()
        assert data["total"] == 1
        assert data["data"]["leader"][0]["level"] == "strong"


def test_leader_signals_success(integration_client):
    """正常获取龙头信号"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_leader_signals.return_value = [
            MockSignal("leader", "strong", "000001.SZ", "平安银行", "msg", 85, date(2026, 4, 5), {"role": "空间", "status": "active"})
        ]
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/signals/leader?min_score=60")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["data"][0]["role"] == "空间"


def test_limit_up_signals_success(integration_client):
    """正常获取涨停缩量信号"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_limit_up_signals.return_value = [
            MockSignal("limit_up", "medium", "000002.SZ", "万科A", "msg", 75, date(2026, 4, 5), {"volume_ratio": 0.3, "limit_up_date": "2026-04-05"})
        ]
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/signals/limit-up")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"][0]["volume_ratio"] == 0.3


def test_startup_signals_success(integration_client):
    """正常获取启动信号"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_startup_signals.return_value = [
            MockSignal("startup", "strong", "000003.SZ", "测试", "msg", 80, date(2026, 4, 5), {"stage": " breakout", "golden_cross_date": "2026-04-01"})
        ]
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/signals/startup?days=5&min_score=70")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 1


def test_daily_report_success(integration_client):
    """正常获取每日复盘报告"""
    with patch("backend.api.short_term.dashboard.get_short_term_core_service") as MockSvc:
        svc = MagicMock()
        svc.get_daily_report.return_value = {
            "summary": "市场活跃",
            "top_stocks": [{"ts_code": "000001.SZ", "name": "平安银行"}],
        }
        MockSvc.return_value = svc

        response = integration_client.get("/api/short-term/dashboard/daily-report")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "summary" in data["data"]


def test_market_brief_success(integration_client):
    """正常获取市场简报"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS, \
         patch("backend.api.short_term.dashboard.get_trade_date_n_days_ago") as mock_yesterday:
        mock_session = MagicMock()
        emotion = MagicMock()
        emotion.trade_date = date(2026, 4, 5)
        emotion.emotion_stage = "高潮"
        emotion.total_limit_up = 100
        emotion.total_limit_down = 2
        emotion.broken_limit_up = 5

        limit_up_stats = MagicMock()
        limit_up_stats.max_height = 8
        limit_up_stats.limit_up_count = 95

        mock_session.query.return_value.filter.return_value.first.side_effect = [emotion, emotion, limit_up_stats]
        mock_session.query.return_value.scalar.side_effect = [date(2026, 4, 5), date(2026, 4, 5)]
        mock_yesterday.return_value = date(2026, 4, 4)

        MockWS.return_value.get_session.return_value = mock_session

        response = integration_client.get("/api/short-term/dashboard/market-brief")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["emotion_cycle"] == "高涨期"
        assert data["data"]["market_status"] == "活跃"
        assert data["data"]["max_continuous"] == 8


def test_market_brief_fallback_on_error(integration_client):
    """市场简报异常时返回默认数据"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS:
        MockWS.return_value.get_session.side_effect = Exception("db error")

        response = integration_client.get("/api/short-term/dashboard/market-brief")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["emotion_cycle"] == "震荡期"
        assert data["data"]["market_status"] == "正常"


def test_limit_up_ladder_success(integration_client):
    """正常获取涨停梯队"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS:
        mock_session = MagicMock()
        mock_session.query.return_value.scalar.return_value = date(2026, 4, 5)
        mock_session.query.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.all.return_value = [
            ("000001.SZ", "平安银行", 3, True),
            ("000002.SZ", "万科A", 2, False),
        ]
        MockWS.return_value.get_session.return_value = mock_session

        response = integration_client.get("/api/short-term/dashboard/limit-up-ladder")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trade_date"] == "2026-04-05"
        assert "3" in data["ladder"]
        assert data["ladder"]["3"][0]["is_space_leader"] is True


def test_limit_up_ladder_empty(integration_client):
    """无涨停数据时返回空 ladder"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS:
        mock_session = MagicMock()
        mock_session.query.return_value.scalar.return_value = None
        MockWS.return_value.get_session.return_value = mock_session

        response = integration_client.get("/api/short-term/dashboard/limit-up-ladder")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trade_date"] is None
        assert data["ladder"] == {}


def test_broken_board_ladder_success(integration_client):
    """正常获取断板梯队"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS:
        mock_session = MagicMock()
        mock_session.query.return_value.scalar.return_value = date(2026, 4, 5)
        mock_session.query.return_value.outerjoin.return_value.filter.return_value.all.return_value = [
            ("000001.SZ", "平安银行", 5, "warning", -2.5, True),
            ("000002.SZ", "万科A", 4, "normal", -5.0, True),
        ]
        MockWS.return_value.get_session.return_value = mock_session

        response = integration_client.get("/api/short-term/dashboard/broken-board-ladder")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trade_date"] == "2026-04-05"
        assert "5" in data["ladder"]
        assert data["ladder"]["5"][0]["break_status"] == "warning"
        assert data["ladder"]["5"][0]["price_change_pct"] == -2.5


def test_broken_board_ladder_empty(integration_client):
    """无断板数据时返回空 ladder"""
    with patch("data_warehouse.service.warehouse_service.WarehouseService") as MockWS:
        mock_session = MagicMock()
        mock_session.query.return_value.scalar.return_value = None
        MockWS.return_value.get_session.return_value = mock_session

        response = integration_client.get("/api/short-term/dashboard/broken-board-ladder")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["trade_date"] is None
        assert data["ladder"] == {}
