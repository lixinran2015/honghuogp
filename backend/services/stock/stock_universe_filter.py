"""
股票池过滤器
建立"可交易股票池"过滤规则，这是所有量化策略的基础

过滤层级：
1. 基础黑名单过滤（必须剔除）
2. 策略专用股票池（S1/S2/S3）
"""

import logging
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy import text

from backend.services.data.postgres_warehouse import PostgresWarehouse

logger = logging.getLogger(__name__)


class StockUniverseFilter:
    """股票池过滤器"""
    
    def __init__(self):
        """初始化过滤器"""
        self.warehouse = PostgresWarehouse()
    
    def mainboard_universe_filter(
        self,
        stock_data: pd.DataFrame,
        filter_st: bool = True,
        allowed_prefixes: List[str] = None
    ) -> pd.DataFrame:
        """
        主板池过滤（仅主板股票，排除创业板、科创板、ST）
        
        过滤条件：
        1. 只保留主板股票（600/601/603/000/001/002开头）
        2. 排除ST股票
        
        Args:
            stock_data: 股票数据DataFrame
            filter_st: 是否过滤ST（默认True）
            allowed_prefixes: 允许的代码前缀
        
        Returns:
            过滤后的DataFrame
        """
        try:
            if allowed_prefixes is None:
                allowed_prefixes = ['600', '601', '603', '000', '001', '002']
            
            if stock_data.empty:
                logger.warning("⚠️ 输入数据为空")
                return pd.DataFrame()
            
            original_count = len(stock_data)
            logger.info(f"📊 开始主板池过滤：原始股票数 {original_count}")
            
            # 1. 代码前缀过滤（只保留主板）
            code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
            if code_col in stock_data.columns:
                before_code = len(stock_data)
                # 提取纯数字代码部分（去掉.SH/.SZ后缀）
                stock_data['_code_prefix'] = stock_data[code_col].astype(str).str.replace(r'\.(SH|SZ|BJ)$', '', regex=True).str[:3]
                stock_data = stock_data[stock_data['_code_prefix'].isin(allowed_prefixes)]
                stock_data = stock_data.drop(columns=['_code_prefix'])
                code_count = before_code - len(stock_data)
                logger.info(f"  ✅ 代码前缀过滤: 剔除 {code_count} 只（保留主板股票）")
            
            # 2. 过滤ST股票（优先用股票名称判断）
            if filter_st:
                before_st = len(stock_data)
                if 'name' in stock_data.columns:
                    # 通过股票名称判断ST
                    stock_data = stock_data[~stock_data['name'].astype(str).str.upper().str.contains('ST', na=False)]
                elif 'is_st' in stock_data.columns:
                    stock_data = stock_data[stock_data['is_st'] == False]
                else:
                    logger.warning("  ⚠️ 缺少name和is_st字段，跳过ST过滤")
                st_count = before_st - len(stock_data)
                logger.info(f"  ✅ 剔除ST股票: {st_count} 只")
            
            final_count = len(stock_data)
            filtered_count = original_count - final_count
            logger.info(f"✅ 主板池过滤完成：剩余 {final_count} 只（剔除 {filtered_count} 只）")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"❌ 主板池过滤失败: {e}", exc_info=True)
            return stock_data  # 出错时返回原数据
    
    def base_universe_filter(
        self,
        stock_data: pd.DataFrame,
        min_amount: float = 1e8,  # 最低成交额：1亿
        min_price: float = 5.0,  # 最低股价：5元
        max_debt_ratio: float = 0.6,  # 最高负债率：60%
        require_profit: bool = True,  # 是否要求盈利
        require_positive_cf: bool = True,  # 是否要求正现金流
        filter_st: bool = True  # 是否过滤ST
    ) -> pd.DataFrame:
        """
        基础黑名单过滤（必须剔除的股票）
        
        过滤条件：
        1. ST/*ST股票
        2. 流动性差（成交额 < 1亿）
        3. 长期亏损（净利润TTM < 0 或 经营现金流TTM < 0）
        4. 高负债（负债率 > 60%，金融行业除外）
        5. 低价股（股价 < 5元）
        
        Args:
            stock_data: 股票数据DataFrame
            min_amount: 最低成交额（默认1亿）
            min_price: 最低股价（默认5元）
            max_debt_ratio: 最高负债率（默认60%）
        
        Returns:
            过滤后的DataFrame
        """
        try:
            if stock_data.empty:
                logger.warning("⚠️ 输入数据为空")
                return pd.DataFrame()
            
            original_count = len(stock_data)
            logger.info(f"📊 开始基础过滤：原始股票数 {original_count}")
            
            # 0. 只保留300/301/688开头的股票
            code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
            if code_col in stock_data.columns:
                before_code = len(stock_data)
                # 提取纯数字代码部分（去掉.SH/.SZ后缀）
                stock_data['_code_prefix'] = stock_data[code_col].astype(str).str.replace(r'\.(SH|SZ)$', '', regex=True).str[:3]
                stock_data = stock_data[stock_data['_code_prefix'].isin(['300', '301', '688'])]
                stock_data = stock_data.drop(columns=['_code_prefix'])
                code_count = before_code - len(stock_data)
                logger.info(f"  ✅ 只保留300/301/688开头股票: 剔除 {code_count} 只")
            
            # 1. 过滤ST股票（优先用股票名称判断）
            if filter_st:
                before_st = len(stock_data)
                if 'name' in stock_data.columns:
                    # 通过股票名称判断ST
                    stock_data = stock_data[~stock_data['name'].astype(str).str.upper().str.contains('ST', na=False)]
                elif 'is_st' in stock_data.columns:
                    stock_data = stock_data[stock_data['is_st'] == False]
                else:
                    logger.warning("  ⚠️ 缺少name和is_st字段，跳过ST过滤")
                st_count = before_st - len(stock_data)
                logger.info(f"  ✅ 剔除ST股票: {st_count} 只")
            
            # 基础池只做代码前缀+ST过滤，不做低价股、流动性、财务数据过滤
            
            final_count = len(stock_data)
            filtered_count = original_count - final_count
            logger.info(f"✅ 基础过滤完成：剩余 {final_count} 只（剔除 {filtered_count} 只）")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"❌ 基础过滤失败: {e}", exc_info=True)
            return stock_data  # 出错时返回原数据
    
    def s1_universe_filter(
        self,
        stock_data: pd.DataFrame,
        max_high_distance: float = 0.05,  # 距离30日最高价的最大距离（5%）
        min_price: float = 10.0,  # 最低股价（默认10元）
        min_amount: float = 2e8,  # 最低成交额（默认2亿）
        kline_data: Optional[Dict] = None  # K线数据字典 {ts_code: DataFrame}
    ) -> pd.DataFrame:
        """
        S1 新高策略股票池
        
        目标：近30日新高附近的股票（不含回踩条件）
        
        过滤条件：
        1. 股价 >= 10元
        2. 成交额 >= 2亿（保证流动性）
        3. 当前收盘价距离近30个交易日最高收盘价 ≤ 5%
        
        Args:
            stock_data: 已通过基础过滤的股票数据
            max_high_distance: 距离30日最高价的最大距离（默认5%）
            min_price: 最低股价（默认10元）
            min_amount: 最低成交额（默认2亿）
            kline_data: K线数据字典（可选，如果不传会自动获取）
        
        Returns:
            过滤后的DataFrame
        """
        try:
            if stock_data.empty:
                return pd.DataFrame()
            
            original_count = len(stock_data)
            logger.info(f"📊 开始S1新高过滤：原始股票数 {original_count}")
            logger.info(f"  配置: 股价>={min_price}元, 成交额>={min_amount/1e8:.0f}亿, 距离30日最高价 ≤ {max_high_distance*100:.0f}%")
            
            # 1. 股价过滤（>=10元）
            price_col = None
            for col in ['close', 'Close', 'lastPrice', 'currentPrice']:
                if col in stock_data.columns:
                    price_col = col
                    break
            
            if price_col:
                before_count = len(stock_data)
                stock_data = stock_data[pd.to_numeric(stock_data[price_col], errors='coerce') >= min_price]
                logger.info(f"  ✅ 股价过滤(>={min_price}元): {before_count} -> {len(stock_data)} (剔除 {before_count - len(stock_data)} 只)")
            
            # 2. 成交额过滤（>= 2亿）
            if 'amount' in stock_data.columns:
                before_count = len(stock_data)
                stock_data = stock_data[pd.to_numeric(stock_data['amount'], errors='coerce') >= min_amount]
                logger.info(f"  ✅ 成交额过滤(>={min_amount/1e8:.0f}亿): {before_count} -> {len(stock_data)} (剔除 {before_count - len(stock_data)} 只)")
            
            code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
            codes = stock_data[code_col].unique().tolist()
            
            # 如果没有传入K线数据，从数据库批量获取
            if kline_data is None:
                kline_data = self._get_kline_batch(codes, days=30)
            
            valid_codes = []
            no_kline_count = 0
            checked_count = 0
            
            # 调试：打印前3个股票的K线数据key
            kline_keys = list(kline_data.keys())[:5]
            stock_codes_sample = codes[:5]
            logger.info(f"  🔍 调试: K线数据keys样本={kline_keys}, 股票代码样本={stock_codes_sample}")
            
            for code in codes:
                kline = kline_data.get(code)
                if kline is None or len(kline) < 5:
                    # K线数据不足，跳过
                    no_kline_count += 1
                    continue
                
                checked_count += 1
                
                # 获取收盘价列
                close_col = 'close' if 'close' in kline.columns else 'Close'
                if close_col not in kline.columns:
                    continue
                
                # 计算近30日最高收盘价
                high_30 = float(kline[close_col].max())
                current_close = float(kline[close_col].iloc[-1])  # 最新收盘价
                
                if high_30 <= 0:
                    continue
                
                # 计算距离最高价的百分比
                distance = (high_30 - current_close) / high_30
                
                # 距离30日最高价 ≤ max_high_distance（默认5%）
                if distance <= max_high_distance:
                    valid_codes.append(code)
            
            logger.info(f"  📊 K线匹配统计: 无K线={no_kline_count}, 已检查={checked_count}, 符合条件={len(valid_codes)}")
            
            stock_data = stock_data[stock_data[code_col].isin(valid_codes)]
            final_count = len(stock_data)
            logger.info(f"✅ S1新高过滤完成：剩余 {final_count} 只（剔除 {original_count - final_count} 只）")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"❌ S1过滤失败: {e}", exc_info=True)
            return stock_data
    
    def _get_kline_batch(self, codes: List[str], days: int = 30, end_date: Optional[str] = None) -> Dict[str, pd.DataFrame]:
        """
        批量获取K线数据
        
        Args:
            codes: 股票代码列表
            days: 获取天数
            end_date: 结束日期（YYYY-MM-DD），默认为当前日期
        
        Returns:
            K线数据字典 {ts_code: DataFrame}
        """
        try:
            from datetime import datetime, timedelta
            
            if not self.warehouse.warehouse_service:
                return {}
            
            # 使用指定的结束日期，如果没有则使用当前日期
            if end_date is None:
                end_date = datetime.now().strftime('%Y-%m-%d')
            
            # 计算开始日期
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            start_date = (end_date_obj - timedelta(days=days*2)).strftime('%Y-%m-%d')  # 多取一些天数
            
            # 使用批量获取方法
            df = self.warehouse.load_history_kline_batch(codes, start_date, end_date)
            
            if df is None or df.empty:
                return {}
            
            # 按股票代码分组
            result = {}
            code_col = 'ts_code' if 'ts_code' in df.columns else 'code'
            
            for code in codes:
                # 尝试多种格式匹配
                stock_df = df[df[code_col] == code].copy()
                
                # 如果6位代码匹配不到，尝试带后缀格式
                if stock_df.empty and len(code) == 6:
                    if code.startswith('6'):
                        ts_code = f"{code}.SH"
                    else:
                        ts_code = f"{code}.SZ"
                    stock_df = df[df[code_col] == ts_code].copy()
                
                # 如果带后缀格式匹配不到，尝试去掉后缀
                if stock_df.empty and '.' in code:
                    pure_code = code.split('.')[0]
                    stock_df = df[df[code_col] == pure_code].copy()
                
                if not stock_df.empty:
                    # 只取最近days天
                    stock_df = stock_df.sort_values('trade_date').tail(days)
                    result[code] = stock_df
            
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ 批量获取K线数据失败: {e}")
            return {}
    
    def _get_historical_s1_stocks(self, lookback_days: int = 30) -> List[str]:
        """
        获取历史上曾经进入S1的所有股票（去重）
        
        Args:
            lookback_days: 回看天数
        
        Returns:
            股票代码列表（ts_code格式）
        """
        try:
            if not self.warehouse.warehouse_service:
                return []
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                result = session.execute(text(f"""
                    SELECT DISTINCT ts_code 
                    FROM dim_stock_universe 
                    WHERE universe_type = 's1' 
                    AND trade_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
                    AND is_active = true
                """))
                codes = [row[0] for row in result]
                logger.info(f"  📊 获取近{lookback_days}天历史S1股票: {len(codes)} 只")
                return codes
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"获取历史S1股票失败: {e}")
            return []
    
    def s2_universe_filter(
        self,
        stock_data: pd.DataFrame,
        min_pullback: Optional[float] = None,
        max_pullback: Optional[float] = None,
        require_price_above_ma10: Optional[bool] = None,
        lookback_days: Optional[int] = None,
        trade_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        S2 新高回踩策略股票池
        
        目标：历史S1股票回踩后站上5日线
        
        过滤条件：
        1. 曾经符合S1新高条件（近N天内）
        2. 从30日最高点回踩10%-25%
        3. 收盘价站上5日均线
        
        Args:
            stock_data: 已通过基础过滤的股票数据
            min_pullback: 最小回踩幅度（默认10%）
            max_pullback: 最大回踩幅度（默认25%）
            require_price_above_ma10: 是否要求收盘价>MA10（默认True）
            lookback_days: 回看天数（默认30天）
            trade_date: 交易日期
        
        Returns:
            过滤后的DataFrame
        """
        try:
            from backend.config.universe_filter_config import S2_FILTER_CONFIG
            
            if min_pullback is None:
                min_pullback = S2_FILTER_CONFIG.get('min_pullback', 0.10)
            if max_pullback is None:
                max_pullback = S2_FILTER_CONFIG.get('max_pullback', 0.25)
            if require_price_above_ma10 is None:
                require_price_above_ma10 = S2_FILTER_CONFIG.get('require_price_above_ma10', True)
            if lookback_days is None:
                lookback_days = S2_FILTER_CONFIG.get('lookback_days', 30)
            
            logger.info(f"📊 开始S2新高回踩过滤")
            logger.info(f"  配置: 回踩{min_pullback*100:.0f}%-{max_pullback*100:.0f}%, 站上MA10={require_price_above_ma10}, 回看{lookback_days}天")
            
            # 1. 获取历史所有曾经进入S1的股票（核心改动）
            historical_s1_codes = self._get_historical_s1_stocks(lookback_days)
            
            if not historical_s1_codes:
                logger.warning("  ⚠️ 未找到历史S1股票，尝试从当前基础池筛选")
                if stock_data.empty:
                    return pd.DataFrame()
                code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
                historical_s1_codes = stock_data[code_col].tolist()
            
            logger.info(f"  📊 候选股票池（历史S1合集）: {len(historical_s1_codes)} 只")
            
            # 2. 获取这些股票的K线数据
            kline_data = self._get_kline_batch(historical_s1_codes, days=35)
            
            valid_codes = []
            no_kline = 0
            too_short = 0
            pullback_fail = 0
            ma10_fail = 0
            
            for code in historical_s1_codes:
                if code not in kline_data or kline_data[code].empty:
                    no_kline += 1
                    continue
                
                df = kline_data[code].sort_values('trade_date', ascending=False)
                
                if len(df) < 10:
                    too_short += 1
                    continue
                
                # 当前收盘价
                current_close = float(df.iloc[0]['close'])
                
                # 30日最高收盘价
                high_30d = df.head(30)['close'].astype(float).max()
                
                # 计算回踩幅度
                pullback = (high_30d - current_close) / high_30d
                
                # 检查回踩幅度是否在范围内
                if pullback < min_pullback or pullback > max_pullback:
                    pullback_fail += 1
                    continue
                
                # 计算10日均线
                ma10 = df.head(10)['close'].astype(float).mean()
                
                # 检查是否站上10日线
                if require_price_above_ma10 and current_close <= ma10:
                    ma10_fail += 1
                    continue
                
                valid_codes.append(code)
                logger.info(f"  ✅ {code}: 回踩{pullback*100:.1f}%, 收盘{current_close:.2f}, MA10={ma10:.2f}")
            
            logger.info(f"  📊 筛选统计: 无K线={no_kline}, 数据不足={too_short}, 回踩不符={pullback_fail}, 未站上MA10={ma10_fail}, 通过={len(valid_codes)}")
            
            # 3. 返回结果
            if stock_data.empty:
                # 如果没有传入stock_data，构造一个简单的DataFrame
                result_df = pd.DataFrame({'ts_code': valid_codes})
            else:
                code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
                result_df = stock_data[stock_data[code_col].isin(valid_codes)]
            
            logger.info(f"✅ S2新高回踩过滤完成：筛选出 {len(valid_codes)} 只")
            
            return result_df
            
        except Exception as e:
            logger.error(f"❌ S2过滤失败: {e}", exc_info=True)
            return stock_data
    
    def s3_universe_filter(
        self,
        stock_data: pd.DataFrame,
        min_turnover_rate: float = 3.0,  # 临时降级：3%
        require_limit_up: bool = False,  # 是否要求涨停
        min_change_pct: float = 3.0  # 临时替代：涨幅 > 3%
    ) -> pd.DataFrame:
        """
        S3 实验策略股票池（情绪/事件驱动/妖股）
        
        目标：次新、妖股、事件驱动
        
        过滤条件：
        1. 换手率 > 5%
        2. 连续涨停 > 1天 OR 今日涨停（可选）
        
        Args:
            stock_data: 已通过基础过滤的股票数据
            min_turnover_rate: 最低换手率（默认5%）
            require_limit_up: 是否要求涨停（默认False）
        
        Returns:
            过滤后的DataFrame
        """
        try:
            if stock_data.empty:
                return pd.DataFrame()
            
            original_count = len(stock_data)
            logger.info(f"📊 开始S3实验策略过滤：原始股票数 {original_count}")
            
            # 1. 换手率过滤（容错：如果数据全部为0，跳过此条件）
            if 'turnover_rate' in stock_data.columns or 'turnoverRate' in stock_data.columns:
                turnover_col = 'turnover_rate' if 'turnover_rate' in stock_data.columns else 'turnoverRate'
                # 检查是否有非0数据
                non_zero_count = (stock_data[turnover_col] > 0).sum()
                if non_zero_count > 0:
                    stock_data = stock_data[stock_data[turnover_col] >= min_turnover_rate]
                else:
                    logger.warning(f"  ⚠️ 换手率数据全部为0，跳过换手率过滤（容错策略）")
            
            # 2. 涨停过滤（可选）或涨幅过滤
            if require_limit_up:
                # 优先使用涨停数据字段
                if 'is_today_limit_up' in stock_data.columns:
                    # 今日涨停 OR 连板>1天
                    if 'continuous_days' in stock_data.columns:
                        stock_data = stock_data[
                            (stock_data['is_today_limit_up'] == True) | 
                            (stock_data['continuous_days'] > 1)
                        ]
                    else:
                        stock_data = stock_data[stock_data['is_today_limit_up'] == True]
                    logger.debug(f"  ✅ 使用涨停数据过滤: {len(stock_data)} 只")
                elif 'change_pct' in stock_data.columns or 'changePct' in stock_data.columns:
                    # 降级：使用涨幅判断涨停（涨幅 >= 9.5%）
                    change_col = 'change_pct' if 'change_pct' in stock_data.columns else 'changePct'
                    stock_data = stock_data[stock_data[change_col] >= 9.5]
                    logger.debug(f"  ⚠️ 涨停数据缺失，使用涨幅过滤（>=9.5%）: {len(stock_data)} 只")
                else:
                    logger.warning(f"  ⚠️ 涨停数据缺失，跳过涨停过滤")
            else:
                # 使用涨幅过滤
                if 'change_pct' in stock_data.columns or 'changePct' in stock_data.columns:
                    change_col = 'change_pct' if 'change_pct' in stock_data.columns else 'changePct'
                    # 涨幅 >= min_change_pct%
                    stock_data = stock_data[stock_data[change_col] >= min_change_pct]
            
            final_count = len(stock_data)
            logger.info(f"✅ S3实验策略过滤完成：剩余 {final_count} 只（剔除 {original_count - final_count} 只）")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"❌ S3过滤失败: {e}", exc_info=True)
            return stock_data
    
    def high_180d_universe_filter(
        self,
        stock_data: pd.DataFrame,
        max_high_distance: float = 0.05,
        min_price: float = 5.0,
        min_amount: float = 2e8,
        max_change_180d: float = 300.0,
        allowed_prefixes: List[str] = None,
        kline_data: Optional[Dict] = None,
        skip_basic_filter: bool = False,
        target_date: Optional[str] = None,
        strategy_name: str = "180日高点"
    ) -> pd.DataFrame:
        """
        180日高点策略股票池（主板强势股）
        
        目标：筛选主板市场中已是180日新高的优质股票
        
        过滤条件：
        1. 已是180日新高（当前收盘价 >= 近180个交易日最高收盘价）
        2. 股价 > 5元
        3. 成交额 > 10亿
        4. 180日涨幅 < 60%（剔除涨幅过大的股票）
        5. 不是ST股票（如果skip_basic_filter=False）
        6. 只保留主板股票（如果skip_basic_filter=False）
        
        Args:
            stock_data: 股票数据
            max_high_distance: 距离180日最高价的最大距离（已废弃，现在要求已是新高）
            min_price: 最低股价（默认5元）
            min_amount: 最低成交额（默认10亿）
            max_change_180d: 最大180日涨幅（默认60%）
            allowed_prefixes: 允许的代码前缀（如果skip_basic_filter=False时使用）
            kline_data: K线数据字典（可选）
            skip_basic_filter: 是否跳过基础过滤（代码前缀、ST），当输入已是主板池时设为True
        
        Returns:
            过滤后的DataFrame
        """
        try:
            if allowed_prefixes is None:
                allowed_prefixes = ['600', '601', '603', '000', '001', '002']
            
            if stock_data.empty:
                return pd.DataFrame()
            
            original_count = len(stock_data)
            logger.info(f"📊 开始{strategy_name}策略过滤：原始股票数 {original_count}")
            logger.info(f"  配置: 已是180日新高, 股价>{min_price}元, 成交额>{min_amount/1e8:.0f}亿, 涨幅限制<{max_change_180d}%")
            
            code_col = 'ts_code' if 'ts_code' in stock_data.columns else 'code'
            
            # 1-2. 代码前缀和ST过滤（如果输入不是主板池，则需要过滤）
            if not skip_basic_filter:
                # 1. 代码前缀过滤（只保留主板）
                if code_col in stock_data.columns:
                    before_count = len(stock_data)
                    # 提取纯数字代码部分
                    stock_data['_code_prefix'] = stock_data[code_col].astype(str).str.replace(r'\.(SH|SZ)$', '', regex=True).str[:3]
                    stock_data = stock_data[stock_data['_code_prefix'].isin(allowed_prefixes)]
                    stock_data = stock_data.drop(columns=['_code_prefix'])
                    logger.info(f"  ✅ 代码前缀过滤: {before_count} -> {len(stock_data)} (只保留主板股票)")
                
                # 2. ST过滤
                if 'name' in stock_data.columns:
                    before_count = len(stock_data)
                    stock_data = stock_data[~stock_data['name'].astype(str).str.upper().str.contains('ST', na=False)]
                    logger.info(f"  ✅ ST过滤: {before_count} -> {len(stock_data)} (剔除ST股票)")
            else:
                logger.info(f"  ⏭️ 跳过基础过滤（输入已是主板池）")
            
            # 3. 股价过滤
            price_col = None
            for col in ['close', 'Close', 'lastPrice', 'currentPrice']:
                if col in stock_data.columns:
                    price_col = col
                    break
            
            if price_col:
                before_count = len(stock_data)
                stock_data = stock_data[pd.to_numeric(stock_data[price_col], errors='coerce') > min_price].copy()
                logger.info(f"  ✅ 股价过滤(>{min_price}元): {before_count} -> {len(stock_data)}")
            
            # 4. 成交额过滤（特殊处理：一字涨停板豁免）
            if 'amount' in stock_data.columns:
                before_count = len(stock_data)
                
                # 判断是否为一字涨停板（豁免成交额要求）
                # 注意：pre_close字段可能不准确，需要直接查询前一交易日数据
                is_limit_board = pd.Series([False] * len(stock_data), index=stock_data.index)
                
                # 检查必要字段
                open_col = None
                for col in ['open', 'Open']:
                    if col in stock_data.columns:
                        open_col = col
                        break
                
                date_col = None
                for col in ['trade_date', 'TradeDate', 'date']:
                    if col in stock_data.columns:
                        date_col = col
                        break
                
                if open_col and date_col and code_col and price_col and target_date:
                    # 批量查询前一交易日的收盘价
                    from data_warehouse.service.warehouse_service import WarehouseService
                    from data_warehouse.models.generated_models import FactDailyPriceQfq
                    from datetime import datetime
                    
                    try:
                        ws = WarehouseService()
                        session = ws.get_session()
                        
                        target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
                        codes = stock_data[code_col].unique().tolist()
                        
                        # 批量查询前一交易日数据
                        prev_data = session.query(
                            FactDailyPriceQfq.ts_code,
                            FactDailyPriceQfq.close
                        ).filter(
                            FactDailyPriceQfq.ts_code.in_(codes),
                            FactDailyPriceQfq.trade_date < target_date_obj
                        ).order_by(
                            FactDailyPriceQfq.ts_code,
                            FactDailyPriceQfq.trade_date.desc()
                        ).all()
                        
                        session.close()
                        
                        # 构建前日收盘价映射（每个股票取最新的一条）
                        prev_close_map = {}
                        for ts_code, close in prev_data:
                            if ts_code not in prev_close_map:
                                prev_close_map[ts_code] = float(close) if close else None
                        
                        # 添加前日收盘价列
                        stock_data['_prev_close'] = stock_data[code_col].map(prev_close_map)
                        
                        # 计算一字涨停板
                        open_values = pd.to_numeric(stock_data[open_col], errors='coerce')
                        close_values = pd.to_numeric(stock_data[price_col], errors='coerce')
                        prev_close_values = pd.to_numeric(stock_data['_prev_close'], errors='coerce')
                        
                        # 涨停判断：今日收盘 / 昨日收盘 >= 1.099
                        is_limit_up = (close_values / prev_close_values) >= 1.099
                        
                        # 一字板判断：|开盘 - 收盘| / 收盘 < 0.5%（更严格）
                        price_diff_pct = abs(open_values - close_values) / close_values * 100
                        is_one_word = price_diff_pct < 0.5
                        
                        # 一字涨停板
                        is_limit_board = is_limit_up & is_one_word & (prev_close_values.notna())
                        
                        stock_data = stock_data.drop(columns=['_prev_close'], errors='ignore')
                        
                        logger.info(f"  检测到 {is_limit_board.sum()} 只一字涨停板（豁免成交额）")
                        
                    except Exception as e:
                        logger.warning(f"  ⚠️ 查询前日收盘价失败: {e}，跳过一字涨停板判断")
                
                # 成交额过滤：正常股票需要>min_amount，一字涨停板豁免
                amount_values = pd.to_numeric(stock_data['amount'], errors='coerce')
                stock_data = stock_data[(amount_values > min_amount) | is_limit_board]
                
                limit_board_count = is_limit_board.sum() if isinstance(is_limit_board, pd.Series) else 0
                if limit_board_count > 0:
                    logger.info(f"  ✅ 成交额过滤(>{min_amount/1e8:.0f}亿): {before_count} -> {len(stock_data)} (其中一字涨停板豁免: {limit_board_count} 只)")
                else:
                    logger.info(f"  ✅ 成交额过滤(>{min_amount/1e8:.0f}亿): {before_count} -> {len(stock_data)}")
            
            # 5. 距离180日高点过滤 + 180日涨幅过滤
            codes = stock_data[code_col].unique().tolist()
            
            # 如果没有传入K线数据，从数据库批量获取
            if kline_data is None:
                kline_data = self._get_kline_batch(codes, days=200, end_date=target_date)  # 传入截止日期
            
            valid_codes = []
            no_kline_count = 0
            checked_count = 0
            high_distance_fail = 0
            excessive_gain_fail = 0
            
            for code in codes:
                kline = kline_data.get(code)
                if kline is None or len(kline) < 180:
                    no_kline_count += 1
                    continue
                
                checked_count += 1
                
                # 获取收盘价列
                close_col = 'close' if 'close' in kline.columns else 'Close'
                if close_col not in kline.columns:
                    continue
                
                # 如果指定了目标日期，只取该日期之前的数据
                if target_date:
                    try:
                        from datetime import datetime
                        
                        # 统一转换为date对象进行比较
                        target_date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
                        
                        # 确保trade_date列是datetime类型
                        if kline['trade_date'].dtype == 'object' or str(kline['trade_date'].dtype) == 'object':
                            kline['trade_date'] = pd.to_datetime(kline['trade_date']).dt.date
                        elif hasattr(kline['trade_date'].iloc[0], 'date'):
                            kline['trade_date'] = kline['trade_date'].dt.date
                        
                        kline = kline[kline['trade_date'] <= target_date_obj]
                        logger.debug(f"  过滤K线到{target_date}，剩余{len(kline)}条")
                    except Exception as e:
                        logger.warning(f"  ⚠️ 目标日期过滤失败: {e}，使用全部K线数据")
                
                # 按日期排序，取最近180天
                kline_sorted = kline.sort_values('trade_date', ascending=False).head(180)
                
                # 当前收盘价（最新）
                current_close = float(kline_sorted[close_col].iloc[0])
                
                # 180日前收盘价（最早）
                close_180d_ago = float(kline_sorted[close_col].iloc[-1])
                
                # 180日最高收盘价
                high_180 = float(kline_sorted[close_col].max())
                
                if high_180 <= 0 or close_180d_ago <= 0:
                    continue
                
                # 条件1：已是180日新高（当前价格 >= 最高价）
                # 计算方式：(最高价 - 当前价) / 最高价
                # distance <= 0 表示当前价格已超过最高价（创新高）
                distance = (high_180 - current_close) / high_180
                # 判断：只保留已是新高的股票（distance <= 0）
                if distance > 0:
                    high_distance_fail += 1
                    continue
                
                # 条件2：180日涨幅 < 60%
                change_180d = (current_close - close_180d_ago) / close_180d_ago * 100
                if change_180d >= max_change_180d:
                    excessive_gain_fail += 1
                    logger.debug(f"  {code}: 涨幅过大 {change_180d:.1f}% > {max_change_180d}%, 180日前={close_180d_ago:.2f}, 当前={current_close:.2f}")
                    continue
                
                valid_codes.append(code)
            
            logger.info(f"  📊 K线匹配统计: 无K线={no_kline_count}, 已检查={checked_count}")
            logger.info(f"     未达高点={high_distance_fail}, 涨幅过大={excessive_gain_fail}, 符合条件={len(valid_codes)}")
            
            stock_data = stock_data[stock_data[code_col].isin(valid_codes)]
            final_count = len(stock_data)
            logger.info(f"✅ {strategy_name}策略过滤完成：剩余 {final_count} 只（剔除 {original_count - final_count} 只）")
            
            return stock_data
            
        except Exception as e:
            logger.error(f"❌ {strategy_name}策略过滤失败: {e}", exc_info=True)
            return stock_data
    
    def _get_financial_data_batch(self, codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取财务数据
        
        Args:
            codes: 股票代码列表
        
        Returns:
            财务数据字典 {code: {roe_ttm, gross_margin, ...}}
        """
        try:
            if not codes:
                return {}
            
            # 获取最新日期的财务数据
            today = datetime.now().strftime('%Y-%m-%d')
            
            if not self.warehouse.warehouse_service:
                logger.warning("⚠️ WarehouseService未初始化")
                return {}
            
            session = self.warehouse.warehouse_service.get_session()
            try:
                # 分批查询，避免参数过多
                batch_size = 500
                financial_data = {}
                
                for i in range(0, len(codes), batch_size):
                    batch_codes = codes[i:i+batch_size]
                    
                    # 从 fact_daily_fundamental 获取估值和盈利能力指标（获取最新数据，不限制日期）
                    # 从 fact_fundamental 获取负债率（需要JOIN）
                    query = text("""
                        SELECT DISTINCT ON (fd.ts_code)
                            fd.ts_code,
                            fd.roe_ttm,
                            fd.gross_margin_ttm,
                            fd.net_margin_ttm,  -- 净利率（替代净利润）
                            fd.op_cf_ttm,
                            COALESCE(ff.debt_ratio, 0) as debt_ratio,  -- 从fact_fundamental获取
                            fd.pe_ttm,
                            '' as industry  -- 暂时为空，后续可从dim_stock获取
                        FROM fact_daily_fundamental fd
                        LEFT JOIN fact_fundamental ff 
                            ON fd.ts_code = ff.ts_code 
                            AND ff.end_date = (
                                SELECT MAX(end_date) 
                                FROM fact_fundamental 
                                WHERE ts_code = ff.ts_code
                            )
                        WHERE fd.ts_code = ANY(:codes)
                            AND fd.roe_ttm IS NOT NULL  -- 只获取有ROE数据的记录
                        ORDER BY fd.ts_code, fd.trade_date DESC
                        LIMIT 10000  -- 限制结果数量，避免过多数据
                    """)
                    
                    result = session.execute(query, {'codes': batch_codes})
                    
                    for row in result:
                        code = row[0]
                        if code not in financial_data:  # 避免重复
                            financial_data[code] = {
                                'roe_ttm': float(row[1]) if row[1] else 0,  # ROE（%）
                                'gross_margin_ttm': float(row[2]) if row[2] else 0,  # 毛利率（%）
                                'gross_margin': float(row[2]) if row[2] else 0,  # 兼容字段名
                                'net_margin_ttm': float(row[3]) if row[3] else 0,  # 净利率（%）
                                'net_profit_ttm': float(row[3]) if row[3] else 0,  # 兼容字段名（用净利率替代）
                                'op_cf_ttm': float(row[4]) if row[4] else 0,  # 经营现金流
                                'debt_ratio': float(row[5]) if row[5] else 0,  # 负债率（%）
                                'pe_ttm': float(row[6]) if row[6] else 999,  # PE TTM
                                'industry': row[7] if row[7] else ''  # 行业
                            }
            finally:
                session.close()
            
            return financial_data
            
        except Exception as e:
            logger.warning(f"⚠️ 批量获取财务数据失败: {e}")
            return {}


def filter_stock_universe(
    stock_data: pd.DataFrame,
    strategy_type: str = 'base',
    **kwargs
) -> pd.DataFrame:
    """
    统一的股票池过滤接口
    
    Args:
        stock_data: 股票数据DataFrame
        strategy_type: 策略类型（'base', 's1', 's2', 's3'）
        **kwargs: 过滤参数
    
    Returns:
        过滤后的DataFrame
    """
    filter_service = StockUniverseFilter()
    
    # 先进行基础过滤
    filtered_data = filter_service.base_universe_filter(stock_data, **kwargs)
    
    # 根据策略类型进行进一步过滤
    if strategy_type == 's1':
        filtered_data = filter_service.s1_universe_filter(filtered_data, **kwargs)
    elif strategy_type == 's2':
        filtered_data = filter_service.s2_universe_filter(filtered_data, **kwargs)
    elif strategy_type == 's3':
        filtered_data = filter_service.s3_universe_filter(filtered_data, **kwargs)
    
    return filtered_data

