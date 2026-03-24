"""
Chrome 浏览器驱动工厂

统一管理 ChromeDriver 的创建，按优先级尝试：
1. 本地 drivers/ 或系统 PATH 中的 chromedriver（无网络请求，定时任务首选）
2. webdriver-manager（需联网检查最新版本）
3. Selenium 内置 Selenium Manager（需联网验证）
"""

import logging
import shutil
from pathlib import Path
from typing import Optional, List, Callable, Any

logger = logging.getLogger(__name__)

# 默认 Chrome 启动参数（无头模式，减少资源占用）
DEFAULT_CHROME_ARGS = [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-logging",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-blink-features=AutomationControlled",
    "--log-level=3",
]

# 本地 ChromeDriver 搜索路径（按优先级）
LOCAL_DRIVER_PATHS = [
    "drivers/chromedriver.exe",
    "C:/Program Files/Google/Chrome/Application/chromedriver.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chromedriver.exe",
]


def _get_project_root() -> Path:
    """获取项目根目录 (backend/scripts/crawler -> 3 层 parent)"""
    return Path(__file__).resolve().parents[3]


def _build_chrome_options(user_agent: Optional[str] = None) -> "Options":
    """构建 Chrome Options"""
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for arg in DEFAULT_CHROME_ARGS:
        options.add_argument(arg)
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    if user_agent:
        options.add_argument(f"user-agent={user_agent}")
    return options


def _find_local_chromedriver() -> Optional[str]:
    """查找本地 ChromeDriver 可执行文件路径"""
    root = _get_project_root()
    for rel in LOCAL_DRIVER_PATHS:
        path = root / rel if not Path(rel).is_absolute() else Path(rel)
        if path.exists():
            return str(path)
    return shutil.which("chromedriver.exe") or shutil.which("chromedriver")


def _create_driver_with_path(options: "Options", driver_path: str) -> Optional[Any]:
    """使用指定路径的 ChromeDriver 创建驱动"""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    try:
        service = Service(driver_path)
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.debug(f"ChromeDriver 路径 {driver_path} 启动失败: {e}")
        return None


def _create_driver_default(options: "Options") -> Optional[Any]:
    """使用 Selenium Manager 默认方式创建驱动（无显式路径）"""
    from selenium import webdriver

    try:
        return webdriver.Chrome(options=options)
    except Exception as e:
        logger.debug(f"Selenium 默认驱动失败: {e}")
        return None


def _try_webdriver_manager(options: "Options") -> Optional[Any]:
    """策略1：使用 webdriver-manager 自动下载匹配版本的 ChromeDriver"""
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        import requests

        driver_path = ChromeDriverManager().install()
        driver = _create_driver_with_path(options, driver_path)
        if driver:
            logger.info("Chrome 启动成功（webdriver-manager）")
            return driver
    except ImportError:
        logger.debug("webdriver-manager 未安装，跳过")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        logger.warning("webdriver-manager 下载失败（网络）: %s", e)
    except Exception as e:
        logger.warning("webdriver-manager 启动失败: %s", e)
    return None


def _try_local_chromedriver(options: "Options") -> Optional[Any]:
    """策略2：使用本地 drivers/ 或 PATH 中的 ChromeDriver"""
    local_path = _find_local_chromedriver()
    if not local_path:
        return None

    driver = _create_driver_with_path(options, local_path)
    if driver:
        logger.info("Chrome 启动成功（本地驱动: %s）", local_path)
        return driver
    return None


def _try_selenium_manager(options: "Options") -> Optional[Any]:
    """策略3：使用 Selenium 4.6+ 内置 Selenium Manager（自动管理驱动）"""
    driver = _create_driver_default(options)
    if driver:
        logger.info("Chrome 启动成功（Selenium Manager）")
        return driver
    return None


def create_chrome_driver(user_agent: Optional[str] = None) -> Optional[Any]:
    """
    创建 Chrome WebDriver 实例。

    按优先级尝试多种方式：
    1. webdriver-manager
    2. 本地 ChromeDriver
    3. Selenium Manager（Selenium 4.6+）

    Args:
        user_agent: 可选，自定义 User-Agent 字符串

    Returns:
        webdriver.Chrome 实例，失败返回 None
    """
    try:
        from selenium import webdriver
    except ImportError:
        logger.error("Selenium 未安装，请运行: pip install selenium")
        return None

    options = _build_chrome_options(user_agent)

    strategies: List[Callable[[Any], Optional[Any]]] = [
        _try_local_chromedriver,   # 优先本地：无需联网，适合定时任务
        _try_webdriver_manager,
        _try_selenium_manager,
    ]

    for strategy in strategies:
        driver = strategy(options)
        if driver is not None:
            return driver

    logger.error(
        "Chrome 启动失败。建议：1) 将 chromedriver.exe 放入项目根目录 drivers/ 下 2) 确保 Chrome 与 ChromeDriver 版本匹配（Chrome 菜单-帮助-关于可查看版本）"
    )
    return None
