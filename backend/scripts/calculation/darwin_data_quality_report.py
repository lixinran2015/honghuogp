#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
达尔文评分数据质量报告
检查达尔文评分公式用到的所有数据字段的完整性
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.darwin.darwin_data_service import DarwinDataService
from data_warehouse.service.warehouse_service import WarehouseService
from sqlalchemy import text
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def generate_darwin_data_quality_report():
    """生成达尔文评分数据质量报告"""
    logger.info("=" * 80)
    logger.info("达尔文评分数据质量报告")
    logger.info("=" * 80)
    
    universe_service = StockUniverseService()
    wh_service = WarehouseService()
    session = wh_service.get_session()
    
    try:
        # 获取S1股票池
        s1_codes = universe_service.get_universe_stocks('s1')
        logger.info(f"S1股票池: {len(s1_codes)} 只股票")
        
        # 转换为ts_code格式
        s1_ts_codes = []
        for code in s1_codes:
            code_str = str(code).strip()
            if code_str.startswith('6'):
                ts_code = f'{code_str}.SH'
            elif code_str.startswith(('0', '3')):
                ts_code = f'{code_str}.SZ'
            else:
                ts_code = code_str
            s1_ts_codes.append(ts_code)
        
        # 获取最新交易日期
        latest_date_query = text('''
            SELECT MAX(trade_date) FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
        ''')
        latest_date_result = session.execute(latest_date_query, {'ts_codes': s1_ts_codes}).fetchone()
        trade_date = str(latest_date_result[0]) if latest_date_result and latest_date_result[0] else '2025-11-17'
        logger.info(f"使用交易日期: {trade_date}")
        
        # 定义达尔文评分用到的所有数据字段
        darwin_fields = {
            # 成长性（25%）
            "成长性": {
                "revenue_growth_yoy": "营收同比增长率",
                "profit_growth_yoy": "净利润同比增长率",
                "profit_volatility": "利润波动性"
            },
            # 盈利能力（25%）
            "盈利能力": {
                "roe_ttm": "ROE(TTM)",
                "net_margin_ttm": "净利率(TTM)"
            },
            # 财务健康度（15%）
            "财务健康度": {
                "roe_ttm": "ROE(TTM)",
                "op_cf_ttm": "经营现金流TTM",
                "debt_ratio": "负债率",
                "net_margin_ttm": "净利率(TTM)"
            },
            # 成本优势/竞争优势（10%）
            "成本优势/竞争优势": {
                "gross_margin_ttm": "毛利率(TTM)",
                "industry_cr4": "行业集中度CR4",
                "market_share": "市场份额"
            },
            # 估值（15%）
            "估值": {
                "pe_ttm": "PE(TTM)",
                "pb_lyr": "PB(LYR)"
            },
            # 资金行为与趋势（10%）
            "资金行为与趋势": {
                "amount": "成交额",
                "turnover_rate": "换手率",
                "ma20": "MA20",
                "close": "收盘价",
                "pct_chg": "涨跌幅"
            }
        }
        
        # 检查fact_daily_fundamental表中的字段（先检查哪些字段存在）
        from sqlalchemy import inspect
        inspector = inspect(session.bind)
        columns = inspector.get_columns('fact_daily_fundamental')
        available_columns = [col['name'] for col in columns]
        
        # 定义需要检查的字段
        fundamental_fields_to_check = [
            'revenue_growth_yoy', 'profit_growth_yoy', 'profit_volatility',
            'roe_ttm', 'net_margin_ttm', 'gross_margin_ttm',
            'op_cf_ttm', 'op_cf_growth_yoy'
        ]
        
        # 只检查存在的字段
        fundamental_fields = [f for f in fundamental_fields_to_check if f in available_columns]
        
        # 检查debt_ratio（可能在fact_fundamental表中）
        if 'debt_ratio' not in available_columns:
            logger.info("⚠️  debt_ratio字段不在fact_daily_fundamental表中，跳过检查")
        
        # PE和PB也在fact_daily_fundamental表中，添加到fundamental_fields中检查
        if 'pe_ttm' in available_columns and 'pe_ttm' not in fundamental_fields:
            fundamental_fields.append('pe_ttm')
        if 'pb_lyr' in available_columns and 'pb_lyr' not in fundamental_fields:
            fundamental_fields.append('pb_lyr')
        
        # 检查fact_daily_price_qfq表中的字段（先检查哪些字段存在）
        price_columns = inspector.get_columns('fact_daily_price_qfq')
        available_price_columns = [col['name'] for col in price_columns]
        
        # 定义需要检查的字段（PE和PB在fundamental表中，不在price表中）
        price_fields_to_check = ['close', 'change_pct', 'amount', 'turnover_rate', 'ma20']
        
        # 只检查存在的字段
        price_fields = [f for f in price_fields_to_check if f in available_price_columns]
        
        print("\n" + "=" * 80)
        print("达尔文评分数据质量报告")
        print("=" * 80)
        print(f"\n报告日期: {trade_date}")
        print(f"股票池: S1 ({len(s1_ts_codes)} 只股票)")
        print("\n" + "-" * 80)
        
        # 1. 检查财务数据表
        print("\n【1. 财务数据表 (fact_daily_fundamental)】")
        print("-" * 80)
        
        fundamental_stats = {}
        for field in fundamental_fields:
            query = text(f'''
                SELECT 
                    COUNT(DISTINCT ts_code) as total,
                    COUNT(DISTINCT CASE WHEN {field} IS NOT NULL THEN ts_code END) as has_data,
                    COUNT(DISTINCT CASE WHEN {field} IS NOT NULL AND {field} != 0 THEN ts_code END) as has_valid_data
                FROM fact_daily_fundamental
                WHERE ts_code = ANY(:ts_codes)
                  AND trade_date = :trade_date
            ''')
            
            result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date}).fetchone()
            if result:
                total = result[0] or 0
                has_data = result[1] or 0
                has_valid = result[2] or 0
                
                completeness = (has_data / total * 100) if total > 0 else 0
                validity = (has_valid / total * 100) if total > 0 else 0
                
                fundamental_stats[field] = {
                    'total': total,
                    'has_data': has_data,
                    'has_valid': has_valid,
                    'completeness': completeness,
                    'validity': validity
                }
                
                status = "✅" if completeness >= 90 else "⚠️" if completeness >= 50 else "❌"
                print(f"{status} {field:25s} 完整性: {has_data:3d}/{total:3d} ({completeness:5.1f}%)  有效性: {has_valid:3d}/{total:3d} ({validity:5.1f}%)")
        
        # 2. 检查价格数据表
        print("\n【2. 价格数据表 (fact_daily_price_qfq)】")
        print("-" * 80)
        
        price_stats = {}
        for field in price_fields:
            query = text(f'''
                SELECT 
                    COUNT(DISTINCT ts_code) as total,
                    COUNT(DISTINCT CASE WHEN {field} IS NOT NULL THEN ts_code END) as has_data,
                    COUNT(DISTINCT CASE WHEN {field} IS NOT NULL AND {field} != 0 THEN ts_code END) as has_valid_data
                FROM fact_daily_price_qfq
                WHERE ts_code = ANY(:ts_codes)
                  AND trade_date = :trade_date
            ''')
            
            result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date}).fetchone()
            if result:
                total = result[0] or 0
                has_data = result[1] or 0
                has_valid = result[2] or 0
                
                completeness = (has_data / total * 100) if total > 0 else 0
                validity = (has_valid / total * 100) if total > 0 else 0
                
                price_stats[field] = {
                    'total': total,
                    'has_data': has_data,
                    'has_valid': has_valid,
                    'completeness': completeness,
                    'validity': validity
                }
                
                status = "✅" if completeness >= 90 else "⚠️" if completeness >= 50 else "❌"
                print(f"{status} {field:25s} 完整性: {has_data:3d}/{total:3d} ({completeness:5.1f}%)  有效性: {has_valid:3d}/{total:3d} ({validity:5.1f}%)")
        
        
        # 3. 按评分维度汇总
        print("\n【3. 按评分维度汇总】")
        print("-" * 80)
        
        dimension_stats = {}
        
        # 成长性（25%）
        growth_fields = ['revenue_growth_yoy', 'profit_growth_yoy', 'profit_volatility']
        growth_completeness = []
        for field in growth_fields:
            if field in fundamental_stats:
                growth_completeness.append(fundamental_stats[field]['completeness'])
        avg_growth = sum(growth_completeness) / len(growth_completeness) if growth_completeness else 0
        dimension_stats['成长性'] = avg_growth
        status = "✅" if avg_growth >= 90 else "⚠️" if avg_growth >= 50 else "❌"
        print(f"{status} 成长性 (25%): {avg_growth:.1f}%")
        for field in growth_fields:
            if field in fundamental_stats:
                print(f"    - {fundamental_stats[field]['completeness']:.1f}% {field}")
        
        # 盈利能力（25%）
        profit_fields = ['roe_ttm', 'net_margin_ttm']
        profit_completeness = []
        for field in profit_fields:
            if field in fundamental_stats:
                profit_completeness.append(fundamental_stats[field]['completeness'])
        avg_profit = sum(profit_completeness) / len(profit_completeness) if profit_completeness else 0
        dimension_stats['盈利能力'] = avg_profit
        status = "✅" if avg_profit >= 90 else "⚠️" if avg_profit >= 50 else "❌"
        print(f"{status} 盈利能力 (25%): {avg_profit:.1f}%")
        for field in profit_fields:
            if field in fundamental_stats:
                print(f"    - {fundamental_stats[field]['completeness']:.1f}% {field}")
        
        # 财务健康度（15%）
        health_fields = ['roe_ttm', 'op_cf_ttm', 'debt_ratio', 'net_margin_ttm']
        health_completeness = []
        for field in health_fields:
            if field in fundamental_stats:
                health_completeness.append(fundamental_stats[field]['completeness'])
        avg_health = sum(health_completeness) / len(health_completeness) if health_completeness else 0
        dimension_stats['财务健康度'] = avg_health
        status = "✅" if avg_health >= 90 else "⚠️" if avg_health >= 50 else "❌"
        print(f"{status} 财务健康度 (15%): {avg_health:.1f}%")
        for field in health_fields:
            if field in fundamental_stats:
                print(f"    - {fundamental_stats[field]['completeness']:.1f}% {field}")
        
        # 成本优势/竞争优势（10%）
        moat_fields = ['gross_margin_ttm']
        moat_completeness = []
        for field in moat_fields:
            if field in fundamental_stats:
                moat_completeness.append(fundamental_stats[field]['completeness'])
        avg_moat = sum(moat_completeness) / len(moat_completeness) if moat_completeness else 0
        dimension_stats['成本优势/竞争优势'] = avg_moat
        status = "✅" if avg_moat >= 90 else "⚠️" if avg_moat >= 50 else "❌"
        print(f"{status} 成本优势/竞争优势 (10%): {avg_moat:.1f}%")
        for field in moat_fields:
            if field in fundamental_stats:
                print(f"    - {fundamental_stats[field]['completeness']:.1f}% {field}")
        print("    - 行业集中度CR4: 暂无数据")
        print("    - 市场份额: 暂无数据")
        
        # 估值（15%）
        valuation_fields = ['pe_ttm', 'pb_lyr']
        valuation_completeness = []
        for field in valuation_fields:
            # PE和PB在fundamental_stats中
            if field in fundamental_stats:
                valuation_completeness.append(fundamental_stats[field]['completeness'])
        avg_valuation = sum(valuation_completeness) / len(valuation_completeness) if valuation_completeness else 0
        dimension_stats['估值'] = avg_valuation
        status = "✅" if avg_valuation >= 90 else "⚠️" if avg_valuation >= 50 else "❌"
        print(f"{status} 估值 (15%): {avg_valuation:.1f}%")
        for field in valuation_fields:
            if field in fundamental_stats:
                print(f"    - {fundamental_stats[field]['completeness']:.1f}% {field}")
        
        # 资金行为与趋势（10%）
        behavior_fields = ['amount', 'turnover_rate', 'ma20', 'close', 'change_pct']
        behavior_completeness = []
        for field in behavior_fields:
            if field in price_stats:
                behavior_completeness.append(price_stats[field]['completeness'])
        avg_behavior = sum(behavior_completeness) / len(behavior_completeness) if behavior_completeness else 0
        dimension_stats['资金行为与趋势'] = avg_behavior
        status = "✅" if avg_behavior >= 90 else "⚠️" if avg_behavior >= 50 else "❌"
        print(f"{status} 资金行为与趋势 (10%): {avg_behavior:.1f}%")
        for field in behavior_fields:
            if field in price_stats:
                print(f"    - {price_stats[field]['completeness']:.1f}% {field}")
        
        # 4. 总体数据质量评分
        print("\n【4. 总体数据质量评分】")
        print("-" * 80)
        
        # 按权重计算加权平均
        weighted_score = (
            avg_growth * 0.25 +
            avg_profit * 0.25 +
            avg_health * 0.15 +
            avg_moat * 0.10 +
            avg_valuation * 0.15 +
            avg_behavior * 0.10
        )
        
        print(f"加权平均数据完整性: {weighted_score:.1f}%")
        
        if weighted_score >= 90:
            print("✅ 数据质量优秀，可以正常进行达尔文评分")
        elif weighted_score >= 70:
            print("⚠️  数据质量良好，部分维度数据可能缺失，评分结果可能受影响")
        elif weighted_score >= 50:
            print("⚠️  数据质量一般，多个维度数据缺失，建议补充数据后再进行评分")
        else:
            print("❌ 数据质量较差，大量数据缺失，无法进行可靠的达尔文评分")
        
        # 5. 缺失数据最多的股票
        print("\n【5. 数据缺失最多的股票（前10只）】")
        print("-" * 80)
        
        # 计算每只股票的数据完整性
        field_count = len(fundamental_fields)
        query_fields = []
        field_sums = []
        for i, field in enumerate(fundamental_fields, 1):
            query_fields.append(f"COUNT(CASE WHEN {field} IS NOT NULL THEN 1 END) as has_{field}")
            field_sums.append(f"COUNT(CASE WHEN {field} IS NOT NULL THEN 1 END)")
        
        # 构建查询字段列表
        field_sum = ' + '.join(field_sums)
        query_sql = f'''
            SELECT 
                ts_code,
                {', '.join(query_fields)}
            FROM fact_daily_fundamental
            WHERE ts_code = ANY(:ts_codes)
              AND trade_date = :trade_date
            GROUP BY ts_code
            ORDER BY ({field_sum}) ASC
            LIMIT 10
        '''
        
        query = text(query_sql)
        result = session.execute(query, {'ts_codes': s1_ts_codes, 'trade_date': trade_date})
        print("股票代码    缺失字段数")
        for row in result:
            # 计算有数据的字段数
            has_count = sum([1 for i in range(1, len(fundamental_fields) + 1) if row[i] > 0])
            missing_count = field_count - has_count
            print(f"{row[0]:15s} {missing_count}")
        
        print("\n" + "=" * 80)
        print("报告生成完成")
        print("=" * 80)
        
    except Exception as e:
        logger.error(f"生成报告失败: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == "__main__":
    generate_darwin_data_quality_report()

