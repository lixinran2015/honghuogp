"""
实时数据源实现（用于补丁推荐结果）
使用新浪/腾讯等实时行情接口
"""
from typing import List, Dict
import logging
import time

from .base import RealtimeDataSource

logger = logging.getLogger(__name__)

# 尝试导入 easyquotation
try:
    import easyquotation
    HAS_EASY = True
except ImportError:
    HAS_EASY = False
    logger.warning("⚠️ easyquotation 未安装，实时数据源将不可用")


class SinaRealtimeSource(RealtimeDataSource):
    """新浪实时数据源（主）+ 腾讯（兜底）"""
    
    def __init__(self):
        """初始化实时数据源"""
        if not HAS_EASY:
            raise RuntimeError("需要安装 easyquotation: pip install easyquotation")
        
        try:
            self._q_sina = easyquotation.use("sina")
            self._q_tencent = easyquotation.use("tencent")
            self.available = True
            logger.debug("✅ SinaRealtimeSource 初始化成功")
        except Exception as e:
            logger.error(f"❌ SinaRealtimeSource 初始化失败: {e}")
            self.available = False
            self._q_sina = None
            self._q_tencent = None

    def _fallback_from_warehouse(self, codes: List[str]) -> Dict[str, Dict]:
        """新浪/腾讯均失败时，从数据仓库取最近收盘价作为降级"""
        result: Dict[str, Dict] = {}
        try:
            from data_warehouse.service.warehouse_service import WarehouseService
            from data_warehouse.models.generated_models import FactDailyPriceQfq
            ws = WarehouseService()
            session = ws.get_session()
            try:
                for code in codes:
                    c = str(code)
                    if c.startswith(('4', '8')):
                        ts_code = f"{c}.BJ"
                    elif c.startswith(('0', '3')):
                        ts_code = f"{c}.SZ"
                    else:
                        ts_code = f"{c}.SH"  # 6xxx, 688xxx
                    row = (
                        session.query(FactDailyPriceQfq.trade_date, FactDailyPriceQfq.close)
                        .filter(FactDailyPriceQfq.ts_code == ts_code)
                        .order_by(FactDailyPriceQfq.trade_date.desc())
                        .first()
                    )
                    if row and row[1] is not None:
                        result[code] = {
                            'price': float(row[1]),
                            'pct_chg': 0.0,
                            'turnover_rate': 0.0,
                            'amount': 0.0,
                            'volume': 0.0,
                        }
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"数据仓库降级失败: {e}")
        return result

    def get_realtime_quotes(self, codes: List[str]) -> Dict[str, Dict]:
        """
        获取实时行情数据（仅用于补丁）
        
        Args:
            codes: 股票代码列表（6位数字格式，如 ['000001', '600519']）
            
        Returns:
            dict: {code: {'price': float, 'pct_chg': float, 'turnover_rate': float, 
                         'amount': float, 'volume': float}, ...}
        """
        if not self.available:
            logger.error("❌ SinaRealtimeSource 不可用")
            return {}
        
        if not codes:
            return {}
        
        # easyquotation 需要6位数字格式，确保格式正确
        normalized_codes = []
        for code in codes:
            code_str = str(code).strip()
            # 去掉.SH/.SZ后缀
            code_str = code_str.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            if len(code_str) == 6:
                normalized_codes.append(code_str)
        
        if not normalized_codes:
            logger.warning("⚠️ 没有有效的股票代码")
            return {}
        
        result: Dict[str, Dict] = {}
        
        try:
            # 优先使用新浪
            logger.debug(f"📡 从新浪获取实时行情: {len(normalized_codes)} 只股票")
            data = self._q_sina.stocks(normalized_codes)
            
            if not data:
                raise Exception("新浪返回数据为空")
            
        except Exception as e:
            logger.warning(f"⚠️ 新浪实时数据失败，尝试腾讯: {e}")
            time.sleep(0.2)
            
            try:
                # 降级到腾讯
                logger.debug(f"📡 从腾讯获取实时行情: {len(normalized_codes)} 只股票")
                data = self._q_tencent.stocks(normalized_codes)
                
                if not data:
                    raise Exception("腾讯返回数据为空")
                    
            except Exception as e2:
                logger.error(f"❌ 腾讯实时数据也失败: {e2}")
                # 降级：从数据仓库获取最近收盘价（非实时，但可用）
                result = self._fallback_from_warehouse(normalized_codes)
                if result:
                    logger.info(f"📦 使用数据仓库最近收盘价作为降级，获取到 {len(result)} 只")
                return result

        # 解析数据；easyquotation 返回的 key 为 sz002487 / sh600519，统一为 6 位便于持仓等用 code_6 查找
        def _norm_key(c: str) -> str:
            c = str(c).strip().lower()
            if c.startswith(('sh', 'sz', 'bj')) and len(c) >= 8 and c[2:8].isdigit():
                return c[2:8]  # 取 6 位代码
            c = c.replace('.sh', '').replace('.sz', '').replace('.bj', '')
            return c if len(c) == 6 and c.isdigit() else (c[2:8] if len(c) >= 8 and c[2:8].isdigit() else c)
        first_logged = False
        for code, info in data.items():
            try:
                # 调试：打印第一个股票的所有字段（仅在DEBUG级别）
                if not first_logged:
                    logger.debug(f"🔍 调试easyquotation字段: {list(info.keys())[:20]}")
                    # 输出成交额相关字段的值
                    amount_related = {k: v for k, v in info.items() if '成交' in k or 'amount' in k.lower() or 'turnover' in k.lower() or 'vol' in k.lower()}
                    logger.debug(f"🔍 成交相关字段值: {amount_related}")
                    first_logged = True
                
                # easyquotation 返回的字段名可能不同，需要适配
                # 常见字段：'now'（当前价）、'close'（昨收）、'换手'、'成交额'、'成交量'
                price = float(info.get('now') or info.get('当前价') or 0)
                yesterday_close = float(info.get('close') or info.get('昨收') or info.get('昨日收盘') or 0)
                
                # 计算涨跌幅：(当前价 - 昨收) / 昨收 * 100
                if yesterday_close > 0 and price > 0:
                    pct_chg = (price - yesterday_close) / yesterday_close * 100
                else:
                    # 备用：尝试从返回字段获取
                    pct_chg = float(info.get('涨跌幅') or info.get('涨跌幅(%)') or info.get('changepercent') or 0)
                # 换手率：easyquotation可能返回'turnover'但实际是成交量，需要检查值是否合理
                raw_turnover = info.get('换手') or info.get('换手率') or info.get('turnover_rate') or 0
                turnover_rate = float(raw_turnover) if raw_turnover else 0
                # 如果换手率超过100%，说明取错了字段，设为0
                if turnover_rate > 100:
                    turnover_rate = 0
                
                # easyquotation 字段混乱问题：
                # - 'turnover': 实际是成交量（手）
                # - 'volume': 实际是成交额（元）
                
                # 成交量（单位：手，1手=100股）
                volume_hands = float(
                    info.get('成交量') or 
                    info.get('turnover') or  # easyquotation的'turnover'是成交量（手）
                    0
                )
                
                # 成交额（单位：元）
                amount = float(
                    info.get('成交额') or 
                    info.get('volume') or  # easyquotation的'volume'实际是成交额（元）
                    info.get('amount') or 
                    0
                )
                
                key6 = _norm_key(code)
                result[key6] = {
                    'price': price,
                    'pct_chg': pct_chg,
                    'turnover_rate': turnover_rate,
                    'amount': amount,
                    'volume': volume_hands,  # 成交量（手）
                }
                
            except Exception as parse_err:
                logger.warning(f"⚠️ 解析实时行情失败 code={code}, data={info}, err={parse_err}")
                continue
        
        # 对「未返回」或「现价为 0」的代码用数据仓库最近收盘价补全（避免自选/持仓显示 -100%）
        missing_or_zero = [c for c in normalized_codes if c not in result or (result[c].get('price') or 0) <= 0]
        if missing_or_zero:
            fallback = self._fallback_from_warehouse(missing_or_zero)
            for code, info in fallback.items():
                if info.get('price') and float(info['price']) > 0:
                    result[code] = info
                    logger.debug(f"📦 代码 {code} 现价缺失/为0，已用数据仓库最近收盘价补全: {info['price']}")
        
        logger.debug(f"✅ 获取到 {len(result)} 只股票的实时行情")
        return result

