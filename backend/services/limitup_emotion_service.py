"""
涨停板和情绪服务
从东方财富获取涨停板数据并计算市场情绪
"""

import sys
from pathlib import Path
import datetime
from typing import List, Dict
import requests
import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.db import get_shared_engine
from data_warehouse.models import FactLimitUpDaily
from data_warehouse.models import FactMarketEmotionDaily

logger = logging.getLogger(__name__)


def fetch_limit_up_from_akshare(trade_date: datetime.date) -> List[Dict]:
    """
    从 AKShare 获取涨停板数据（优先使用）
    返回格式与 fetch_limit_up_from_eastmoney 一致
    """
    try:
        from backend.services.akshare_service import get_akshare_service
        service = get_akshare_service()
        df = service.get_limit_up_stocks(trade_date)
        
        if df is None or df.empty:
            return []
        
        results = []
        for _, row in df.iterrows():
            code = str(row.get("代码", "")).strip()
            if not code:
                continue
            
            # 转换为 ts_code 格式
            if code.startswith("6"):
                ts_code = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                ts_code = f"{code}.SZ"
            else:
                continue
            
            # 解析时间（格式：092500 -> 09:25:00）
            first_hit_time_str = row.get("首次封板时间", None)
            last_hit_time_str = row.get("最后封板时间", None)
            
            first_hit_time = None
            last_hit_time = None
            
            if first_hit_time_str and len(str(first_hit_time_str)) == 6:
                try:
                    time_str = str(first_hit_time_str)
                    first_hit_time = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                except:
                    pass
            
            if last_hit_time_str and len(str(last_hit_time_str)) == 6:
                try:
                    time_str = str(last_hit_time_str)
                    last_hit_time = f"{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                except:
                    pass
            
            # 计算涨停价（最新价 / (1 + 涨跌幅/100)）
            close_price = float(row.get("最新价", 0))
            change_pct = float(row.get("涨跌幅", 0))
            limit_up_price = close_price if change_pct >= 9.5 else close_price / (1 + change_pct / 100)
            
            # 判断是否一字板（首次封板时间=最后封板时间且时间很早）
            is_one_word = False
            if first_hit_time and last_hit_time and first_hit_time == last_hit_time:
                if first_hit_time.startswith("09:25") or first_hit_time.startswith("09:30"):
                    is_one_word = True
            
            results.append({
                "ts_code": ts_code,
                "close": close_price,
                "change_pct": change_pct,
                "limit_up_price": limit_up_price,
                "turnover_rate": float(row.get("换手率", 0)),
                "amount": float(row.get("成交额", 0)),
                "seal_amount": float(row.get("封板资金", 0)),  # 封单金额
                "first_hit_time": first_hit_time,  # 格式：HH:MM:SS
                "last_hit_time": last_hit_time,
                "is_one_word": is_one_word,
                "is_continuous": bool(row.get("连板数", 1) > 1),
                "continuous_days": int(row.get("连板数", 1)),
                "limit_reason": str(row.get("所属行业", "")),  # AKShare返回的是行业，不是涨停原因
            })
        
        logger.info(f"✅ 从 AKShare 获取到 {len(results)} 只涨停股票")
        return results
        
    except Exception as e:
        logger.warning(f"⚠️ 从 AKShare 获取涨停板数据失败: {e}")
        return []


def fetch_limit_up_from_eastmoney(trade_date: datetime.date) -> List[Dict]:
    """
    从东方财富获取某天涨停板列表.
    返回结构统一为：
    [
      {
        "ts_code": "600519.SH",
        "close": 1234.56,
        "change_pct": 9.99,
        "limit_up_price": 1234.56,
        "turnover_rate": 12.34,
        "amount": 123456789.0,
        "seal_amount": 23456789.0,
        "first_hit_time": "09:35",
        "last_hit_time": "14:55",
        "is_one_word": True/False,
        "is_continuous": True/False,
        "continuous_days": 1/2/3/...,
        "limit_reason": "XX概念+YY预期"
      },
      ...
    ]
    """
    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "dpt": "app_zdt",
        "Pageindex": 0,
        "pagesize": 200,
        "date": trade_date.strftime("%Y%m%d"),
        "type": "ZTP"  # 涨停池
    }
    
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        
        # 检查响应内容
        if not resp.text or len(resp.text.strip()) == 0:
            logger.warning(f"[eastmoney] fetch limit up failed for {trade_date}: 响应为空")
            return []
        
        try:
            json_data = resp.json()
        except Exception as e:
            logger.warning(f"[eastmoney] fetch limit up failed for {trade_date}: JSON解析失败 - {e}, 响应: {resp.text[:200]}")
            return []
        
        if json_data is None:
            logger.warning(f"[eastmoney] fetch limit up failed for {trade_date}: 返回数据为空")
            return []
        
        # 检查返回码
        if json_data.get("rc") != 0:
            logger.debug(f"[eastmoney] {trade_date} 返回码非0: {json_data.get('rc')}, 可能无数据")
            return []
        
        data = json_data.get("data")
        if data is None:
            logger.warning(f"[eastmoney] fetch limit up failed for {trade_date}: data字段为None")
            return []
        
        if not isinstance(data, dict):
            logger.warning(f"[eastmoney] fetch limit up failed for {trade_date}: data不是字典类型")
            return []
        
        pool = data.get("pool", [])
        if not pool:
            logger.debug(f"[eastmoney] {trade_date} 无涨停板数据（pool为空）")
            return []
    except Exception as e:
        logger.error(f"[eastmoney] fetch limit up failed for {trade_date}: {e}")
        return []

    results = []
    for item in pool:
        # 字段名以东财当前格式为准
        code = item.get("c")           # 600519
        market = item.get("m")         # 1=SH, 0=SZ
        if market == 1:
            ts_code = f"{code}.SH"
        elif market == 0:
            ts_code = f"{code}.SZ"
        else:
            continue

        # 处理时间字段
        first_hit_time_str = item.get("ft", None)  # '09:35'
        last_hit_time_str = item.get("lt", None)   # '14:55'
        
        results.append(
            {
                "ts_code": ts_code,
                "close": float(item.get("p", 0)),
                "change_pct": float(item.get("zdp", 0)),
                "limit_up_price": float(item.get("np", 0)),
                "turnover_rate": float(item.get("hs", 0)),
                "amount": float(item.get("a", 0)),
                "seal_amount": float(item.get("fd", 0)),
                "first_hit_time": first_hit_time_str,  # 保留字符串格式，后续转换为datetime
                "last_hit_time": last_hit_time_str,
                "is_one_word": bool(item.get("yd", 0)),  # 一字
                "is_continuous": bool(item.get("lbc", 1) > 1),
                "continuous_days": int(item.get("lbc", 1)),
                "limit_reason": item.get("dr", ""),
            }
        )
    return results


def upsert_limitup_and_emotion(trade_date: datetime.date):
    """
    拉取指定日期的涨停板列表，写入 fact_limit_up_daily 和 fact_market_emotion_daily
    优先使用 AKShare，失败则使用东财接口
    使用 SQLAlchemy 批量插入
    """
    # 优先使用 AKShare
    records = fetch_limit_up_from_akshare(trade_date)
    source = "akshare"
    
    # 如果 AKShare 失败或无数据，使用东财接口
    if not records:
        logger.info("AKShare 无数据，尝试使用东财接口...")
        records = fetch_limit_up_from_eastmoney(trade_date)
        source = "eastmoney"
    
    if not records:
        logger.warning(f"⚠️ {trade_date} 未获取到涨停板数据")
        return
    
    engine = get_shared_engine()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 准备涨停板明细数据
        limitup_rows = []
        for r in records:
            # 处理时间字段
            first_hit_dt = None
            last_hit_dt = None
            
            if r["first_hit_time"]:
                try:
                    # 支持两种格式：HH:MM 和 HH:MM:SS
                    time_str = r['first_hit_time']
                    if len(time_str) == 5:  # HH:MM
                        first_hit_dt = datetime.datetime.strptime(
                            f"{trade_date} {time_str}", 
                            "%Y-%m-%d %H:%M"
                        )
                    elif len(time_str) == 8:  # HH:MM:SS
                        first_hit_dt = datetime.datetime.strptime(
                            f"{trade_date} {time_str}", 
                            "%Y-%m-%d %H:%M:%S"
                        )
                    else:
                        first_hit_dt = None
                except Exception as e:
                    logger.debug(f"解析 first_hit_time 失败: {e}")
                    first_hit_dt = None
            
            if r["last_hit_time"]:
                try:
                    # 支持两种格式：HH:MM 和 HH:MM:SS
                    time_str = r['last_hit_time']
                    if len(time_str) == 5:  # HH:MM
                        last_hit_dt = datetime.datetime.strptime(
                            f"{trade_date} {time_str}", 
                            "%Y-%m-%d %H:%M"
                        )
                    elif len(time_str) == 8:  # HH:MM:SS
                        last_hit_dt = datetime.datetime.strptime(
                            f"{trade_date} {time_str}", 
                            "%Y-%m-%d %H:%M:%S"
                        )
                    else:
                        last_hit_dt = None
                except Exception as e:
                    logger.debug(f"解析 last_hit_time 失败: {e}")
                    last_hit_dt = None
            
            limitup_rows.append({
                "ts_code": r["ts_code"],
                "trade_date": trade_date,
                "first_hit_time": first_hit_dt,
                "last_hit_time": last_hit_dt,
                "is_one_word": r["is_one_word"],
                "close": r["close"],
                "change_pct": r["change_pct"],
                "limit_up_price": r["limit_up_price"],
                "turnover_rate": r["turnover_rate"],
                "amount": r["amount"],
                "seal_amount": r["seal_amount"],
                "is_continuous": r["is_continuous"],
                "continuous_days": r["continuous_days"],
                "limit_reason": r["limit_reason"],
                "source": source,
            })
        
        # 使用批量插入优化
        if limitup_rows:
            df_limitup = pd.DataFrame(limitup_rows)
            
            with engine.connect() as conn:
                temp_table_name = 'temp_limitup_import'
                
                # 1. 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
                
                # 2. 创建临时表
                df_limitup.to_sql(
                    temp_table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000
                )
                conn.commit()
                
                # 3. 批量upsert
                update_set = """
                    first_hit_time = EXCLUDED.first_hit_time,
                    last_hit_time = EXCLUDED.last_hit_time,
                    is_one_word = EXCLUDED.is_one_word,
                    close = EXCLUDED.close,
                    change_pct = EXCLUDED.change_pct,
                    limit_up_price = EXCLUDED.limit_up_price,
                    turnover_rate = EXCLUDED.turnover_rate,
                    amount = EXCLUDED.amount,
                    seal_amount = EXCLUDED.seal_amount,
                    is_continuous = EXCLUDED.is_continuous,
                    continuous_days = EXCLUDED.continuous_days,
                    limit_reason = EXCLUDED.limit_reason,
                    source = EXCLUDED.source,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                insert_cols = ', '.join(df_limitup.columns)
                select_cols = ', '.join(df_limitup.columns)
                
                sql = f"""
                INSERT INTO fact_limit_up_daily 
                ({insert_cols})
                SELECT {select_cols}
                FROM {temp_table_name}
                ON CONFLICT (ts_code, trade_date) 
                DO UPDATE SET {update_set}
                """
                
                conn.execute(text(sql))
                conn.commit()
                
                # 4. 删除临时表
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
                conn.commit()
        
        # 计算情绪统计
        total_limit_up = len(records)
        total_limit_down = 0  # 如需要可另写跌停接口
        broken_limit_up = 0   # 可由当日分时/日内数据计算
        highest_streak = max([r["continuous_days"] for r in records], default=0)
        
        # 写入/更新情绪表
        emotion_record = {
            "trade_date": trade_date,
            "total_limit_up": total_limit_up,
            "total_limit_down": total_limit_down,
            "broken_limit_up": broken_limit_up,
            "highest_streak": highest_streak,
            "mainline_sector": None,  # 后续策略写回
            "emotion_stage": None,    # 后续情绪模型算好再写回
        }
        
        # 使用 SQLAlchemy ORM 写入情绪表
        existing = session.query(FactMarketEmotionDaily).filter(
            FactMarketEmotionDaily.trade_date == trade_date
        ).first()
        
        if existing:
            existing.total_limit_up = total_limit_up
            existing.total_limit_down = total_limit_down
            existing.broken_limit_up = broken_limit_up
            existing.highest_streak = highest_streak
        else:
            new_emotion = FactMarketEmotionDaily(**emotion_record)
            session.add(new_emotion)
        
        session.commit()
        
        logger.info(f"✅ 成功更新 {trade_date} 的涨停板数据: {total_limit_up} 只涨停，最高连板 {highest_streak} 板")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 更新涨停板和情绪数据失败: {e}", exc_info=True)
        raise
    finally:
        session.close()

