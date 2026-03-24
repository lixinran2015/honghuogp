"""
报告生成服务
自动生成每日/每周投研报告
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


class ReportGenerator:
    """报告生成服务类"""
    
    def __init__(self):
        self.output_dir = project_root / "output"
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_short_term_report(self, short_stocks: List[Dict], market_summary: Dict) -> str:
        """
        生成每日短线战报
        
        Args:
            short_stocks: 短线推荐股票列表
            market_summary: 市场概况
            
        Returns:
            str: 报告文件路径
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = self.output_dir / f"ShortTerm_Report_{date_str}.md"
            
            # 筛选ShortScore ≥ 85的股票（次日涨停候选）
            limit_up_candidates = [s for s in short_stocks if s.get('综合得分', 0) >= 85]
            
            content = f"""# 每日短线战报

**日期**: {datetime.now().strftime("%Y-%m-%d")}

## 市场概况

- 上证指数: {market_summary.get('indices', {}).get('sse', {}).get('value', 0):.2f} ({market_summary.get('indices', {}).get('sse', {}).get('changePct', 0):+.2f}%)
- 深证成指: {market_summary.get('indices', {}).get('szse', {}).get('value', 0):.2f} ({market_summary.get('indices', {}).get('szse', {}).get('changePct', 0):+.2f}%)

## 今日主线板块

（待实现：板块热度分析）

## 次日涨停候选（ShortScore ≥ 85）

共 {len(limit_up_candidates)} 只股票：

"""
            
            for idx, stock in enumerate(limit_up_candidates[:10], 1):
                content += f"""
### {idx}. {stock.get('股票名称', '')} ({stock.get('代码', '')})

- **当前价格**: ¥{stock.get('最新价', 0):.2f}
- **涨幅**: {stock.get('涨跌幅', 0):+.2f}%
- **换手率**: {stock.get('换手率', '0%')}
- **成交额**: {stock.get('成交额', 0)/100000000:.2f} 亿
- **综合得分**: {stock.get('综合得分', 0):.2f}
- **买点**: {stock.get('入手价格区间', 'N/A')}
- **推荐理由**: {stock.get('推荐理由', '')}

"""
            
            content += """
## 风险提示

1. 短线交易风险较高，请控制仓位
2. 注意市场情绪变化，及时止盈止损
3. 关注板块轮动，避免追高
"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ 生成每日短线战报: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 生成每日短线战报失败: {e}", exc_info=True)
            return ""
    
    def generate_middle_term_report(self, swing_stocks: List[Dict]) -> str:
        """
        生成每周波段报告
        
        Args:
            swing_stocks: 波段推荐股票列表
            
        Returns:
            str: 报告文件路径
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = self.output_dir / f"MiddleTerm_Report_{date_str}.md"
            
            content = f"""# 每周波段报告

**日期**: {datetime.now().strftime("%Y-%m-%d")}

## 波段候选

共 {len(swing_stocks)} 只股票：

"""
            
            for idx, stock in enumerate(swing_stocks[:10], 1):
                content += f"""
### {idx}. {stock.get('股票名称', '')} ({stock.get('代码', '')})

- **当前价格**: ¥{stock.get('最新价', 0):.2f}
- **涨幅**: {stock.get('涨跌幅', 0):+.2f}%
- **换手率**: {stock.get('换手率', '0%')}
- **综合得分**: {stock.get('综合得分', 0):.2f}
- **建仓区间**: {stock.get('入手价格区间', 'N/A')}
- **推荐理由**: {stock.get('推荐理由', '')}

"""
            
            content += """
## 技术图形分析

（待实现：技术指标分析）

## 建仓建议

1. 建议分批建仓，控制单只股票仓位
2. 关注技术支撑位，设置止损点
3. 波段持有时间建议1-3个月
"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ 生成每周波段报告: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 生成每周波段报告失败: {e}", exc_info=True)
            return ""
    
    def generate_long_term_report(self, long_stocks: List[Dict]) -> str:
        """
        生成长期价值报告
        
        Args:
            long_stocks: 长线推荐股票列表
            
        Returns:
            str: 报告文件路径
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = self.output_dir / f"LongTerm_Report_{date_str}.md"
            
            content = f"""# 长期价值报告

**日期**: {datetime.now().strftime("%Y-%m-%d")}

## 当前最值得投资的长期公司

共 {len(long_stocks)} 只股票：

"""
            
            for idx, stock in enumerate(long_stocks[:10], 1):
                content += f"""
### {idx}. {stock.get('股票名称', '')} ({stock.get('代码', '')})

- **当前价格**: ¥{stock.get('最新价', 0):.2f}
- **达尔文评分**: {stock.get('达尔文评分', 0):.2f}
- **财务健康系数**: {stock.get('财务健康系数', 0):.2f}
- **综合得分**: {stock.get('综合得分', 0):.2f}
- **建仓区间**: {stock.get('建仓区间', 'N/A')}
- **风险清单**: {stock.get('风险提示', '无')}

"""
            
            content += """
## 风险提示

1. 长期投资需要耐心，建议持有1年以上
2. 关注公司基本面变化
3. 定期回顾投资组合
"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ 生成长期价值报告: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 生成长期价值报告失败: {e}", exc_info=True)
            return ""
    
    def generate_fund_report(self, fund_recommendations: List[Dict]) -> str:
        """
        生成基金定投报告
        
        Args:
            fund_recommendations: 基金定投建议列表
            
        Returns:
            str: 报告文件路径
        """
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            file_path = self.output_dir / f"Fund_Report_{date_str}.md"
            
            content = f"""# 基金定投报告

**日期**: {datetime.now().strftime("%Y-%m-%d")}

## 本周定投建议

"""
            
            for rec in fund_recommendations:
                rec_type = {
                    'increase': '加仓',
                    'normal': '正常定投',
                    'pause': '暂停定投',
                    'unknown': '未知'
                }.get(rec.get('recommendation', 'unknown'), '未知')
                
                content += f"""
### {rec.get('name', '')} ({rec.get('code', '')})

- **建议**: {rec_type}
- **理由**: {rec.get('reason', '')}
- **PE分位数**: {rec.get('pe_percentile', 0):.1f}%
- **PB分位数**: {rec.get('pb_percentile', 0):.1f}%
- **当前PE**: {rec.get('pe', 0):.2f}
- **当前PB**: {rec.get('pb', 0):.2f}

"""
            
            content += """
## 分位数统计

（待实现：详细分位数统计）

## 推荐指数

建议重点关注PE分位数较低的指数，分批定投。
"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ 生成基金定投报告: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"❌ 生成基金定投报告失败: {e}", exc_info=True)
            return ""

