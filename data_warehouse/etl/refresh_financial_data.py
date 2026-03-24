"""
重新获取并更新财务数据（包含毛利率、负债率、经营现金流）
使用多数据源补齐缺失的财务指标
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import DimStock
from data_warehouse.models import RawFundamental
from data_warehouse.models import FactFundamental
from sqlalchemy.orm import Session
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def refresh_financial_data(limit=200, batch_size=20):
    """
    重新获取财务数据并更新到PostgreSQL
    
    Args:
        limit: 要更新的股票数量
        batch_size: 每批处理的股票数量
    """
    logger.info("=" * 60)
    logger.info(f"开始重新获取财务数据（目标：{limit}只股票）")
    logger.info("=" * 60)
    
    # 初始化服务
    financial_fetcher = FinancialDataFetcher()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取股票列表（从dim_stock表）
    session = raw_layer.get_session()
    try:
        stocks = session.query(DimStock).filter(
            DimStock.exchange.in_(['SSE', 'SZSE'])  # 只获取A股
        ).limit(limit).all()
        
        stock_codes = []
        for stock in stocks:
            # 转换为6位数字代码
            code = stock.symbol
            if code.isdigit() and len(code) == 6:
                stock_codes.append(code)
        
        logger.info(f"✅ 从dim_stock表提取了 {len(stock_codes)} 只A股代码")
    finally:
        session.close()
    
    if not stock_codes:
        logger.error("❌ 没有股票代码，无法更新财务数据")
        return
    
    # 获取今日日期
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = datetime.strptime(today, "%Y-%m-%d").date()
    report_type = 'annual'
    
    # 批量获取财务数据，每批完成后立即更新到数据库
    total = len(stock_codes)
    total_updated = 0
    total_fact_count = 0
    
    logger.info(f"📥 开始批量获取财务数据（每批{batch_size}只，延迟0.5秒，每批完成后立即更新数据库）...")
    
    for i in range(0, total, batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        logger.info(f"\n处理第 {batch_num}/{total_batches} 批（{len(batch)}只股票）...")
        
        # 获取本批数据
        batch_financial_data = {}
        for idx, code in enumerate(batch, 1):
            try:
                # 获取财务数据（会尝试Tushare和akshare，包含毛利率、负债率、经营现金流）
                result = financial_fetcher.get_stock_financial_data(code)
                
                if result is not None:
                    batch_financial_data[code] = result
                    # 检查是否有真实数据
                    has_data = (
                        result.get('roe_ttm', 0) > 0 or
                        result.get('gross_margin', 0) > 0 or
                        result.get('net_margin', 0) > 0 or
                        result.get('debt_ratio', 0) > 0 or
                        result.get('operating_cashflow', 0) != 0
                    )
                    if has_data and idx % 5 == 0:
                        logger.info(f"  进度: {idx}/{len(batch)} ({idx*100//len(batch)}%) - {code}: ROE={result.get('roe_ttm', 0)*100:.2f}%, 毛利率={result.get('gross_margin', 0)*100:.2f}%, 负债率={result.get('debt_ratio', 0)*100:.2f}%")
                else:
                    logger.debug(f"  ⚠️ {code} 财务数据获取失败")
                
                # 延迟，避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"  ⚠️ 获取 {code} 财务数据失败: {e}")
                continue
        
        logger.info(f"  ✅ 第 {batch_num} 批完成，已获取 {len(batch_financial_data)} 只股票的财务数据")
        
        # 立即更新本批数据到PostgreSQL
        if batch_financial_data:
            logger.info(f"  📦 更新第 {batch_num} 批数据到数据库...")
            session = raw_layer.get_session()
            try:
                updated_count = 0
                for code, data in batch_financial_data.items():
                    try:
                        # 确定交易所和ts_code
                        if code.startswith('6'):
                            ts_code = f"{code}.SH"
                        elif code.startswith('0') or code.startswith('3'):
                            ts_code = f"{code}.SZ"
                        else:
                            continue
                        
                        # 检查是否已存在
                        existing = session.query(RawFundamental).filter(
                            RawFundamental.ts_code == ts_code,
                            RawFundamental.end_date == end_date,
                            RawFundamental.report_type == report_type,
                            RawFundamental.source == 'akshare_refresh'
                        ).first()
                        
                        # 准备数据
                        roe_val = float(data.get('roe_ttm', 0) or 0)
                        gross_margin_val = float(data.get('gross_margin', 0) or 0)
                        net_margin_val = float(data.get('net_margin', 0) or 0)
                        debt_ratio_val = float(data.get('debt_ratio', 0) or 0)
                        op_cf_val = float(data.get('operating_cashflow', 0) or 0)
                        total_debt_val = float(data.get('total_debt', 0) or 0)
                        total_asset_val = float(data.get('total_asset', 0) or 0)
                        
                        if existing:
                            # 更新现有记录
                            existing.roe = roe_val * 100 if roe_val < 1 else roe_val
                            existing.gross_margin = gross_margin_val * 100 if gross_margin_val < 1 else gross_margin_val
                            existing.net_margin = net_margin_val * 100 if net_margin_val < 1 else net_margin_val
                            existing.debt_ratio = debt_ratio_val * 100 if debt_ratio_val < 1 else debt_ratio_val
                            existing.op_cf = op_cf_val
                            existing.total_debt = total_debt_val
                            existing.total_asset = total_asset_val
                            existing.raw_payload = data
                            updated_count += 1
                        else:
                            # 创建新记录
                            raw_fundamental = RawFundamental(
                                ts_code=ts_code,
                                end_date=end_date,
                                report_type=report_type,
                                roe=roe_val * 100 if roe_val < 1 else roe_val,
                                gross_margin=gross_margin_val * 100 if gross_margin_val < 1 else gross_margin_val,
                                net_margin=net_margin_val * 100 if net_margin_val < 1 else net_margin_val,
                                debt_ratio=debt_ratio_val * 100 if debt_ratio_val < 1 else debt_ratio_val,
                                op_cf=op_cf_val,
                                total_debt=total_debt_val,
                                total_asset=total_asset_val,
                                source='akshare_refresh',
                                raw_payload=data
                            )
                            session.add(raw_fundamental)
                            updated_count += 1
                    
                    except Exception as e:
                        logger.debug(f"  更新 {code} 财务数据失败: {e}")
                        continue
        
                session.commit()
                logger.info(f"  ✅ 成功更新 {updated_count} 只股票的财务数据到raw表")
                total_updated += updated_count
                
                # 合并到fact表
                fact_count = 0
                for code, data in batch_financial_data.items():
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
                
                logger.info(f"  ✅ 合并完成，共 {fact_count} 只股票")
                total_fact_count += fact_count
                
            except Exception as e:
                session.rollback()
                logger.error(f"  ❌ 更新第 {batch_num} 批数据失败: {e}", exc_info=True)
            finally:
                session.close()
        
        # 批次间延迟
        if i + batch_size < total:
            time.sleep(2)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 财务数据更新完成！")
    logger.info(f"   更新股票数: {total_updated} 只")
    logger.info(f"   合并到fact表: {total_fact_count} 只")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        # 更新200只股票的财务数据
        refresh_financial_data(limit=200, batch_size=20)
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 更新失败: {e}", exc_info=True)
        sys.exit(1)

