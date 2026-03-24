

"""
同步交易日历表 (dim_trade_calendar)
从 Tushare 获取交易日历数据并同步到数据库

使用方法:
    # 同步未来一年的交易日历
    python backend/scripts/data_update/sync_trade_calendar.py

    # 同步指定日期范围
    python backend/scripts/data_update/sync_trade_calendar.py --start-date 2024-01-01 --end-date 2025-12-31

    # 只同步上交所
    python backend/scripts/data_update/sync_trade_calendar.py --exchange SSE

    # 只同步深交所
    python backend/scripts/data_update/sync_trade_calendar.py --exchange SZSE
"""
import sys
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import tushare as ts
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional, List
from data_warehouse.service.warehouse_service import WarehouseService
from data_warehouse.config import TUSHARE_TOKEN
from data_warehouse.models.generated_models import DimTradeCalendar
from sqlalchemy import text
import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def sync_trade_calendar(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    exchange: Optional[str] = None,
    years_ahead: int = 1
):
    """
    同步交易日历数据
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)，如果为None则使用今天
        end_date: 结束日期 (YYYY-MM-DD)，如果为None则使用今天+未来N年
        exchange: 交易所 ('SSE' 或 'SZSE')，如果为None则同步两个交易所
        years_ahead: 如果未指定end_date，同步未来N年的数据（默认1年）
    """
    try:
        # 初始化Tushare
        if not TUSHARE_TOKEN:
            logger.error("❌ TUSHARE_TOKEN 未配置，请在 config.json 或环境变量中设置")
            return False
        
        ts.set_token(TUSHARE_TOKEN)
        pro = ts.pro_api()
        logger.info("✅ Tushare Pro 初始化成功")
        
        # 确定日期范围
        today = date.today()
        if not start_date:
            start_date = today.strftime('%Y-%m-%d')
        if not end_date:
            end_date = (today + timedelta(days=365 * years_ahead)).strftime('%Y-%m-%d')
        
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        logger.info(f"📅 同步日期范围: {start_date} ~ {end_date}")
        
        # 确定要同步的交易所
        # 注意：由于表主键是 trade_date，每个日期只能有一条记录
        # 上交所和深交所在同一天都是交易日，所以只同步一个交易所即可（默认SSE）
        if exchange is None:
            exchanges = ['SSE']  # 默认只同步上交所（深交所交易日历相同）
            logger.info(f"📊 同步交易所: SSE（上交所和深交所在同一天都是交易日，只保存一条记录）")
        else:
            exchanges = [exchange]
            logger.info(f"📊 同步交易所: {exchange}")
        
        # 初始化数据库
        ws = WarehouseService()
        session = ws.get_session()
        
        try:
            total_inserted = 0
            total_updated = 0
            
            for exch in exchanges:
                logger.info(f"\n{'='*60}")
                logger.info(f"处理交易所: {exch}")
                logger.info(f"{'='*60}")
                
                # 转换日期格式为 Tushare 格式 (YYYYMMDD)
                start_date_ts = start_date.replace('-', '')
                end_date_ts = end_date.replace('-', '')
                
                # 从 Tushare 获取交易日历
                logger.info(f"📥 从 Tushare 获取交易日历数据...")
                try:
                    trade_cal_df = pro.trade_cal(
                        exchange=exch,
                        start_date=start_date_ts,
                        end_date=end_date_ts
                    )
                    
                    if trade_cal_df is None or trade_cal_df.empty:
                        logger.warning(f"⚠️ {exch} 交易所未获取到数据")
                        continue
                    
                    logger.info(f"✅ 获取到 {len(trade_cal_df)} 条记录")
                    
                except Exception as e:
                    logger.error(f"❌ 从 Tushare 获取 {exch} 交易日历失败: {e}")
                    continue
                
                # 处理数据并插入/更新数据库
                # 注意：由于 trade_date 是主键，每个日期只能有一条记录
                # 上交所和深交所在同一天都是交易日，所以只保存一条即可
                inserted = 0
                updated = 0
                
                for _, row in trade_cal_df.iterrows():
                    try:
                        # 解析日期
                        cal_date_str = str(row['cal_date'])
                        trade_date_obj = datetime.strptime(cal_date_str, '%Y%m%d').date()
                        
                        # 解析是否开市
                        is_open = bool(int(row['is_open']))
                        
                        # 检查是否已存在（不区分交易所，因为主键是 trade_date）
                        existing = session.query(DimTradeCalendar).filter(
                            DimTradeCalendar.trade_date == trade_date_obj
                        ).first()
                        
                        if existing:
                            # 更新（如果 is_open 有变化）
                            if existing.is_open != is_open:
                                existing.is_open = is_open
                                existing.exchange = exch  # 更新交易所字段（使用最新的）
                                existing.updated_at = datetime.now()
                                updated += 1
                        else:
                            # 插入
                            new_record = DimTradeCalendar(
                                trade_date=trade_date_obj,
                                is_open=is_open,
                                exchange=exch,
                                updated_at=datetime.now()
                            )
                            session.add(new_record)
                            inserted += 1
                        
                    except Exception as e:
                        logger.warning(f"⚠️ 处理日期 {row.get('cal_date')} 失败: {e}")
                        continue
                
                # 提交当前交易所的数据
                session.commit()
                logger.info(f"✅ {exch} 同步完成: 新增 {inserted} 条，更新 {updated} 条")
                
                total_inserted += inserted
                total_updated += updated
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ 交易日历同步完成!")
            logger.info(f"   总计新增: {total_inserted} 条")
            logger.info(f"   总计更新: {total_updated} 条")
            logger.info(f"{'='*60}")
            
            return True
            
        finally:
            session.close()
            
    except ImportError:
        logger.error("❌ tushare 未安装，请运行: pip install tushare")
        return False
    except Exception as e:
        logger.error(f"❌ 同步交易日历失败: {e}", exc_info=True)
        return False


def main():
    """主函数"""
    try:
        parser = argparse.ArgumentParser(description='同步交易日历表')
        parser.add_argument('--start-date', type=str, help='开始日期 (YYYY-MM-DD)，默认今天')
        parser.add_argument('--end-date', type=str, help='结束日期 (YYYY-MM-DD)，默认未来1年')
        parser.add_argument('--exchange', type=str, choices=['SSE', 'SZSE'], help='交易所 (SSE/SZSE)，默认只同步SSE')
        parser.add_argument('--years-ahead', type=int, default=1, help='如果未指定end-date，同步未来N年（默认1年）')
        
        args = parser.parse_args()
        
        logger.info("=" * 60)
        logger.info("开始同步交易日历")
        logger.info("=" * 60)
        
        success = sync_trade_calendar(
            start_date=args.start_date,
            end_date=args.end_date,
            exchange=args.exchange,
            years_ahead=args.years_ahead
        )
        
        if success:
            logger.info("✅ 同步完成")
        else:
            logger.error("❌ 同步失败")
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

