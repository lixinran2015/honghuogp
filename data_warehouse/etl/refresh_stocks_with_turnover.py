"""
重新获取股票数据（包含换手率）
使用easyquotation获取换手率数据，然后更新到PostgreSQL
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime, date
from akshare_safe_wrapper import fetch_realtime_a_stock_easy, fetch_today_closing_data_akshare
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.models import DimStock
from data_warehouse.models import RawDailyPrice
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def refresh_stocks_with_turnover(target_date: str = None):
    """
    重新获取股票数据（包含换手率）并更新到PostgreSQL
    
    Args:
        target_date: 目标日期（YYYY-MM-DD），如果为None则使用今天
    """
    logger.info("=" * 60)
    logger.info("开始重新获取股票数据（包含换手率）")
    logger.info("=" * 60)
    
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")
    
    trade_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    
    # 初始化服务
    raw_layer = RawDataLayer()
    clean_layer = CleanDataLayer()
    
    # 尝试使用easyquotation获取数据（包含换手率）
    logger.info(f"📥 尝试使用easyquotation获取股票数据（包含换手率）...")
    try:
        df = fetch_realtime_a_stock_easy(cache=False, force_refresh=True)
        if df is not None and not df.empty and '换手率' in df.columns:
            valid_turnover = (df['换手率'] > 0).sum()
            logger.info(f"✅ 使用easyquotation获取到 {len(df)} 只股票，{valid_turnover} 只有换手率数据")
        else:
            logger.warning("⚠️ easyquotation未返回有效数据，尝试akshare...")
            df = fetch_today_closing_data_akshare(cache=False)
            if df is not None and not df.empty:
                logger.info(f"✅ 使用akshare获取到 {len(df)} 只股票（可能没有换手率）")
            else:
                logger.error("❌ 无法获取股票数据")
                return
    except Exception as e:
        logger.warning(f"⚠️ easyquotation获取失败: {e}，尝试akshare...")
        try:
            df = fetch_today_closing_data_akshare(cache=False)
            if df is not None and not df.empty:
                logger.info(f"✅ 使用akshare获取到 {len(df)} 只股票（可能没有换手率）")
            else:
                logger.error("❌ 无法获取股票数据")
                return
        except Exception as e2:
            logger.error(f"❌ 获取股票数据失败: {e2}")
            return
    
    if df is None or df.empty:
        logger.error("❌ 股票数据为空")
        return
    
    # 更新到PostgreSQL
    logger.info(f"\n📦 更新股票数据到PostgreSQL数据仓库...")
    session = raw_layer.get_session()
    try:
        updated_count = 0
        for idx, row in df.iterrows():
            try:
                # 获取股票代码
                code = str(row.get('代码', row.get('code', ''))).strip()
                if not code:
                    continue
                
                # 标准化代码
                code_clean = code.replace('sh', '').replace('sz', '').replace('bj', '').replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
                if len(code_clean) > 6:
                    code_clean = code_clean[-6:]
                
                if not code_clean.isdigit() or len(code_clean) != 6:
                    continue
                
                # 确定交易所和ts_code
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
                    name = str(row.get('名称', row.get('name', ''))).strip()
                    stock = DimStock(
                        ts_code=ts_code,
                        exchange=exchange,
                        symbol=code_clean,
                        name=name if name else code_clean
                    )
                    session.add(stock)
                
                # 获取换手率
                turnover_rate = float(row.get('换手率', row.get('turnover_rate', 0)) or 0)
                
                # 保存或更新日线数据到raw_daily_price
                existing = session.query(RawDailyPrice).filter(
                    RawDailyPrice.ts_code == ts_code,
                    RawDailyPrice.trade_date == trade_date,
                    RawDailyPrice.source == 'easyquotation'
                ).first()
                
                if existing:
                    # 更新现有记录（特别是换手率）
                    existing.open = float(row.get('今开', row.get('open', 0)) or 0)
                    existing.high = float(row.get('最高', row.get('high', 0)) or 0)
                    existing.low = float(row.get('最低', row.get('low', 0)) or 0)
                    existing.close = float(row.get('最新价', row.get('当前价', row.get('lastPrice', 0))) or 0)
                    existing.pre_close = float(row.get('昨收', row.get('pre_close', 0)) or 0)
                    existing.vol = float(row.get('成交量', row.get('volume', 0)) or 0)
                    existing.amount = float(row.get('成交额', row.get('amount', 0)) or 0)
                    existing.turnover_rate = turnover_rate  # 更新换手率
                    existing.raw_payload = row.to_dict()
                    updated_count += 1
                else:
                    # 创建新记录
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
                        turnover_rate=turnover_rate,  # 保存换手率
                        source='easyquotation',
                        raw_payload=row.to_dict()
                    )
                    session.add(raw_price)
                    updated_count += 1
            
            except Exception as e:
                logger.debug(f"  处理股票 {code} 失败: {e}")
                continue
        
        session.commit()
        logger.info(f"✅ 成功更新 {updated_count} 只股票的日线数据到raw表（包含换手率）")
        
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
            except Exception as e:
                logger.debug(f"  合并 {code} 股票数据失败: {e}")
                continue
        
        logger.info(f"✅ 合并完成，共 {fact_count} 只股票")
        
        # 统计换手率数据
        if '换手率' in df.columns:
            valid_turnover_count = (df['换手率'] > 0).sum()
        logger.info(f"📊 换手率数据统计: {valid_turnover_count}/{len(df)} 只有有效换手率")
        
    except Exception as e:
        session.rollback()
        logger.error(f"❌ 更新股票数据失败: {e}", exc_info=True)
    finally:
        session.close()
    
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ 股票数据更新完成！")
    logger.info(f"   更新股票数: {updated_count} 只")
    logger.info(f"   合并到fact表: {fact_count} 只")
    logger.info(f"   有效换手率: {valid_turnover_count} 只")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        # 更新今天的股票数据（包含换手率）
        refresh_stocks_with_turnover()
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 更新失败: {e}", exc_info=True)
        sys.exit(1)

