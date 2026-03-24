"""
股票评分服务
从 app.py 提取评分逻辑，封装为 StockScorer 类
"""

import pandas as pd
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StockScorer:
    """股票评分服务类"""
    
    def score_short_term(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        短线票评分：计算埋伏强度
        
        评分公式：
        埋伏强度 = (涨幅-1.0)*0.3 + (换手率-3.0)*0.4 + (成交额/10亿)*0.3
        
        Args:
            df: 筛选后的股票数据DataFrame
            
        Returns:
            DataFrame: 添加了'埋伏强度'列的DataFrame
        """
        try:
            if df.empty:
                logger.warning("输入数据为空，无法评分")
                return df
            
            required_cols = ['pct_chg', 'turnover_rate', 'amount']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.warning(f"缺少必要字段: {missing_cols}，无法计算评分")
                return df
            
            # 计算埋伏强度
            df['埋伏强度'] = (
                (df['pct_chg'] - 1.0) * 0.3 +    # 涨幅权重30%（1%-5%范围，适中最好）
                (df['turnover_rate'] - 3.0) * 0.4 +  # 换手率权重40%（≥3%即可）
                (df['amount'] / 1000000000) * 0.3  # 成交额权重30%（≥8亿）
            )
            
            logger.info(f"成功计算短线票评分，共 {len(df)} 只股票")
            return df
            
        except Exception as e:
            logger.error(f"短线票评分失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return df
    
    def score_swing_term(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        波段票评分：计算趋势强度
        
        评分公式：
        趋势强度 = (涨幅+2.0)*0.5 + (换手率-1.0)*0.3 + (成交额/1亿)*0.2
        
        Args:
            df: 筛选后的股票数据DataFrame
            
        Returns:
            DataFrame: 添加了'趋势强度'列的DataFrame
        """
        try:
            if df.empty:
                logger.warning("输入数据为空，无法评分")
                return df
            
            required_cols = ['pct_chg', 'turnover_rate', 'amount']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.warning(f"缺少必要字段: {missing_cols}，无法计算评分")
                return df
            
            # 计算趋势强度
            df['趋势强度'] = (
                (df['pct_chg'] + 2.0) * 0.5 +    # 涨幅权重50%（-3%~5%范围）
                (df['turnover_rate'] - 1.0) * 0.3 +  # 换手率权重30%（1%-12%范围）
                (df['amount'] / 100000000) * 0.2  # 成交额权重20%（≥3亿）
            )
            
            logger.info(f"成功计算波段票评分，共 {len(df)} 只股票")
            return df
            
        except Exception as e:
            logger.error(f"波段票评分失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return df
    
    def calculate_buy_range(self, price: float, strategy_type: str) -> Dict[str, float]:
        """
        计算入手价格区间
        
        Args:
            price: 当前价格
            strategy_type: 策略类型（"短线票" 或 "波段票"）
            
        Returns:
            dict: {"min": float, "max": float}
        """
        try:
            if strategy_type == "短线票":
                # 短线票：价格区间相对紧凑（98%-102%），追求精准时机
                price_low = round(price * 0.98, 2)
                price_high = round(price * 1.02, 2)
            elif strategy_type == "波段票":
                # 波段票：价格区间相对宽松（95%-105%），有时间等待更好价位
                price_low = round(price * 0.95, 2)
                price_high = round(price * 1.05, 2)
            else:
                # 默认策略：中等价格区间（96%-104%）
                price_low = round(price * 0.96, 2)
                price_high = round(price * 1.04, 2)
            
            return {"min": price_low, "max": price_high}
            
        except Exception as e:
            logger.error(f"计算入手价格区间失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return {"min": price * 0.95, "max": price * 1.05}
    
    def generate_reason(self, stock: Dict, strategy_type: str) -> str:
        """
        生成推荐理由
        
        Args:
            stock: 股票数据字典（包含 pct_chg, turnover_rate, amount 等字段）
            strategy_type: 策略类型（"短线票" 或 "波段票"）
            
        Returns:
            str: 推荐理由文本
        """
        try:
            change_pct = stock.get('pct_chg', 0.0)
            turnover = stock.get('turnover_rate', 0)
            amount = stock.get('amount', 0)
            amount_yi = amount / 100000000 if amount > 0 else 0  # 转换为亿元
            
            if strategy_type == "短线票":
                if change_pct >= 4.0:
                    reason = f"埋伏突破(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，成交{amount_yi:.1f}亿，即将启动"
                elif change_pct >= 2.0:
                    reason = f"低位启动(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，成交{amount_yi:.1f}亿，埋伏机会"
                else:
                    reason = f"刚启动(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，成交{amount_yi:.1f}亿，低位埋伏"
            elif strategy_type == "波段票":
                if change_pct >= 3.0:
                    reason = f"突破型(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，趋势突破"
                elif change_pct >= 0:
                    reason = f"稳健型(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，技术支撑"
                else:
                    reason = f"超跌反弹(涨幅{change_pct:.2f}%)，换手{turnover:.2f}%，价值回归"
            else:
                # 默认策略
                if change_pct > 2:
                    reason = f"温和上涨{change_pct:.2f}%，换手率{turnover:.2f}%"
                elif change_pct > 0:
                    reason = f"微涨{change_pct:.2f}%，换手率{turnover:.2f}%"
                elif change_pct > -2:
                    reason = f"小幅调整{change_pct:.2f}%，换手率{turnover:.2f}%"
                else:
                    reason = f"深度调整{change_pct:.2f}%，换手率{turnover:.2f}%"
            
            return reason
            
        except Exception as e:
            logger.error(f"生成推荐理由失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return "数据异常，无法生成推荐理由"

