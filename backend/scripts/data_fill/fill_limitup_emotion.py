"""
补充涨停板和市场情绪数据
使用AKShare获取涨停板统计和市场情绪指标
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import logging
import time
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
load_dotenv()

from data_warehouse.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fill_limit_up_daily(trade_date: str):
    """
    补充单日涨停板数据
    
    Args:
        trade_date: 交易日期 YYYY-MM-DD
    """
    logger.info(f"📥 获取 {trade_date} 的涨停板数据...")
    
    try:
        import akshare as ak
        
        time.sleep(1)
        
        # 获取涨停板数据
        df = ak.stock_zt_pool_em(date=trade_date.replace('-', ''))
        
        if df is None or df.empty:
            logger.warning(f"⚠️ {trade_date} 无涨停板数据")
            return False
        
        # 准备数据
        rows = []
        for _, row in df.iterrows():
            code = str(row['代码']).strip()
            
            # 判断交易所
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                ts_code = f"{code}.SZ"
            else:
                continue
            
            # 解析时间（结合 trade_date 转为完整时间戳）
            first_time = str(row.get('首次封板时间', '')).strip() if pd.notna(row.get('首次封板时间')) else None
            last_time = str(row.get('最后封板时间', '')).strip() if pd.notna(row.get('最后封板时间')) else None
            first_ts = f"{trade_date} {first_time}" if first_time and len(first_time) <= 8 else None
            last_ts = f"{trade_date} {last_time}" if last_time and len(last_time) <= 8 else None

            # 连板天数：优先 连板数/昨日连板数
            cont_days = None
            for col in ('连板数', '昨日连板数'):
                if pd.notna(row.get(col)):
                    try:
                        cont_days = int(float(row[col]))
                        break
                    except (ValueError, TypeError):
                        pass

            # 封板资金（封单金额）
            seal_amount = None
            for col in ('封板资金', '封单资金', 'fd'):
                if col in row.index and pd.notna(row.get(col)):
                    try:
                        seal_amount = float(row[col])
                        break
                    except (ValueError, TypeError):
                        pass

            rows.append({
                'ts_code': ts_code,
                'trade_date': trade_date,
                'source': 'akshare',
                'close': float(row.get('最新价', 0)) if pd.notna(row.get('最新价')) else None,
                'change_pct': float(row.get('涨跌幅', 0)) if pd.notna(row.get('涨跌幅')) else None,
                'turnover_rate': float(row.get('换手率', 0)) if pd.notna(row.get('换手率')) else None,
                'amount': float(row.get('成交额', 0)) if pd.notna(row.get('成交额')) else None,
                'seal_amount': seal_amount,
                'first_hit_time': first_ts,
                'last_hit_time': last_ts,
                'limit_reason': str(row.get('涨停原因', '')) if pd.notna(row.get('涨停原因')) else None,
                'is_continuous': cont_days is not None and cont_days >= 2,
                'continuous_days': cont_days,
            })
        
        if not rows:
            logger.warning(f"⚠️ {trade_date} 未解析到有效涨停板数据")
            return False
        
        # 批量入库
        engine = create_engine(DATABASE_URL, echo=False)
        with engine.connect() as conn:
            temp_table_name = 'temp_limit_up_import'
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 创建临时表
            df_data = pd.DataFrame(rows)
            df_data.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            conn.commit()
            
            # 批量插入（列名与 fact_limit_up_daily 表一致）
            sql = f"""
            INSERT INTO fact_limit_up_daily
            (ts_code, trade_date, source, close, change_pct, turnover_rate, amount, seal_amount,
             first_hit_time, last_hit_time, limit_reason, is_continuous, continuous_days)
            SELECT ts_code, trade_date::date, source, close, change_pct, turnover_rate, amount, seal_amount,
                   first_hit_time::timestamp, last_hit_time::timestamp, limit_reason,
                   is_continuous, continuous_days
            FROM {temp_table_name}
            ON CONFLICT (ts_code, trade_date)
            DO UPDATE SET
                close = EXCLUDED.close,
                change_pct = EXCLUDED.change_pct,
                turnover_rate = EXCLUDED.turnover_rate,
                amount = EXCLUDED.amount,
                seal_amount = EXCLUDED.seal_amount,
                first_hit_time = EXCLUDED.first_hit_time,
                last_hit_time = EXCLUDED.last_hit_time,
                limit_reason = EXCLUDED.limit_reason,
                is_continuous = EXCLUDED.is_continuous,
                continuous_days = EXCLUDED.continuous_days
            """
            
            conn.execute(text(sql))
            conn.commit()
            
            # 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
        
        logger.info(f"✅ {trade_date} 成功导入 {len(rows)} 条涨停板数据")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ {trade_date} 涨停板数据获取失败: {e}")
        return False


def _judge_emotion_stage(
    limit_up_count: int,
    limit_down_count: int,
    advance_decline_ratio: float,
    highest_streak: int,
    chain_board_count: int,
) -> str:
    """
    冰点判断方案（多维度，符合市场共识）

    参考维度：
    - 涨停家数：冰点 < 20，极冰 < 10
    - 跌停家数：冰点时通常 > 30
    - 涨跌比：冰点 < 0.5
    - 最高连板：冰点时受压制 <= 3~4 板
    - 连板数量（2板+）：冰点 < 5

    规则：
    - 涨停 >= 30 不判冰点（结构性行情）
    - 涨停 >= 50 且 涨跌比 >= 1.2 → 高潮
    - 多条件满足时判冰点
    """
    # 1. 高潮：涨停多 + 涨跌比好
    if limit_up_count >= 50 and advance_decline_ratio >= 1.2:
        return 'high_tide'

    # 2. 回暖：涨停尚可 或 涨跌比尚可
    if limit_up_count >= 30:
        return 'warming'
    if limit_up_count >= 20 and advance_decline_ratio >= 1.0:
        return 'warming'

    # 3. 冰点：多维度综合判断
    # 极冰：涨停极少
    if limit_up_count <= 5:
        return 'freezing'

    # 冰点条件（满足多条强化判断）
    cond_limit_up_low = limit_up_count < 20
    cond_ratio_low = advance_decline_ratio < 0.5
    cond_limit_down_high = limit_down_count >= 25
    cond_streak_low = highest_streak <= 3
    cond_chain_few = chain_board_count < 5

    ice_score = sum([
        cond_limit_up_low,
        cond_ratio_low,
        cond_limit_down_high,
        cond_streak_low,
        cond_chain_few,
    ])

    # 涨停 < 20 且 满足 >= 2 个冰点条件 → 冰点
    if limit_up_count < 20 and ice_score >= 2:
        return 'freezing'
    # 涨停 < 15 且 (涨跌比极低 或 跌停多)
    if limit_up_count < 15 and (advance_decline_ratio <= 0.4 or limit_down_count >= 30):
        return 'freezing'

    # 4. 正常
    return 'normal'


def calculate_market_emotion(trade_date: str):
    """
    计算单日市场情绪指标

    Args:
        trade_date: 交易日期 YYYY-MM-DD
    """
    logger.info(f"📊 计算 {trade_date} 的市场情绪...")
    
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        
        with engine.connect() as conn:
            # 统计涨停板数量
            result = conn.execute(text(f"""
                SELECT COUNT(*) 
                FROM fact_limit_up_daily 
                WHERE trade_date = '{trade_date}'
            """))
            limit_up_count = result.scalar() or 0

            # 统计涨跌家数、跌停数（日线表可作涨停数 fallback，当 fact_limit_up_daily 无采集时）
            result = conn.execute(text(f"""
                SELECT 
                    SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) as up_count,
                    SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) as down_count,
                    SUM(CASE WHEN change_pct >= 9.5 THEN 1 ELSE 0 END) as limit_up_qfq,
                    SUM(CASE WHEN change_pct <= -9.5 THEN 1 ELSE 0 END) as limit_down_count,
                    AVG(turnover_rate) as avg_turnover
                FROM fact_daily_price_qfq
                WHERE trade_date = '{trade_date}'
            """))
            row = result.fetchone()
            
            if row is None:
                logger.warning(f"⚠️ {trade_date} 无行情数据，无法计算市场情绪")
                return False
            
            up_count = row[0] or 0
            down_count = row[1] or 0
            limit_up_qfq = row[2] or 0
            limit_down_count = row[3] or 0
            avg_turnover = row[4] or 0

            # 涨停数：优先采集表，无数据时用日线统计兜底
            if limit_up_count == 0 and limit_up_qfq > 0:
                limit_up_count = limit_up_qfq

            # 跌停数：优先 AKShare 跌停股池（与涨停同源，更准确）；仅支持近30日；超期则用日线统计
            try:
                trade_dt = datetime.strptime(trade_date, '%Y-%m-%d')
                if (datetime.now() - trade_dt).days <= 35:  # 留余量覆盖非交易日
                    import akshare as ak
                    time.sleep(0.5)  # 限流
                    df_dt = ak.stock_zt_pool_dtgc_em(date=trade_date.replace('-', ''))
                    if df_dt is not None and not df_dt.empty:
                        limit_down_count = len(df_dt)
                        logger.debug(f"  {trade_date} AKShare 跌停股池: {limit_down_count} 只")
            except Exception as e:
                logger.debug(f"  {trade_date} 跌停股池获取失败，使用日线统计: {e}")

            # 涨跌比
            advance_decline_ratio = up_count / down_count if down_count > 0 else 0
            
            # 统计连板：最高连板高度、2板及以上数量
            result = conn.execute(text(f"""
                SELECT 
                    COALESCE(MAX(continuous_days), 1),
                    COUNT(*) FILTER (WHERE continuous_days >= 2)
                FROM fact_limit_up_daily
                WHERE trade_date = '{trade_date}'
            """))
            streak_row = result.fetchone()
            highest_streak = streak_row[0] or 1
            chain_board_count = streak_row[1] or 0

            # 冰点判断方案（多维度，符合市场共识）
            emotion_stage = _judge_emotion_stage(
                limit_up_count=limit_up_count,
                limit_down_count=limit_down_count,
                advance_decline_ratio=advance_decline_ratio,
                highest_streak=highest_streak,
                chain_board_count=chain_board_count,
            )

            # 插入市场情绪数据（列名与 fact_market_emotion_daily 表一致）
            conn.execute(text(f"""
                INSERT INTO fact_market_emotion_daily 
                (trade_date, total_limit_up, total_limit_down, broken_limit_up, highest_streak, emotion_stage)
                VALUES (
                    '{trade_date}', 
                    {limit_up_count}, 
                    {limit_down_count},
                    0,
                    {highest_streak}, 
                    '{emotion_stage}'
                )
                ON CONFLICT (trade_date) 
                DO UPDATE SET
                    total_limit_up = EXCLUDED.total_limit_up,
                    total_limit_down = EXCLUDED.total_limit_down,
                    broken_limit_up = EXCLUDED.broken_limit_up,
                    highest_streak = EXCLUDED.highest_streak,
                    emotion_stage = EXCLUDED.emotion_stage
            """))
            conn.commit()
        
        logger.info(f"✅ {trade_date} 市场情绪计算完成 (情绪: {emotion_stage}, 涨停: {limit_up_count}, 跌停: {limit_down_count})")
        return True
        
    except Exception as e:
        logger.error(f"❌ {trade_date} 市场情绪计算失败: {e}", exc_info=True)
        return False


def fill_recent_data(days: int = 90):
    """
    补充最近N天的涨停板和市场情绪数据
    
    Args:
        days: 回溯天数
    """
    logger.info("="*60)
    logger.info(f"开始补充最近 {days} 天的涨停板和市场情绪数据")
    logger.info("="*60)
    
    # 生成日期列表（只包含交易日）
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 获取交易日列表
    engine = create_engine(DATABASE_URL, echo=False)
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT DISTINCT trade_date
            FROM fact_daily_price_qfq
            WHERE trade_date >= '{start_date.strftime('%Y-%m-%d')}'
              AND trade_date <= '{end_date.strftime('%Y-%m-%d')}'
            ORDER BY trade_date DESC
        """))
        trade_dates = [row[0].strftime('%Y-%m-%d') for row in result]
    
    total = len(trade_dates)
    logger.info(f"共 {total} 个交易日需要处理")
    
    success_count = 0
    fail_count = 0
    
    for idx, trade_date in enumerate(trade_dates, start=1):
        logger.info(f"\n[{idx}/{total}] 处理 {trade_date}...")
        
        try:
            # 补充涨停板数据
            limitup_success = fill_limit_up_daily(trade_date)
            
            # 计算市场情绪
            emotion_success = calculate_market_emotion(trade_date)
            
            if limitup_success and emotion_success:
                success_count += 1
                time.sleep(0.5)
            else:
                fail_count += 1
                time.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ {trade_date} 处理异常: {e}")
            fail_count += 1
            time.sleep(3)
        
        # 每10天输出一次进度
        if idx % 10 == 0:
            logger.info(f"\n进度: {idx}/{total} ({idx*100//total}%) | 成功: {success_count} | 失败: {fail_count}")
    
    logger.info("\n" + "="*60)
    logger.info("涨停板和市场情绪数据补充完成")
    logger.info(f"总计: {total} 天 | 成功: {success_count} | 失败: {fail_count}")
    logger.info("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='补充涨停板和市场情绪数据')
    parser.add_argument('--days', type=int, default=90, help='回溯天数')
    
    args = parser.parse_args()
    
    fill_recent_data(days=args.days)

