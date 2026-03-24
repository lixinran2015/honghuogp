"""
将文件数据仓库的数据迁移到PostgreSQL数据仓库
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from backend.services.data.data_warehouse import DataWarehouse
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import DimStock
from data_warehouse.models import FactDailyPrice
from data_warehouse.models import FactFundamental
from sqlalchemy.orm import Session
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def migrate_stocks_data():
    """迁移股票数据"""
    logger.info("=" * 60)
    logger.info("开始迁移股票数据到PostgreSQL数据仓库")
    logger.info("=" * 60)
    
    # 初始化数据仓库
    file_warehouse = DataWarehouse()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取所有可用的股票数据日期
    stocks_dir = file_warehouse.stocks_dir
    dates = []
    for file in stocks_dir.glob("*.csv"):
        date_str = file.stem
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            continue
    
    dates.sort(reverse=True)  # 从最新日期开始
    logger.info(f"找到 {len(dates)} 个日期的股票数据")
    
    total_migrated = 0
    for date_str in dates:
        logger.info(f"\n处理日期: {date_str}")
        
        # 从文件数据仓库加载数据
        stock_data = file_warehouse.load_stocks_data(date_str)
        if stock_data is None or stock_data.empty:
            logger.warning(f"  ⚠️ {date_str} 的股票数据为空，跳过")
            continue
        
        logger.info(f"  📊 加载了 {len(stock_data)} 只股票")
        
        # 转换为PostgreSQL格式并保存
        migrated_count = 0
        session = raw_layer.get_session()
        try:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            for idx, row in stock_data.iterrows():
                try:
                    # 获取股票代码和名称
                    code = str(row.get('code', row.get('代码', ''))).strip()
                    name = str(row.get('name', row.get('名称', ''))).strip()
                    
                    if not code:
                        continue
                    
                    # 标准化代码
                    code_clean = code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    if len(code_clean) > 6:
                        code_clean = code_clean[-6:]
                    
                    if not code_clean.isdigit() or len(code_clean) != 6:
                        continue
                    
                    # 确定交易所
                    if code_clean.startswith('6'):
                        exchange = 'SSE'
                        ts_code = f"{code_clean}.SH"
                    elif code_clean.startswith('0') or code_clean.startswith('3'):
                        exchange = 'SZSE'
                        ts_code = f"{code_clean}.SZ"
                    elif code_clean.startswith('8') or code_clean.startswith('4'):
                        exchange = 'BSE'
                        ts_code = f"{code_clean}.BJ"
                    else:
                        continue
                    
                    # 更新或创建股票维度表
                    stock = session.query(DimStock).filter(DimStock.ts_code == ts_code).first()
                    if not stock:
                        stock = DimStock(
                            ts_code=ts_code,
                            exchange=exchange,
                            symbol=code_clean,
                            name=name if name else code_clean
                        )
                        session.add(stock)
                    else:
                        if name:
                            stock.name = name
                    
                    # 保存日线数据到raw_daily_price
                    from data_warehouse.models import RawDailyPrice
                    
                    # 检查是否已存在
                    existing = session.query(RawDailyPrice).filter(
                        RawDailyPrice.ts_code == ts_code,
                        RawDailyPrice.trade_date == trade_date,
                        RawDailyPrice.source == 'file_warehouse'
                    ).first()
                    
                    if not existing:
                        raw_price = RawDailyPrice(
                            ts_code=ts_code,
                            trade_date=trade_date,
                            open=float(row.get('open', row.get('开盘', row.get('今开', 0))) or 0),
                            high=float(row.get('high', row.get('最高', 0)) or 0),
                            low=float(row.get('low', row.get('最低', 0)) or 0),
                            close=float(row.get('lastPrice', row.get('最新价', row.get('当前价', 0))) or 0),
                            pre_close=float(row.get('pre_close', row.get('昨收', 0)) or 0),
                            vol=float(row.get('volume', row.get('成交量', 0)) or 0),
                            amount=float(row.get('amount', row.get('成交额', 0)) or 0),
                            turnover_rate=float(row.get('turnover_rate', row.get('换手率', 0)) or 0),
                            source='file_warehouse',
                            raw_payload={}
                        )
                        session.add(raw_price)
                        migrated_count += 1
                
                except Exception as e:
                    logger.debug(f"  处理股票 {code} 失败: {e}")
                    continue
            
            session.commit()
            logger.info(f"  ✅ 成功迁移 {migrated_count} 只股票的日线数据到raw表")
            total_migrated += migrated_count
            
            # 合并到fact表（为每只股票调用合并方法）
            logger.info(f"  🔄 合并到fact_daily_price表...")
            fact_count = 0
            for idx, row in stock_data.iterrows():
                try:
                    code = str(row.get('code', row.get('代码', ''))).strip()
                    if not code:
                        continue
                    
                    code_clean = code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    if len(code_clean) > 6:
                        code_clean = code_clean[-6:]
                    
                    if not code_clean.isdigit() or len(code_clean) != 6:
                        continue
                    
                    if code_clean.startswith('6'):
                        ts_code = f"{code_clean}.SH"
                    elif code_clean.startswith('0') or code_clean.startswith('3'):
                        ts_code = f"{code_clean}.SZ"
                    elif code_clean.startswith('8') or code_clean.startswith('4'):
                        ts_code = f"{code_clean}.BJ"
                    else:
                        continue
                    
                    # 合并数据
                    fact_data = clean_layer.merge_daily_prices(ts_code, trade_date)
                    if fact_data:
                        clean_layer.save_fact_daily_price(fact_data)
                        fact_count += 1
                except Exception as e:
                    logger.debug(f"  合并股票 {code} 失败: {e}")
                    continue
            
            logger.info(f"  ✅ 合并完成，共 {fact_count} 只股票")
            
        except Exception as e:
            session.rollback()
            logger.error(f"  ❌ 迁移 {date_str} 的数据失败: {e}", exc_info=True)
        finally:
            session.close()
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ 股票数据迁移完成，共迁移 {total_migrated} 条记录")
    logger.info(f"{'=' * 60}")


def migrate_financial_data():
    """迁移财务数据"""
    logger.info("\n" + "=" * 60)
    logger.info("开始迁移财务数据到PostgreSQL数据仓库")
    logger.info("=" * 60)
    
    # 初始化数据仓库
    file_warehouse = DataWarehouse()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取所有可用的财务数据日期
    financial_dir = file_warehouse.financial_dir
    dates = []
    for file in financial_dir.glob("*.json"):
        date_str = file.stem
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            continue
    
    dates.sort(reverse=True)  # 从最新日期开始
    logger.info(f"找到 {len(dates)} 个日期的财务数据")
    
    total_migrated = 0
    for date_str in dates:
        logger.info(f"\n处理日期: {date_str}")
        
        # 从文件数据仓库加载数据
        financial_data = file_warehouse.load_financial_data(date_str)
        if financial_data is None or len(financial_data) == 0:
            logger.warning(f"  ⚠️ {date_str} 的财务数据为空，跳过")
            continue
        
        logger.info(f"  📊 加载了 {len(financial_data)} 只股票的财务数据")
        
        # 转换为PostgreSQL格式并保存
        migrated_count = 0
        session = raw_layer.get_session()
        try:
            # 财务数据使用报告期（这里用数据日期作为报告期）
            end_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            report_type = 'annual'  # 默认年度报告
            
            for code, data in financial_data.items():
                try:
                    # 标准化代码
                    code_clean = str(code).replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    if len(code_clean) > 6:
                        code_clean = code_clean[-6:]
                    
                    if not code_clean.isdigit() or len(code_clean) != 6:
                        continue
                    
                    # 确定交易所和ts_code
                    if code_clean.startswith('6'):
                        ts_code = f"{code_clean}.SH"
                    elif code_clean.startswith('0') or code_clean.startswith('3'):
                        ts_code = f"{code_clean}.SZ"
                    elif code_clean.startswith('8') or code_clean.startswith('4'):
                        ts_code = f"{code_clean}.BJ"
                    else:
                        continue
                    
                    # 保存财务数据到raw_fundamental
                    from data_warehouse.models import RawFundamental
                    
                    # 检查是否已存在
                    existing = session.query(RawFundamental).filter(
                        RawFundamental.ts_code == ts_code,
                        RawFundamental.end_date == end_date,
                        RawFundamental.report_type == report_type,
                        RawFundamental.source == 'file_warehouse'
                    ).first()
                    
                    if not existing:
                        raw_fundamental = RawFundamental(
                            ts_code=ts_code,
                            end_date=end_date,
                            report_type=report_type,
                            roe=float(data.get('roe_ttm', 0) or 0),
                            net_margin=float(data.get('net_margin', 0) or 0),
                            gross_margin=float(data.get('gross_margin', 0) or 0),
                            op_cf=float(data.get('operating_cashflow', 0) or 0),
                            total_debt=float(data.get('total_debt', 0) or 0),
                            total_asset=float(data.get('total_asset', 0) or 0),
                            source='file_warehouse',
                            raw_payload=data
                        )
                        session.add(raw_fundamental)
                        migrated_count += 1
                
                except Exception as e:
                    logger.debug(f"  处理股票 {code} 财务数据失败: {e}")
                    continue
            
            session.commit()
            logger.info(f"  ✅ 成功迁移 {migrated_count} 只股票的财务数据到raw表")
            total_migrated += migrated_count
            
            # 合并到fact表（为每只股票调用合并方法）
            logger.info(f"  🔄 合并到fact_fundamental表...")
            fact_count = 0
            for code, data in financial_data.items():
                try:
                    code_clean = str(code).replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                    if len(code_clean) > 6:
                        code_clean = code_clean[-6:]
                    
                    if not code_clean.isdigit() or len(code_clean) != 6:
                        continue
                    
                    if code_clean.startswith('6'):
                        ts_code = f"{code_clean}.SH"
                    elif code_clean.startswith('0') or code_clean.startswith('3'):
                        ts_code = f"{code_clean}.SZ"
                    elif code_clean.startswith('8') or code_clean.startswith('4'):
                        ts_code = f"{code_clean}.BJ"
                    else:
                        continue
                    
                    # 合并数据
                    fact_data = clean_layer.merge_fundamental(ts_code, end_date, report_type)
                    if fact_data:
                        clean_layer.save_fact_fundamental(fact_data)
                        fact_count += 1
                except Exception as e:
                    logger.debug(f"  合并股票 {code} 财务数据失败: {e}")
                    continue
            
            logger.info(f"  ✅ 合并完成，共 {fact_count} 只股票")
            
        except Exception as e:
            session.rollback()
            logger.error(f"  ❌ 迁移 {date_str} 的财务数据失败: {e}", exc_info=True)
        finally:
            session.close()
    
    logger.info(f"\n{'=' * 60}")
    logger.info(f"✅ 财务数据迁移完成，共迁移 {total_migrated} 条记录")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    try:
        # 迁移股票数据
        migrate_stocks_data()
        
        # 迁移财务数据
        migrate_financial_data()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 数据迁移全部完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 数据迁移失败: {e}", exc_info=True)
        sys.exit(1)

