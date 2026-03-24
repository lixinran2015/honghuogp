"""
补全数据仓库的基础数据指标
1. 股票日线数据（包含换手率）
2. 财务数据（毛利率、负债率、经营现金流）
3. 确保数据完整性
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date, timedelta
from akshare_safe_wrapper import fetch_realtime_a_stock_easy, fetch_today_closing_data_akshare
from backend.services.data.financial_data_fetcher import FinancialDataFetcher
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import DimStock
from data_warehouse.models import RawDailyPrice
from data_warehouse.models import RawFundamental
from data_warehouse.config import DATABASE_URL
from sqlalchemy import create_engine, text
import time
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_data_completeness():
    """检查数据完整性"""
    logger.info("=" * 60)
    logger.info("检查数据仓库完整性")
    logger.info("=" * 60)
    
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # 检查股票数据
        result = conn.execute(text("""
            SELECT 
                COUNT(DISTINCT ts_code) as stock_count,
                COUNT(*) as total_records,
                COUNT(CASE WHEN turnover_rate IS NOT NULL AND turnover_rate > 0 THEN 1 END) as turnover_count
            FROM fact_daily_price
        """))
        row = result.fetchone()
        logger.info(f"\n股票日线数据:")
        logger.info(f"  股票数量: {row[0]}")
        logger.info(f"  总记录数: {row[1]}")
        logger.info(f"  有换手率数据: {row[2]} 条 ({row[2]*100//row[1] if row[1] > 0 else 0}%)")
        
        # 检查财务数据
        result = conn.execute(text("""
            SELECT 
                COUNT(DISTINCT ts_code) as stock_count,
                COUNT(*) as total_records,
                COUNT(CASE WHEN debt_ratio IS NOT NULL AND debt_ratio > 0 THEN 1 END) as debt_ratio_count,
                COUNT(CASE WHEN gross_margin IS NOT NULL AND gross_margin > 0 THEN 1 END) as gross_margin_count,
                COUNT(CASE WHEN op_cf IS NOT NULL AND op_cf != 0 THEN 1 END) as op_cf_count
            FROM fact_fundamental
        """))
        row = result.fetchone()
        logger.info(f"\n财务数据:")
        logger.info(f"  股票数量: {row[0]}")
        logger.info(f"  总记录数: {row[1]}")
        logger.info(f"  有负债率数据: {row[2]} 条 ({row[2]*100//row[1] if row[1] > 0 else 0}%)")
        logger.info(f"  有毛利率数据: {row[3]} 条 ({row[3]*100//row[1] if row[1] > 0 else 0}%)")
        logger.info(f"  有经营现金流数据: {row[4]} 条 ({row[4]*100//row[1] if row[1] > 0 else 0}%)")
    
    logger.info("=" * 60)


def complete_stocks_data(target_date: str = None, use_akshare_history: bool = True):
    """
    补全股票日线数据（包含换手率）
    
    Args:
        target_date: 目标日期（YYYY-MM-DD），如果为None则使用今天
        use_akshare_history: 如果easyquotation失败，是否使用akshare历史数据
    """
    logger.info("=" * 60)
    logger.info("补全股票日线数据（包含换手率）")
    logger.info("=" * 60)
    
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    trade_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取股票列表
    session = raw_layer.get_session()
    try:
        stocks = session.query(DimStock).filter(
            DimStock.exchange.in_(['SSE', 'SZSE'])
        ).all()
        stock_codes = [stock.symbol for stock in stocks if stock.symbol.isdigit() and len(stock.symbol) == 6]
        logger.info(f"✅ 获取到 {len(stock_codes)} 只A股代码")
    finally:
        session.close()
    
    # 尝试使用easyquotation获取数据（包含换手率）
    logger.info(f"📥 尝试使用easyquotation获取股票数据（包含换手率）...")
    df = None
    try:
        df = fetch_realtime_a_stock_easy(cache=False, force_refresh=True)
        if df is not None and not df.empty and '换手率' in df.columns:
            valid_turnover = (df['换手率'] > 0).sum()
            logger.info(f"✅ 使用easyquotation获取到 {len(df)} 只股票，{valid_turnover} 只有换手率数据")
        else:
            logger.warning("⚠️ easyquotation未返回有效数据，尝试akshare...")
            df = None
    except Exception as e:
        logger.warning(f"⚠️ easyquotation获取失败: {e}，尝试akshare...")
        df = None
    
    # 如果easyquotation失败，使用akshare
    if df is None or df.empty:
        if use_akshare_history:
            logger.info("📥 使用akshare获取股票数据...")
            try:
                df = fetch_today_closing_data_akshare(cache=False)
                if df is not None and not df.empty:
                    logger.info(f"✅ 使用akshare获取到 {len(df)} 只股票（可能没有换手率）")
                else:
                    logger.error("❌ 无法获取股票数据")
                    return
            except Exception as e:
                logger.error(f"❌ 获取股票数据失败: {e}")
                return
        else:
            logger.error("❌ 无法获取股票数据")
            return
    
    # 更新到PostgreSQL
    logger.info(f"\n📦 更新股票数据到PostgreSQL...")
    session = raw_layer.get_session()
    try:
        updated_count = 0
        for idx, row in df.iterrows():
            try:
                code = str(row.get('代码', row.get('code', ''))).strip()
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
                else:
                    continue
                
                # 获取换手率
                turnover_rate = float(row.get('换手率', row.get('turnover_rate', 0)) or 0)
                
                # 保存到raw_daily_price
                existing = session.query(RawDailyPrice).filter(
                    RawDailyPrice.ts_code == ts_code,
                    RawDailyPrice.trade_date == trade_date,
                    RawDailyPrice.source == 'easyquotation' if turnover_rate > 0 else 'akshare'
                ).first()
                
                if existing:
                    existing.turnover_rate = turnover_rate
                    existing.open = float(row.get('今开', row.get('open', 0)) or 0)
                    existing.high = float(row.get('最高', row.get('high', 0)) or 0)
                    existing.low = float(row.get('最低', row.get('low', 0)) or 0)
                    existing.close = float(row.get('最新价', row.get('当前价', row.get('lastPrice', 0))) or 0)
                    existing.pre_close = float(row.get('昨收', row.get('pre_close', 0)) or 0)
                    existing.vol = float(row.get('成交量', row.get('volume', 0)) or 0)
                    existing.amount = float(row.get('成交额', row.get('amount', 0)) or 0)
                    updated_count += 1
                else:
                    raw_price = RawDailyPrice(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        open=float(row.get('今开', row.get('open', 0)) or 0),
                        high=float(row.get('最高', row.get('high', 0)) or 0),
                        low=float(row.get('最低', row.get('low', 0)) or 0),
                        close=float(row.get('最新价', row.get('当前价', row.get('lastPrice', 0))) or 0),
                        pre_close=float(row.get('昨收', row.get('pre_close', 0)) or 0),
                        vol=float(row.get('成交量', row.get('volume', 0)) or 0),
                        amount=float(row.get('成交额', row.get('amount', 0)) or 0),
                        turnover_rate=turnover_rate,
                        source='easyquotation' if turnover_rate > 0 else 'akshare',
                        raw_payload=row.to_dict()
                    )
                    session.add(raw_price)
                    updated_count += 1
            
            except Exception as e:
                logger.debug(f"  处理股票 {code} 失败: {e}")
                continue
        
        session.commit()
        logger.info(f"✅ 成功更新 {updated_count} 只股票的日线数据到raw表")
        
        # 合并到fact表
        logger.info(f"🔄 合并到fact_daily_price表...")
        fact_count = 0
        valid_turnover_count = 0
        for idx, row in df.iterrows():
            try:
                code = str(row.get('代码', row.get('code', ''))).strip()
                if not code:
                    continue
                
                code_clean = code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                if len(code_clean) > 6:
                    code_clean = code_clean[-6:]
                
                if code_clean.startswith('6'):
                    ts_code = f"{code_clean}.SH"
                elif code_clean.startswith('0') or code_clean.startswith('3'):
                    ts_code = f"{code_clean}.SZ"
                else:
                    continue
                
                fact_data = clean_layer.merge_daily_prices(ts_code, trade_date)
                if fact_data:
                    clean_layer.save_fact_daily_price(fact_data)
                    fact_count += 1
                    if fact_data.get('turnover_rate', 0) > 0:
                        valid_turnover_count += 1
            except Exception as e:
                logger.debug(f"  合并 {code} 股票数据失败: {e}")
                continue
        
        logger.info(f"✅ 合并完成，共 {fact_count} 只股票，{valid_turnover_count} 只有换手率数据")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 更新股票数据失败: {e}", exc_info=True)
    finally:
        session.close()


def complete_financial_data(limit=500, batch_size=30):
    """
    补全财务数据（毛利率、负债率、经营现金流）
    使用多数据源确保数据完整
    
    Args:
        limit: 要更新的股票数量
        batch_size: 每批处理的股票数量
    """
    logger.info("=" * 60)
    logger.info(f"补全财务数据（目标：{limit}只股票）")
    logger.info("=" * 60)
    
    financial_fetcher = FinancialDataFetcher()
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 获取股票列表
    session = raw_layer.get_session()
    try:
        stocks = session.query(DimStock).filter(
            DimStock.exchange.in_(['SSE', 'SZSE'])
        ).limit(limit).all()
        
        stock_codes = []
        for stock in stocks:
            code = stock.symbol
            if code.isdigit() and len(code) == 6:
                stock_codes.append(code)
        
        logger.info(f"✅ 获取到 {len(stock_codes)} 只A股代码")
    finally:
        session.close()
    
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = datetime.strptime(today, "%Y-%m-%d").date()
    report_type = 'annual'
    
    total_updated = 0
    total_fact_count = 0
    
    logger.info(f"📥 开始批量获取财务数据（每批{batch_size}只，延迟0.5秒）...")
    
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(stock_codes) + batch_size - 1) // batch_size
        
        logger.info(f"\n处理第 {batch_num}/{total_batches} 批（{len(batch)}只股票）...")
        
        batch_financial_data = {}
        for idx, code in enumerate(batch, 1):
            try:
                result = financial_fetcher.get_stock_financial_data(code)
                
                if result is not None:
                    batch_financial_data[code] = result
                    if idx % 10 == 0:
                        logger.info(f"  进度: {idx}/{len(batch)} ({idx*100//len(batch)}%)")
                
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
                        if code.startswith('6'):
                            ts_code = f"{code}.SH"
                        elif code.startswith('0') or code.startswith('3'):
                            ts_code = f"{code}.SZ"
                        else:
                            continue
                        
                        existing = session.query(RawFundamental).filter(
                            RawFundamental.ts_code == ts_code,
                            RawFundamental.end_date == end_date,
                            RawFundamental.report_type == report_type,
                            RawFundamental.source == 'akshare_complete'
                        ).first()
                        
                        roe_val = float(data.get('roe_ttm', 0) or 0)
                        gross_margin_val = float(data.get('gross_margin', 0) or 0)
                        net_margin_val = float(data.get('net_margin', 0) or 0)
                        debt_ratio_val = float(data.get('debt_ratio', 0) or 0)
                        op_cf_val = float(data.get('operating_cashflow', 0) or 0)
                        total_debt_val = float(data.get('total_debt', 0) or 0)
                        total_asset_val = float(data.get('total_asset', 0) or 0)
                        
                        if existing:
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
                                source='akshare_complete',
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
        
        if i + batch_size < len(stock_codes):
            time.sleep(2)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 财务数据补全完成！")
    logger.info(f"   更新股票数: {total_updated} 只")
    logger.info(f"   合并到fact表: {total_fact_count} 只")
    logger.info("=" * 60)


def test_api_endpoints():
    """测试API接口"""
    logger.info("=" * 60)
    logger.info("测试API接口")
    logger.info("=" * 60)
    
    import requests
    
    base_url = "http://localhost:8888"
    
    # 1. 测试数据仓库摘要
    try:
        response = requests.get(f"{base_url}/api/data-warehouse/summary", timeout=5)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ /api/data-warehouse/summary: 成功")
            logger.info(f"   股票数据: {data.get('stocks', {}).get('latest', {}).get('count', 0)} 只")
            logger.info(f"   财务数据: {data.get('financial', {}).get('latest', {}).get('count', 0)} 只")
        else:
            logger.error(f"❌ /api/data-warehouse/summary: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ /api/data-warehouse/summary: {e}")
    
    # 2. 测试股票数据
    try:
        response = requests.get(f"{base_url}/api/data-warehouse/stocks?date=2025-11-17&limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ /api/data-warehouse/stocks: 成功")
            logger.info(f"   返回数量: {data.get('returned', 0)} 只")
            if data.get('data'):
                sample = data['data'][0]
                has_turnover = sample.get('换手率', sample.get('turnover_rate', 0)) > 0
                logger.info(f"   换手率数据: {'有' if has_turnover else '无'}")
        else:
            logger.error(f"❌ /api/data-warehouse/stocks: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ /api/data-warehouse/stocks: {e}")
    
    # 3. 测试财务数据
    try:
        response = requests.get(f"{base_url}/api/data-warehouse/financial?date=2025-11-17&limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ /api/data-warehouse/financial: 成功")
            logger.info(f"   返回数量: {data.get('returned', 0)} 只")
            if data.get('data'):
                sample = data['data'][0]
                has_debt = sample.get('debt_ratio', 0) > 0
                has_gross = sample.get('gross_margin', 0) > 0
                has_cf = sample.get('operating_cashflow', 0) != 0
                logger.info(f"   负债率数据: {'有' if has_debt else '无'}")
                logger.info(f"   毛利率数据: {'有' if has_gross else '无'}")
                logger.info(f"   经营现金流数据: {'有' if has_cf else '无'}")
        else:
            logger.error(f"❌ /api/data-warehouse/financial: {response.status_code}")
    except Exception as e:
        logger.error(f"❌ /api/data-warehouse/financial: {e}")
    
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        # 1. 检查数据完整性
        check_data_completeness()
        
        # 2. 补全股票日线数据（包含换手率）
        logger.info("\n" + "=" * 60)
        complete_stocks_data(target_date='2025-11-17', use_akshare_history=True)
        
        # 3. 补全财务数据（毛利率、负债率、经营现金流）
        logger.info("\n" + "=" * 60)
        complete_financial_data(limit=500, batch_size=30)
        
        # 4. 再次检查数据完整性
        logger.info("\n" + "=" * 60)
        check_data_completeness()
        
        # 5. 测试API接口
        logger.info("\n" + "=" * 60)
        test_api_endpoints()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 数据仓库补全完成！")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补全失败: {e}", exc_info=True)
        sys.exit(1)

