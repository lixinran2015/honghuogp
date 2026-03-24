"""
行业板块服务
从 AkShare 初始化行业板块数据，并更新板块日线
"""

import sys
import time
from pathlib import Path
import datetime
import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import Date, Integer, Numeric, String

# 项目根目录：backend/services/sector/sector_service.py -> 4 层 parent = 仓库根（与 data/eastmoney_industry_list.json 同层）
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import akshare as ak
except ImportError:
    ak = None
    logging.warning("akshare 未安装，sector_service 功能将不可用")

from data_warehouse.config import DATABASE_URL
from data_warehouse.db import get_shared_engine
from data_warehouse.models import DimSector
from data_warehouse.models import FactStockSector
from data_warehouse.models import FactSectorDaily

logger = logging.getLogger(__name__)

# 东财行业列表接口（与 AkShare 一致），浏览器可打开时用带浏览器头的请求避免断连
EASTMONEY_INDUSTRY_LIST_URL = "https://17.push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_INDUSTRY_PARAMS = {
    "pn": "1",
    "pz": "100",
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f3",
    "fs": "m:90 t:2 f:!50",
    "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,"
    "f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,"
    "f140,f141,f207,f208,f209,f222",
}
EASTMONEY_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json",
}


def _fetch_industry_list_with_browser_headers():
    """
    用浏览器请求头直接请求东财行业列表接口，避免被断连。
    返回与 ak.stock_board_industry_name_em() 一致的 DataFrame，至少含 板块代码、板块名称。
    """
    import requests
    r = requests.get(
        EASTMONEY_INDUSTRY_LIST_URL,
        params=EASTMONEY_INDUSTRY_PARAMS,
        headers=EASTMONEY_BROWSER_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("data") or not data["data"].get("diff"):
        raise ValueError("东财返回数据为空")
    diff = data["data"]["diff"]
    # 东财 diff 里 f12=板块代码, f14=板块名称
    rows = [{"板块代码": str(d.get("f12", "")), "板块名称": str(d.get("f14", ""))} for d in diff]
    return pd.DataFrame(rows)


# 本地行业列表 JSON 备用路径（网络全失败时，可从浏览器保存的接口返回放这里）
EASTMONEY_INDUSTRY_LIST_JSON_PATH = project_root / "data" / "eastmoney_industry_list.json"


def _raise_with_file_hint(err):
    """网络/接口全失败时抛出异常并提示用本地 JSON 备用"""
    url = f"{EASTMONEY_INDUSTRY_LIST_URL}?pn=1&pz=100&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90%20t:2%20f:!50&fields=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152,f124,f107,f104,f105,f140,f141,f207,f208,f209,f222"
    raise RuntimeError(
        f"获取行业列表失败: {err}\n\n"
        f"备用方式：在浏览器打开上述接口，复制全部 JSON 保存为\n  {EASTMONEY_INDUSTRY_LIST_JSON_PATH}\n"
        f"再重新运行本脚本即可从本地文件加载。\n接口 URL:\n  {url}"
    ) from err


def _load_industry_list_from_file():
    """
    从本地 JSON 文件加载东财行业列表（与接口返回格式一致）。
    仅保留板块代码以 BK 开头的行业板块（东财行业板块格式）；债券/期权等非 BK 代码会被过滤。
    用于网络直连/AkShare 均失败时：在浏览器打开「行业板块」接口 URL，复制全部 JSON 保存为
    data/eastmoney_industry_list.json，再运行初始化脚本即可。
    返回 DataFrame 含列 板块代码、板块名称。
    """
    if not EASTMONEY_INDUSTRY_LIST_JSON_PATH.exists():
        raise FileNotFoundError(f"本地文件不存在: {EASTMONEY_INDUSTRY_LIST_JSON_PATH}")
    import json
    with open(EASTMONEY_INDUSTRY_LIST_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("data") or not data["data"].get("diff"):
        raise ValueError("JSON 格式不符，需包含 data.diff 数组")
    diff = data["data"]["diff"]
    rows = [{"板块代码": str(d.get("f12", "")), "板块名称": str(d.get("f14", ""))} for d in diff]
    df = pd.DataFrame(rows)
    # 东财行业板块代码以 BK 开头，过滤掉债券/期权等（如 137364、H20阳优、HO2602-C-3450）
    df = df[df["板块代码"].str.upper().str.startswith("BK", na=False)]
    if df.empty:
        raise ValueError(
            "JSON 中无行业板块数据（板块代码应以 BK 开头，如 BK0475）。"
            "请用「行业板块」接口 URL 在浏览器打开，复制全部 JSON 覆盖保存到 data/eastmoney_industry_list.json。"
            "接口 URL 见脚本日志或 _raise_with_file_hint 中的链接（含 fs=m:90 t:2 f:!50 的为行业板块）。"
        )
    return df


def init_industry_from_akshare():
    """
    一次性初始化行业板块及成分股（以东财行业为例）
    使用 SQLAlchemy 批量插入优化
    """
    if ak is None:
        logger.error("❌ akshare 未安装，无法初始化行业板块数据")
        return
    
    engine = get_shared_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        logger.info("📥 开始获取行业板块数据...")
        
        # 1) 拉行业列表（直连 -> 本地文件 -> AkShare；网络全失败时可用本地 JSON 备用）
        industry_df = None
        try:
            logger.info("📥 使用浏览器请求头直连东财接口...")
            industry_df = _fetch_industry_list_with_browser_headers()
        except Exception as e:
            logger.warning(f"⚠️ 直连东财失败: {e}")
            try:
                logger.info("📥 尝试从本地文件加载: data/eastmoney_industry_list.json")
                industry_df = _load_industry_list_from_file()
            except (FileNotFoundError, ValueError, KeyError, TypeError) as e_file:
                logger.warning(f"⚠️ 本地文件不可用: {e_file}，改用 AkShare...")
                industry_df = None
        if industry_df is None or industry_df.empty:
            for attempt in range(3):
                try:
                    industry_df = ak.stock_board_industry_name_em()
                    if industry_df is not None and not industry_df.empty:
                        break
                except Exception as e2:
                    if attempt < 2:
                        wait = 5 * (attempt + 1)
                        logger.warning(f"⚠️ AkShare 失败，{wait}s 后重试 ({attempt + 1}/2): {e2}")
                        time.sleep(wait)
                    else:
                        _raise_with_file_hint(e2)
        if industry_df is None or industry_df.empty:
            _raise_with_file_hint(RuntimeError("获取行业列表为空或失败"))
        logger.info(f"✅ 获取到 {len(industry_df)} 个行业板块")
        
        # 准备行业板块数据
        sector_rows = []
        for _, row in industry_df.iterrows():
            sector_id = row["板块代码"]       # 如 'BK0471'
            name = row["板块名称"]
            sector_rows.append({
                "sector_id": sector_id,
                "sector_type": "industry",
                "name": name,
                "level": 1,  # 默认一级行业
                "provider": "eastmoney",
            })
        
        # 批量插入行业板块维表
        if sector_rows:
            df_sectors = pd.DataFrame(sector_rows)
            
            with engine.connect() as conn:
                temp_table_name = 'temp_sector_import'
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 创建临时表
                df_sectors.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000
                )
                conn.commit()
                
                # 批量upsert
                update_set = """
                    sector_type = EXCLUDED.sector_type,
                    name = EXCLUDED.name,
                    level = EXCLUDED.level,
                    provider = EXCLUDED.provider,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                insert_cols = ', '.join(df_sectors.columns)
                select_cols = ', '.join(df_sectors.columns)
                
                sql = f"""
                INSERT INTO dim_sector 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (sector_id) 
                DO UPDATE SET {update_set}
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
        
        logger.info(f"✅ 成功导入 {len(sector_rows)} 个行业板块到 dim_sector")
        
        # 2) 拉每个行业的成分股
        today = datetime.date.today()
        stock_sector_rows = []
        
        logger.info("📥 开始获取各行业成分股...")
        from backend.services.akshare_service import get_akshare_service
        service = get_akshare_service()
        delay_between_sectors = 5.0   # 每个行业请求后间隔（秒），避免东财断开连接/限流
        max_retries = 2               # 失败后重试次数

        for idx, row in enumerate(industry_df.iterrows(), 1):
            _, row_data = row
            sector_id = row_data["板块代码"]
            sector_name = row_data["板块名称"]
            
            logger.info(f"[{idx}/{len(industry_df)}] 获取 {sector_name} ({sector_id}) 的成分股...")
            
            cons_df = None
            for attempt in range(max_retries + 1):
                try:
                    cons_df = service.get_industry_stocks(sector_name)
                    break
                except Exception as e:
                    if attempt < max_retries:
                        wait = 5 * (attempt + 1)
                        logger.warning(f"⚠️ 获取 {sector_name} 成分股失败，{wait}s 后重试 ({attempt + 1}/{max_retries}): {e}")
                        time.sleep(wait)
                    else:
                        logger.warning(f"⚠️ 获取 {sector_name} 成分股失败（已重试 {max_retries} 次）: {e}")
                        break

            if cons_df is None or cons_df.empty:
                if cons_df is not None:
                    logger.debug(f"  {sector_name} 无成分股数据")
                time.sleep(delay_between_sectors)
                continue

            try:
                for _, c in cons_df.iterrows():
                    # 尝试多个可能的列名
                    code = None
                    for col_name in ["代码", "股票代码", "code"]:
                        if col_name in c and pd.notna(c[col_name]):
                            code = str(c[col_name]).strip()
                            break
                    
                    if not code:
                        continue
                    
                    # 简单按前缀判断交易所
                    if code.startswith("6"):
                        ts_code = f"{code}.SH"
                    elif code.startswith("0") or code.startswith("3"):
                        ts_code = f"{code}.SZ"
                    else:
                        continue  # 跳过不认识的代码
                    
                    stock_sector_rows.append({
                        "ts_code": ts_code,
                        "sector_id": sector_id,
                        "start_date": today,
                        "end_date": None,
                        "is_primary": True,
                    })
            except Exception as e:
                logger.warning(f"⚠️ 解析 {sector_name} 成分股失败: {e}")
            
            # 每个行业请求后间隔，避免 Connection aborted / Remote end closed
            time.sleep(delay_between_sectors)
        
        # 批量插入股票-板块关联表
        if stock_sector_rows:
            df_stock_sector = pd.DataFrame(stock_sector_rows)
            
            with engine.connect() as conn:
                temp_table_name = 'temp_stock_sector_import'
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 创建临时表
                df_stock_sector.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=5000
                )
                conn.commit()
                
                # 批量插入（使用 DO NOTHING 避免重复）
                # 需要处理 end_date 的类型转换（临时表可能是text，需要转换为date）
                insert_cols = ', '.join(df_stock_sector.columns)
                select_cols_list = []
                for col in df_stock_sector.columns:
                    if col == 'end_date':
                        # end_date 可能是 NULL，需要特殊处理
                        select_cols_list.append(f"NULLIF({col}, '')::DATE")
                    else:
                        select_cols_list.append(col)
                select_cols = ', '.join(select_cols_list)
                
                sql = f"""
                INSERT INTO fact_stock_sector 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (ts_code, sector_id, start_date) 
                DO NOTHING
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
            
            logger.info(f"✅ 成功导入 {len(stock_sector_rows)} 条股票-板块关联数据")
        
        logger.info("✅ 行业板块数据初始化完成！")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 初始化行业板块数据失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


def update_sector_daily(trade_date: datetime.date):
    """
    每日更新板块指数日线（用于板块热度）
    使用 SQLAlchemy
    """
    if ak is None:
        logger.error("❌ akshare 未安装，无法更新板块日线数据")
        return
    
    engine = get_shared_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 获取东财行业板块（仅 BK 开头，AkShare 行业指数日K 只支持东财行业；跳过 83xxxx/90xxxx/期权等误入数据）
        sectors = session.query(DimSector.sector_id, DimSector.name).filter(
            DimSector.sector_type == 'industry',
            DimSector.sector_id.like('BK%')
        ).all()
        
        if not sectors:
            # 辅助诊断：看 dim_sector 里是否有其他类型
            from sqlalchemy import func
            type_counts = session.query(DimSector.sector_type, func.count(DimSector.sector_id)).group_by(DimSector.sector_type).all()
            type_hint = f"（dim_sector 当前: {dict(type_counts)}）" if type_counts else "（dim_sector 表为空或未初始化行业板块）"
            logger.warning(
                "📥 开始更新 0 个板块的日线数据；fact_sector_daily 将无新数据。"
                " 请先执行「行业板块初始化」以写入 sector_type='industry' 的板块，或检查 dim_sector 数据。%s",
                type_hint
            )
        else:
            logger.info(f"📥 开始更新 {len(sectors)} 个板块的日线数据...")
        
        sector_daily_rows = []
        # start/end 格式 YYYYMMDD，覆盖 trade_date 前后若干日
        start_str = (trade_date - datetime.timedelta(days=30)).strftime("%Y%m%d")
        end_str = (trade_date + datetime.timedelta(days=1)).strftime("%Y%m%d")
        for i, (sector_id, name) in enumerate(sectors):
            if i > 0:
                time.sleep(0.4)  # 避免东方财富接口限流/RemoteDisconnected
            k_df = None
            for attempt in range(4):
                try:
                    k_df = ak.stock_board_industry_hist_em(
                        symbol=name,
                        start_date=start_str,
                        end_date=end_str,
                        period="日k",
                        adjust="",
                    )
                    break
                except (ConnectionError, OSError) as e:
                    err_str = str(e).lower()
                    if attempt < 3 and ("connection" in err_str or "remote" in err_str or "reset" in err_str):
                        time.sleep(1.0 * (attempt + 1))  # 1s, 2s, 3s 退避
                        continue
                    logger.warning(f"[sector_daily] fetch failed for {sector_id} {name}: {e}")
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if attempt < 3 and ("connection" in err_str or "remote" in err_str or "reset" in err_str):
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    logger.warning(f"[sector_daily] fetch failed for {sector_id} {name}: {e}")
                    break
            if k_df is None or k_df.empty or "日期" not in k_df.columns:
                continue
            # k_df columns 示例: ['日期', '收盘', '涨跌幅', '成交量', '成交额', ...]
            row = k_df[k_df["日期"] == trade_date.strftime("%Y-%m-%d")]
            if row.empty:
                continue
            row = row.iloc[0]

            sector_daily_rows.append({
                "sector_id": sector_id,
                "trade_date": trade_date,
                "close": float(row["收盘"]) if pd.notna(row["收盘"]) else None,
                "pre_close": None,  # 可用前一日值填
                "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else None,
                "volume": float(row["成交量"]) if pd.notna(row["成交量"]) else None,
                "amount": float(row["成交额"]) if pd.notna(row["成交额"]) else None,
                "num_stocks": None,  # 成分股数量可通过 fact_stock_sector 统计
                "num_up": None,      # 上涨家数后续由策略写回
                "num_limit_up": None,  # 涨停家数可由 fact_limit_up_daily 统计
                "heat_score": None,   # 板块热度评分（策略层回写）
            })
        
        # 批量插入板块日线
        if sector_daily_rows:
            df_sector_daily = pd.DataFrame(sector_daily_rows)
            # 明确 dtype，避免 pandas 推断为 object 导致 PostgreSQL numeric 类型不匹配
            dtype_map = {
                "sector_id": String(50),
                "trade_date": Date,
                "close": Numeric(12, 4),
                "pre_close": Numeric(12, 4),
                "change_pct": Numeric(8, 4),
                "volume": Numeric(20, 4),
                "amount": Numeric(20, 4),
                "num_stocks": Integer,
                "num_up": Integer,
                "num_limit_up": Integer,
                "heat_score": Numeric(8, 4),
            }
            with engine.connect() as conn:
                temp_table_name = 'temp_sector_daily_import'
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 创建临时表（指定 dtype 避免 text→numeric 类型不匹配）
                df_sector_daily.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000,
                    dtype={c: dtype_map[c] for c in df_sector_daily.columns if c in dtype_map},
                )
                conn.commit()
                
                # 批量upsert
                update_set = """
                    close = EXCLUDED.close,
                    pre_close = EXCLUDED.pre_close,
                    change_pct = EXCLUDED.change_pct,
                    volume = EXCLUDED.volume,
                    amount = EXCLUDED.amount,
                    num_stocks = EXCLUDED.num_stocks,
                    num_up = EXCLUDED.num_up,
                    num_limit_up = EXCLUDED.num_limit_up,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                insert_cols = ', '.join(df_sector_daily.columns)
                select_cols = ', '.join(df_sector_daily.columns)
                
                sql = f"""
                INSERT INTO fact_sector_daily 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (sector_id, trade_date) 
                DO UPDATE SET {update_set}
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
            
            logger.info(f"✅ 成功更新 {len(sector_daily_rows)} 个板块的日线数据")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 更新板块日线数据失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


# 申万一级行业 -> 主题（6 个代表性行业，用于主题轮动/板块轮动）
SW_THEME_MAP = [
    ("801150.SI", "医药生物", "aging_health"),
    ("801730.SI", "电力设备", "new_energy"),
    ("801080.SI", "电子", "semiconductor"),
    ("801750.SI", "计算机", "ai_digital"),
    ("801120.SI", "食品饮料", "consumption"),
    ("801010.SI", "农林牧渔", "agriculture"),
]


def update_sector_daily_tushare(trade_date: datetime.date):
    """
    使用 Tushare 申万行业指数更新板块日线（用于板块轮动/主题轮动）。
    仅更新 6 个长期主题对应的申万行业，需 config 中 tushare token 且积分≥120。
    """
    try:
        from backend.services.tushare_service import TushareService
    except ImportError:
        logger.error("❌ 无法导入 TushareService，update_sector_daily_tushare 不可用")
        return

    svc = TushareService()
    if not svc.available:
        logger.warning("⚠️ Tushare 未配置或不可用，跳过板块日线更新")
        return

    date_str = trade_date.strftime("%Y%m%d")
    engine = get_shared_engine()

    # 确保 dim_sector 有申万板块
    with engine.connect() as conn:
        for ts_code, name, _ in SW_THEME_MAP:
            sector_id = f"SW{ts_code.replace('.SI', '')}"
            conn.execute(
                text("""
                INSERT INTO dim_sector (sector_id, sector_type, name) VALUES (:sid, 'industry', :name)
                ON CONFLICT (sector_id) DO UPDATE SET name = EXCLUDED.name
                """),
                {"sid": sector_id, "name": name},
            )
        conn.commit()

    sector_daily_rows = []
    dtype_map = {
        "sector_id": String(50),
        "trade_date": Date,
        "close": Numeric(12, 4),
        "pre_close": Numeric(12, 4),
        "change_pct": Numeric(8, 4),
        "volume": Numeric(20, 4),
        "amount": Numeric(20, 4),
    }

    for ts_code, name, _ in SW_THEME_MAP:
        try:
            df = svc.pro.sw_daily(ts_code=ts_code, start_date=date_str, end_date=date_str)
            if df is None or df.empty:
                continue
            sector_id = f"SW{ts_code.replace('.SI', '')}"
            r = df.iloc[0]
            close = float(r["close"]) if pd.notna(r.get("close")) else None
            change_pct = float(r["pct_change"]) if "pct_change" in r and pd.notna(r["pct_change"]) else None
            vol = float(r["vol"]) if "vol" in r and pd.notna(r.get("vol")) else None
            amount_val = float(r["amount"]) if "amount" in r and pd.notna(r.get("amount")) else None
            sector_daily_rows.append({
                "sector_id": sector_id,
                "trade_date": trade_date,
                "close": close,
                "pre_close": None,
                "change_pct": change_pct,
                "volume": vol,
                "amount": amount_val,
            })
            time.sleep(0.35)
        except Exception as e:
            logger.warning(f"[sector_daily_tushare] {name} 获取失败: {e}")

    if not sector_daily_rows:
        logger.info("📊 Tushare 申万行业当日无新数据")
        return

    df_in = pd.DataFrame(sector_daily_rows)
    temp_name = "temp_sector_daily_tushare"
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()
        df_in.to_sql(
            temp_name,
            conn,
            if_exists="append",
            index=False,
            dtype={c: dtype_map[c] for c in df_in.columns if c in dtype_map},
        )
        conn.commit()
        conn.execute(
            text(f"""
            INSERT INTO fact_sector_daily (sector_id, trade_date, close, pre_close, change_pct, volume, amount)
            SELECT sector_id, trade_date, close, pre_close, change_pct, volume, amount FROM {temp_name}
            ON CONFLICT (sector_id, trade_date) DO UPDATE SET
            close = EXCLUDED.close, pre_close = EXCLUDED.pre_close, change_pct = EXCLUDED.change_pct,
            volume = EXCLUDED.volume, amount = EXCLUDED.amount, updated_at = CURRENT_TIMESTAMP
            """)
        )
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_name}"))
        conn.commit()

    logger.info(f"✅ Tushare 申万行业日线已更新 {len(sector_daily_rows)} 条，日期={trade_date}")

