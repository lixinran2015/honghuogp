"""
因子验证测试脚本

运行Phase 1的因子有效性验证
"""

import sys
import os
# 添加项目根目录到Python路径
project_root = os.path.join(os.path.dirname(__file__), '../..')
sys.path.insert(0, os.path.abspath(project_root))

import logging
from datetime import date, timedelta
import pandas as pd
import numpy as np

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_factor_validation():
    """测试因子验证系统"""
    print("=" * 60)
    print("Phase 1: 因子有效性验证测试")
    print("=" * 60)

    try:
        # 导入验证模块
        from backend.services.factor_validation import (
            FactorValidator,
            FactorReportGenerator,
            ICAnalyzer,
            LayeredBacktest,
            VIFAnalyzer,
        )
        from data_warehouse.service.warehouse_service import WarehouseService

        print("\n✅ 模块导入成功")

        # 初始化服务
        ws = WarehouseService()
        validator = FactorValidator(ws)

        # 检查数据表是否存在
        print("\n📊 检查数据表...")
        session = ws.get_session()
        try:
            from sqlalchemy import text

            # 检查fact_leader_score_history表
            check_query = text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'fact_leader_score_history'
            """)
            result = session.execute(check_query).scalar()

            if result == 0:
                print("❌ fact_leader_score_history表不存在")
                print("   请先运行龙头评分同步: POST /api/leader-score/sync-pool")
                return False

            # 检查数据量
            count_query = text("SELECT COUNT(*) FROM fact_leader_score_history")
            count = session.execute(count_query).scalar()
            print(f"   fact_leader_score_history: {count}条记录")

            if count < 100:
                print("⚠️  数据量不足，建议先同步更多数据")

        finally:
            session.close()

        # 获取因子数据
        print("\n📈 获取因子数据...")
        end_date = date.today()
        start_date = end_date - timedelta(days=90)  # 最近3个月

        factor_data = validator.get_leader_tracking_factors(start_date, end_date)

        if not factor_data:
            print("❌ 未获取到因子数据")
            return False

        print(f"   获取到 {len(factor_data)} 个因子:")
        for name, df in factor_data.items():
            print(f"   - {name}: {len(df)}条记录")

        # 运行IC分析
        print("\n🔍 运行IC分析...")
        ic_analyzer = ICAnalyzer(ws)
        ic_results = {}

        for factor_name, df in factor_data.items():
            try:
                result = ic_analyzer.analyze_factor(
                    factor_name=factor_name,
                    factor_data=df,
                    forward_return_days=5,
                )
                ic_results[factor_name] = result

                valid_mark = "✅" if result.is_valid() else "❌"
                print(f"   {valid_mark} {factor_name}:")
                print(f"      IC均值: {result.ic_mean:.4f} (|IC|>0.03)")
                print(f"      IC IR: {result.ic_ir:.4f} (>0.5)")
                print(f"      等级: {result.get_grade()}")
            except Exception as e:
                print(f"   ❌ {factor_name}分析失败: {e}")

        # 运行分层回测
        print("\n📊 运行分层回测...")
        layered_backtest = LayeredBacktest(ws)
        layered_results = {}

        for factor_name, df in factor_data.items():
            try:
                result = layered_backtest.run(
                    factor_name=factor_name,
                    factor_data=df,
                    num_layers=5,
                    holding_period=5,
                )
                layered_results[factor_name] = result

                valid_mark = "✅" if result.is_monotonic() else "❌"
                print(f"   {valid_mark} {factor_name}:")
                print(f"      单调性得分: {result.monotonicity_score:.4f} (>0.6)")
                print(f"      多空夏普: {result.long_short_sharpe:.4f}")
                print(f"      等级: {result.get_grade()}")
            except Exception as e:
                print(f"   ❌ {factor_name}分层回测失败: {e}")

        # 运行VIF分析
        print("\n🔗 运行VIF分析...")
        try:
            vif_analyzer = VIFAnalyzer()

            # 合并因子数据
            merged_df = None
            for factor_name, df in factor_data.items():
                df_copy = df[['ts_code', 'trade_date', 'factor_value']].copy()
                df_copy.columns = ['ts_code', 'trade_date', factor_name]

                if merged_df is None:
                    merged_df = df_copy
                else:
                    merged_df = merged_df.merge(
                        df_copy,
                        on=['ts_code', 'trade_date'],
                        how='outer'
                    )

            # 标准化
            for col in factor_data.keys():
                if col in merged_df.columns:
                    merged_df[col] = (merged_df[col] - merged_df[col].mean()) / merged_df[col].std()

            # 运行VIF
            vif_results = vif_analyzer.analyze(merged_df[list(factor_data.keys())])

            print("   VIF结果 (VIF<3为良好):")
            for name, result in vif_results.items():
                valid_mark = "✅" if result.vif_value < 3 else "⚠️"
                print(f"   {valid_mark} {name}: VIF={result.vif_value:.4f} ({result.get_status()})")

        except Exception as e:
            print(f"   ❌ VIF分析失败: {e}")

        # 生成综合报告
        print("\n📋 生成综合验证报告...")
        generator = FactorReportGenerator()

        # 手动构建验证结果
        validation_results = {}
        for factor_name in factor_data.keys():
            from backend.services.factor_validation.factor_validator import (
                FactorValidationResult, ICResult, LayeredResult
            )

            ic_result = ic_results.get(factor_name)
            layered_result = layered_results.get(factor_name)

            # 计算综合得分
            overall_score = 0
            if ic_result:
                overall_score += 40 if abs(ic_result.ic_mean) > 0.03 else 0
                overall_score += 20 if ic_result.ic_ir > 0.5 else 0
            if layered_result:
                overall_score += 40 * layered_result.monotonicity_score

            # 确定等级
            if overall_score >= 80:
                overall_grade = 'A'
            elif overall_score >= 60:
                overall_grade = 'B'
            else:
                overall_grade = 'C'

            validation_results[factor_name] = FactorValidationResult(
                factor_name=factor_name,
                ic_result=ic_result,
                layered_result=layered_result,
                vif_result=vif_results.get(factor_name),
                overall_score=overall_score,
                overall_grade=overall_grade,
                recommendations=[],
            )

        # 打印摘要
        print("\n" + "=" * 60)
        print("验证结果摘要")
        print("=" * 60)

        valid_count = sum(1 for r in validation_results.values() if r.overall_grade in ['A', 'B'])
        print(f"\n有效因子(A/B级): {valid_count}/{len(validation_results)}")

        for name, result in validation_results.items():
            status = "✅ 有效" if result.overall_grade in ['A', 'B'] else "❌ 需优化"
            print(f"\n{name}:")
            print(f"   等级: {result.overall_grade} (得分: {result.overall_score:.1f}) {status}")

            if result.ic_result:
                print(f"   IC: {result.ic_result.ic_mean:.4f} (IR={result.ic_result.ic_ir:.2f})")
            if result.layered_result:
                print(f"   分层: 单调性={result.layered_result.monotonicity_score:.2f}")

        # 保存HTML报告
        report_path = "factor_validation_report.html"
        html_report = generator.generate_html_report(validation_results)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_report)
        print(f"\n📄 HTML报告已保存: {report_path}")

        # 生成Markdown报告
        md_report = generator.generate_markdown_report(validation_results)
        md_path = "factor_validation_report.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_report)
        print(f"📄 Markdown报告已保存: {md_path}")

        print("\n" + "=" * 60)
        print("✅ 因子验证测试完成")
        print("=" * 60)

        return True

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 测试失败: {e}")
        return False


if __name__ == "__main__":
    success = test_factor_validation()
    sys.exit(0 if success else 1)
