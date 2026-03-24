"""
批量初始化财务数据并迁移到PostgreSQL
使用多数据源（akshare + Tushare）补齐财务数据
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from backend.services.data.data_warehouse import DataWarehouse
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import DimStock
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def init_and_migrate_financial_data(limit=200, batch_size=50):
    """
    初始化财务数据并迁移到PostgreSQL
    
    Args:
        limit: 要初始化的股票数量
        batch_size: 每批处理的股票数量
    """
    logger.info("=" * 60)
    logger.info(f"开始批量初始化财务数据（目标：{limit}只股票）")
    logger.info("=" * 60)
    
    # 初始化服务
    file_warehouse = DataWarehouse()
    financial_fetcher = FinancialDataFetcher()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取股票列表（从最新股票数据中）
    latest_date = file_warehouse.get_latest_stocks_date()
    if not latest_date:
        logger.error("❌ 没有股票数据，无法初始化财务数据")
        return
    
    stock_data = file_warehouse.load_stocks_data(latest_date)
    if stock_data is None or stock_data.empty:
        logger.error(f"❌ {latest_date} 的股票数据为空")
        return
    
    logger.info(f"📊 从 {latest_date} 的股票数据中提取股票代码...")
    
    # 提取A股代码
    stock_codes = []
    for _, row in stock_data.iterrows():
        code = str(row.get('code', row.get('代码', ''))).strip()
        if code:
            code_clean = code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            if len(code_clean) > 6:
                code_clean = code_clean[-6:]
            
            if code_clean.isdigit() and len(code_clean) == 6:
                # 只保留A股（排除北交所）
                if code_clean.startswith('6') or code_clean.startswith('0') or code_clean.startswith('3'):
                    stock_codes.append(code_clean)
        
        if len(stock_codes) >= limit:
            break
    
    logger.info(f"✅ 提取了 {len(stock_codes)} 只A股代码")
    
    # 获取今日日期
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 批量获取财务数据
    financial_data = {}
    total = len(stock_codes)
    
    logger.info(f"📥 开始批量获取财务数据（每批{batch_size}只，延迟0.3秒）...")
    
    for i in range(0, total, batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        logger.info(f"\n处理第 {batch_num}/{total_batches} 批（{len(batch)}只股票）...")
        
        for idx, code in enumerate(batch, 1):
            try:
                # 获取财务数据（会尝试Tushare和akshare）
                result = financial_fetcher.get_stock_financial_data(code)
                
                if result is not None:
                    financial_data[code] = result
                    if idx % 10 == 0:
                        logger.info(f"  进度: {idx}/{len(batch)} ({idx*100//len(batch)}%)")
                else:
                    logger.debug(f"  ⚠️ {code} 财务数据获取失败")
                
                # 延迟，避免请求过快
                time.sleep(0.3)
                
            except Exception as e:
                logger.debug(f"  ⚠️ 获取 {code} 财务数据失败: {e}")
                continue
        
        logger.info(f"  ✅ 第 {batch_num} 批完成，已获取 {len(financial_data)} 只股票的财务数据")
        
        # 批次间延迟
        if i + batch_size < total:
            time.sleep(1)
    
    logger.info(f"\n✅ 共获取 {len(financial_data)} 只股票的财务数据")
    
    if not financial_data:
        logger.warning("⚠️ 没有获取到财务数据")
        return
    
    # 保存到文件数据仓库
    logger.info(f"\n💾 保存财务数据到文件数据仓库...")
    success = file_warehouse.save_financial_data(today, financial_data)
    if success:
        logger.info(f"✅ 已保存到文件数据仓库: {today}")
    else:
        logger.error("❌ 保存到文件数据仓库失败")
    
    # 迁移到PostgreSQL
    logger.info(f"\n📦 迁移财务数据到PostgreSQL数据仓库...")
    session = raw_layer.get_session()
    try:
        end_date = datetime.strptime(today, "%Y-%m-%d").date()
        report_type = 'annual'
        
        migrated_count = 0
        for code, data in financial_data.items():
            try:
                # 确定交易所和ts_code
                if code.startswith('6'):
                    ts_code = f"{code}.SH"
                elif code.startswith('0') or code.startswith('3'):
                    ts_code = f"{code}.SZ"
                else:
                    continue
                
                # 保存到raw_fundamental
                from data_warehouse.models import RawFundamental
                
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
                        roe=float(data.get('roe_ttm', 0) or 0) / 100 if data.get('roe_ttm', 0) > 1 else float(data.get('roe_ttm', 0) or 0),
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
                logger.debug(f"  迁移 {code} 财务数据失败: {e}")
                continue
        
        session.commit()
        logger.info(f"✅ 成功迁移 {migrated_count} 只股票的财务数据到raw表")
        
        # 合并到fact表
        logger.info(f"🔄 合并到fact_fundamental表...")
        fact_count = 0
        for code, data in financial_data.items():
            try:
                if code.startswith('6'):
                    ts_code = f"{code}.SH"
                elif code.startswith('0') or code.startswith('3'):
                    ts_code = f"{code}.SZ"
                else:
                    continue
                
                fact_data = clean_layer.merge_fundamental(ts_code, end_date, report_type)
                if fact_data:
                    clean_layer.save_fact_fundamental(fact_data)
                    fact_count += 1
            except Exception as e:
                logger.debug(f"  合并 {code} 财务数据失败: {e}")
                continue
        
        logger.info(f"✅ 合并完成，共 {fact_count} 只股票")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 迁移财务数据失败: {e}", exc_info=True)
    finally:
        session.close()
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 财务数据初始化和迁移完成！")
    logger.info(f"   文件数据仓库: {len(financial_data)} 只股票")
    logger.info(f"   PostgreSQL数据仓库: {fact_count} 只股票")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        # 初始化200只股票的财务数据
        init_and_migrate_financial_data(limit=200, batch_size=50)
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}", exc_info=True)
        sys.exit(1)

