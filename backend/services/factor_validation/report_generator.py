"""
因子有效性报告生成器

生成HTML/JSON格式的因子分析报告
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import date, datetime
import json

from .factor_validator import FactorValidator, FactorValidationResult

logger = logging.getLogger(__name__)


class FactorReportGenerator:
    """
    因子报告生成器

    生成格式：
    - HTML报告：可视化展示
    - JSON报告：供API调用
    - Markdown报告：便于分享
    """

    def __init__(self):
        pass

    def generate_html_report(
        self,
        results: Dict[str, FactorValidationResult],
        report_title: str = "因子有效性分析报告",
    ) -> str:
        """
        生成HTML报告

        Args:
            results: 各因子的验证结果
            report_title: 报告标题

        Returns:
            str: HTML内容
        """
        html_parts = []

        # HTML头部
        html_parts.append(self._get_html_header(report_title))

        # 报告摘要
        html_parts.append(self._generate_summary_section(results))

        # 各因子详细分析
        for factor_name, result in results.items():
            html_parts.append(self._generate_factor_section(factor_name, result))

        # 综合建议
        html_parts.append(self._generate_recommendations_section(results))

        # HTML尾部
        html_parts.append(self._get_html_footer())

        return "\n".join(html_parts)

    def generate_json_report(
        self,
        results: Dict[str, FactorValidationResult],
    ) -> Dict[str, Any]:
        """生成JSON格式的报告"""
        return {
            'report_type': '因子有效性分析',
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_factors': len(results),
                'grade_distribution': self._get_grade_distribution(results),
                'valid_factors': sum(1 for r in results.values() if r.overall_grade in ['A', 'B']),
            },
            'factors': {name: result.to_dict() for name, result in results.items()},
        }

    def generate_markdown_report(
        self,
        results: Dict[str, FactorValidationResult],
    ) -> str:
        """生成Markdown格式的报告"""
        lines = []

        lines.append("# 因子有效性分析报告")
        lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # 摘要
        lines.append("## 执行摘要\n")
        lines.append(f"- 分析因子数: {len(results)}")
        lines.append(f"- 有效因子数(A/B级): {sum(1 for r in results.values() if r.overall_grade in ['A', 'B'])}")
        lines.append(f"- 无效因子数(C级): {sum(1 for r in results.values() if r.overall_grade == 'C')}\n")

        # 各因子详情
        for factor_name, result in results.items():
            lines.append(f"## {factor_name}\n")
            lines.append(f"**综合等级**: {result.overall_grade} (得分: {result.overall_score:.2f})\n")

            if result.ic_result:
                lines.append("### IC分析\n")
                lines.append(f"- IC均值: {result.ic_result.ic_mean:.4f}")
                lines.append(f"- IC IR: {result.ic_result.ic_ir:.4f}")
                lines.append(f"- 正IC比例: {result.ic_result.ic_positive_ratio:.2%}\n")

            if result.layered_result:
                lines.append("### 分层回测\n")
                lines.append(f"- 单调性得分: {result.layered_result.monotonicity_score:.4f}")
                lines.append(f"- 多空收益: {result.layered_result.long_short_return:.4f}")
                lines.append(f"- 多空夏普: {result.layered_result.long_short_sharpe:.4f}\n")

            if result.recommendations:
                lines.append("### 改进建议\n")
                for rec in result.recommendations:
                    lines.append(f"- {rec}")
                lines.append("")

        return "\n".join(lines)

    def _get_html_header(self, title: str) -> str:
        """获取HTML头部"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f7fa;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .header p {{
            margin: 0;
            opacity: 0.9;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .card h3 {{
            margin: 0 0 15px 0;
            color: #333;
            font-size: 16px;
        }}
        .grade-badge {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
        }}
        .grade-A {{ background: #52c41a; color: white; }}
        .grade-B {{ background: #faad14; color: white; }}
        .grade-C {{ background: #f5222d; color: white; }}
        .factor-section {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .factor-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e8e8e8;
        }}
        .factor-header h2 {{
            margin: 0;
            color: #333;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric {{
            background: #f6f8fa;
            padding: 15px;
            border-radius: 8px;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: bold;
            color: #333;
        }}
        .metric-value.positive {{ color: #52c41a; }}
        .metric-value.negative {{ color: #f5222d; }}
        .recommendations {{
            background: #fff7e6;
            border-left: 4px solid #faad14;
            padding: 15px;
            border-radius: 0 8px 8px 0;
        }}
        .recommendations h4 {{
            margin: 0 0 10px 0;
            color: #d46b08;
        }}
        .recommendations ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .recommendations li {{
            margin-bottom: 5px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
"""

    def _generate_summary_section(self, results: Dict[str, FactorValidationResult]) -> str:
        """生成摘要部分"""
        total = len(results)
        valid = sum(1 for r in results.values() if r.overall_grade in ['A', 'B'])
        invalid = total - valid

        grade_a = sum(1 for r in results.values() if r.overall_grade == 'A')
        grade_b = sum(1 for r in results.values() if r.overall_grade == 'B')
        grade_c = sum(1 for r in results.values() if r.overall_grade == 'C')

        return f"""
        <div class="summary-cards">
            <div class="card">
                <h3>分析因子总数</h3>
                <div class="metric-value">{total}</div>
            </div>
            <div class="card">
                <h3>有效因子(A/B级)</h3>
                <div class="metric-value positive">{valid}</div>
            </div>
            <div class="card">
                <h3>无效因子(C级)</h3>
                <div class="metric-value negative">{invalid}</div>
            </div>
            <div class="card">
                <h3>等级分布</h3>
                <div style="margin-top: 10px;">
                    <span class="grade-badge grade-A">A: {grade_a}</span>
                    <span class="grade-badge grade-B" style="margin-left: 8px;">B: {grade_b}</span>
                    <span class="grade-badge grade-C" style="margin-left: 8px;">C: {grade_c}</span>
                </div>
            </div>
        </div>
"""

    def _generate_factor_section(self, factor_name: str, result: FactorValidationResult) -> str:
        """生成单个因子的分析部分"""
        grade_class = f"grade-{result.overall_grade}"

        html = f"""
        <div class="factor-section">
            <div class="factor-header">
                <h2>{factor_name}</h2>
                <span class="grade-badge {grade_class}">
                    等级 {result.overall_grade} (得分: {result.overall_score:.1f})
                </span>
            </div>
            <div class="metrics-grid">
"""

        # IC指标
        if result.ic_result:
            ic_class = "positive" if result.ic_result.ic_mean > 0 else "negative"
            html += f"""
                <div class="metric">
                    <div class="metric-label">IC均值</div>
                    <div class="metric-value {ic_class}">{result.ic_result.ic_mean:.4f}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">IC IR</div>
                    <div class="metric-value">{result.ic_result.ic_ir:.4f}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">正IC比例</div>
                    <div class="metric-value">{result.ic_result.ic_positive_ratio:.2%}</div>
                </div>
"""

        # 分层回测指标
        if result.layered_result:
            html += f"""
                <div class="metric">
                    <div class="metric-label">单调性得分</div>
                    <div class="metric-value">{result.layered_result.monotonicity_score:.4f}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">多空收益</div>
                    <div class="metric-value">{result.layered_result.long_short_return:.2%}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">多空夏普</div>
                    <div class="metric-value">{result.layered_result.long_short_sharpe:.4f}</div>
                </div>
"""

        html += "</div>"  # 关闭 metrics-grid

        # 改进建议
        if result.recommendations:
            html += """
            <div class="recommendations">
                <h4>改进建议</h4>
                <ul>
"""
            for rec in result.recommendations:
                html += f"<li>{rec}</li>"
            html += """
                </ul>
            </div>
"""

        html += "</div>"  # 关闭 factor-section
        return html

    def _generate_recommendations_section(self, results: Dict[str, FactorValidationResult]) -> str:
        """生成综合建议部分"""
        all_recommendations = []
        for result in results.values():
            all_recommendations.extend(result.recommendations)

        # 去重
        unique_recommendations = list(set(all_recommendations))

        if not unique_recommendations or unique_recommendations == ["因子表现良好"]:
            return ""

        html = """
        <div class="factor-section">
            <div class="factor-header">
                <h2>综合改进建议</h2>
            </div>
            <div class="recommendations">
                <ul>
"""
        for rec in unique_recommendations[:10]:  # 最多显示10条
            if rec != "因子表现良好":
                html += f"<li>{rec}</li>"

        html += """
                </ul>
            </div>
        </div>
"""
        return html

    def _get_html_footer(self) -> str:
        """获取HTML尾部"""
        return """
    </div>
</body>
</html>
"""

    def _get_grade_distribution(self, results: Dict[str, FactorValidationResult]) -> Dict[str, int]:
        """获取等级分布"""
        distribution = {'A': 0, 'B': 0, 'C': 0}
        for result in results.values():
            if result.overall_grade in distribution:
                distribution[result.overall_grade] += 1
        return distribution


# 便捷函数
def run_factor_validation(
    warehouse_service=None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> str:
    """
    运行完整的因子验证流程并生成报告

    Returns:
        str: HTML报告内容
    """
    validator = FactorValidator(warehouse_service)
    generator = FactorReportGenerator()

    # 获取因子数据
    logger.info("获取龙头跟踪因子数据...")
    factor_data = validator.get_leader_tracking_factors(start_date, end_date)

    # 验证因子
    logger.info("开始验证因子...")
    results = validator.validate_multiple(factor_data)

    # 生成报告
    logger.info("生成报告...")
    report = generator.generate_html_report(results)

    return report
