"""
iFinD 登录管理器（全局单例）
避免多个模块重复登录，统一管理登录状态
"""
import logging
import threading

logger = logging.getLogger(__name__)

# 全局登录状态（进程级别，所有模块共享）
_ifind_logged_in = False
_ifind_lock = threading.Lock()
_last_login_error = None

# iFinD账号配置
IFIND_USERNAME = 'shrhqy002'
IFIND_PASSWORD = 'P2kNCM66'

#IFIND_USERNAME = 'gryhjk002'
#IFIND_PASSWORD = '2hyuKY0c'


def ensure_ifind_login(force_relogin: bool = False) -> bool:
    """
    确保 iFinDPy 已登录（全局单例）
    
    Args:
        force_relogin: 是否强制重新登录
    
    Returns:
        bool: 是否登录成功
    """
    global _ifind_logged_in, _last_login_error
    
    with _ifind_lock:
        # 如果已登录且不强制重新登录，直接返回
        if _ifind_logged_in and not force_relogin:
            return True
        
        # 尝试登录
        try:
            from iFinDPy import THS_iFinDLogin
            
            logger.info("🔐 正在登录 iFinDPy...")
            result = THS_iFinDLogin(IFIND_USERNAME, IFIND_PASSWORD)
            
            if result == 0:
                _ifind_logged_in = True
                _last_login_error = None
                logger.info("✅ iFinDPy 登录成功")
                return True
            else:
                _ifind_logged_in = False
                
                # 错误码说明
                error_msg = {
                    -201: "用户名或密码错误，或账号已在其他地方登录",
                    -202: "网络连接失败",
                    -203: "登录超时"
                }.get(result, f"未知错误({result})")
                
                _last_login_error = f"错误码: {result}，原因: {error_msg}"
                logger.warning(f"⚠️ iFinDPy 登录失败，{_last_login_error}")
                logger.info("   将使用其他数据源（腾讯、东财等）")
                return False
                
        except ImportError:
            _ifind_logged_in = False
            _last_login_error = "iFinDPy 模块未安装"
            logger.warning("⚠️ iFinDPy 模块未安装，请安装: pip install iFinDPy")
            return False
        except Exception as e:
            _ifind_logged_in = False
            _last_login_error = str(e)
            logger.warning(f"⚠️ iFinDPy 登录异常: {e}")
            return False


def is_logged_in() -> bool:
    """检查是否已登录"""
    return _ifind_logged_in


def logout():
    """登出 iFinDPy"""
    global _ifind_logged_in
    
    with _ifind_lock:
        if not _ifind_logged_in:
            return
        
        try:
            from iFinDPy import THS_iFinDLogout
            THS_iFinDLogout()
            _ifind_logged_in = False
            logger.info("✅ iFinDPy 登出成功")
        except Exception as e:
            logger.warning(f"⚠️ iFinDPy 登出失败: {e}")


def get_last_error() -> str:
    """获取最后一次登录错误"""
    return _last_login_error

