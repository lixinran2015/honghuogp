"""
同花顺客户端
使用 THS_BD 接口获取涨跌停状态和量比数据
"""
import logging
from typing import List, Dict, Optional
from datetime import date, datetime
import pandas as pd

from backend.services.data_sources.ifind_login_manager import ensure_ifind_login

logger = logging.getLogger(__name__)


class TonghuashunClient:
    """同花顺客户端"""
    
    def __init__(self):
        """初始化客户端"""
        self.available = False
        if ensure_ifind_login():
            self.available = True
        else:
            logger.warning("⚠️ 同花顺客户端不可用（登录失败）")
    
    def get_limit_up_status_and_volume_ratio(
        self,
        ts_codes: List[str],
        trade_date: str,
        minimal: bool = False,
    ) -> pd.DataFrame:
        """
        批量获取股票的涨跌停状态、量比、股票简称、收盘价、成交额、涨跌幅数据
        
        Args:
            ts_codes: 股票代码列表（格式：600000.SH, 000001.SZ）
            trade_date: 交易日期（格式：YYYY-MM-DD 或 YYYYMMDD）
        
        Returns:
            DataFrame: 包含 ts_code, up_and_down_status, volume_ratio, stock_name, close_price, amount, change_pct 等字段
        """
        if not self.available:
            logger.warning("⚠️ 同花顺客户端不可用")
            return pd.DataFrame()
        
        try:
            from iFinDPy import THS_BD
            
            # 转换日期格式（YYYY-MM-DD -> YYYYMMDD）
            if '-' in trade_date:
                trade_date_str = trade_date.replace('-', '')
            else:
                trade_date_str = trade_date
            
            # 构建股票代码字符串（逗号分隔）
            if isinstance(ts_codes, list):
                ths_code_str = ','.join(ts_codes)
            else:
                ths_code_str = str(ts_codes)
            
            logger.info(f"📥 从同花顺获取涨跌停状态、量比、股票简称、收盘价、涨跌幅数据: {len(ts_codes)} 只股票，日期: {trade_date}")
            
            # 调用 THS_BD 接口，一次性获取多个指标
            # 指标列表：
            # - 标准模式：涨跌停状态;量比;股票简称;收盘价;涨跌幅（已移除成交额）
            # - minimal=True：仅获取涨跌停状态 + 量比（给日线ETL等只需量比/状态的场景，减少不必要指标）
            if minimal:
                indicators = 'ths_up_and_down_status_stock;ths_vol_ratio_stock'
            else:
                indicators = 'ths_up_and_down_status_stock;ths_vol_ratio_stock;ths_stock_short_name_stock;ths_close_price_stock;ths_chg_ratio_stock'
            
            # 参数选项：每个指标对应一个参数（用分号分隔）
            # 格式：日期;日期,5,100;;日期,0;日期,0
            # 根据用户示例：2025-12-11;2025-12-11,5,100;;2025-12-11,0;2025-12-11,0
            # 注意：同花顺接口可能支持带横线的日期格式，先尝试带横线格式
            trade_date_with_dash = trade_date  # 保持原始格式（YYYY-MM-DD）
            param_option = f'{trade_date_with_dash};{trade_date_with_dash},5,100;;{trade_date_with_dash},0;{trade_date_with_dash},0'
            
            try:
                result_combined = THS_BD(
                    ths_code_str,
                    indicators,
                    param_option,
                    format='format:dataframe'
                )
                
                # 记录原始返回结果的结构
                logger.info(f"📥 THS_BD 原始返回类型: {type(result_combined)}")
                if isinstance(result_combined, dict):
                    logger.info(f"📥 错误码: {result_combined.get('errorcode')}, 错误信息: {result_combined.get('errmsg')}")
                    if 'data' in result_combined and result_combined['data'] is not None:
                        if isinstance(result_combined['data'], pd.DataFrame):
                            logger.info(f"📥 原始DataFrame列名: {result_combined['data'].columns.tolist()}")
                            logger.info(f"📥 原始DataFrame形状: {result_combined['data'].shape}")
                            if not result_combined['data'].empty:
                                logger.info(f"📥 前3行数据:\n{result_combined['data'].head(3).to_string()}")
                
                # 解析合并结果
                df = self._parse_combined_result(result_combined)
                if not df.empty:
                    logger.info(f"✅ 一次性获取多个指标成功，共 {len(df)} 条记录")
                    return df
                else:
                    logger.warning("⚠️ 解析结果为空")
            except Exception as e:
                logger.error(f"❌ 一次性获取多个指标失败: {e}", exc_info=True)
            
            # 如果一次性获取失败，降级为分别获取（仅获取涨跌停状态和量比）
            logger.warning("⚠️ 降级为分别获取涨跌停状态和量比")
            param_option_simple = f'{trade_date_str}'
            
            # 获取涨跌停状态
            result_status = THS_BD(
                ths_code_str,
                'ths_up_and_down_status_stock',
                param_option_simple,
                format='format:dataframe'
            )
            
            # 获取量比
            result_volume_ratio = THS_BD(
                ths_code_str,
                'ths_vol_ratio_stock',
                param_option_simple,
                format='format:dataframe'
            )
            
            # 处理返回结果
            df_status = self._parse_result(result_status, 'up_and_down_status')
            df_volume_ratio = self._parse_result(result_volume_ratio, 'volume_ratio')
            
            # 合并数据
            if df_status.empty and df_volume_ratio.empty:
                logger.warning("⚠️ 未获取到数据")
                return pd.DataFrame()
            
            # 合并两个DataFrame
            if not df_status.empty and not df_volume_ratio.empty:
                # 按 ts_code 合并
                df = pd.merge(df_status, df_volume_ratio, on='ts_code', how='outer')
            elif not df_status.empty:
                df = df_status
            else:
                df = df_volume_ratio
            
            logger.info(f"✅ 成功获取 {len(df)} 只股票的数据")
            return df
            
        except ImportError:
            logger.error("❌ iFinDPy 模块未安装")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ 获取同花顺数据失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _parse_combined_result(self, result) -> pd.DataFrame:
        """
        解析 THS_BD 返回的合并结果（包含多个指标）
        
        Args:
            result: THS_BD 返回的结果
        
        Returns:
            DataFrame: 解析后的数据，包含 ts_code, up_and_down_status, volume_ratio, stock_name, close_price, change_pct
        """
        try:
            # 检查返回类型
            if isinstance(result, dict):
                errorcode = result.get('errorcode', -1)
                errmsg = result.get('errmsg', '')
                data = result.get('data')
            else:
                errorcode = getattr(result, 'errorcode', -1)
                errmsg = getattr(result, 'errmsg', '')
                data = getattr(result, 'data', None)
            
            if errorcode != 0:
                logger.warning(f"⚠️ 同花顺接口返回错误: {errmsg} (错误码: {errorcode})")
                return pd.DataFrame()
            
            if data is None:
                logger.warning(f"⚠️ 同花顺接口返回数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            if isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                df = pd.DataFrame(data)
            
            if df.empty:
                return pd.DataFrame()
            
            # 查找股票代码列
            code_col = None
            for col in df.columns:
                col_lower = str(col).lower()
                if 'code' in col_lower or '代码' in col or col == 'ts_code':
                    code_col = col
                    break
            
            if code_col:
                df.rename(columns={code_col: 'ts_code'}, inplace=True)
            elif len(df.columns) >= 1:
                df.rename(columns={df.columns[0]: 'ts_code'}, inplace=True)
            
            # 查找指标列（根据指标名称匹配）
            # 同花顺返回的列名可能是：ths_up_and_down_status_stock, ths_vol_ratio_stock 等
            col_mapping = {}
            
            # 记录所有列名以便调试
            logger.debug(f"原始列名: {df.columns.tolist()}")
            
            for col in df.columns:
                if col == 'ts_code':
                    continue
                    
                col_str = str(col).lower()
                col_upper = str(col).upper()
                
                # 涨跌停状态 - 匹配 ths_up_and_down_status_stock 或类似
                if 'up_and_down_status' in col_str or 'updown' in col_str or 'status' in col_str or '状态' in col_str:
                    if col not in col_mapping:
                        col_mapping[col] = 'up_and_down_status'
                        logger.debug(f"匹配涨跌停状态: {col} -> up_and_down_status")
                
                # 量比 - 匹配 ths_vol_ratio_stock 或类似
                elif 'vol_ratio' in col_str or ('volume' in col_str and 'ratio' in col_str) or '量比' in col_str:
                    if col not in col_mapping:
                        col_mapping[col] = 'volume_ratio'
                        logger.debug(f"匹配量比: {col} -> volume_ratio")
                
                # 股票简称 - 匹配 ths_stock_short_name_stock 或类似
                elif 'short_name' in col_str or ('stock' in col_str and 'name' in col_str) or '简称' in col_str:
                    if col not in col_mapping:
                        col_mapping[col] = 'stock_name'
                        logger.debug(f"匹配股票简称: {col} -> stock_name")
                
                # 收盘价 - 匹配 ths_close_price_stock 或类似
                elif 'close_price' in col_str or ('close' in col_str and 'price' in col_str) or '收盘' in col_str:
                    if col not in col_mapping:
                        col_mapping[col] = 'close_price'
                        logger.debug(f"匹配收盘价: {col} -> close_price")
                
                # 涨跌幅 - 匹配 ths_chg_ratio_stock 或类似
                elif 'chg_ratio' in col_str or ('chg' in col_str and 'ratio' in col_str) or ('涨跌' in col_str and ('%' in col_str or 'pct' in col_str)):
                    if col not in col_mapping:
                        col_mapping[col] = 'change_pct'
                        logger.debug(f"匹配涨跌幅: {col} -> change_pct")
            
            # 重命名列
            for old_col, new_col in col_mapping.items():
                if old_col in df.columns:
                    df.rename(columns={old_col: new_col}, inplace=True)
            
            # 确保 ts_code 列存在
            if 'ts_code' not in df.columns:
                logger.warning(f"⚠️ 无法找到股票代码列，列名: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # 返回标准化的DataFrame
            result_df = df.copy()
            result_df['ts_code'] = result_df['ts_code'].astype(str).str.strip()
            
            # 记录实际获取到的列
            actual_cols = [col for col in result_df.columns if col != 'ts_code']
            logger.info(f"📊 解析后的列: {result_df.columns.tolist()}")
            
            # 检查是否成功解析了所有需要的字段
            required_fields = ['up_and_down_status', 'volume_ratio', 'stock_name', 'close_price', 'change_pct']
            missing_fields = [field for field in required_fields if field not in result_df.columns]
            if missing_fields:
                logger.warning(f"⚠️ 缺少以下字段: {missing_fields}")
                # 打印前几行数据以便调试
                if not result_df.empty:
                    logger.info(f"前3行数据示例:\n{result_df.head(3).to_string()}")
            else:
                logger.info(f"✅ 成功解析所有字段: {required_fields}")
            
            return result_df
            
        except Exception as e:
            logger.error(f"❌ 解析同花顺合并结果失败: {e}", exc_info=True)
            return pd.DataFrame()
    
    def _parse_result(self, result, field_name: str) -> pd.DataFrame:
        """
        解析 THS_BD 返回结果
        
        Args:
            result: THS_BD 返回的结果
            field_name: 字段名称
        
        Returns:
            DataFrame: 解析后的数据
        """
        try:
            # 检查返回类型
            if isinstance(result, dict):
                errorcode = result.get('errorcode', -1)
                errmsg = result.get('errmsg', '')
                data = result.get('data')
            else:
                errorcode = getattr(result, 'errorcode', -1)
                errmsg = getattr(result, 'errmsg', '')
                data = getattr(result, 'data', None)
            
            if errorcode != 0:
                logger.warning(f"⚠️ 同花顺接口返回错误: {errmsg} (错误码: {errorcode})")
                return pd.DataFrame()
            
            if data is None:
                logger.warning(f"⚠️ 同花顺接口返回数据为空")
                return pd.DataFrame()
            
            # 转换为DataFrame
            if isinstance(data, pd.DataFrame):
                df = data.copy()
            else:
                df = pd.DataFrame(data)
            
            if df.empty:
                return pd.DataFrame()
            
            # 标准化列名
            # THS_BD 返回的DataFrame格式通常是：第一列是股票代码，后续列是指标值
            # 列名可能是 'code', '股票代码', 'ts_code' 等
            code_col = None
            for col in df.columns:
                col_lower = str(col).lower()
                if 'code' in col_lower or '代码' in col or col == 'ts_code':
                    code_col = col
                    break
            
            if code_col:
                df.rename(columns={code_col: 'ts_code'}, inplace=True)
            elif len(df.columns) >= 1:
                # 假设第一列是股票代码
                df.rename(columns={df.columns[0]: 'ts_code'}, inplace=True)
            
            # 查找指标值列（除了ts_code之外的其他列）
            indicator_col = None
            for col in df.columns:
                if col != 'ts_code':
                    indicator_col = col
                    break
            
            if indicator_col:
                df.rename(columns={indicator_col: field_name}, inplace=True)
            else:
                logger.warning(f"⚠️ 无法找到指标值列，列名: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # 确保 ts_code 列存在
            if 'ts_code' not in df.columns:
                logger.warning(f"⚠️ 无法找到股票代码列，列名: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # 返回标准化的DataFrame
            result_df = df[['ts_code', field_name]].copy()
            
            # 清理数据：确保ts_code格式正确
            result_df['ts_code'] = result_df['ts_code'].astype(str).str.strip()
            
            return result_df
            
        except Exception as e:
            logger.error(f"❌ 解析同花顺返回结果失败: {e}", exc_info=True)
            return pd.DataFrame()
