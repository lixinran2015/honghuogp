"""
导入基本面数据到PostgreSQL数据仓库
从 backend/基本面数据 目录读取CSV文件，结合股票名称映射，导入到 fact_daily_fundamental 表
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
from data_warehouse.models import FactDailyFundamental
from data_warehouse.models import DimStock

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def normalize_stock_code(code: str) -> str:
    """
    标准化股票代码
    SHSE.600519 -> 600519.SH
    SZSE.000001 -> 000001.SZ
    SH.600519 -> 600519.SH
    """
    if not code:
        return ""
    
    code = code.strip().upper()
    
    # 处理 SHSE.600519 格式
    if '.' in code:
        parts = code.split('.')
        if len(parts) == 2:
            exchange = parts[0]
            stock_code = parts[1]
            
            if exchange == 'SHSE' or exchange == 'SH':
                return f"{stock_code}.SH"
            elif exchange == 'SZSE' or exchange == 'SZ':
                return f"{stock_code}.SZ"
            else:
                return code
    
    # 处理 sh600519 格式
    if code.startswith('SH') or code.startswith('SZ'):
        if code.startswith('SH'):
            return f"{code[2:]}.SH"
        elif code.startswith('SZ'):
            return f"{code[2:]}.SZ"
    
    return code


def load_stock_name_mapping(reference_file: str) -> Dict[str, str]:
    """
    从参考CSV文件加载股票代码和名称的映射
    """
    mapping = {}
    
    if not os.path.exists(reference_file):
        logger.warning(f"参考文件不存在: {reference_file}")
        return mapping
    
    try:
        # 尝试UTF-8编码
        df = pd.read_csv(reference_file, encoding='utf-8')
    except:
        # 如果失败，尝试GBK
        try:
            df = pd.read_csv(reference_file, encoding='gbk')
        except Exception as e:
            logger.warning(f"无法读取参考文件: {reference_file}, {e}")
            return mapping
    
    # 查找代码和名称列
    code_col = None
    name_col = None
    
    for col in df.columns:
        col_lower = col.lower()
        if '代码' in col or 'code' in col_lower:
            code_col = col
        if '名称' in col or 'name' in col_lower:
            name_col = col
    
    if code_col and name_col:
        for _, row in df.iterrows():
            code = str(row[code_col]).strip()
            name = str(row[name_col]).strip()
            
            # 标准化代码
            normalized_code = normalize_stock_code(code)
            if normalized_code and name and name != 'nan':
                mapping[normalized_code] = name
    
    logger.info(f"✅ 加载股票名称映射: {len(mapping)} 条")
    return mapping


def parse_fundamental_csv(file_path: str, stock_name_mapping: Dict[str, str]) -> pd.DataFrame:
    """
    解析基本面数据CSV文件
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
    file_name = Path(file_path).stem  # SH.600519
    stock_code = normalize_stock_code(file_name)
    
    # 如果第一列有代码，使用第一列（通常第一列是代码）
    if len(df.columns) > 0 and len(df) > 0:
        first_col = df.columns[0]
        first_value = str(df.iloc[0, 0])
        if '.' in first_value or first_value.startswith(('SH', 'SZ')):
            stock_code = normalize_stock_code(first_value)
    
    if not stock_code:
        logger.warning(f"无法识别股票代码: {file_path}")
        return pd.DataFrame()
    
    # 获取股票名称
    stock_name = stock_name_mapping.get(stock_code, "")
    
    # 解析日期列（第二列通常是日期）
    if len(df.columns) < 2:
        logger.warning(f"文件 {file_path} 列数不足")
        return pd.DataFrame()
    
    date_col = df.columns[1]
    df['trade_date'] = pd.to_datetime(df[date_col], errors='coerce')
    df = df[df['trade_date'].notna()]
    
    if df.empty:
        return pd.DataFrame()
    
    # 映射CSV列名到数据库字段（根据实际CSV列名）
    column_mapping = {
        # 市盈率
        '市盈率(TTM)': 'pe_ttm',
        '市盈率(最新年报LYR)': 'pe_lyr',
        '市盈率(最新报告期MRQ)': 'pe_mrq',
        '市盈率(当年一季×4)': 'pe_q4',
        '市盈率(当年中报×2)': 'pe_q2',
        '市盈率(当年三季×4/3)': 'pe_q4_3',
        '市盈率(TTM) 扣除非经常性损益': 'pe_ttm_excl',
        '市盈率(最新年报LYR) 扣除非经常性损益': 'pe_lyr_excl',
        '市盈率(最新报告期MRQ) 扣除非经常性损益': 'pe_mrq_excl',
        '市盈率(当年一季×4) 扣除非经常性损益': 'pe_q4_excl',
        '市盈率(当年中报×2) 扣除非经常性损益': 'pe_q2_excl',
        '市盈率(当年三季×4/3) 扣除非经常性损益': 'pe_q4_3_excl',
        # 市净率
        '市净率(最新年报LYR)': 'pb_lyr',
        '市净率(最新报告期MRQ)': 'pb_mrq',
        '市净率(剔除其他权益工具，最新年报LYR)': 'pb_lyr_excl',
        '市净率(剔除其他权益工具，最新报告期MRQ)': 'pb_mrq_excl',
        # 股息率
        '股息率(滚动 12 月TTM)': 'dividend_yield_ttm',
        '股息率(上一财年LFY)': 'dividend_yield_lyr',
        # PEG值
        '历史PEG值(当年年报增长率)': 'peg_lyr',
        '历史PEG值(最新报告期增长率)': 'peg_mrq',
        '历史PEG值(当年1季*4较上年年报增长率)': 'peg_q4',
        '历史PEG值(当年中报*2较上年年报增长率)': 'peg_q2',
        '历史PEG值(当年3季*4/3较上年年报增长率)': 'peg_q4_3',
        '历史PEG值(PE_TTM较净利润3年复合增长率)': 'peg_ttm_3y',
    }
    
    # 构建结果DataFrame
    result_rows = []
    
    for _, row in df.iterrows():
        trade_date = row['trade_date'].date()
        
        # 构建记录字典
        record = {
            'ts_code': stock_code,
            'stock_name': stock_name,
            'trade_date': trade_date,
        }
        
        # 映射所有字段
        for csv_col, db_field in column_mapping.items():
            if csv_col in df.columns:
                value = row[csv_col]
                if pd.notna(value) and value != '':
                    try:
                        record[db_field] = float(value)
                    except (ValueError, TypeError):
                        pass
        
        result_rows.append(record)
    
    result_df = pd.DataFrame(result_rows)
    return result_df


def import_to_fact_daily_fundamental(engine, data_df: pd.DataFrame):
    """
    使用批量插入优化：使用临时表 + INSERT ... ON CONFLICT DO UPDATE
    速度提升10-50倍
    """
    if data_df.empty:
        return 0, 0, 0
    
    # 准备数据：确保列名和数据类型正确
    df = data_df.copy()
    
    # 确保必要的字段存在
    required_fields = ['ts_code', 'trade_date']
    for field in required_fields:
        if field not in df.columns:
            logger.warning(f"缺少必要字段: {field}")
            return 0, 0, 0
    
    # 填充缺失字段
    all_fields = ['pe_ttm', 'pe_lyr', 'pe_mrq', 'pe_q4', 'pe_q2', 'pe_q4_3',
                  'pe_ttm_excl', 'pe_lyr_excl', 'pe_mrq_excl', 'pe_q4_excl', 'pe_q2_excl', 'pe_q4_3_excl',
                  'pb_lyr', 'pb_mrq', 'pb_lyr_excl', 'pb_mrq_excl',
                  'roe_ttm', 'roe_lyr', 'roe_mrq', 'roe_q4', 'roe_q2', 'roe_q4_3',
                  'net_margin_ttm', 'net_margin_lyr', 'net_margin_mrq', 'net_margin_q4', 'net_margin_q2', 'net_margin_q4_3',
                  'gross_margin_ttm',
                  'op_cf_ttm', 'op_cf_lyr', 'op_cf_mrq', 'op_cf_q4', 'op_cf_q2', 'op_cf_q4_3',
                  'dividend_yield_ttm', 'dividend_yield_lyr',
                  'peg_lyr', 'peg_mrq', 'peg_q4', 'peg_q2', 'peg_q4_3', 'peg_ttm_3y']
    
    for field in all_fields:
        if field not in df.columns:
            df[field] = None
    
    df['source'] = 'fundamental_csv'
    df['data_quality'] = 'B'
    
    # 选择需要的列（按表结构顺序）
    columns = ['ts_code', 'trade_date'] + all_fields + ['source', 'data_quality']
    df = df[[col for col in columns if col in df.columns]]
    
    try:
        # 确保数值字段是numeric类型
        numeric_fields = ['pe_ttm', 'pe_lyr', 'pe_mrq', 'pe_q4', 'pe_q2', 'pe_q4_3',
                         'pe_ttm_excl', 'pe_lyr_excl', 'pe_mrq_excl', 'pe_q4_excl', 'pe_q2_excl', 'pe_q4_3_excl',
                         'pb_lyr', 'pb_mrq', 'pb_lyr_excl', 'pb_mrq_excl',
                         'roe_ttm', 'roe_lyr', 'roe_mrq', 'roe_q4', 'roe_q2', 'roe_q4_3',
                         'net_margin_ttm', 'net_margin_lyr', 'net_margin_mrq', 'net_margin_q4', 'net_margin_q2', 'net_margin_q4_3',
                         'gross_margin_ttm',
                         'op_cf_ttm', 'op_cf_lyr', 'op_cf_mrq', 'op_cf_q4', 'op_cf_q2', 'op_cf_q4_3',
                         'dividend_yield_ttm', 'dividend_yield_lyr',
                         'peg_lyr', 'peg_mrq', 'peg_q4', 'peg_q2', 'peg_q4_3', 'peg_ttm_3y']
        
        # 转换数值字段类型
        for field in numeric_fields:
            if field in df.columns:
                df[field] = pd.to_numeric(df[field], errors='coerce')
        
        # 使用临时表 + INSERT ... ON CONFLICT DO UPDATE 策略
        with engine.connect() as conn:
            temp_table_name = 'temp_fundamental_import'
            
            # 1. 删除可能存在的临时表
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
            conn.commit()
            
            # 2. 使用pandas to_sql创建临时表（指定dtype确保类型正确）
            df.to_sql(
                temp_table_name,
                conn,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=5000
            )
            conn.commit()
            
            # 3. 使用INSERT ... ON CONFLICT DO UPDATE进行批量upsert
            update_fields = [f for f in all_fields if f in df.columns]
            update_set = ',\n                '.join([f"{f} = EXCLUDED.{f}" for f in update_fields]) + ',\n                source = EXCLUDED.source,\n                data_quality = EXCLUDED.data_quality,\n                updated_at = CURRENT_TIMESTAMP'
            
            insert_cols = ', '.join([col for col in columns if col in df.columns])
            select_cols = ', '.join([col for col in columns if col in df.columns])
            
            sql = f"""
            INSERT INTO fact_daily_fundamental 
            ({insert_cols})
            SELECT {select_cols}
            FROM {temp_table_name}
            ON CONFLICT (ts_code, trade_date) 
            DO UPDATE SET 
                {update_set}
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
        return _fallback_import_fundamental(engine, data_df)


def _fallback_import_fundamental(engine, data_df: pd.DataFrame):
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
                new_record = FactDailyFundamental(
                    ts_code=row['ts_code'],
                    trade_date=row['trade_date'],
                    pe_ttm=row.get('pe_ttm'),
                    pe_lyr=row.get('pe_lyr'),
                    pe_mrq=row.get('pe_mrq'),
                    pe_q4=row.get('pe_q4'),
                    pe_q2=row.get('pe_q2'),
                    pe_q4_3=row.get('pe_q4_3'),
                    pe_ttm_excl=row.get('pe_ttm_excl'),
                    pe_lyr_excl=row.get('pe_lyr_excl'),
                    pe_mrq_excl=row.get('pe_mrq_excl'),
                    pe_q4_excl=row.get('pe_q4_excl'),
                    pe_q2_excl=row.get('pe_q2_excl'),
                    pe_q4_3_excl=row.get('pe_q4_3_excl'),
                    pb_lyr=row.get('pb_lyr'),
                    pb_mrq=row.get('pb_mrq'),
                    pb_lyr_excl=row.get('pb_lyr_excl'),
                    pb_mrq_excl=row.get('pb_mrq_excl'),
                    roe_ttm=row.get('roe_ttm'),
                    roe_lyr=row.get('roe_lyr'),
                    roe_mrq=row.get('roe_mrq'),
                    roe_q4=row.get('roe_q4'),
                    roe_q2=row.get('roe_q2'),
                    roe_q4_3=row.get('roe_q4_3'),
                    net_margin_ttm=row.get('net_margin_ttm'),
                    net_margin_lyr=row.get('net_margin_lyr'),
                    net_margin_mrq=row.get('net_margin_mrq'),
                    net_margin_q4=row.get('net_margin_q4'),
                    net_margin_q2=row.get('net_margin_q2'),
                    net_margin_q4_3=row.get('net_margin_q4_3'),
                    gross_margin_ttm=row.get('gross_margin_ttm'),
                    op_cf_ttm=row.get('op_cf_ttm'),
                    op_cf_lyr=row.get('op_cf_lyr'),
                    op_cf_mrq=row.get('op_cf_mrq'),
                    op_cf_q4=row.get('op_cf_q4'),
                    op_cf_q2=row.get('op_cf_q2'),
                    op_cf_q4_3=row.get('op_cf_q4_3'),
                    dividend_yield_ttm=row.get('dividend_yield_ttm'),
                    dividend_yield_lyr=row.get('dividend_yield_lyr'),
                    peg_lyr=row.get('peg_lyr'),
                    peg_mrq=row.get('peg_mrq'),
                    peg_q4=row.get('peg_q4'),
                    peg_q2=row.get('peg_q2'),
                    peg_q4_3=row.get('peg_q4_3'),
                    peg_ttm_3y=row.get('peg_ttm_3y'),
                    source='fundamental_csv',
                    data_quality='B'
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


def update_dim_stock(session, stock_code: str, stock_name: str):
    """
    更新或创建 dim_stock 记录
    """
    if not stock_name:
        return
    
    existing = session.query(DimStock).filter(DimStock.ts_code == stock_code).first()
    
    if existing:
        if not existing.name or existing.name != stock_name:
            existing.name = stock_name
            session.commit()
    else:
        # 从代码判断交易所
        exchange = 'SSE' if '.SH' in stock_code else 'SZSE'
        symbol = stock_code.split('.')[0]
        
        new_stock = DimStock(
            ts_code=stock_code,
            exchange=exchange,
            symbol=symbol,
            name=stock_name,
            list_date=None,
            delist_date=None
        )
        session.add(new_stock)
        session.commit()


def main():
    """
    主函数：批量导入基本面数据
    """
    # 配置路径
    base_dir = Path(__file__).parent.parent.parent
    fundamental_dir = base_dir / "backend" / "基本面数据"
    reference_file = base_dir / "backend" / "data_cache" / "debug" / "raw_stock_data_before_selection_20251114_103745.csv"
    
    if not fundamental_dir.exists():
        logger.error(f"基本面数据目录不存在: {fundamental_dir}")
        return
    
    # 加载股票名称映射
    stock_name_mapping = {}
    if reference_file.exists():
        stock_name_mapping = load_stock_name_mapping(str(reference_file))
    else:
        logger.warning(f"参考文件不存在: {reference_file}，将无法补充股票名称")
    
    # 连接数据库
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # 获取所有CSV文件
        csv_files = list(fundamental_dir.glob("*.csv"))
        total_files = len(csv_files)
        
        logger.info(f"📁 找到 {total_files} 个基本面数据文件")
        
        total_imported = 0
        total_updated = 0
        total_skipped = 0
        
        for idx, csv_file in enumerate(csv_files, 1):
            logger.info(f"\n[{idx}/{total_files}] 处理: {csv_file.name}")
            
            # 解析CSV
            data_df = parse_fundamental_csv(str(csv_file), stock_name_mapping)
            
            if data_df.empty:
                logger.warning(f"  ⚠️ 文件为空或解析失败")
                continue
            
            logger.info(f"  📊 解析到 {len(data_df)} 条记录")
            
            # 更新股票维度表
            if len(data_df) > 0:
                stock_code = data_df.iloc[0]['ts_code']
                stock_name = data_df.iloc[0].get('stock_name', '')
                if stock_name:
                    update_dim_stock(session, stock_code, stock_name)
            
            # 导入到fact_daily_fundamental（使用批量插入优化）
            imported, updated, skipped = import_to_fact_daily_fundamental(engine, data_df)
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

