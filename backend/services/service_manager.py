"""
全局服务管理器
实现服务单例化，避免重复创建和初始化
"""
import logging
import threading
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import hashlib

logger = logging.getLogger(__name__)


class ServiceManager:
    """
    全局服务管理器（单例模式）
    
    功能：
    1. 服务单例化 - 避免重复创建服务实例
    2. K线数据缓存 - 避免重复查询相同数据
    3. 线程安全 - 支持多线程环境
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        with self.__class__._lock:
            if self._initialized:
                return
            self._initialized = True
        self._services: Dict[str, Any] = {}
        self._cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        
        # 缓存配置
        self._cache_ttl = 300  # 缓存有效期（秒）
        self._max_cache_size = 100  # 最大缓存条目数
        
        logger.info("✅ ServiceManager 初始化完成")
    
    # ========== 服务单例管理 ==========
    
    def get_market_data_service(self):
        """获取 MarketDataService 单例"""
        if 'market_data_service' not in self._services:
            with self._lock:
                if 'market_data_service' not in self._services:
                    try:
                        from backend.services.market_data_service_v2 import MarketDataService
                    except ImportError:
                        from backend.services.market_data_service import MarketDataService
                    self._services['market_data_service'] = MarketDataService()
                    logger.info("✅ MarketDataService 单例创建完成")
        return self._services['market_data_service']
    
    def get_postgres_warehouse(self):
        """获取 PostgresWarehouse 单例"""
        if 'postgres_warehouse' not in self._services:
            with self._lock:
                if 'postgres_warehouse' not in self._services:
                    try:
                        from backend.services.data.postgres_warehouse import PostgresWarehouse
                        warehouse = PostgresWarehouse()
                        if warehouse._initialized:
                            self._services['postgres_warehouse'] = warehouse
                            logger.info("✅ PostgresWarehouse 单例创建完成")
                        else:
                            logger.warning("⚠️ PostgresWarehouse 初始化未完成，下次调用将重试")
                    except Exception as e:
                        logger.warning(f"⚠️ PostgresWarehouse 初始化失败: {e}")
        return self._services['postgres_warehouse']
    
    def get_stock_universe_service(self):
        """获取 StockUniverseService 单例"""
        if 'stock_universe_service' not in self._services:
            with self._lock:
                if 'stock_universe_service' not in self._services:
                    from backend.services.stock.stock_universe_service import StockUniverseService
                    self._services['stock_universe_service'] = StockUniverseService()
                    logger.info("✅ StockUniverseService 单例创建完成")
        return self._services['stock_universe_service']
    
    def get_recommendation_result_service(self):
        """获取 RecommendationResultService 单例"""
        if 'recommendation_result_service' not in self._services:
            with self._lock:
                if 'recommendation_result_service' not in self._services:
                    from backend.services.recommendation.recommendation_result_service import RecommendationResultService
                    self._services['recommendation_result_service'] = RecommendationResultService()
                    logger.info("✅ RecommendationResultService 单例创建完成")
        return self._services['recommendation_result_service']
    
    def get_data_warehouse(self):
        """获取 DataWarehouse 单例"""
        if 'data_warehouse' not in self._services:
            with self._lock:
                if 'data_warehouse' not in self._services:
                    from backend.services.data.data_warehouse import DataWarehouse
                    self._services['data_warehouse'] = DataWarehouse()
                    logger.info("✅ DataWarehouse 单例创建完成")
        return self._services['data_warehouse']
    
    def get_tushare_service(self):
        """获取 TushareService 单例，避免多处重复初始化"""
        if 'tushare_service' not in self._services:
            with self._lock:
                if 'tushare_service' not in self._services:
                    from backend.services.tushare_service import TushareService
                    self._services['tushare_service'] = TushareService()
                    logger.info("✅ TushareService 单例创建完成")
        return self._services['tushare_service']

    def get_data_scheduler(self, warehouse=None):
        """获取 DataScheduler 单例，避免多处重复初始化"""
        if 'data_scheduler' not in self._services:
            with self._lock:
                if 'data_scheduler' not in self._services:
                    from backend.services.data.data_scheduler import DataScheduler
                    w = warehouse if warehouse is not None else self.get_data_warehouse()
                    self._services['data_scheduler'] = DataScheduler(warehouse=w)
                    logger.info("✅ DataScheduler 单例创建完成")
        return self._services['data_scheduler']

    def get_financial_data_service(self):
        """获取 FinancialDataService 单例"""
        if 'financial_data_service' not in self._services:
            with self._lock:
                if 'financial_data_service' not in self._services:
                    from backend.services.data.financial_data_service import FinancialDataService
                    self._services['financial_data_service'] = FinancialDataService()
                    logger.info("✅ FinancialDataService 单例创建完成")
        return self._services['financial_data_service']
    
    def get_darwin_data_service(self):
        """获取 DarwinDataService 单例"""
        if 'darwin_data_service' not in self._services:
            with self._lock:
                if 'darwin_data_service' not in self._services:
                    from backend.services.darwin.darwin_data_service import DarwinDataService
                    self._services['darwin_data_service'] = DarwinDataService()
                    logger.info("✅ DarwinDataService 单例创建完成")
        return self._services['darwin_data_service']
    
    def get_stock_filter_service(self):
        """获取 StockFilterService 单例"""
        if 'stock_filter_service' not in self._services:
            with self._lock:
                if 'stock_filter_service' not in self._services:
                    from backend.services.stock.stock_filter_service import StockFilterService
                    self._services['stock_filter_service'] = StockFilterService()
                    logger.info("✅ StockFilterService 单例创建完成")
        return self._services['stock_filter_service']
    
    # ========== K线数据缓存 ==========
    
    def _generate_cache_key(self, codes: list, days: int) -> str:
        """生成缓存键"""
        codes_str = ','.join(sorted([str(c) for c in codes]))
        key_str = f"{codes_str}:{days}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get_cached_kline(self, codes: list, days: int) -> Optional[pd.DataFrame]:
        """
        获取缓存的K线数据
        
        Args:
            codes: 股票代码列表
            days: 天数
            
        Returns:
            DataFrame 或 None（未命中缓存）
        """
        cache_key = self._generate_cache_key(codes, days)
        
        with self._cache_lock:
            if cache_key in self._cache:
                cache_entry = self._cache[cache_key]
                # 检查是否过期
                if datetime.now() - cache_entry['timestamp'] < timedelta(seconds=self._cache_ttl):
                    logger.debug(f"✅ K线缓存命中: {len(codes)} 只股票, {days} 天")
                    return cache_entry['data'].copy()
                else:
                    # 过期，删除
                    del self._cache[cache_key]
        
        return None
    
    def set_cached_kline(self, codes: list, days: int, data: pd.DataFrame):
        """
        设置K线数据缓存
        
        Args:
            codes: 股票代码列表
            days: 天数
            data: K线数据
        """
        cache_key = self._generate_cache_key(codes, days)
        
        with self._cache_lock:
            # 检查缓存大小，清理过期条目
            if len(self._cache) >= self._max_cache_size:
                self._cleanup_cache()
            
            self._cache[cache_key] = {
                'data': data.copy(),
                'timestamp': datetime.now()
            }
            logger.debug(f"✅ K线数据已缓存: {len(codes)} 只股票, {days} 天")
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        now = datetime.now()
        expired_keys = []
        
        for key, entry in self._cache.items():
            if now - entry['timestamp'] > timedelta(seconds=self._cache_ttl):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        # 如果还是太多，删除最旧的
        if len(self._cache) >= self._max_cache_size:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1]['timestamp'])
            for key, _ in sorted_items[:len(self._cache) // 2]:
                del self._cache[key]
        
        logger.debug(f"🧹 缓存清理完成: 删除 {len(expired_keys)} 个过期条目")
    
    def clear_cache(self):
        """清空所有缓存"""
        with self._cache_lock:
            self._cache.clear()
        logger.info("🧹 所有缓存已清空")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        with self._cache_lock:
            return {
                'cache_size': len(self._cache),
                'max_size': self._max_cache_size,
                'ttl_seconds': self._cache_ttl
            }


# 全局单例
_service_manager: Optional[ServiceManager] = None


def get_service_manager() -> ServiceManager:
    """获取全局服务管理器"""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager

