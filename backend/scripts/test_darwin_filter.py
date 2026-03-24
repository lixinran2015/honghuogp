"""
达尔文长期筛选器测试脚本
用于测试财务筛选功能的各个模块
"""

import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.strategy.darwin_long_term import DarwinLongTermFilter
from backend.models.stock_data import StockData
from backend.services.market_data_service import MarketDataService
from backend.services.darwin.darwin_data_service import DarwinDataService
from backend.services.tushare_service import TushareService
from backend.services.financial.multi_period_financial_service import MultiPeriodFinancialService
from backend.services.financial.industry_percentile_service import IndustryPercentileService
from backend.services.industry.industry_cycle_service import IndustryCycleService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_darwin_filter.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


def test_single_stock(stock_code: str):
    """测试单只股票的筛选过程"""
    logger.info("=" * 80)
    logger.info(f"测试单只股票: {stock_code}")
    logger.info("=" * 80)
    
    try:
        # 1. 获取股票市场数据（从所有股票中获取，不限制base股票池）
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        from datetime import date
        from sqlalchemy import text
        import pandas as pd
        
        warehouse = PostgresWarehouse()
        stocks_df = None
        
        if warehouse._initialized and warehouse.warehouse_service:
            # 获取最新交易日期
            latest_date = warehouse.get_latest_stocks_date()
            if latest_date:
                logger.debug(f"📅 使用交易日期: {latest_date}")
                
                # 直接从fact_daily_price_qfq表获取所有股票（不限制base股票池）
                session = warehouse.warehouse_service.get_session()
                try:
                    query = text("""
                        SELECT 
                            qfq.ts_code,
                            qfq.trade_date,
                            qfq.open,
                            qfq.high,
                            qfq.low,
                            qfq.close,
                            qfq.pre_close,
                            qfq.vol,
                            qfq.amount,
                            qfq.turnover_rate,
                            qfq.change_pct,
                            qfq.pe_ttm,
                            qfq.pb,
                            qfq.ps_ttm,
                            qfq.pcf_ttm,
                            qfq.is_suspended,
                            qfq.is_st,
                            qfq.ma5,
                            qfq.ma10,
                            qfq.ma20,
                            qfq.ma60,
                            qfq.avg_volume_5,
                            qfq.volume_ratio,
                            qfq.slope_ma20,
                            ds.name as stock_name
                        FROM fact_daily_price_qfq qfq
                        INNER JOIN dim_stock ds ON qfq.ts_code = ds.ts_code
                        WHERE qfq.trade_date = :trade_date
                        ORDER BY qfq.ts_code
                    """)
                    
                    results = session.execute(query, {'trade_date': date.fromisoformat(latest_date)}).fetchall()
                    
                    if results:
                        # 转换为DataFrame（使用与PostgresWarehouse相同的格式）
                        data_list = []
                        for r in results:
                            ts_code = r[0]
                            stock_name = r[24] if len(r) > 24 else ts_code
                            is_st = r[16] if r[16] else False
                            
                            data_list.append({
                                '代码': ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                                '股票名称': stock_name,
                                '当前价': float(r[5]) if r[5] else 0.0,
                                '涨跌幅': float(r[10]) if r[10] else 0.0,
                                '涨跌额': (float(r[5]) - float(r[6])) if r[5] and r[6] else 0.0,
                                '成交量': float(r[7]) if r[7] else 0.0,
                                '成交额': float(r[8]) if r[8] else 0.0,
                                '换手率': float(r[9]) if r[9] else 0.0,
                                '开盘': float(r[2]) if r[2] else 0.0,
                                '最高': float(r[3]) if r[3] else 0.0,
                                '最低': float(r[4]) if r[4] else 0.0,
                                '昨收': float(r[6]) if r[6] else 0.0,
                                'code': ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                                'name': stock_name,
                                'lastPrice': float(r[5]) if r[5] else 0.0,
                                'pct_chg': float(r[10]) if r[10] else 0.0,
                                'amount': float(r[8]) if r[8] else 0.0,
                                'turnover_rate': float(r[9]) if r[9] else 0.0,
                                'avgVolume5': float(r[21]) if len(r) > 21 and r[21] else 0.0,
                                'volume': float(r[7]) if r[7] else 0.0,
                                'change_pct': float(r[10]) if r[10] else 0.0,
                                'is_st': is_st,
                                'close': float(r[5]) if r[5] else 0.0,
                                'ma20': float(r[19]) if len(r) > 19 and r[19] else None,
                                'slope_ma20': float(r[23]) if len(r) > 23 and r[23] else None,
                                'pe_ttm': float(r[11]) if len(r) > 11 and r[11] else None,
                                'pb': float(r[12]) if len(r) > 12 and r[12] else None,
                            })
                        
                        stocks_df = pd.DataFrame(data_list)
                        logger.debug(f"✅ 从fact_daily_price_qfq获取到 {len(stocks_df)} 只股票（所有股票，不限制base股票池）")
                    else:
                        logger.warning("⚠️ 从fact_daily_price_qfq未获取到数据，尝试使用MarketDataService")
                        from backend.services.market_data_service import MarketDataService
                        market_service = MarketDataService()
                        stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
                finally:
                    session.close()
            else:
                logger.warning("⚠️ 无法获取最新交易日期，使用MarketDataService")
                from backend.services.market_data_service import MarketDataService
                market_service = MarketDataService()
                stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
        else:
            logger.warning("⚠️ PostgreSQL数据仓库不可用，使用MarketDataService")
            from backend.services.market_data_service import MarketDataService
            market_service = MarketDataService()
            stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
        
        if stocks_df is None or stocks_df.empty:
            logger.error("无法获取股票数据")
            return
        
        # 查找目标股票（支持多种列名格式）
        logger.debug(f"📊 DataFrame列名: {list(stocks_df.columns)}")
        logger.debug(f"📊 DataFrame形状: {stocks_df.shape}")
        
        # 显示股票代码范围统计
        code_col = None
        for col in ['代码', 'code', 'ts_code', '股票代码']:
            if col in stocks_df.columns:
                code_col = col
                break
        
        if code_col:
            codes = stocks_df[code_col].astype(str).str.strip()
            # 统计代码范围
            sh_codes = codes[codes.str.startswith('6')]
            sz_codes = codes[codes.str.startswith('0')]
            cyb_codes = codes[codes.str.startswith('3')]
            kcb_codes = codes[codes.str.startswith('688')]
            bj_codes = codes[codes.str.startswith('8')]
            
            logger.debug(f"📊 股票代码分布:")
            logger.debug(f"   沪市（6开头）: {len(sh_codes)} 只")
            logger.debug(f"   深市主板（0开头）: {len(sz_codes)} 只")
            logger.debug(f"   创业板（3开头）: {len(cyb_codes)} 只")
            logger.debug(f"   科创板（688开头）: {len(kcb_codes)} 只")
            logger.debug(f"   北交所（8开头）: {len(bj_codes)} 只")
            
            # 显示各板块的示例代码
            if not sh_codes.empty:
                logger.debug(f"   沪市示例: {', '.join(sh_codes.head(3).tolist())}")
            if not sz_codes.empty:
                logger.debug(f"   深市主板示例: {', '.join(sz_codes.head(3).tolist())}")
            if not cyb_codes.empty:
                logger.debug(f"   创业板示例: {', '.join(cyb_codes.head(3).tolist())}")
            if not kcb_codes.empty:
                logger.debug(f"   科创板示例: {', '.join(kcb_codes.head(3).tolist())}")
        
        # 显示前5只股票代码示例
        logger.debug(f"\n📊 前5只股票代码示例:")
        for idx, row in stocks_df.head(5).iterrows():
            code_val = row.get('代码') or row.get('code') or row.get('ts_code', 'N/A')
            name_val = row.get('名称') or row.get('name') or row.get('股票名称', 'N/A')
            logger.debug(f"   索引{idx}: 代码={code_val}, 名称={name_val}")
        
        # 尝试多种列名和格式
        if code_col is None:
            for col in ['代码', 'code', 'ts_code', '股票代码']:
                if col in stocks_df.columns:
                    code_col = col
                    logger.info(f"✅ 使用列名: {code_col}")
                    break
        
        if code_col is None:
            logger.error(f"❌ 无法找到股票代码列，可用列: {list(stocks_df.columns)}")
            return
        
        # 尝试多种代码格式匹配
        stock_row = None
        
        # 1. 直接匹配（6位数字）
        stock_row = stocks_df[stocks_df[code_col] == stock_code]
        if not stock_row.empty:
            logger.info(f"✅ 找到股票（直接匹配）: {stock_code}")
        
        # 2. 如果失败，尝试匹配带后缀的格式
        if stock_row.empty:
            for suffix in ['.SH', '.SZ', '.BJ']:
                full_code = f"{stock_code}{suffix}"
                stock_row = stocks_df[stocks_df[code_col] == full_code]
                if not stock_row.empty:
                    logger.info(f"✅ 找到股票（带后缀）: {full_code}")
                    break
        
        # 3. 如果还是失败，尝试部分匹配（去除后缀）
        if stock_row.empty:
            # 去除DataFrame中代码的后缀再匹配
            stocks_df_copy = stocks_df.copy()
            stocks_df_copy['code_clean'] = stocks_df_copy[code_col].astype(str).str.replace('.SH', '').str.replace('.SZ', '').str.replace('.BJ', '').str.strip()
            stock_row = stocks_df_copy[stocks_df_copy['code_clean'] == stock_code]
            if not stock_row.empty:
                # 使用原始DataFrame的索引
                stock_row = stocks_df.loc[stock_row.index]
                logger.info(f"✅ 找到股票（去除后缀后匹配）: {stock_code}")
        
        # 4. 如果还是失败，尝试字符串包含匹配（处理可能的空格或格式问题）
        if stock_row.empty:
            stocks_df_copy = stocks_df.copy()
            stocks_df_copy['code_str'] = stocks_df_copy[code_col].astype(str).str.strip()
            stock_row = stocks_df_copy[stocks_df_copy['code_str'].str.contains(stock_code, na=False, regex=False)]
            if not stock_row.empty:
                logger.info(f"✅ 找到股票（字符串包含匹配）: {stock_code}")
                # 取第一个匹配的
                stock_row = stock_row.head(1)
        
        if stock_row.empty:
            logger.error(f"❌ 未找到股票: {stock_code}")
            logger.info(f"💡 提示：")
            logger.info(f"   1. 请检查股票代码是否正确（6位数字，如 600519）")
            logger.info(f"   2. 数据仓库中可能没有这只股票的数据")
            logger.info(f"   3. 可以查看上面的代码示例，确认数据格式")
            
            # 尝试查找类似的代码
            stocks_df_copy = stocks_df.copy()
            stocks_df_copy['code_str'] = stocks_df_copy[code_col].astype(str).str.strip()
            similar_codes = stocks_df_copy[stocks_df_copy['code_str'].str.startswith(stock_code[:3], na=False)]
            if not similar_codes.empty:
                logger.info(f"   4. 找到以 {stock_code[:3]} 开头的股票:")
                for idx, row in similar_codes.head(5).iterrows():
                    code_val = row.get('代码') or row.get('code', 'N/A')
                    name_val = row.get('名称') or row.get('name') or row.get('股票名称', 'N/A')
                    logger.info(f"      {code_val} - {name_val}")
            
            # 建议使用数据仓库中实际存在的股票
            logger.info(f"\n💡 建议：")
            logger.info(f"   数据仓库中主要包含创业板和科创板股票")
            logger.info(f"   可以尝试使用以下股票代码进行测试：")
            if not cyb_codes.empty:
                logger.info(f"   - 创业板: {cyb_codes.iloc[0]} (示例)")
            if not kcb_codes.empty:
                logger.info(f"   - 科创板: {kcb_codes.iloc[0]} (示例)")
            if not sh_codes.empty:
                logger.info(f"   - 沪市: {sh_codes.iloc[0]} (示例)")
            if not sz_codes.empty:
                logger.info(f"   - 深市主板: {sz_codes.iloc[0]} (示例)")
            return
        
        stock_dict = stock_row.iloc[0].to_dict()
        stock_data = StockData.from_dict(stock_dict)
        logger.info(f"✅ 获取股票数据: {stock_data.name} ({stock_data.code})")
        
        # 2. 获取财务数据
        darwin_data_service = DarwinDataService()
        financial_data = darwin_data_service.get_financial_data_batch([stock_code])
        industry_info = darwin_data_service.get_industry_info_batch([stock_code])
        
        if stock_code in industry_info:
            stock_data.sector = industry_info[stock_code]
            logger.info(f"✅ 行业信息: {industry_info[stock_code]}")
        
        if stock_code not in financial_data:
            logger.warning(f"⚠️ 未获取到财务数据: {stock_code}")
            return
        
        logger.info(f"✅ 获取财务数据: {len(financial_data)} 条")
        
        # 3. 测试各个服务模块
        logger.info("\n" + "-" * 80)
        logger.info("测试各个服务模块")
        logger.info("-" * 80)
        
        # 3.1 测试行业周期服务
        industry_name = industry_info.get(stock_code, '')
        if industry_name:
            industry_cycle_service = IndustryCycleService()
            cycle = industry_cycle_service.get_industry_cycle(industry_name)
            net_cash_threshold = industry_cycle_service.get_net_cash_ratio_threshold(industry_name)
            cash_receipt_threshold = industry_cycle_service.get_cash_receipt_ratio_threshold(industry_name)
            
            logger.info(f"📊 行业周期判断:")
            logger.info(f"   行业: {industry_name}")
            logger.info(f"   周期: {cycle}")
            logger.info(f"   净现比阈值: {net_cash_threshold:.2f}")
            logger.info(f"   收现比阈值: {cash_receipt_threshold:.2f}")
        
        # 3.2 测试多期财务数据服务
        tushare_service = TushareService()
        multi_period_service = MultiPeriodFinancialService(tushare_service)
        
        # 转换为ts_code格式
        ts_code = f"{stock_code}.SH" if stock_code.startswith('6') else f"{stock_code}.SZ"
        
        quarterly_data = multi_period_service.get_multi_period_data(ts_code, periods=3, freq='Q')
        if quarterly_data is not None and not quarterly_data.empty:
            logger.info(f"📈 多期财务数据:")
            logger.info(f"   获取到 {len(quarterly_data)} 期数据")
            logger.info(f"   最新报告期: {quarterly_data.iloc[0]['end_date']}")
            if 'ocf' in quarterly_data.columns:
                logger.info(f"   最新经营现金流: {quarterly_data.iloc[0]['ocf']:,.0f}")
            if 'revenue' in quarterly_data.columns:
                logger.info(f"   最新营收: {quarterly_data.iloc[0]['revenue']:,.0f}")
        else:
            logger.warning(f"⚠️ 未获取到多期财务数据: {ts_code}")
        
        # 3.3 测试行业分位数服务
        if industry_name:
            industry_percentile_service = IndustryPercentileService(tushare_service)
            roe_percentile_50 = industry_percentile_service.get_percentile(industry_name, 'roe', percentile=0.5)
            gross_margin_percentile_50 = industry_percentile_service.get_percentile(industry_name, 'grossprofit_margin', percentile=0.5)
            
            logger.info(f"📊 行业分位数:")
            logger.info(f"   ROE中位数: {roe_percentile_50:.2f}%")
            logger.info(f"   毛利率中位数: {gross_margin_percentile_50:.2f}%")
        
        # 4. 执行筛选
        logger.info("\n" + "-" * 80)
        logger.info("执行达尔文筛选")
        logger.info("-" * 80)
        
        darwin_filter = DarwinLongTermFilter()
        result = darwin_filter.filter_darwin_companies(
            stock_data=[stock_data],
            financial_data=financial_data,
            limit=20
        )
        
        # 5. 输出结果
        logger.info("\n" + "=" * 80)
        logger.info("筛选结果")
        logger.info("=" * 80)
        
        logger.info(f"核心池 (darwin_core): {len(result.darwin_core)} 只")
        for stock in result.darwin_core:
            logger.info(f"  ✅ {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')})")
        
        logger.info(f"\n观察池 (darwin_watch): {len(result.darwin_watch)} 只")
        for stock in result.darwin_watch:
            logger.info(f"  👀 {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')})")
        
        if result.warning:
            logger.warning(f"\n⚠️ 警告: {result.warning}")
        
        logger.info(f"\n筛选步骤统计:")
        for step, count in result.filter_steps.items():
            logger.info(f"  {step}: {count} 只")
        
        logger.info("\n" + "=" * 80)
        logger.info("测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


def test_batch_stocks(stock_codes: list, limit: int = 20):
    """测试批量股票筛选"""
    logger.info("=" * 80)
    logger.info(f"测试批量股票筛选: {len(stock_codes)} 只股票")
    logger.info("=" * 80)
    
    try:
        # 1. 获取股票市场数据（从所有股票中获取，不限制base股票池）
        from backend.services.data.postgres_warehouse import PostgresWarehouse
        from datetime import date
        from sqlalchemy import text
        import pandas as pd
        
        warehouse = PostgresWarehouse()
        stocks_df = None
        
        if warehouse._initialized and warehouse.warehouse_service:
            # 获取最新交易日期
            latest_date = warehouse.get_latest_stocks_date()
            if latest_date:
                logger.debug(f"📅 使用交易日期: {latest_date}")
                
                # 直接从fact_daily_price_qfq表获取所有股票（不限制base股票池）
                session = warehouse.warehouse_service.get_session()
                try:
                    query = text("""
                        SELECT 
                            qfq.ts_code,
                            qfq.trade_date,
                            qfq.open,
                            qfq.high,
                            qfq.low,
                            qfq.close,
                            qfq.pre_close,
                            qfq.vol,
                            qfq.amount,
                            qfq.turnover_rate,
                            qfq.change_pct,
                            qfq.pe_ttm,
                            qfq.pb,
                            qfq.ps_ttm,
                            qfq.pcf_ttm,
                            qfq.is_suspended,
                            qfq.is_st,
                            qfq.ma5,
                            qfq.ma10,
                            qfq.ma20,
                            qfq.ma60,
                            qfq.avg_volume_5,
                            qfq.volume_ratio,
                            qfq.slope_ma20,
                            ds.name as stock_name
                        FROM fact_daily_price_qfq qfq
                        INNER JOIN dim_stock ds ON qfq.ts_code = ds.ts_code
                        WHERE qfq.trade_date = :trade_date
                        ORDER BY qfq.ts_code
                    """)
                    
                    results = session.execute(query, {'trade_date': date.fromisoformat(latest_date)}).fetchall()
                    
                    if results:
                        # 转换为DataFrame（使用与PostgresWarehouse相同的格式）
                        data_list = []
                        for r in results:
                            ts_code = r[0]
                            stock_name = r[24] if len(r) > 24 else ts_code
                            is_st = r[16] if r[16] else False
                            
                            data_list.append({
                                '代码': ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                                '股票名称': stock_name,
                                '当前价': float(r[5]) if r[5] else 0.0,
                                '涨跌幅': float(r[10]) if r[10] else 0.0,
                                '涨跌额': (float(r[5]) - float(r[6])) if r[5] and r[6] else 0.0,
                                '成交量': float(r[7]) if r[7] else 0.0,
                                '成交额': float(r[8]) if r[8] else 0.0,
                                '换手率': float(r[9]) if r[9] else 0.0,
                                '开盘': float(r[2]) if r[2] else 0.0,
                                '最高': float(r[3]) if r[3] else 0.0,
                                '最低': float(r[4]) if r[4] else 0.0,
                                '昨收': float(r[6]) if r[6] else 0.0,
                                'code': ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                                'name': stock_name,
                                'lastPrice': float(r[5]) if r[5] else 0.0,
                                'pct_chg': float(r[10]) if r[10] else 0.0,
                                'amount': float(r[8]) if r[8] else 0.0,
                                'turnover_rate': float(r[9]) if r[9] else 0.0,
                                'avgVolume5': float(r[21]) if len(r) > 21 and r[21] else 0.0,
                                'volume': float(r[7]) if r[7] else 0.0,
                                'change_pct': float(r[10]) if r[10] else 0.0,
                                'is_st': is_st,
                                'close': float(r[5]) if r[5] else 0.0,
                                'ma20': float(r[19]) if len(r) > 19 and r[19] else None,
                                'slope_ma20': float(r[23]) if len(r) > 23 and r[23] else None,
                                'pe_ttm': float(r[11]) if len(r) > 11 and r[11] else None,
                                'pb': float(r[12]) if len(r) > 12 and r[12] else None,
                            })
                        
                        stocks_df = pd.DataFrame(data_list)
                        logger.debug(f"✅ 从fact_daily_price_qfq获取到 {len(stocks_df)} 只股票（所有股票，不限制base股票池）")
                    else:
                        logger.warning("⚠️ 从fact_daily_price_qfq未获取到数据，尝试使用MarketDataService")
                        from backend.services.market_data_service import MarketDataService
                        market_service = MarketDataService()
                        stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
                finally:
                    session.close()
            else:
                logger.warning("⚠️ 无法获取最新交易日期，使用MarketDataService")
                from backend.services.market_data_service import MarketDataService
                market_service = MarketDataService()
                stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
        else:
            logger.warning("⚠️ PostgreSQL数据仓库不可用，使用MarketDataService")
            from backend.services.market_data_service import MarketDataService
            market_service = MarketDataService()
            stocks_df = market_service.get_realtime_stocks(force_refresh=False, use_warehouse=True)
        
        if stocks_df is None or stocks_df.empty:
            logger.error("无法获取股票数据")
            return
        
        # 2. 筛选目标股票
        code_col = '代码' if '代码' in stocks_df.columns else 'code'
        stock_data_list = []
        
        for code in stock_codes:
            stock_row = stocks_df[stocks_df[code_col] == code]
            if not stock_row.empty:
                stock_dict = stock_row.iloc[0].to_dict()
                try:
                    stock_data = StockData.from_dict(stock_dict)
                    stock_data_list.append(stock_data)
                except Exception as e:
                    logger.debug(f"转换股票数据失败 {code}: {e}")
        
        logger.info(f"✅ 获取到 {len(stock_data_list)} 只股票的市场数据")
        
        if not stock_data_list:
            logger.error("未找到任何目标股票")
            return
        
        # 3. 获取财务数据和行业信息
        darwin_data_service = DarwinDataService()
        stock_codes_6digit = [stock.code.replace('.SH', '').replace('.SZ', '') for stock in stock_data_list]
        financial_data = darwin_data_service.get_financial_data_batch(stock_codes_6digit)
        industry_info = darwin_data_service.get_industry_info_batch(stock_codes_6digit)
        
        logger.info(f"✅ 获取到财务数据: {len(financial_data)} 只")
        logger.info(f"✅ 获取到行业信息: {len(industry_info)} 只")
        
        # 4. 添加行业信息
        for stock in stock_data_list:
            code_6digit = stock.code.replace('.SH', '').replace('.SZ', '')
            if code_6digit in industry_info:
                stock.sector = industry_info[code_6digit]
        
        # 5. 执行筛选
        logger.info("\n" + "-" * 80)
        logger.info("执行达尔文筛选")
        logger.info("-" * 80)
        
        darwin_filter = DarwinLongTermFilter()
        result = darwin_filter.filter_darwin_companies(
            stock_data=stock_data_list,
            financial_data=financial_data,
            limit=limit
        )
        
        # 6. 输出结果
        logger.info("\n" + "=" * 80)
        logger.info("筛选结果")
        logger.info("=" * 80)
        
        logger.info(f"核心池 (darwin_core): {len(result.darwin_core)} 只")
        for i, stock in enumerate(result.darwin_core[:10], 1):  # 只显示前10只
            logger.info(f"  {i}. {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')})")
        if len(result.darwin_core) > 10:
            logger.info(f"  ... 还有 {len(result.darwin_core) - 10} 只")
        
        logger.info(f"\n观察池 (darwin_watch): {len(result.darwin_watch)} 只")
        for i, stock in enumerate(result.darwin_watch[:10], 1):  # 只显示前10只
            logger.info(f"  {i}. {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')})")
        if len(result.darwin_watch) > 10:
            logger.info(f"  ... 还有 {len(result.darwin_watch) - 10} 只")
        
        if result.warning:
            logger.warning(f"\n⚠️ 警告: {result.warning}")
        
        logger.info(f"\n筛选步骤统计:")
        for step, count in result.filter_steps.items():
            logger.info(f"  {step}: {count} 只")
        
        logger.info("\n" + "=" * 80)
        logger.info("测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


def test_api_endpoint():
    """测试API接口"""
    import requests
    
    logger.info("=" * 80)
    logger.info("测试API接口: GET /api/stock-filters/darwin")
    logger.info("=" * 80)
    
    try:
        url = "http://localhost:8000/api/stock-filters/darwin"
        params = {"limit": 20}
        
        logger.info(f"请求URL: {url}")
        logger.info(f"参数: {params}")
        
        response = requests.get(url, params=params, timeout=120)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ API调用成功")
            logger.info(f"核心池: {len(data.get('darwin_core', []))} 只")
            logger.info(f"观察池: {len(data.get('darwin_watch', []))} 只")
            
            if data.get('warning'):
                logger.warning(f"⚠️ 警告: {data.get('warning')}")
            
            logger.info(f"\n筛选步骤统计:")
            for step, count in data.get('filter_steps', {}).items():
                logger.info(f"  {step}: {count} 只")
        else:
            logger.error(f"❌ API调用失败: {response.status_code}")
            logger.error(f"响应: {response.text}")
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ 无法连接到API服务器，请确保后端服务已启动")
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="达尔文长期筛选器测试脚本")
    parser.add_argument("--mode", choices=["single", "batch", "api"], default="single",
                        help="测试模式: single(单只股票), batch(批量股票), api(API接口)")
    parser.add_argument("--codes", nargs="+", help="股票代码列表（6位数字，如 600519 000001）")
    parser.add_argument("--limit", type=int, default=20, help="返回数量限制")
    
    args = parser.parse_args()
    
    if args.mode == "single":
        if not args.codes or len(args.codes) == 0:
            logger.error("单只股票测试模式需要提供股票代码: --codes 600519")
            sys.exit(1)
        test_single_stock(args.codes[0])
    
    elif args.mode == "batch":
        if not args.codes or len(args.codes) == 0:
            # 默认测试一些知名股票
            test_codes = ["600519", "000001", "000002", "600036", "600000"]
            logger.info(f"未提供股票代码，使用默认测试股票: {test_codes}")
            test_batch_stocks(test_codes, limit=args.limit)
        else:
            test_batch_stocks(args.codes, limit=args.limit)
    
    elif args.mode == "api":
        test_api_endpoint()
