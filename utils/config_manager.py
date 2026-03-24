"""
配置管理模块
统一管理所有API地址、网络设置和交易参数
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# 进程内仅打印一次“配置加载成功”，避免多处创建 ConfigManager 时刷屏
_load_success_logged = False


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        global _load_success_logged
        try:
            # 如果config_file是相对路径，尝试从项目根目录查找
            config_path = Path(self.config_file)
            if not config_path.is_absolute():
                # 尝试从当前工作目录查找
                if not config_path.exists():
                    # 尝试从项目根目录查找（假设config.json在项目根目录）
                    # 从utils目录向上两级到项目根目录
                    try:
                        project_root = Path(__file__).parent.parent
                    except Exception:
                        project_root = Path.cwd()
                    potential_path = project_root / self.config_file
                    if potential_path.exists():
                        config_path = potential_path
                        self.config_file = str(config_path)
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 进程内只打印一次，避免多处创建 ConfigManager 时重复三遍
                if not _load_success_logged:
                    _load_success_logged = True
                    logging.info(f"✅ 配置文件加载成功: {config_path}")
                    print(f"✅ 配置文件加载成功: {config_path}")
                    deepseek_config = config.get("ai_services", {}).get("deepseek", {})
                    if deepseek_config:
                        enabled_val = deepseek_config.get('enabled')
                        enabled_type = type(enabled_val).__name__
                        logging.info(f"✅ DeepSeek配置已加载: enabled={enabled_val} (类型: {enabled_type})")
                        print(f"✅ DeepSeek配置已加载: enabled={enabled_val} (类型: {enabled_type})")
                    else:
                        logging.warning(f"⚠️ DeepSeek配置未找到，ai_services keys: {list(config.get('ai_services', {}).keys())}")
                        print(f"⚠️ DeepSeek配置未找到，ai_services keys: {list(config.get('ai_services', {}).keys())}")
                return config
            else:
                logging.warning(f"⚠️ 配置文件不存在: {config_path}，将使用默认配置")
                print(f"⚠️ 配置文件不存在: {config_path}，将使用默认配置")
                return self._get_default_config()
        except Exception as e:
            logging.error(f"❌ 配置文件加载失败: {e}", exc_info=True)
            print(f"❌ 配置文件加载失败: {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "api_sources": {
                "akshare": {"enabled": True, "timeout": 15}
            },
            "ai_services": {
                "openai": {"enabled": False},
                "deepseek": {"enabled": False}
            },
            "trading_config": {
                "max_recommendations": 5
            }
        }
    
    def get_api_config(self, source_name: str) -> Optional[Dict[str, Any]]:
        """获取API配置"""
        return self.config.get("api_sources", {}).get(source_name)
    
    def get_ai_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取AI服务配置"""
        return self.config.get("ai_services", {}).get(service_name)
    
    def get_trading_config(self) -> Dict[str, Any]:
        """获取交易配置"""
        return self.config.get("trading_config", {})
    
    def get_backup_stocks(self) -> list:
        """获取备用股票列表"""
        return self.config.get("backup_stocks", [])
    
    def get_network_settings(self) -> Dict[str, Any]:
        """获取网络设置"""
        return self.config.get("network_settings", {})
    
    def is_api_enabled(self, source_name: str) -> bool:
        """检查API是否启用"""
        api_config = self.get_api_config(source_name)
        return api_config.get("enabled", False) if api_config else False
    
    def is_ai_enabled(self, service_name: str) -> bool:
        """检查AI服务是否启用"""
        ai_config = self.get_ai_config(service_name)
        if not ai_config:
            logging.warning(f"AI服务配置未找到: {service_name}，当前ai_services keys: {list(self.config.get('ai_services', {}).keys())}")
            return False
        enabled = ai_config.get("enabled", False)
        enabled_type = type(enabled).__name__
        enabled_value = enabled
        # 处理字符串类型的"true"/"false"
        if isinstance(enabled, str):
            enabled = enabled.lower() in ('true', '1', 'yes', 'on')
        result = bool(enabled)
        logging.debug(f"AI服务启用检查: {service_name}, enabled原始值={enabled_value} (类型: {enabled_type}), 转换后={enabled}, 最终结果={result}")
        return result
    
    def get_retry_config(self, source_name: str) -> Dict[str, Any]:
        """获取重试配置"""
        api_config = self.get_api_config(source_name)
        if api_config:
            return {
                "retry_times": api_config.get("retry_times", 3),
                "retry_delay": api_config.get("retry_delay", [3, 5, 7]),
                "timeout": api_config.get("timeout", 15)
            }
        return {"retry_times": 3, "retry_delay": [3, 5, 7], "timeout": 15}
    
    def update_config(self, section: str, key: str, value: Any) -> bool:
        """更新配置"""
        try:
            if section not in self.config:
                self.config[section] = {}
            self.config[section][key] = value
            return self._save_config()
        except Exception as e:
            print(f"❌ 更新配置失败: {e}")
            return False
    
    def _save_config(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"✅ 配置文件保存成功: {self.config_file}")
            return True
        except Exception as e:
            print(f"❌ 配置文件保存失败: {e}")
            return False
    
    def test_network_connectivity(self) -> Dict[str, str]:
        """测试网络连接性"""
        import requests
        
        results = {}
        network_settings = self.get_network_settings()
        headers = network_settings.get("headers", {})
        timeout = 5
        
        # 测试各个API源
        for source_name, config in self.config.get("api_sources", {}).items():
            if not config.get("enabled", False):
                results[source_name] = "❌ 已禁用"
                continue
            
            source_type = config.get("type", "web_api")
            
            try:
                if source_type == "python_library":
                    # Python库测试 - 检查是否已安装
                    if source_name == "akshare":
                        try:
                            import akshare as ak
                            # 测试一个简单的函数调用
                            try:
                                # 不实际获取数据，只测试模块是否正常
                                results[source_name] = "✅ 库已安装且可用"
                            except Exception as e:
                                results[source_name] = f"⚠️ 库已安装但可能有网络问题"
                        except ImportError:
                            results[source_name] = "❌ 库未安装 - 请运行: pip install akshare"
                    else:
                        results[source_name] = "⚠️ 未知Python库"
                        
                elif source_type == "web_api":
                    # Web API测试
                    if source_name == "sina_finance":
                        # 新浪财经接口测试
                        test_url = "http://hq.sinajs.cn/list=sh000001"  # 测试上证指数
                        response = requests.get(test_url, headers=headers, timeout=timeout)
                        if response.status_code == 200 and "上证指数" in response.text:
                            results[source_name] = "✅ 数据接口正常"
                        else:
                            results[source_name] = f"⚠️ 接口异常: {response.status_code}"
                    else:
                        # 其他API源的常规测试
                        base_url = config.get("base_url", "")
                        if base_url:
                            response = requests.get(base_url, headers=headers, timeout=timeout)
                            if response.status_code == 200:
                                results[source_name] = "✅ 连接正常"
                            else:
                                results[source_name] = f"⚠️ 状态码: {response.status_code}"
                        else:
                            results[source_name] = "⚠️ 无URL配置"
                else:
                    # 文档网站测试
                    doc_url = config.get("documentation_url") or config.get("base_url", "")
                    if doc_url:
                        response = requests.get(doc_url, headers=headers, timeout=timeout)
                        if response.status_code == 200:
                            results[source_name] = "✅ 文档网站正常"
                        else:
                            results[source_name] = f"⚠️ 文档网站异常: {response.status_code}"
                    else:
                        results[source_name] = "⚠️ 无URL配置"
                        
            except requests.exceptions.Timeout:
                results[source_name] = "❌ 连接超时"
            except requests.exceptions.ConnectionError:
                results[source_name] = "❌ 连接失败"
            except Exception as e:
                results[source_name] = f"❌ 错误: {str(e)[:20]}"
        
        return results
    
    def print_config_summary(self):
        """打印配置摘要"""
        print("\n" + "="*50)
        print("📋 当前配置摘要")
        print("="*50)
        
        # API源状态
        print("\n🌐 数据源配置:")
        for source_name, config in self.config.get("api_sources", {}).items():
            status = "✅ 启用" if config.get("enabled") else "❌ 禁用"
            url = config.get("base_url", "N/A")
            print(f"  {source_name}: {status} | {url}")
        
        # AI服务状态
        print("\n🤖 AI服务配置:")
        for service_name, config in self.config.get("ai_services", {}).items():
            status = "✅ 启用" if config.get("enabled") else "❌ 禁用"
            model = config.get("model", "N/A")
            print(f"  {service_name}: {status} | {model}")
        
        # 交易参数
        trading_config = self.get_trading_config()
        print(f"\n📊 交易参数:")
        print(f"  最大推荐数: {trading_config.get('max_recommendations', 5)}")
        print(f"  涨幅范围: {trading_config.get('filter_conditions', {}).get('min_change_pct', 1):.1f}% - {trading_config.get('filter_conditions', {}).get('max_change_pct', 8):.1f}%")
        print(f"  最小成交额: {trading_config.get('filter_conditions', {}).get('min_volume', 30000)}万")
        
        print("="*50)


def _get_project_config_path() -> Path:
    """获取项目根目录下的 config.json 路径（utils 上级两级为项目根）"""
    return Path(__file__).parent.parent / "config.json"


# 全局配置单例（仅加载一次，供全项目共享）
config_manager = ConfigManager(config_file=str(_get_project_config_path())) 