"""
导入前复权数据到PostgreSQL数据仓库
从 data_cache/前复权 目录读取CSV文件，导入到 fact_daily_price_qfq 表
"""

import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Optional
import logging

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.config import DATABASE_URL
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from data_warehouse.models import FactDailyPriceQfq
from data_warehouse.models import DimStock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def normalize_stock_code(code: str) -> str:
    """
    标准化股票代码
    sz.301678 -> 301678.SZ
    sh.600519 -> 600519.SH
    """
    if not code:
        return ""
    
    code = code.strip().lower()
    
    # 处理 sz.301678 格式
    if '.' in code:
        parts = code.split('.')
        if len(parts) == 2:
            exchange = parts[0]
            stock_code = parts[1]
            
            if exchange == 'sh' or exchange == 'shse':
                return f"{stock_code}.SH"
            elif exchange == 'sz' or exchange == 'szse':
                return f"{stock_code}.SZ"
            else:
                return code
    
    return code


def parse_qfq_csv(file_path: str) -> pd.DataFrame:
    """
    解析前复权数据CSV文件
    """
    try:
        # 使用GBK编码读取
        df = pd.read_csv(file_path, encoding='gbk')
    except Exception as e:
        logger.error(f"无法读取文件 {file_path}: {e}")
        return pd.DataFrame()
    
    if df.empty:
        return pd.DataFrame()
    
    # 从文件名获取股票代码
    file_name = Path(file_path).stem  # sz.301678
    stock_code = normalize_stock_code(file_name)
    
    # 如果第二列有代码，使用第二列（通常第二列是代码）
    if len(df.columns) > 1 and len(df) > 0:
        code_col = df.columns[1]  # 第二列是"代码"
        first_value = str(df.iloc[0, 1])
        if '.' in first_value.lower():
            stock_code = normalize_stock_code(first_value)
    
    if not stock_code:
        logger.warning(f"无法识别股票代码: {file_path}")
        return pd.DataFrame()
    
    # 解析日期列（第一列通常是日期）
    if len(df.columns) < 1:
        logger.warning(f"文件 {file_path} 列数不足")
        return pd.DataFrame()
    
    date_col = df.columns[0]  # 第一列是"日期"
    df['trade_date'] = pd.to_datetime(df[date_col], errors='coerce')
    df = df[df['trade_date'].notna()]
    
    if df.empty:
        return pd.DataFrame()
    
    # 映射CSV列名到数据库字段
    column_mapping = {
        '开盘价': 'open',
        '最高价': 'high',
        '最低价': 'low',
        '收盘价': 'close',
        '前收盘': 'pre_close',
        '成交量': 'vol',
        '成交金额': 'amount',
        '换手率': 'turnover_rate',
        '涨跌幅百分比': 'change_pct',
        '滚动市盈率': 'pe_ttm',
        '市净率': 'pb',
        '滚动市销率': 'ps_ttm',
        '滚动市现率': 'pcf_ttm',
        '未停牌': 'is_suspended',  # 1=未停牌，0=停牌
        '是否st': 'is_st',  # 1=ST，0=非ST
        '量比': 'volume_ratio',  # 量比字段
        '5日均量': 'avg_volume_5',  # 5日平均成交量
    }
    
    # 构建结果DataFrame
    result_rows = []
    
    for _, row in df.iterrows():
        trade_date = row['trade_date'].date()
        
        # 构建记录字典
        record = {
            'ts_code': stock_code,
            'trade_date': trade_date,
        }
        
        # 映射所有字段
        for csv_col, db_field in column_mapping.items():
            if csv_col in df.columns:
                value = row[csv_col]
                if pd.notna(value) and value != '':
                    try:
                        if db_field in ['is_suspended', 'is_st']:
                            # 布尔字段：1表示True，0表示False
                            # 对于is_suspended：1=未停牌（False），0=停牌（True）
                            if db_field == 'is_suspended':
                                record[db_field] = bool(value == 0)  # 0=停牌=True
                            else:
                                record[db_field] = bool(value == 1)  # 1=ST=True
                        else:
                            record[db_field] = float(value)
                    except (ValueError, TypeError):
                        pass
        
        result_rows.append(record)
    
    result_df = pd.DataFrame(result_rows)
    return result_df


def import_to_fact_daily_price_qfq(engine, data_df: pd.DataFrame):
    """
    使用批量插入优化：使用pandas to_sql + ON CONFLICT DO UPDATE
    速度提升10-50倍
    """
    if data_df.empty:
        return 0, 0, 0
    
    # 准备数据：确保列名和数据类型正确
    df = data_df.copy()
    
    # 确保必要的字段存在
    required_fields = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close']
    for field in required_fields:
        if field not in df.columns:
            logger.warning(f"缺少必要字段: {field}")
            return 0, 0, 0
    
    # 填充缺失字段
    df['pre_close'] = df.get('pre_close', None)
    df['vol'] = df.get('vol', None)
    df['amount'] = df.get('amount', None)
    df['turnover_rate'] = df.get('turnover_rate', None)
    df['change_pct'] = df.get('change_pct', None)
    df['pe_ttm'] = df.get('pe_ttm', None)
    df['pb'] = df.get('pb', None)
    df['ps_ttm'] = df.get('ps_ttm', None)
    df['pcf_ttm'] = df.get('pcf_ttm', None)
    df['is_suspended'] = df.get('is_suspended', False)
    df['is_st'] = df.get('is_st', False)
    df['volume_ratio'] = df.get('volume_ratio', None)  # 量比字段
    df['avg_volume_5'] = df.get('avg_volume_5', None)  # 5日平均成交量
    df['source'] = 'qfq_csv'
    
    # 选择需要的列（按表结构顺序）
    columns = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
               'vol', 'amount', 'turnover_rate', 'change_pct', 'pe_ttm', 'pb', 
               'ps_ttm', 'pcf_ttm', 'is_suspended', 'is_st', 'volume_ratio', 'avg_volume_5', 'source']
    df = df[[col for col in columns if col in df.columns]]
    
    try:
        # 使用临时表 + INSERT ... ON CONFLICT DO UPDATE 策略（PostgreSQL最快的批量upsert方式）
        with engine.connect() as conn:
            temp_table_name = 'temp_qfq_import'
            
            # 1. 创建临时表（确保列顺序和类型匹配）
            # 先删除可能存在的临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 2. 使用pandas to_sql创建临时表
            df.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=5000  # 增大批次
            )
            conn.commit()
            
            # 3. 使用INSERT ... ON CONFLICT DO UPDATE进行批量upsert
            # 明确指定列顺序，避免列顺序不匹配
            update_set = """
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                pre_close = EXCLUDED.pre_close,
                vol = EXCLUDED.vol,
                amount = EXCLUDED.amount,
                turnover_rate = EXCLUDED.turnover_rate,
                change_pct = EXCLUDED.change_pct,
                pe_ttm = EXCLUDED.pe_ttm,
                pb = EXCLUDED.pb,
                ps_ttm = EXCLUDED.ps_ttm,
                pcf_ttm = EXCLUDED.pcf_ttm,
                is_suspended = EXCLUDED.is_suspended,
                is_st = EXCLUDED.is_st,
                volume_ratio = EXCLUDED.volume_ratio,
                avg_volume_5 = EXCLUDED.avg_volume_5,
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP
            """
            
            sql = f"""
            INSERT INTO fact_daily_price_qfq 
            (ts_code, trade_date, open, high, low, close, pre_close, vol, amount, 
             turnover_rate, change_pct, pe_ttm, pb, ps_ttm, pcf_ttm, is_suspended, is_st, volume_ratio, avg_volume_5, source)
            SELECT 
                ts_code, trade_date, open, high, low, close, pre_close, vol, amount,
                turnover_rate, change_pct, pe_ttm, pb, ps_ttm, pcf_ttm, is_suspended, is_st, volume_ratio, avg_volume_5, source
            FROM {temp_table_name}
            ON CONFLICT (ts_code, trade_date) 
            DO UPDATE SET {update_set}
            """
            
            result = conn.execute(text(sql))
            conn.commit()
            
            # 4. 删除临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            imported = len(df)
            return imported, 0, 0
            
    except Exception as e:
        logger.error(f"批量导入失败: {e}", exc_info=True)
        # 如果批量导入失败，回退到逐条插入（但使用更大的批次）
        return _fallback_import(engine, data_df)


def _fallback_import(engine, data_df: pd.DataFrame):
    """
    回退方案：逐条插入（但使用更大的批次和批量提交）
    """
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    imported = 0
    
    try:
        # 批量处理，每1000条提交一次
        batch_size = 1000
        for i in range(0, len(data_df), batch_size):
            batch = data_df.iloc[i:i+batch_size]
            
            for _, row in batch.iterrows():
                new_record = FactDailyPriceQfq(
                    ts_code=row['ts_code'],
                    trade_date=row['trade_date'],
                    open=row.get('open'),
                    high=row.get('high'),
                    low=row.get('low'),
                    close=row.get('close'),
                    pre_close=row.get('pre_close'),
                    vol=row.get('vol'),
                    amount=row.get('amount'),
                    turnover_rate=row.get('turnover_rate'),
                    change_pct=row.get('change_pct'),
                    pe_ttm=row.get('pe_ttm'),
                    pb=row.get('pb'),
                    ps_ttm=row.get('ps_ttm'),
                    pcf_ttm=row.get('pcf_ttm'),
                    is_suspended=row.get('is_suspended', False),
                    is_st=row.get('is_st', False),
                    volume_ratio=row.get('volume_ratio'),
                    avg_volume_5=row.get('avg_volume_5'),
                    source='qfq_csv',
                )
                session.merge(new_record)  # 使用merge自动处理冲突
                imported += 1
            
            session.commit()
            if (i + batch_size) % 5000 == 0:
                logger.info(f"  回退模式：已处理 {i + batch_size} 条")
        
        return imported, 0, 0
    except Exception as e:
        session.rollback()
        logger.error(f"回退导入也失败: {e}")
        return 0, 0, len(data_df)
    finally:
        session.close()


def update_dim_stock(session, stock_code: str):
    """
    更新或创建 dim_stock 记录（如果不存在）
    """
    existing = session.query(DimStock).filter(DimStock.ts_code == stock_code).first()
    
    if not existing:
        # 从代码判断交易所
        exchange = 'SSE' if '.SH' in stock_code else 'SZSE'
        symbol = stock_code.split('.')[0]
        
        new_stock = DimStock(
            ts_code=stock_code,
            exchange=exchange,
            symbol=symbol,
            name='',  # 名称暂时为空，可以从其他数据源补充
            list_date=None,
            delist_date=None
        )
        session.add(new_stock)
        session.commit()


def main():
    """
    主函数：批量导入前复权数据
    """
    # 配置路径
    base_dir = Path(__file__).parent.parent.parent
    qfq_dir = base_dir / "data_cache" / "前复权"
    
    if not qfq_dir.exists():
        logger.error(f"前复权数据目录不存在: {qfq_dir}")
        return
    
    # 连接数据库
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 获取所有CSV文件
        csv_files = list(qfq_dir.glob("*.csv"))
        total_files = len(csv_files)
        
        logger.info(f"📁 找到 {total_files} 个前复权数据文件")
        
        total_imported = 0
        total_updated = 0
        total_skipped = 0
        
        for idx, csv_file in enumerate(csv_files, 1):
            logger.info(f"\n[{idx}/{total_files}] 处理: {csv_file.name}")
            
            # 解析CSV
            data_df = parse_qfq_csv(str(csv_file))
            
            if data_df.empty:
                logger.warning(f"  ⚠️ 文件为空或解析失败")
                continue
            
            logger.info(f"  📊 解析到 {len(data_df)} 条记录")
            
            # 更新股票维度表
            if len(data_df) > 0:
                stock_code = data_df.iloc[0]['ts_code']
                update_dim_stock(session, stock_code)
            
            # 导入到fact_daily_price_qfq（使用批量插入优化）
            imported, updated, skipped = import_to_fact_daily_price_qfq(engine, data_df)
            total_imported += imported
            total_updated += updated
            total_skipped += skipped
            
            logger.info(f"  ✅ 导入 {imported} 条，更新 {updated} 条，跳过 {skipped} 条")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 导入完成！")
        logger.info(f"   总文件数: {total_files}")
        logger.info(f"   总导入: {total_imported} 条")
        logger.info(f"   总更新: {total_updated} 条")
        logger.info(f"   总跳过: {total_skipped} 条")
        logger.info(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"❌ 导入过程出错: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()

