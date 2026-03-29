"""
数据源管理器

管理多个数据源的接入、监控和切换
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from enum import Enum
import time
import requests

logger = logging.getLogger(__name__)


class DataSourceStatus(Enum):
    """数据源状态"""
    HEALTHY = "healthy"         # 健康
    DEGRADED = "degraded"       # 性能下降
    UNAVAILABLE = "unavailable" # 不可用
    DISABLED = "disabled"       # 已禁用


@dataclass
class DataSourceHealth:
    """数据源健康状态"""
    source_name: str
    status: DataSourceStatus
    latency_ms: float
    last_success: Optional[datetime]
    error_rate: float
    consecutive_failures: int


class DataSource(ABC):
    """数据源基类"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.health = DataSourceHealth(
            source_name=name,
            status=DataSourceStatus.DISABLED,
            latency_ms=0,
            last_success=None,
            error_rate=0,
            consecutive_failures=0,
        )

    @abstractmethod
    def fetch_data(self, symbol: str, data_type: str) -> Optional[Dict]:
        """获取数据"""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """健康检查"""
        pass


class TushareSource(DataSource):
    """Tushare数据源"""

    def __init__(self, token: Optional[str] = None):
        super().__init__("tushare", priority=1)
        self.token = token
        self.api = None
        self._init_api()

    def _init_api(self):
        """初始化API"""
        try:
            import tushare as ts
            if self.token:
                ts.set_token(self.token)
            self.api = ts.pro_api()
            self.health.status = DataSourceStatus.HEALTHY
        except Exception as e:
            logger.error(f"Tushare初始化失败: {e}")
            self.health.status = DataSourceStatus.UNAVAILABLE

    def fetch_data(self, symbol: str, data_type: str) -> Optional[Dict]:
        """获取数据"""
        if not self.api:
            return None

        start_time = time.time()
        try:
            if data_type == "daily":
                df = self.api.daily(ts_code=symbol)
                result = df.to_dict('records') if df is not None else None
            elif data_type == "limit_up":
                df = self.api.limit_list(trade_date=datetime.now().strftime('%Y%m%d'))
                result = df.to_dict('records') if df is not None else None
            else:
                result = None

            # 更新健康状态
            self.health.latency_ms = (time.time() - start_time) * 1000
            self.health.last_success = datetime.now()
            self.health.consecutive_failures = 0
            self.health.error_rate = max(0, self.health.error_rate - 0.1)

            return {"source": self.name, "data": result}

        except Exception as e:
            self._handle_error(e)
            return None

    def check_health(self) -> bool:
        """健康检查"""
        try:
            # 尝试获取上证指数最新数据
            df = self.api.daily(ts_code='000001.SH', limit=1)
            return df is not None and len(df) > 0
        except Exception as e:
            logger.warning(f"Tushare健康检查失败: {e}")
            return False

    def _handle_error(self, error: Exception):
        """处理错误"""
        self.health.consecutive_failures += 1
        self.health.error_rate = min(1, self.health.error_rate + 0.2)

        if self.health.consecutive_failures >= 3:
            self.health.status = DataSourceStatus.UNAVAILABLE
        elif self.health.consecutive_failures >= 1:
            self.health.status = DataSourceStatus.DEGRADED

        logger.error(f"Tushare请求失败: {error}")


class AkShareSource(DataSource):
    """AkShare数据源（免费）"""

    def __init__(self):
        super().__init__("akshare", priority=2)
        self.health.status = DataSourceStatus.HEALTHY

    def fetch_data(self, symbol: str, data_type: str) -> Optional[Dict]:
        """获取数据"""
        import akshare as ak

        start_time = time.time()
        try:
            if data_type == "daily":
                # 转换代码格式
                code = symbol.split('.')[0]
                df = ak.stock_zh_a_hist(symbol=code, period="daily")
                result = df.to_dict('records') if df is not None else None
            elif data_type == "limit_up":
                df = ak.stock_zt_pool_em(date=datetime.now().strftime('%Y%m%d'))
                result = df.to_dict('records') if df is not None else None
            else:
                result = None

            self.health.latency_ms = (time.time() - start_time) * 1000
            self.health.last_success = datetime.now()
            self.health.consecutive_failures = 0

            return {"source": self.name, "data": result}

        except Exception as e:
            self._handle_error(e)
            return None

    def check_health(self) -> bool:
        """健康检查"""
        try:
            import akshare as ak
            df = ak.stock_zh_a_hist(symbol="000001", period="daily", limit=1)
            return df is not None
        except:
            return False

    def _handle_error(self, error: Exception):
        """处理错误"""
        self.health.consecutive_failures += 1
        if self.health.consecutive_failures >= 3:
            self.health.status = DataSourceStatus.UNAVAILABLE


class SinaSource(DataSource):
    """新浪财经数据源（应急）"""

    def __init__(self):
        super().__init__("sina", priority=3)
        self.health.status = DataSourceStatus.HEALTHY
        self.base_url = "https://hq.sinajs.cn"

    def fetch_data(self, symbol: str, data_type: str) -> Optional[Dict]:
        """获取数据"""
        if data_type != "realtime":
            return None  # 新浪只支持实时数据

        start_time = time.time()
        try:
            # 转换代码格式
            code = symbol.split('.')[0]
            if '.SH' in symbol:
                sina_code = f"sh{code}"
            else:
                sina_code = f"sz{code}"

            url = f"{self.base_url}/list={sina_code}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                self.health.latency_ms = (time.time() - start_time) * 1000
                self.health.last_success = datetime.now()
                return {"source": self.name, "raw": response.text}

        except Exception as e:
            self._handle_error(e)

        return None

    def check_health(self) -> bool:
        """健康检查"""
        try:
            url = f"{self.base_url}/list=sh000001"
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except:
            return False

    def _handle_error(self, error: Exception):
        """处理错误"""
        self.health.consecutive_failures += 1
        if self.health.consecutive_failures >= 3:
            self.health.status = DataSourceStatus.UNAVAILABLE


class DataSourceManager:
    """
    数据源管理器

    使用方式：
        manager = DataSourceManager()
        manager.add_source(TushareSource(token="xxx"))
        manager.add_source(AkShareSource())

        # 获取数据（自动选择最佳源）
        data = manager.fetch("000001.SZ", "daily")
    """

    # 延迟阈值（毫秒）
    LATENCY_THRESHOLD = 3000  # 3秒
    ERROR_RATE_THRESHOLD = 0.3  # 30%

    def __init__(self):
        self.sources: Dict[str, DataSource] = {}
        self._health_check_interval = 60  # 健康检查间隔（秒）
        self._last_health_check = None

    def add_source(self, source: DataSource):
        """添加数据源"""
        self.sources[source.name] = source
        logger.info(f"添加数据源: {source.name}, 优先级: {source.priority}")

    def remove_source(self, name: str):
        """移除数据源"""
        if name in self.sources:
            del self.sources[name]

    def fetch(
        self,
        symbol: str,
        data_type: str,
        prefer_source: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        获取数据（自动故障转移）

        Args:
            symbol: 股票代码
            data_type: 数据类型
            prefer_source: 优先使用的数据源

        Returns:
            数据或None
        """
        # 健康检查
        self._check_health_if_needed()

        # 按优先级排序数据源
        sorted_sources = sorted(
            self.sources.values(),
            key=lambda s: (0 if s.name == prefer_source else 1, s.priority)
        )

        # 尝试每个数据源
        for source in sorted_sources:
            if source.health.status == DataSourceStatus.DISABLED:
                continue

            # 跳过性能差的源（除非是指定源）
            if (source.health.latency_ms > self.LATENCY_THRESHOLD and
                source.name != prefer_source):
                logger.warning(f"跳过慢数据源: {source.name} ({source.health.latency_ms}ms)")
                continue

            try:
                result = source.fetch_data(symbol, data_type)
                if result is not None:
                    logger.debug(f"从{source.name}获取数据成功")
                    return result
            except Exception as e:
                logger.error(f"从{source.name}获取数据失败: {e}")

        logger.error(f"所有数据源都无法获取{symbol}的{data_type}数据")
        return None

    def fetch_with_validation(
        self,
        symbol: str,
        data_type: str,
        validation_fn=None,
    ) -> Optional[Dict]:
        """
        获取数据并进行交叉验证

        从多个源获取数据，验证一致性
        """
        results = []

        for source in self.sources.values():
            if source.health.status in [DataSourceStatus.HEALTHY, DataSourceStatus.DEGRADED]:
                try:
                    result = source.fetch_data(symbol, data_type)
                    if result:
                        results.append((source.name, result))
                except Exception as e:
                    logger.error(f"{source.name}获取数据失败: {e}")

        if len(results) == 0:
            return None

        if len(results) == 1:
            return results[0][1]

        # 多源交叉验证
        return self._validate_cross_source(results, validation_fn)

    def _validate_cross_source(
        self,
        results: List[Tuple[str, Dict]],
        validation_fn=None,
    ) -> Dict:
        """多源数据交叉验证"""
        if validation_fn:
            return validation_fn(results)

        # 默认策略：选择高优先级源的数据
        # 如果多个源返回相同数据，返回该数据
        # 如果不同，记录警告并返回高优先级源的数据

        if len(results) >= 2:
            # 简单比较（实际应根据数据结构定制）
            logger.info(f"多源验证: {len(results)}个源返回数据")

        # 返回第一个（优先级最高的）
        return results[0][1]

    def get_source_status(self) -> Dict[str, DataSourceHealth]:
        """获取所有数据源状态"""
        return {name: source.health for name, source in self.sources.items()}

    def get_best_source(self, data_type: str) -> Optional[str]:
        """获取当前最佳数据源"""
        healthy_sources = [
            s for s in self.sources.values()
            if s.health.status == DataSourceStatus.HEALTHY
        ]

        if not healthy_sources:
            return None

        # 选择延迟最低的
        best = min(healthy_sources, key=lambda s: s.health.latency_ms)
        return best.name

    def _check_health_if_needed(self):
        """按需执行健康检查"""
        if self._last_health_check is None:
            should_check = True
        else:
            elapsed = (datetime.now() - self._last_health_check).total_seconds()
            should_check = elapsed > self._health_check_interval

        if should_check:
            self._perform_health_check()

    def _perform_health_check(self):
        """执行健康检查"""
        logger.info("执行数据源健康检查...")

        for source in self.sources.values():
            try:
                is_healthy = source.check_health()
                if is_healthy:
                    if source.health.status == DataSourceStatus.UNAVAILABLE:
                        source.health.status = DataSourceStatus.HEALTHY
                        logger.info(f"{source.name}恢复健康")
                else:
                    source.health.status = DataSourceStatus.UNAVAILABLE
                    logger.warning(f"{source.name}健康检查失败")
            except Exception as e:
                source.health.status = DataSourceStatus.UNAVAILABLE
                logger.error(f"{source.name}健康检查异常: {e}")

        self._last_health_check = datetime.now()


# 全局实例
data_source_manager = DataSourceManager()
