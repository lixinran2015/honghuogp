"""
增强财务数据获取：专门补全毛利率和经营现金流
使用优化后的获取逻辑
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import RawFundamental
from data_warehouse.config import DATABASE_URL
from sqlalchemy import create_engine, text
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def enhance_financial_data(limit=500, batch_size=20):
    """
    增强财务数据：补全毛利率和经营现金流
    
    Args:
        limit: 要更新的股票数量
        batch_size: 每批处理的股票数量
    """
    logger.info("=" * 60)
    logger.info(f"增强财务数据获取（目标：{limit}只股票，补全毛利率和经营现金流）")
    logger.info("=" * 60)
    
    financial_fetcher = FinancialDataFetcher()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取需要更新的股票列表（已有财务数据但缺少毛利率或经营现金流）
    session = raw_layer.get_session()
    try:
        result = session.execute(text("""
            SELECT DISTINCT ts_code
            FROM fact_fundamental
            WHERE end_date = '2025-11-17'
            AND (gross_margin IS NULL OR gross_margin = 0 OR op_cf IS NULL OR op_cf = 0)
            LIMIT :limit
        """), {'limit': limit})
        
        stock_codes = []
        for row in result:
            ts_code = row[0]
            # 转换为6位数字代码
            code = ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            if code.isdigit() and len(code) == 6:
                stock_codes.append(code)
        
        logger.info(f"✅ 找到 {len(stock_codes)} 只需要补全毛利率或经营现金流的股票")
    finally:
        session.close()
    
    if not stock_codes:
        logger.info("✅ 所有股票的财务数据都已完整，无需补全")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = datetime.strptime(today, "%Y-%m-%d").date()
    report_type = 'annual'
    
    total_updated = 0
    total_fact_count = 0
    gross_margin_count = 0
    op_cf_count = 0
    
    logger.info(f"📥 开始批量获取财务数据（每批{batch_size}只，延迟0.5秒）...")
    
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(stock_codes) + batch_size - 1) // batch_size
        
        logger.info(f"\n处理第 {batch_num}/{total_batches} 批（{len(batch)}只股票）...")
        
        batch_financial_data = {}
        for idx, code in enumerate(batch, 1):
            try:
                logger.info(f"  正在获取 {code} 的财务数据... ({idx}/{len(batch)})")
                result = financial_fetcher.get_stock_financial_data(code)
                
                if result is not None:
                    batch_financial_data[code] = result
                    has_gross = result.get('gross_margin', 0) > 0
                    has_cf = result.get('operating_cashflow', 0) != 0
                    logger.info(f"  ✅ {code}: ROE={result.get('roe_ttm', 0)*100:.2f}%, 毛利率={'有' if has_gross else '无'}, 经营现金流={'有' if has_cf else '无'}")
                else:
                    logger.warning(f"  ⚠️ {code}: 获取财务数据失败")
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"  ⚠️ 获取 {code} 财务数据失败: {e}")
                continue
        
        logger.info(f"  ✅ 第 {batch_num} 批完成，已获取 {len(batch_financial_data)} 只股票的财务数据")
        
        # 更新到PostgreSQL
        if batch_financial_data:
            logger.info(f"  📦 更新第 {batch_num} 批数据到数据库...")
            session = raw_layer.get_session()
            try:
                updated_count = 0
                batch_gross_count = 0
                batch_cf_count = 0
                
                for code, data in batch_financial_data.items():
                    try:
                        if code.startswith('6'):
                            ts_code = f"{code}.SH"
                        elif code.startswith('0') or code.startswith('3'):
                            ts_code = f"{code}.SZ"
                        else:
                            continue
                        
                        # 检查是否已有数据
                        existing = session.query(RawFundamental).filter(
                            RawFundamental.ts_code == ts_code,
                            RawFundamental.end_date == end_date,
                            RawFundamental.report_type == report_type,
                            RawFundamental.source == 'akshare_enhanced'
                        ).first()
                        
                        roe_val = float(data.get('roe_ttm', 0) or 0)
                        gross_margin_val = float(data.get('gross_margin', 0) or 0)
                        net_margin_val = float(data.get('net_margin', 0) or 0)
                        debt_ratio_val = float(data.get('debt_ratio', 0) or 0)
                        op_cf_val = float(data.get('operating_cashflow', 0) or 0)
                        total_debt_val = float(data.get('total_debt', 0) or 0)
                        total_asset_val = float(data.get('total_asset', 0) or 0)
                        
                        if gross_margin_val > 0:
                            batch_gross_count += 1
                        if op_cf_val != 0:
                            batch_cf_count += 1
                        
                        if existing:
                            # 更新现有记录（只更新缺失的字段）
                            if gross_margin_val > 0:
                                existing.gross_margin = gross_margin_val * 100 if gross_margin_val < 1 else gross_margin_val
                            if op_cf_val != 0:
                                existing.op_cf = op_cf_val
                            existing.roe = roe_val * 100 if roe_val < 1 else roe_val
                            existing.net_margin = net_margin_val * 100 if net_margin_val < 1 else net_margin_val
                            existing.debt_ratio = debt_ratio_val * 100 if debt_ratio_val < 1 else debt_ratio_val
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
                                source='akshare_enhanced',
                                raw_payload=data
                            )
                            session.add(raw_fundamental)
                            updated_count += 1
                    
                    except Exception as e:
                        logger.debug(f"  更新 {code} 财务数据失败: {e}")
                        continue
                
                session.commit()
                logger.info(f"  ✅ 成功更新 {updated_count} 只股票的财务数据到raw表")
                logger.info(f"     其中：毛利率 {batch_gross_count} 只，经营现金流 {batch_cf_count} 只")
                total_updated += updated_count
                gross_margin_count += batch_gross_count
                op_cf_count += batch_cf_count
                
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
        
        if i + batch_size < len(stock_codes):
            time.sleep(2)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 财务数据增强完成！")
    logger.info(f"   更新股票数: {total_updated} 只")
    logger.info(f"   合并到fact表: {total_fact_count} 只")
    logger.info(f"   获取到毛利率: {gross_margin_count} 只")
    logger.info(f"   获取到经营现金流: {op_cf_count} 只")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        enhance_financial_data(limit=500, batch_size=20)
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 增强失败: {e}", exc_info=True)
        sys.exit(1)

