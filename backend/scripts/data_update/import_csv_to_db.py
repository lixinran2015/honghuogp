#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将CSV股票快照数据导入到数据库

用法：
    python backend/scripts/data_update/import_csv_to_db.py --date 2025-12-02
    python backend/scripts/data_update/import_csv_to_db.py --date 2025-12-02 --batch-size 500
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd

# 添加项目根目录到路径（backend/scripts/data_update -> backend/scripts -> backend -> 项目根目录）
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from data_warehouse.models import FactDailyPriceQfq
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def import_csv_to_db(date: str, batch_size: int = 500) -> bool:
    """
    将CSV股票数据导入到数据库
    
    Args:
        date: 日期（YYYY-MM-DD）
        batch_size: 批量插入大小
    
    Returns:
        是否成功
    """
    try:
        # 1. 读取CSV文件
        csv_path = project_root / 'backend' / 'data_warehouse' / 'stocks' / f'{date}.csv'
        
        if not csv_path.exists():
            logger.error(f"❌ CSV文件不存在: {csv_path}")
            return False
        
        logger.info(f"📖 读取CSV文件: {csv_path}")
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        logger.info(f"✅ 读取到 {len(df)} 条数据")
        
        # 2. 数据清洗和转换
        logger.info("🔄 开始数据清洗...")
        
        # 列名映射：中文 -> 英文
        column_mapping = {
            '代码': 'code',
            '名称': 'name',
            '最新价': 'close',
            '涨跌幅': 'pct_chg',
            '涨跌额': 'change',
            '成交量': 'volume',
            '成交额': 'amount',
            '换手率': 'turnover_rate',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '昨收': 'pre_close'
        }
        
        df = df.rename(columns=column_mapping)
        
        # 过滤：只保留A股（6位数字代码）
        df['code'] = df['code'].astype(str)
        df = df[df['code'].str.match(r'^\d{6}$')].copy()
        logger.info(f"✅ 过滤后A股数量: {len(df)} 只")
        
        # 转换为ts_code格式（添加.SH/.SZ后缀）
        def convert_to_ts_code(code: str) -> str:
            code = str(code).strip()
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith(('0', '3')):
                return f"{code}.SZ"
            elif code.startswith(('8', '4')):
                return f"{code}.BJ"
            else:
                return f"{code}.SZ"
        
        df['ts_code'] = df['code'].apply(convert_to_ts_code)
        
        # 转换日期格式
        trade_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        # 3. 连接数据库
        logger.info("🔌 连接数据库...")
        warehouse = PostgresWarehouse()
        
        if not warehouse.warehouse_service:
            logger.error("❌ 数据库服务未初始化")
            return False
        
        session = warehouse.warehouse_service.get_session()
        
        try:
            # 4. 删除当天的旧数据（如果存在）
            logger.info(f"🗑️ 删除 {date} 的旧数据...")
            delete_result = session.execute(text("""
                DELETE FROM fact_daily_price_qfq 
                WHERE trade_date = :trade_date
            """), {'trade_date': trade_date})
            session.commit()
            logger.info(f"✅ 删除了 {delete_result.rowcount} 条旧数据")
            
            # 5. 批量插入新数据
            logger.info(f"📥 开始批量插入数据（批次大小: {batch_size}）...")
            inserted_count = 0
            failed_count = 0
            
            for i in range(0, len(df), batch_size):
                batch_df = df.iloc[i:i+batch_size]
                batch_num = i // batch_size + 1
                total_batches = (len(df) + batch_size - 1) // batch_size
                
                logger.info(f"  📦 处理批次 {batch_num}/{total_batches} ({len(batch_df)} 条)...")
                
                for idx, row in batch_df.iterrows():
                    try:
                        # 验证必要字段
                        if pd.isna(row['close']) or pd.isna(row['open']) or pd.isna(row['high']) or pd.isna(row['low']):
                            logger.debug(f"  ⚠️ 跳过 {row['ts_code']}: 缺少价格数据")
                            failed_count += 1
                            continue
                        
                        # 验证价格数据是否为正数
                        if float(row['close']) <= 0 or float(row['open']) <= 0:
                            logger.debug(f"  ⚠️ 跳过 {row['ts_code']}: 价格数据异常（close={row['close']}, open={row['open']}）")
                            failed_count += 1
                            continue
                        
                        record = FactDailyPriceQfq(
                            ts_code=row['ts_code'],
                            trade_date=trade_date,
                            open=float(row['open']),
                            high=float(row['high']),
                            low=float(row['low']),
                            close=float(row['close']),
                            pre_close=float(row['pre_close']) if pd.notna(row['pre_close']) else None,
                            change_pct=float(row['pct_chg']) if pd.notna(row.get('pct_chg')) else None,
                            vol=float(row['volume']) if pd.notna(row.get('volume')) else None,
                            amount=float(row['amount']) if pd.notna(row.get('amount')) else None,
                            turnover_rate=float(row['turnover_rate']) if pd.notna(row.get('turnover_rate')) else None,
                            source='csv_import'
                        )
                        session.add(record)
                        inserted_count += 1
                        
                        # 每插入100条打印一次进度
                        if inserted_count % 100 == 0:
                            logger.debug(f"    已插入 {inserted_count} 条...")
                        
                    except Exception as e:
                        # 记录第一个失败的详细错误
                        if failed_count == 0:
                            logger.error(f"  ❌ 第一条失败记录详情: {row.get('ts_code', 'unknown')}")
                            logger.error(f"     错误信息: {e}", exc_info=True)
                        else:
                            logger.debug(f"  ⚠️ 插入 {row.get('ts_code', 'unknown')} 失败: {e}")
                        failed_count += 1
                        continue
                
                # 每个批次提交一次
                session.commit()
                logger.info(f"  ✅ 批次 {batch_num} 提交成功")
            
            # 查询实际插入的数据量
            actual_count = session.execute(text("""
                SELECT COUNT(*) 
                FROM fact_daily_price_qfq 
                WHERE trade_date = :trade_date AND source = 'csv_import'
            """), {'trade_date': trade_date}).scalar()
            
            logger.info("=" * 60)
            logger.info(f"🎉 导入完成！")
            logger.info(f"   日期: {date}")
            logger.info(f"   尝试插入: {inserted_count} 条")
            logger.info(f"   数据库实际: {actual_count} 条")
            logger.info(f"   跳过/失败: {failed_count} 条")
            logger.info(f"   CSV总计: {len(df)} 条")
            logger.info("=" * 60)
            
            if actual_count > 0:
                logger.info(f"✅ 成功导入 {actual_count} 条数据到数据库")
                return True
            else:
                logger.warning(f"⚠️ 未导入任何数据，请检查CSV格式或数据库连接")
                return False
            
            return True
            
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f"❌ 导入失败: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='将CSV股票数据导入到数据库')
    parser.add_argument(
        '--date',
        type=str,
        required=True,
        help='日期（格式：YYYY-MM-DD），如 2025-12-02'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=500,
        help='批量插入大小（默认500）'
    )
    
    args = parser.parse_args()
    
    # 验证日期格式
    try:
        datetime.strptime(args.date, '%Y-%m-%d')
    except ValueError:
        logger.error("❌ 日期格式错误，应为 YYYY-MM-DD")
        sys.exit(1)
    
    success = import_csv_to_db(args.date, args.batch_size)
    sys.exit(0 if success else 1)

