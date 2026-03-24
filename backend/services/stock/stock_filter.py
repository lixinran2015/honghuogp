"""
股票筛选服务
从 app.py 提取筛选逻辑，封装为 StockFilter 类
"""

import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StockFilter:
    """股票筛选服务类"""
    
    def filter_short_term(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        筛选短线票（涨停板/龙头策略）
        
        真正的涨停板策略筛选条件：
        - 涨幅 ≥ 6%（或竞价强势 >3%）
        - 换手率 ≥ 10%（30%以内）
        - 成交额 ≥ 5亿
        - 量价结构：量增价升
        - 板块热度 top 3（在调用层处理）
        - 板块内龙头（在调用层处理）
        - 情绪周期：回暖或高潮（在调用层处理）
        - 强度排序：板块内前 3 名（在调用层处理）
        
        Args:
            df: 原始股票数据DataFrame
            
        Returns:
            DataFrame: 筛选后的股票数据
        """
        try:
            if df.empty:
                logger.warning("输入数据为空，无法筛选")
                return pd.DataFrame()
            
            # 数据标准化
            normalized_df = self._normalize_data(df.copy())
            
            # 排除指数和ST股票
            filtered_df = self._exclude_indices_and_st(normalized_df)
            
            if filtered_df.empty:
                logger.warning("排除指数和ST后数据为空")
                return pd.DataFrame()
            
            # 检查是否为交易时间数据（通过涨跌幅范围判断）
            if 'pct_chg' in filtered_df.columns and not filtered_df.empty:
                # 确保 max() 和 min() 返回标量值
                max_change_val = filtered_df['pct_chg'].max()
                min_change_val = filtered_df['pct_chg'].min()
                # 如果返回 Series，取第一个值
                if isinstance(max_change_val, pd.Series):
                    max_change = float(max_change_val.iloc[0]) if len(max_change_val) > 0 else 0.0
                else:
                    max_change = float(max_change_val) if pd.notna(max_change_val) else 0.0
                
                if isinstance(min_change_val, pd.Series):
                    min_change = float(min_change_val.iloc[0]) if len(min_change_val) > 0 else 0.0
                else:
                    min_change = float(min_change_val) if pd.notna(min_change_val) else 0.0
                
                is_trading_time = max_change > 2.0 or min_change < -2.0
                
                if not is_trading_time:
                    logger.warning(f"检测到非交易时间数据（涨跌幅范围: {min_change:.2f}% ~ {max_change:.2f}%）")
                    # 非交易时间：使用更宽松的条件（涨幅≥3%，用于竞价强势判断）
                    mask = filtered_df['pct_chg'] >= 3.0
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"短线票筛选（非交易时间/竞价）：选择涨幅≥3%的股票，剩余 {len(filtered_df)} 只")
                else:
                    # 交易时间：涨幅 ≥ 6%（涨停板策略）
                    mask = filtered_df['pct_chg'] >= 6.0
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"短线票筛选（涨停板策略）：选择涨幅≥6%的股票，剩余 {len(filtered_df)} 只")
            
            # 换手率筛选：≥ 10%（30%以内）
            if 'turnover_rate' in filtered_df.columns and not filtered_df.empty:
                # 确保换手率是数值类型
                filtered_df['turnover_rate'] = pd.to_numeric(filtered_df['turnover_rate'], errors='coerce').fillna(0.0)
                max_turnover = float(filtered_df['turnover_rate'].max())
                valid_count = (filtered_df['turnover_rate'] > 0).sum()
                is_valid_turnover = max_turnover > 0.1 and valid_count > len(filtered_df) * 0.1  # 至少10%的股票有有效数据
                
                if is_valid_turnover:
                    # 换手率≥10%且≤30%
                    mask = (filtered_df['turnover_rate'] >= 10.0) & (filtered_df['turnover_rate'] <= 30.0)
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"短线票换手率筛选(10%-30%)，剩余 {len(filtered_df)} 只股票")
                else:
                    logger.warning(f"换手率数据无效（最大值:{max_turnover:.2f}%，有效数据:{valid_count}/{len(filtered_df)}），跳过换手率筛选")
            
            # 成交额筛选：≥ 5亿
            if 'amount' in filtered_df.columns and not filtered_df.empty:
                min_volume = 500000000  # 5亿
                mask = filtered_df['amount'] >= min_volume
                filtered_df = filtered_df.loc[mask].copy()
                logger.info(f"短线票成交额筛选(≥5亿)，剩余 {len(filtered_df)} 只股票")
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"短线票筛选失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return pd.DataFrame()
    
    def filter_swing_term(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        筛选波段票
        
        筛选条件：
        - 涨幅-1%~2%
        - 换手率1%-4%
        - 成交额≥5000万
        - 排除：指数、ST股票、科创板（688开头）、北交所（8开头）
        
        Args:
            df: 原始股票数据DataFrame
            
        Returns:
            DataFrame: 筛选后的股票数据
        """
        try:
            if df.empty:
                logger.warning("输入数据为空，无法筛选")
                return pd.DataFrame()
            
            # 数据标准化
            normalized_df = self._normalize_data(df.copy())
            
            # 排除指数和ST股票
            filtered_df = self._exclude_indices_and_st(normalized_df)
            
            if filtered_df.empty:
                logger.warning("排除指数和ST后数据为空")
                return pd.DataFrame()
            
            # 检查是否为交易时间数据
            if 'pct_chg' in filtered_df.columns and not filtered_df.empty:
                # 确保 max() 和 min() 返回标量值
                max_change_val = filtered_df['pct_chg'].max()
                min_change_val = filtered_df['pct_chg'].min()
                # 如果返回 Series，取第一个值
                if isinstance(max_change_val, pd.Series):
                    max_change = float(max_change_val.iloc[0]) if len(max_change_val) > 0 else 0.0
                else:
                    max_change = float(max_change_val) if pd.notna(max_change_val) else 0.0
                
                if isinstance(min_change_val, pd.Series):
                    min_change = float(min_change_val.iloc[0]) if len(min_change_val) > 0 else 0.0
                else:
                    min_change = float(min_change_val) if pd.notna(min_change_val) else 0.0
                
                is_trading_time = max_change > 2.0 or min_change < -2.0
                
                if not is_trading_time:
                    logger.warning(f"检测到非交易时间数据（涨跌幅范围: {min_change:.2f}% ~ {max_change:.2f}%）")
                    # 非交易时间：选择涨幅-0.5%~0.5%的股票
                    mask = (filtered_df['pct_chg'] <= 0.5) & (filtered_df['pct_chg'] >= -0.5)
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"波段票筛选（非交易时间）：选择涨幅-0.5%~0.5%的股票，剩余 {len(filtered_df)} 只")
                else:
                    # 交易时间：涨幅-1%~3%
                    mask = (filtered_df['pct_chg'] <= 3.0) & (filtered_df['pct_chg'] >= -1.0)
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"波段票筛选：选择涨幅-1%~3%的股票，剩余 {len(filtered_df)} 只")
            
            # 换手率筛选
            if 'turnover_rate' in filtered_df.columns and not filtered_df.empty:
                # 确保换手率是数值类型
                filtered_df['turnover_rate'] = pd.to_numeric(filtered_df['turnover_rate'], errors='coerce').fillna(0.0)
                max_turnover = float(filtered_df['turnover_rate'].max())
                valid_count = (filtered_df['turnover_rate'] > 0).sum()
                is_valid_turnover = max_turnover > 0.1 and valid_count > len(filtered_df) * 0.1  # 至少10%的股票有有效数据
                
                if is_trading_time and is_valid_turnover:
                    # 交易时间且换手率数据有效：换手率1%-4%
                    mask = (filtered_df['turnover_rate'] >= 1.0) & (filtered_df['turnover_rate'] <= 4.0)
                    filtered_df = filtered_df.loc[mask].copy()
                    logger.info(f"波段票换手率筛选(1%-4%)，剩余 {len(filtered_df)} 只股票")
                else:
                    logger.warning(f"换手率数据无效（最大值:{max_turnover:.2f}%，有效数据:{valid_count}/{len(filtered_df)}），跳过换手率筛选")
            
            # 成交额筛选：≥5000万
            if 'amount' in filtered_df.columns and not filtered_df.empty:
                min_volume = 50000000  # 5000万
                mask = filtered_df['amount'] >= min_volume
                filtered_df = filtered_df.loc[mask].copy()
                logger.info(f"波段票成交额筛选(≥5000万)，剩余 {len(filtered_df)} 只股票")
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"波段票筛选失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return pd.DataFrame()
    
    def _normalize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据标准化：字段映射和类型转换
        
        Args:
            df: 原始数据DataFrame
            
        Returns:
            DataFrame: 标准化后的DataFrame
        """
        try:
            # 字段映射（支持多种可能的字段名）
            column_mapping = {
                '代码': 'code',
                '名称': 'name',
                '股票名称': 'name',
                '最新价': 'price',
                '当前价': 'price',
                '涨跌幅': 'pct_chg',
                '换手率': 'turnover_rate',
                'turnover_rate': 'turnover_rate',  # 支持英文字段名
                'turnover': 'turnover_rate',       # 支持简写
                '成交额': 'amount',
                '成交量': 'volume'
            }
            
            # 只重命名存在的列
            existing_mapping = {k: v for k, v in column_mapping.items() if k in df.columns}
            if existing_mapping:
                df = df.rename(columns=existing_mapping)
            
            # 数据类型转换
            for col in ['pct_chg', 'turnover_rate']:
                if col in df.columns:
                    try:
                        # 确保 df[col] 是 Series，不是 DataFrame
                        col_data = df[col]
                        if isinstance(col_data, pd.DataFrame):
                            # 如果返回的是 DataFrame（列名重复），取第一列
                            logger.warning(f"列 {col} 返回了 DataFrame，取第一列")
                            col_data = col_data.iloc[:, 0]
                        
                        # 如果已经是数值类型，直接使用
                        if pd.api.types.is_numeric_dtype(col_data):
                            df[col] = pd.to_numeric(col_data, errors='coerce').fillna(0.0)
                        else:
                            # 如果是字符串，去除%符号并转换
                            df[col] = pd.to_numeric(
                                col_data.astype(str).str.replace('%', '', regex=False).str.replace(' ', '', regex=False),
                                errors='coerce'
                            ).fillna(0.0)
                        
                        # 数据质量检查：如果换手率全为0，记录警告
                        if col == 'turnover_rate' and len(df) > 0:
                            max_turnover = df[col].max()
                            valid_count = (df[col] > 0).sum()
                            if max_turnover == 0:
                                logger.warning(f"⚠️ 换手率数据无效：所有股票的换手率都为0（共{len(df)}只）")
                            elif valid_count < len(df) * 0.1:  # 如果有效数据少于10%
                                logger.warning(f"⚠️ 换手率数据质量较差：只有{valid_count}/{len(df)}只股票有有效换手率数据")
                            else:
                                logger.debug(f"✅ 换手率数据有效：{valid_count}/{len(df)}只股票有有效数据（最大值: {max_turnover:.2f}%）")
                    except Exception as e:
                        logger.warning(f"转换字段 {col} 失败: {e}，尝试直接转换")
                        try:
                            col_data = df[col]
                            if isinstance(col_data, pd.DataFrame):
                                col_data = col_data.iloc[:, 0]
                            df[col] = pd.to_numeric(col_data, errors='coerce').fillna(0.0)
                        except Exception as e2:
                            logger.error(f"转换字段 {col} 最终失败: {e2}")
                            df[col] = 0.0  # 设置默认值
            
            if 'amount' in df.columns:
                try:
                    col_data = df['amount']
                    if isinstance(col_data, pd.DataFrame):
                        logger.warning(f"列 amount 返回了 DataFrame，取第一列")
                        col_data = col_data.iloc[:, 0]
                    df['amount'] = pd.to_numeric(col_data, errors='coerce')
                except Exception as e:
                    logger.warning(f"转换字段 amount 失败: {e}")
                    df['amount'] = 0.0
            
            # 确保索引唯一（处理重复索引）
            if df.index.duplicated().any():
                logger.warning(f"检测到重复索引，重置索引")
                df = df.reset_index(drop=True)
            
            return df
            
        except Exception as e:
            logger.error(f"数据标准化失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return df
    
    def _exclude_indices_and_st(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        排除指数、ST股票、科创板、北交所
        
        Args:
            df: 标准化后的DataFrame
            
        Returns:
            DataFrame: 排除后的DataFrame
        """
        try:
            if df.empty:
                return df
            
            # 指数识别关键词
            EXCLUDE_KEYWORDS = [
                "指数", "综指", "成指", "上证", "深证", "中证", 
                "新兴综指", "沪深300", "创业板指", "科创50", "北证", "申万"
            ]
            
            def is_index_row(row):
                """判断是否为指数"""
                name = str(row.get('name', row.get('名称', '')))
                code = str(row.get('code', row.get('代码', '')))
                
                # 关键词匹配
                if any(k in name for k in EXCLUDE_KEYWORDS):
                    return True
                
                # 代码前缀匹配（处理带交易所前缀的代码）
                clean_code = code.replace('sz', '').replace('sh', '')
                
                # 指数代码前缀
                if clean_code.startswith(('000', '399', '88', '89')):
                    return True
                
                # 特殊处理：300开头的可能是创业板个股
                if clean_code.startswith('300'):
                    if any(k in name for k in EXCLUDE_KEYWORDS):
                        return True
                    return False
                
                return False
            
            # 标注指数
            if 'name' in df.columns:
                df['is_index'] = df.apply(is_index_row, axis=1)
            else:
                df['is_index'] = False
            
            # 基本筛选：排除指数、ST、退市、停牌、科创板、北交所
            # 优先使用标准化后的字段名
            name_col = None
            for col_name in ['name', '名称', '股票名称']:
                if col_name in df.columns:
                    name_col = col_name
                    break
            
            code_col = None
            for col_name in ['code', '代码']:
                if col_name in df.columns:
                    code_col = col_name
                    break
            
            if name_col is None or code_col is None:
                logger.warning(f"缺少必要字段: name_col={name_col}, code_col={code_col}, 可用字段={list(df.columns)}")
                return df[~df['is_index']].copy() if 'is_index' in df.columns else df.copy()
            
            # 构建筛选条件（使用布尔Series）
            mask = pd.Series(True, index=df.index)
            
            # 排除指数
            if 'is_index' in df.columns:
                mask = mask & (~df['is_index'])
            
            # 排除ST股票等
            if name_col:
                try:
                    name_data = df[name_col]
                    # 确保是 Series，不是 DataFrame
                    if isinstance(name_data, pd.DataFrame):
                        name_data = name_data.iloc[:, 0]
                    name_series = name_data.astype(str)
                    mask = mask & (~name_series.str.contains('ST', na=False))
                    mask = mask & (~name_series.str.contains('退', na=False))
                except Exception as e:
                    logger.warning(f"名称字段筛选失败: {e}")
            
            # 排除科创板、北交所
            if code_col:
                try:
                    code_data = df[code_col]
                    # 确保是 Series，不是 DataFrame
                    if isinstance(code_data, pd.DataFrame):
                        code_data = code_data.iloc[:, 0]
                    code_series = code_data.astype(str)
                    clean_code = code_series.str.replace('sz', '', regex=False).str.replace('sh', '', regex=False).str.replace('SH', '', regex=False).str.replace('SZ', '', regex=False).str.strip()
                    mask = mask & (~clean_code.str.startswith('688', na=False))
                    mask = mask & (~clean_code.str.startswith('8', na=False))
                except Exception as e:
                    logger.warning(f"代码字段筛选失败: {e}")
            
            # 应用筛选条件
            filtered_df = df[mask].copy()
            
            # 删除临时列
            if 'is_index' in filtered_df.columns:
                filtered_df = filtered_df.drop(columns=['is_index'])
            
            logger.info(f"排除指数和ST后剩余 {len(filtered_df)} 只股票")
            return filtered_df
            
        except Exception as e:
            logger.error(f"排除指数和ST失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return df

