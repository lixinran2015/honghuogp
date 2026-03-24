"""
同步 dim_stock.industry 为申万一级行业
- 阶段一：按申万一级指数拉取成分股（index_member_all(l1_code=...)），批量覆盖。
- 阶段二：对有财务数据但 industry 仍为空的股票，按 ts_code 逐只查询（index_member_all(ts_code=...)）补漏，
  避免「有财务数据的股票不在指数成分里」导致选股+行业周期 0 条。单次补漏有上限，避免限频与超时。
供行业周期等模块使用，避免多套行业体系混用。
"""
import sys
import io
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import logging
from datetime import datetime
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import get_tushare_token

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 阶段二单次补漏上限（按 ts_code 逐只查询，避免限频与超时）
SW_FILL_MISSING_MAX = 800

# 申万2021一级行业指数代码（index_classify 不可用时使用，与 Tushare index_classify 一致）
SW_L1_FALLBACK = [
    ("801010.SI", "农林牧渔"),
    ("801030.SI", "基础化工"),
    ("801040.SI", "钢铁"),
    ("801050.SI", "有色金属"),
    ("801080.SI", "电子"),
    ("801110.SI", "家用电器"),
    ("801120.SI", "食品饮料"),
    ("801130.SI", "纺织服饰"),
    ("801140.SI", "轻工制造"),
    ("801150.SI", "医药生物"),
    ("801160.SI", "公用事业"),
    ("801170.SI", "交通运输"),
    ("801180.SI", "房地产"),
    ("801200.SI", "商贸零售"),
    ("801210.SI", "社会服务"),
    ("801230.SI", "综合"),
    ("801710.SI", "建筑材料"),
    ("801720.SI", "建筑装饰"),
    ("801730.SI", "电力设备"),
    ("801740.SI", "国防军工"),
    ("801750.SI", "计算机"),
    ("801760.SI", "传媒"),
    ("801770.SI", "通信"),
    ("801780.SI", "银行"),
    ("801790.SI", "非银金融"),
    ("801880.SI", "汽车"),
    ("801890.SI", "机械设备"),
]


class RateLimiter:
    """Tushare 限频：200次/分钟"""
    def __init__(self, max_calls: int = 180, period: float = 60.0):
        import threading
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait_if_needed(self):
        import time
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                wait_time = self.period - (now - min(self.calls)) + 0.2
                if wait_time > 0:
                    logger.debug(f"限频等待 {wait_time:.1f}s")
                    time.sleep(wait_time)
                    now = time.time()
                    self.calls = [t for t in self.calls if now - t < self.period]
            self.calls.append(now)


def fetch_sw_l1_list(pro) -> list:
    """获取申万一级行业列表 (l1_code, l1_name)"""
    try:
        df = pro.index_classify(level='L1', src='SW')
        if df is not None and not df.empty:
            # 列名可能是 index_code/l1_code, name/l1_name
            code_col = 'index_code' if 'index_code' in df.columns else 'l1_code'
            name_col = 'name' if 'name' in df.columns else 'l1_name'
            if code_col not in df.columns:
                code_col = df.columns[0]
            if name_col not in df.columns:
                name_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            result = []
            for _, row in df.iterrows():
                code = str(row.get(code_col, '')).strip()
                name = str(row.get(name_col, '')).strip()
                if not code or not name:
                    continue
                if not code.endswith('.SI'):
                    code = code + '.SI'
                result.append((code, name))
            if result:
                logger.info(f"index_classify 获取到 {len(result)} 个申万一级行业")
                return result
    except Exception as e:
        logger.warning(f"index_classify 失败，使用内置列表: {e}")
    return SW_L1_FALLBACK


def sync_industry_from_sw(task_type: str = 'manual', task_id: str = None) -> int:
    """
    从 Tushare 申万行业成分同步 dim_stock.industry
    返回更新的股票数量
    """
    token = get_tushare_token()
    if not token:
        logger.error("❌ 未配置 Tushare token，无法同步申万行业")
        return -1

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    ws = WarehouseService()
    session = ws.get_session()
    rate_limiter = RateLimiter(max_calls=180, period=60.0)

    try:
        # 1. 获取申万一级行业列表
        l1_list = fetch_sw_l1_list(pro)
        if not l1_list:
            logger.error("❌ 无法获取申万一级行业列表")
            return -1

        # 2. 按行业拉取成分股，构建 ts_code -> l1_name
        ts_to_industry = {}
        for l1_code, l1_name in l1_list:
            try:
                rate_limiter.wait_if_needed()
                df = pro.index_member_all(l1_code=l1_code, is_new='Y')
                time.sleep(0.15)
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        tc = row.get('ts_code')
                        if tc and pd.notna(tc):
                            ts_to_industry[str(tc).strip()] = l1_name
            except Exception as e:
                logger.debug(f"index_member_all {l1_code} 失败: {e}")
                continue

        logger.info(f"申万成分股共 {len(ts_to_industry)} 只")

        # 3. 阶段一：分批更新 dim_stock.industry（每批 500 条）
        now = datetime.now()
        items = list(ts_to_industry.items())
        batch_size = 500
        updated = 0
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            for ts_code, industry in batch:
                r = session.execute(
                    text("UPDATE dim_stock SET industry = :industry, updated_at = :now WHERE ts_code = :ts_code"),
                    {'industry': industry, 'ts_code': ts_code, 'now': now}
                )
                if r.rowcount:
                    updated += 1
            session.commit()

        # 4. 阶段二：对有财务数据但 industry 仍为空的股票，按 ts_code 逐只查申万接口补漏
        fill_sql = text("""
            SELECT DISTINCT d.ts_code
            FROM dim_stock d
            INNER JOIN fact_fundamental f ON f.ts_code = d.ts_code
            WHERE (d.industry IS NULL OR TRIM(d.industry) = '')
            LIMIT :limit
        """)
        missing_rows = session.execute(fill_sql, {"limit": SW_FILL_MISSING_MAX}).fetchall()
        missing_codes = [r[0] for r in missing_rows if r[0]]
        fill_ts_to_industry = {}
        if missing_codes:
            logger.info(f"阶段二：共 {len(missing_codes)} 只有财务数据但无行业，按 ts_code 补漏（本次最多 {SW_FILL_MISSING_MAX} 只）")
            for ts_code in missing_codes:
                try:
                    rate_limiter.wait_if_needed()
                    df = pro.index_member_all(ts_code=ts_code, is_new='Y')
                    time.sleep(0.12)
                    if df is not None and not df.empty:
                        row = df.iloc[0]
                        l1_name = row.get('l1_name')
                        if l1_name and pd.notna(l1_name):
                            fill_ts_to_industry[str(ts_code).strip()] = str(l1_name).strip()
                except Exception as e:
                    logger.debug(f"index_member_all(ts_code={ts_code}) 失败: {e}")
                    continue
            if fill_ts_to_industry:
                for ts_code, industry in fill_ts_to_industry.items():
                    r = session.execute(
                        text("UPDATE dim_stock SET industry = :industry, updated_at = :now WHERE ts_code = :ts_code"),
                        {'industry': industry, 'ts_code': ts_code, 'now': now}
                    )
                    if r.rowcount:
                        updated += 1
                session.commit()
                logger.info(f"阶段二补漏完成，本次更新 {len(fill_ts_to_industry)} 只")

        logger.info(f"✅ 申万行业同步完成，共更新 {updated} 只股票")
        return updated

    except Exception as e:
        logger.error(f"❌ 申万行业同步失败: {e}", exc_info=True)
        session.rollback()
        return -1
    finally:
        session.close()


if __name__ == '__main__':
    sync_industry_from_sw()
