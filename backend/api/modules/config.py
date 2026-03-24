"""
模块配置管理
用于控制短线/长线模块的启用/禁用
支持配置热加载和运行时切换
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_MODULE_CONFIG = {
    "short_term": {
        "enabled": True,
        "name": "短线龙头",
        "description": "涨停、龙头、板块轮动等短线策略",
        "features": {
            "leader_tracking": True,
            "limit_up": True,
            "sector_rotation": True,
            "sentiment": True,
            "backtest": True,
            "stock_startup": True,
            "hot_sectors": True,
            "abnormal_analysis": True,
            "monitor_near5": True,
            "watchlist": True,
            "guba_popularity": True,
            "startup_watch": True,
            "hot_sector": True,
            "money_flow": True,
            "stock_selector": True
        }
    },
    "long_term": {
        "enabled": False,
        "name": "趋势长线",
        "description": "基本面、达尔文评分、长期趋势等价值投资",
        "features": {
            "darwin": False,
            "long_term_recommendation": False,
            "industry_leaders": False,
            "industry_cycle": False,
            "monthly_themes": False,
            "stable_rise": False,
            "high_180d": False,
            "stock_filters": False,
            "engines": False
        }
    },
    "common": {
        "enabled": True,
        "name": "基础功能",
        "description": "共享基础模块",
        "features": {
            "market": True,
            "fund": True,
            "reports": True,
            "stock_universe": True,
            "stock_kline": True,
            "holdings": True,
            "sold_stock": True,
            "data_management": True,
            "data_warehouse": True,
            "scheduled_task": True,
            "daily_review": True,
            "knowledge_base": True,
            "ai_chat": True,
            "recommendation": True
        }
    }
}


class ModuleConfig:
    """模块配置管理器"""

    _instance = None
    _config = None
    _config_path = None
    _last_load_time = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        """初始化配置"""
        self._config_path = Path(__file__).parent.parent.parent.parent / "config.json"
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self._config = config.get("modules", DEFAULT_MODULE_CONFIG)
                    self._last_load_time = datetime.now()
                    logger.info("✅ 模块配置加载成功")
            else:
                logger.warning(f"⚠️ 配置文件不存在，使用默认配置: {self._config_path}")
                self._config = DEFAULT_MODULE_CONFIG.copy()
                self._last_load_time = datetime.now()
        except Exception as e:
            logger.error(f"❌ 加载模块配置失败: {e}")
            self._config = DEFAULT_MODULE_CONFIG.copy()
            self._last_load_time = datetime.now()

    def reload_config(self) -> bool:
        """热加载配置"""
        try:
            self._load_config()
            logger.info("🔄 配置热加载成功")
            return True
        except Exception as e:
            logger.error(f"❌ 配置热加载失败: {e}")
            return False

    def _save_config(self) -> bool:
        """保存配置到文件"""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)
            else:
                full_config = {}

            full_config["modules"] = self._config

            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, ensure_ascii=False, indent=2)

            logger.info("💾 配置保存成功")
            return True
        except Exception as e:
            logger.error(f"❌ 配置保存失败: {e}")
            return False

    def set_module_enabled(self, module_name: str, enabled: bool) -> bool:
        """设置模块启用状态"""
        if module_name not in self._config:
            logger.warning(f"⚠️ 未知模块: {module_name}")
            return False

        self._config[module_name]["enabled"] = enabled
        success = self._save_config()
        if success:
            logger.info(f"{'✅' if enabled else '❌'} 模块 {module_name} 已{'启用' if enabled else '禁用'}")
        return success

    def set_feature_enabled(self, module_name: str, feature_name: str, enabled: bool) -> bool:
        """设置功能启用状态"""
        if module_name not in self._config:
            logger.warning(f"⚠️ 未知模块: {module_name}")
            return False

        module = self._config[module_name]
        if "features" not in module:
            module["features"] = {}

        module["features"][feature_name] = enabled
        success = self._save_config()
        if success:
            logger.info(f"{'✅' if enabled else '❌'} 功能 {module_name}.{feature_name} 已{'启用' if enabled else '禁用'}")
        return success

    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self._config

    def is_module_enabled(self, module_name: str) -> bool:
        """检查模块是否启用"""
        module = self._config.get(module_name, {})
        return module.get("enabled", False)

    def is_feature_enabled(self, module_name: str, feature_name: str) -> bool:
        """检查功能是否启用"""
        module = self._config.get(module_name, {})
        if not module.get("enabled", False):
            return False
        features = module.get("features", {})
        return features.get(feature_name, False)

    def get_enabled_modules(self) -> Dict[str, Dict[str, Any]]:
        """获取所有启用的模块"""
        return {
            name: config for name, config in self._config.items()
            if config.get("enabled", False)
        }

    def get_enabled_features(self, module_name: str) -> Dict[str, bool]:
        """获取模块中所有启用的功能"""
        module = self._config.get(module_name, {})
        if not module.get("enabled", False):
            return {}
        return {
            name: enabled for name, enabled in module.get("features", {}).items()
            if enabled
        }

    def get_module_info(self, module_name: str) -> Optional[Dict[str, Any]]:
        """获取模块信息"""
        return self._config.get(module_name)

    def get_all_modules(self) -> Dict[str, Any]:
        """获取所有模块信息（包括禁用状态）"""
        return {
            name: {
                "enabled": config.get("enabled", False),
                "name": config.get("name", name),
                "description": config.get("description", ""),
                "features": config.get("features", {})
            }
            for name, config in self._config.items()
        }


# 全局配置实例
module_config = ModuleConfig()
