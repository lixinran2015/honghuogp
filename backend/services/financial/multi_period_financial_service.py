"""
多期财务数据获取服务
用于获取连续3-5期财务数据，验证指标连续性
优先从本地 fact_fundamental 读取，不足时再调 Tushare
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MultiPeriodFinancialService:
    """多期财务数据获取服务（本地优先，Tushare 兜底）"""
    
    def __init__(self, tushare_service=None):
        """
        初始化多期财务数据服务
        
        Args:
            tushare_service: TushareService实例，如果为None则自动创建
        """
        if tushare_service is None:
            from backend.services.tushare_service import TushareService
            self.tushare_service = TushareService()
        else:
            self.tushare_service = tushare_service

    def _get_from_fact_fundamental(
        self,
        ts_code: str,
        periods: int,
        freq: str
    ) -> Optional[pd.DataFrame]:
        """从本地 fact_fundamental 表读取多期数据（无 Tushare 调用）"""
        try:
            from sqlalchemy import text
            from data_warehouse.db import get_shared_engine
            engine = get_shared_engine()
            start_date = (datetime.now() - timedelta(days=max(periods * 365, 730))).strftime('%Y-%m-%d')
            with engine.connect() as conn:
                df = pd.read_sql(
                    text("""
                        SELECT ts_code, end_date, roe, net_margin, gross_margin, op_cf, net_profit, revenue,
                               operate_profit, fin_exp
                        FROM fact_fundamental
                        WHERE ts_code = :ts_code AND end_date >= :start_date
                        ORDER BY end_date DESC
                        LIMIT :limit
                    """),
                    conn,
                    params={'ts_code': ts_code, 'start_date': start_date, 'limit': periods * 2}
                )
            if df is None or df.empty:
                return None
            df = df.drop_duplicates(subset=['ts_code', 'end_date'], keep='first')
            df['end_date'] = pd.to_datetime(df['end_date']).dt.strftime('%Y%m%d').astype(str)
            df['n_income_attr_p'] = pd.to_numeric(df.get('net_profit', pd.Series(dtype=float)), errors='coerce')
            df['ocf'] = pd.to_numeric(df.get('op_cf', pd.Series(dtype=float)), errors='coerce')
            if 'operate_profit' in df.columns:
                df['operate_profit'] = pd.to_numeric(df['operate_profit'], errors='coerce')
            if 'fin_exp' in df.columns:
                df['fin_exp'] = pd.to_numeric(df['fin_exp'], errors='coerce')
            df['revenue'] = pd.to_numeric(df.get('revenue', pd.Series(dtype=float)), errors='coerce')
            df['net_profit'] = pd.to_numeric(df.get('net_profit', pd.Series(dtype=float)), errors='coerce')
            for col in ['roe', 'net_margin', 'gross_margin']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    df[col] = df[col].apply(lambda x: x / 100 if pd.notna(x) and abs(x) > 1 else x)
            df['month'] = df['end_date'].str[4:6].astype(int)
            if freq == 'Y':
                df = df[df['month'] == 12]
            else:
                df = df[df['month'].isin([3, 6, 9, 12])]
            df = df.drop(columns=['month'], errors='ignore').head(periods)
            if len(df) < (2 if freq == 'Y' else 2):
                return None
            logger.debug(f"{ts_code} 从 fact_fundamental 读取 {len(df)} 期数据（freq={freq}）")
            return df.reset_index(drop=True)
        except Exception as e:
            logger.debug(f"从 fact_fundamental 读取失败 {ts_code}: {e}")
            return None

    def get_goodwill_equity_from_local(self, ts_code: str) -> Optional[tuple[float, float]]:
        """从本地 fact_fundamental 读取最新 goodwill、total_equity（商誉检查用）"""
        try:
            from sqlalchemy import text
            from data_warehouse.db import get_shared_engine
            engine = get_shared_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT goodwill, total_equity
                        FROM fact_fundamental
                        WHERE ts_code = :ts_code AND goodwill IS NOT NULL AND total_equity IS NOT NULL
                        ORDER BY end_date DESC
                        LIMIT 1
                    """),
                    {'ts_code': ts_code}
                ).fetchone()
            if row and row[0] is not None and row[1] is not None:
                return (float(row[0]), float(row[1]))
        except Exception as e:
            logger.debug(f"从 fact_fundamental 读取 goodwill/equity 失败 {ts_code}: {e}")
        return None

    def get_audit_result_from_local(self, ts_code: str) -> Optional[str]:
        """从本地 fact_fundamental 读取最新 audit_result（审计意见检查用）"""
        try:
            from sqlalchemy import text
            from data_warehouse.db import get_shared_engine
            engine = get_shared_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    text("""
                        SELECT audit_result
                        FROM fact_fundamental
                        WHERE ts_code = :ts_code AND audit_result IS NOT NULL
                        ORDER BY end_date DESC
                        LIMIT 1
                    """),
                    {'ts_code': ts_code}
                ).fetchone()
            if row and row[0]:
                return str(row[0]).strip()
        except Exception as e:
            logger.debug(f"从 fact_fundamental 读取 audit_result 失败 {ts_code}: {e}")
        return None

    def get_multi_period_data(
        self,
        ts_code: str,
        periods: int = 3,
        freq: str = 'Q'  # 'Q'季度 或 'Y'年度
    ) -> Optional[pd.DataFrame]:
        """
        获取连续多期财务数据（季度/年度）
        用于验证指标的连续性
        
        Args:
            ts_code: 股票代码（Tushare格式，如 '000001.SZ'）
            periods: 需要获取的期数（默认3期）
            freq: 频率，'Q'季度或'Y'年度
        
        Returns:
            DataFrame: 按报告期倒序排列的财务数据，包含以下字段：
                - ts_code: 股票代码
                - end_date: 报告期
                - roe: ROE
                - grossprofit_margin: 毛利率
                - netprofit_margin: 净利率
                - debt_to_assets: 资产负债率
                - revenue: 营业收入
                - net_profit: 净利润
                - n_income_attr_p: 扣非归母净利润
                - ocf: 经营活动现金流净额
        """
        # 1. 优先从本地 fact_fundamental 读取（持续亏损、现金流断裂 所需字段已落库）
        local_df = self._get_from_fact_fundamental(ts_code, periods, freq)
        if local_df is not None and len(local_df) >= (2 if freq == 'Y' else 2):
            required = ['n_income_attr_p'] if freq == 'Y' else ['ocf']
            if all(c in local_df.columns for c in required):
                return local_df

        # 2. 本地不足时回退到 Tushare（利息偿付、商誉等需 ebit/fin_exp/goodwill 仍依赖接口）
        if not self.tushare_service.available:
            logger.warning(f"Tushare服务不可用，无法获取多期财务数据: {ts_code}")
            return None
        
        try:
            # 计算日期范围（最近N期）
            end_date = datetime.now().strftime('%Y%m%d')
            
            if freq == 'Q':
                # 季度数据：往前推至少1年（365天），确保能获取到足够的季度数据
                # 对于3期，需要至少9个月的数据，但为了保险起见，往前推1年
                start_date = (datetime.now() - timedelta(days=max(periods*90, 365))).strftime('%Y%m%d')
            else:
                # 年度数据：往前推N年
                start_date = (datetime.now() - timedelta(days=periods*365)).strftime('%Y%m%d')
            
            # 获取财务指标
            fina_df = None
            try:
                # 尝试获取包含净利润的字段（fina_indicator可能包含net_profit相关字段）
                fina_df = self.tushare_service.pro.fina_indicator(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,end_date,roe,grossprofit_margin,netprofit_margin,debt_to_assets,ebit'
                )
            except Exception as e:
                logger.debug(f"获取财务指标失败 {ts_code}: {e}")
            
            # 获取利润表
            profit_df = None
            try:
                # Tushare的income接口可能不返回net_profit字段，尝试使用n_income或其他字段
                # 先尝试获取所有可用字段，看看实际返回什么
                profit_df = self.tushare_service.pro.income(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,end_date,revenue,n_income,n_income_attr_p,operate_profit,fin_exp'
                )
                # 如果返回了n_income字段，将其重命名为net_profit
                if profit_df is not None and not profit_df.empty and 'n_income' in profit_df.columns:
                    profit_df['net_profit'] = profit_df['n_income']
                    logger.debug(f"{ts_code} ✅ 从n_income字段创建net_profit字段")
            except Exception as e:
                logger.debug(f"获取利润表失败 {ts_code}: {e}")
                # 如果第一次尝试失败，尝试使用原来的字段列表
                try:
                    profit_df = self.tushare_service.pro.income(
                        ts_code=ts_code,
                        start_date=start_date,
                        end_date=end_date,
                        fields='ts_code,end_date,revenue,n_income_attr_p,operate_profit,fin_exp'
                    )
                except Exception as e2:
                    logger.debug(f"获取利润表（备用方案）失败 {ts_code}: {e2}")
            
            # 获取现金流量表
            cashflow_df = None
            try:
                cashflow_df = self.tushare_service.pro.cashflow(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,end_date,n_cashflow_act'
                )
                # 重命名字段
                if cashflow_df is not None and not cashflow_df.empty:
                    cashflow_df = cashflow_df.rename(columns={'n_cashflow_act': 'ocf'})
            except Exception as e:
                logger.debug(f"获取现金流量表失败 {ts_code}: {e}")
            
            # 获取资产负债表（用于计算有息负债等）
            balance_df = None
            try:
                balance_df = self.tushare_service.pro.balancesheet(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,end_date,total_assets,total_liab,total_equity,goodwill,inventory'
                )
            except Exception as e:
                logger.debug(f"获取资产负债表失败 {ts_code}: {e}")
            
            # 合并数据
            df = None
            if fina_df is not None and not fina_df.empty:
                df = fina_df.copy()
                
                if profit_df is not None and not profit_df.empty:
                    # 检查profit_df中是否有net_profit字段
                    if 'net_profit' not in profit_df.columns:
                        logger.debug(f"{ts_code} profit_df中缺少net_profit字段")
                    
                    df = pd.merge(df, profit_df, on=['ts_code', 'end_date'], how='outer', suffixes=('', '_profit'))
                
                if cashflow_df is not None and not cashflow_df.empty:
                    df = pd.merge(df, cashflow_df, on=['ts_code', 'end_date'], how='outer')
                
                if balance_df is not None and not balance_df.empty:
                    df = pd.merge(df, balance_df, on=['ts_code', 'end_date'], how='outer')
            elif profit_df is not None and not profit_df.empty:
                df = profit_df.copy()
                if cashflow_df is not None and not cashflow_df.empty:
                    df = pd.merge(df, cashflow_df, on=['ts_code', 'end_date'], how='outer')
                if balance_df is not None and not balance_df.empty:
                    df = pd.merge(df, balance_df, on=['ts_code', 'end_date'], how='outer')
            elif cashflow_df is not None and not cashflow_df.empty:
                df = cashflow_df.copy()
                if balance_df is not None and not balance_df.empty:
                    df = pd.merge(df, balance_df, on=['ts_code', 'end_date'], how='outer')
            elif balance_df is not None and not balance_df.empty:
                df = balance_df.copy()
            
            if df is None or df.empty:
                logger.debug(f"未获取到财务数据: {ts_code}")
                return None
            
            # 检查net_profit字段是否存在，如果不存在，尝试从其他字段创建
            if 'net_profit' not in df.columns:
                # 1. 尝试从net_profit_profit恢复
                if 'net_profit_profit' in df.columns:
                    df['net_profit'] = df['net_profit_profit']
                    df = df.drop(columns=['net_profit_profit'])
                    logger.debug(f"{ts_code} 从net_profit_profit恢复net_profit字段")
                # 2. 尝试从n_income创建（如果存在）
                elif 'n_income' in df.columns:
                    df['net_profit'] = df['n_income']
                    logger.debug(f"{ts_code} 从n_income字段创建net_profit字段")
                # 3. 使用n_income_attr_p作为替代（归属母公司净利润，通常与净利润接近）
                elif 'n_income_attr_p' in df.columns:
                    df['net_profit'] = df['n_income_attr_p']
                    logger.debug(f"{ts_code} 使用n_income_attr_p作为net_profit的替代")
                else:
                    logger.warning(f"{ts_code} ⚠️ 无法创建net_profit字段，缺少所有相关字段")
            
            # 按报告期倒序排序
            df = df.sort_values('end_date', ascending=False)
            
            # 去重：如果同一报告期有多条记录，保留第一条（可能是合并时产生的重复）
            df = df.drop_duplicates(subset=['ts_code', 'end_date'], keep='first')
            
            # 过滤数据：根据频率要求
            if freq == 'Q':
                # 季度数据：只保留季度报告（3月、6月、9月、12月）
                original_count = len(df)
                df['end_date_str'] = df['end_date'].astype(str)
                df['month'] = df['end_date_str'].str[4:6].astype(int)
                df_quarterly = df[df['month'].isin([3, 6, 9, 12])]
                
                # 如果过滤后数据不足，使用所有数据
                if len(df_quarterly) < periods:
                    logger.debug(f"{ts_code} 季度数据过滤后只剩{len(df_quarterly)}期，使用所有数据（共{original_count}期）")
                    df = df.drop(columns=['end_date_str', 'month'])
                else:
                    df = df_quarterly.drop(columns=['end_date_str', 'month'])
            elif freq == 'Y':
                # 年度数据：只保留年度报告（12月31日）
                original_count = len(df)
                df['end_date_str'] = df['end_date'].astype(str)
                df['month'] = df['end_date_str'].str[4:6].astype(int)
                df_annual = df[df['month'] == 12]  # 只保留12月的数据（年度报告）
                
                # 如果过滤后数据不足，记录警告但继续使用
                if len(df_annual) < periods:
                    logger.warning(f"{ts_code} ⚠️ 年度数据过滤后只剩{len(df_annual)}期（需要{periods}期），使用所有年度数据（共{original_count}期原始数据）")
                    if len(df_annual) > 0:
                        df = df_annual.drop(columns=['end_date_str', 'month'])
                    else:
                        # 如果没有年度数据，尝试使用所有数据（可能是数据源问题）
                        logger.warning(f"{ts_code} ⚠️ 未找到年度数据（12月），使用所有数据")
                        df = df.drop(columns=['end_date_str', 'month'])
                else:
                    df = df_annual.drop(columns=['end_date_str', 'month'])
            
            # 取最近N期
            df = df.head(periods)
            
            # 添加调试日志：显示获取到的数据（仅在DEBUG级别）
            if len(df) > 0:
                logger.debug(f"{ts_code} 获取到 {len(df)} 期数据，报告期：{df['end_date'].tolist()}")
                if freq == 'Y' and 'n_income_attr_p' not in df.columns:
                    # 年度数据检查时，如果没有n_income_attr_p字段，记录警告
                    logger.warning(f"{ts_code} ⚠️ 年度数据中缺少n_income_attr_p字段，无法进行持续亏损检查")
            
            # 数据清洗：处理百分比格式
            numeric_cols = ['roe', 'grossprofit_margin', 'netprofit_margin', 'debt_to_assets']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    # 如果值>1，认为是百分比，需要除以100
                    df[col] = df[col].apply(lambda x: x / 100 if pd.notna(x) and x > 1 else x)
            
            # 确保数值列为float类型
            numeric_cols_all = numeric_cols + ['revenue', 'net_profit', 'n_income_attr_p', 'ocf', 
                                                'operate_profit', 'fin_exp', 'total_assets', 'total_liab', 
                                                'total_equity', 'goodwill', 'inventory', 'ebit']
            for col in numeric_cols_all:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            logger.debug(f"✅ 成功获取 {len(df)} 期财务数据: {ts_code}")
            return df
            
        except Exception as e:
            logger.error(f"获取多期财务数据失败 {ts_code}: {e}", exc_info=True)
            return None
    
    def check_continuous_compliance(
        self,
        df: pd.DataFrame,
        indicator: str,
        threshold: float,
        periods: int = 3,
        comparison: str = '>='  # '>=' 或 '<='
    ) -> bool:
        """
        检查指标是否连续N期达标
        
        Args:
            df: 多期财务数据DataFrame
            indicator: 指标名称（如'roe', 'ocf'）
            threshold: 阈值
            periods: 需要连续达标的期数
            comparison: 比较运算符（'>=' 或 '<='）
        
        Returns:
            bool: 是否连续N期达标
        """
        if df is None or len(df) < periods:
            return False
        
        if indicator not in df.columns:
            logger.debug(f"指标 {indicator} 不在数据中")
            return False
        
        recent_periods = df.head(periods)
        
        # 检查是否有NaN或无效值
        values = recent_periods[indicator].values
        if np.any(pd.isna(values)) or np.any(np.isinf(values)):
            return False
        
        if comparison == '>=':
            return bool((values >= threshold).all())
        else:
            return bool((values <= threshold).all())
    
    def check_continuous_compliance_and_trend(
        self,
        df: pd.DataFrame,
        indicator: str,
        threshold: float,
        periods: int = 3,
        allow_decline: bool = False
    ) -> bool:
        """
        检查指标是否连续N期达标，且不下降（如果allow_decline=False）
        
        Args:
            df: 多期财务数据DataFrame
            indicator: 指标名称
            threshold: 阈值
            periods: 需要连续达标的期数
            allow_decline: 是否允许下降
        
        Returns:
            bool: 是否连续N期达标且不下降
        """
        if not self.check_continuous_compliance(df, indicator, threshold, periods):
            return False
        
        if not allow_decline:
            # 检查是否下降
            recent_periods = df.head(periods)
            if len(recent_periods) < periods:
                return False
            
            values = recent_periods[indicator].values
            # 检查是否有下降（后一期小于前一期）
            for i in range(1, len(values)):
                if pd.isna(values[i]) or pd.isna(values[i-1]):
                    return False
                if values[i] < values[i-1]:
                    return False
        
        return True
