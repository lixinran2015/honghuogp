#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定时任务：刷新股票快照并生成推荐
在四个时间点（09:15, 11:30, 13:00, 15:00）执行

用法：
    python backend/scripts/refresh_stock_snapshot.py
    python backend/scripts/refresh_stock_snapshot.py --snapshot-time 11:30
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, time as dt_time
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from backend.services.market_data_service_v2 import MarketDataService
from backend.services.stock.stock_universe_service import StockUniverseService
from backend.services.stock.stock_filter_service import StockFilterService
from backend.services.recommendation.recommendation_engine import RecommendationEngine
from backend.services.recommendation.recommendation_result_service import RecommendationResultService
from backend.models.stock_data import StockData

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def refresh_snapshot_and_recommendations(snapshot_time: Optional[str] = None, task_type: str = 'scheduled'):
    """
    刷新股票快照并生成推荐
    
    Args:
        snapshot_time: 快照时间点（格式：HH:MM），如果为None则自动判断
        task_type: 任务类型（'scheduled' 或 'manual'）
    """
    from backend.utils.task_logger import task_execution_log
    
    with task_execution_log('refresh_snapshot', task_type) as log_entry:
        try:
            now = datetime.now()
            
            # 自动判断时间点
            if snapshot_time is None:
                current_time = now.time()
                if current_time < dt_time(9, 30):
                    snapshot_time = "09:15"
                elif current_time < dt_time(13, 0):
                    snapshot_time = "11:30"
                elif current_time < dt_time(15, 0):
                    snapshot_time = "13:00"
                else:
                    snapshot_time = "15:00"
            
            trade_date = now.strftime("%Y-%m-%d")
            
            logger.info("=" * 60)
            logger.info(f"🚀 开始刷新快照 & 推荐")
            logger.info(f"   交易日期: {trade_date}")
            logger.info(f"   快照时间: {snapshot_time}")
            logger.info("=" * 60)
            
            # 初始化服务
            market_service = MarketDataService()
            universe_service = StockUniverseService()
            filter_service = StockFilterService()
            engine = RecommendationEngine()
            result_service = RecommendationResultService()
            
            # 初始化数据管理服务（用于获取30日新高筛选结果）
            from backend.services.data.data_management_service import DataManagementService
            data_mgmt_service = DataManagementService()
            
            # 1. 获取监控股票池列表（S1股票池 + 30日新高筛选）
            logger.info("📊 步骤1: 获取监控股票池（S1 + 30日新高）...")
            try:
                monitor_codes = set()  # 使用set自动去重
                
                # 1.1 获取S1股票池
                logger.info("  📥 获取S1股票池...")
                s1_codes = universe_service.get_universe_stocks(
                    universe_type='s1',
                    trade_date=trade_date,
                    active_only=True
                )
                # 转换为6位数字格式（去掉.SH/.SZ后缀）
                s1_codes_clean = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') 
                                 for code in s1_codes if code]
                monitor_codes.update(s1_codes_clean)
                logger.info(f"  ✅ S1股票池: {len(s1_codes_clean)} 只")
                
                # 1.2 获取30日新高筛选结果（从数据管理服务）
                logger.info("  📥 获取30日新高筛选结果...")
                try:
                    metrics = data_mgmt_service.get_data_quality_metrics()
                    new_high_stocks = metrics.get('data_dimensions', {}).get('new_high_strategy', {}).get('valid_stocks', [])
                    
                    if new_high_stocks:
                        # 转换为6位数字格式
                        new_high_codes_clean = [code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '') 
                                               for code in new_high_stocks if code]
                        new_added = len(set(new_high_codes_clean) - monitor_codes)
                        monitor_codes.update(new_high_codes_clean)
                        logger.info(f"  ✅ 30日新高筛选: {len(new_high_codes_clean)} 只（新增 {new_added} 只）")
                    else:
                        logger.warning("  ⚠️ 30日新高筛选结果为空")
                except Exception as e:
                    logger.warning(f"  ⚠️ 获取30日新高筛选失败: {e}，仅使用S1股票池")
                
                # 转换为列表
                base_codes = list(monitor_codes)
                
                # 限制股票数量，避免超时
                max_stocks = 500  # 最多处理500只股票，避免超时
                if len(base_codes) > max_stocks:
                    logger.warning(f"⚠️ 股票池过大({len(base_codes)}只)，限制为前{max_stocks}只")
                    base_codes = base_codes[:max_stocks]
                
                if not base_codes:
                    logger.warning("⚠️ 监控股票池为空，使用全市场（限制100只）")
                    # 降级：从Baostock获取全市场（限制数量）
                    try:
                        df_all = market_service.get_daily_snapshot_df()
                        base_codes = df_all['code'].tolist()[:100] if not df_all.empty else []
                    except Exception as e:
                        logger.error(f"⚠️ 获取全市场失败: {e}")
                        base_codes = []
                
                logger.info(f"✅ 获取到监控股票池: {len(base_codes)} 只股票（S1 + 30日新高合并去重）")
            except Exception as e:
                logger.error(f"❌ 获取监控股票池失败: {e}", exc_info=True)
                # 降级：使用全市场
                try:
                    df_all = market_service.get_daily_snapshot_df()
                    base_codes = df_all['code'].tolist() if not df_all.empty else []
                    logger.info(f"✅ 降级方案：使用全市场 {len(base_codes)} 只股票")
                except Exception as e2:
                    logger.error(f"❌ 降级方案也失败: {e2}")
                    return False
            
            # 2. 获取当天基础快照（用 Baostock）
            logger.info("📸 步骤2: 获取当日基础快照...")
            logger.info(f"   正在获取 {len(base_codes)} 只股票的日线数据（预计耗时 {len(base_codes) * 0.3:.0f} 秒），请稍候...")
            try:
                # 使用标准输出，确保进度可见
                import sys
                sys.stdout.flush()
                daily_df = market_service.get_daily_snapshot_df(codes=base_codes, date=trade_date.replace('-', ''))
                
                if daily_df.empty:
                    logger.error("❌ 无法获取日线快照数据")
                    return False
                
                logger.info(f"✅ 获取到日线快照: {len(daily_df)} 只股票")
            except Exception as e:
                logger.error(f"❌ 获取日线快照失败: {e}", exc_info=True)
                return False
            
            # 3. 获取历史 K 线（用于策略计算）
            logger.info("📚 步骤3: 获取历史K线数据...")
            try:
                # 计算日期范围（最近120天）
                from datetime import timedelta
                end_date = now.strftime("%Y%m%d")
                start_date = (now - timedelta(days=120)).strftime("%Y%m%d")  # 120天足够
                
                # 限制股票数量，避免超时（历史K线获取更慢）
                codes_for_history = base_codes[:100]  # 最多100只，避免超时
                logger.info(f"   正在获取 {len(codes_for_history)} 只股票的历史K线（{start_date} ~ {end_date}），请稍候...")
                
                history_df = market_service.get_history_kline_df(
                    codes=codes_for_history,
                    start_date=start_date,
                    end_date=end_date
                )
                
                logger.info(f"✅ 获取到历史K线: {len(history_df)} 条数据（{history_df['code'].nunique() if not history_df.empty else 0} 只股票）")
            except Exception as e:
                logger.error(f"❌ 获取历史K线失败: {e}", exc_info=True)
                history_df = pd.DataFrame()  # 继续执行，但策略可能受影响
            
            # 4. 转换为 StockData 对象列表
            logger.info("🔄 步骤4: 转换数据格式...")
            try:
                stock_data_list = []
                for _, row in daily_df.iterrows():
                    try:
                        stock = StockData(
                            code=str(row.get('code', '')).strip(),
                            name=row.get('name', ''),
                            currentPrice=float(row.get('close', 0)),
                            changePct=float(row.get('pct_chg', 0)),
                            turnoverRate=float(row.get('turnover_rate', 0)),
                            amount=float(row.get('amount', 0)),
                            sector=row.get('industry', '')
                        )
                        stock_data_list.append(stock)
                    except Exception as e:
                        logger.debug(f"转换股票数据失败: {e}")
                        continue
                
                logger.info(f"✅ 转换为StockData对象: {len(stock_data_list)} 只股票")
            except Exception as e:
                logger.error(f"❌ 数据转换失败: {e}", exc_info=True)
                return False
            
            # 5. 运行策略公式（只用快照+历史）
            logger.info("🧮 步骤5: 计算策略...")
            try:
                strategy_results = filter_service.filter_all_strategies(
                    stock_data=stock_data_list,
                    historical_data=history_df if not history_df.empty else None
                )
                
                logger.info(f"✅ 策略计算完成: {len(strategy_results)} 个策略")
            except Exception as e:
                logger.error(f"❌ 策略计算失败: {e}", exc_info=True)
                return False
            
            # 6. 融合为推荐草稿（不补实时价）
            logger.info("📝 步骤6: 生成推荐草稿...")
            try:
                generated_at = now
                
                # 生成各类推荐
                recommendation_types = ['today', 'short', 'swing', 'darwin']
                saved_count = 0
                
                for rec_type in recommendation_types:
                    try:
                        recommendations = engine.generate_recommendations(
                            strategy_signals=strategy_results,
                            recommendation_type=rec_type,
                            limit=50  # 生成更多，最终按limit返回
                        )
                        
                        if recommendations:
                            # 保存到数据库
                            result_service.save_recommendations(
                                trade_date=trade_date,
                                generated_at=generated_at,
                                recommendation_type=rec_type,
                                recommendations=recommendations
                            )
                            saved_count += 1
                            logger.info(f"✅ {rec_type} 推荐已保存: {len(recommendations)} 只股票")
                        else:
                            logger.warning(f"⚠️ {rec_type} 推荐为空，跳过保存")
                            
                    except Exception as e:
                        logger.error(f"❌ 生成 {rec_type} 推荐失败: {e}", exc_info=True)
                        continue
                
                logger.info(f"✅ 推荐草稿生成完成: {saved_count}/{len(recommendation_types)} 种类型")
            except Exception as e:
                logger.error(f"❌ 生成推荐草稿失败: {e}", exc_info=True)
                return False
            
            # 更新处理记录数（处理的股票数量）
            if log_entry:
                log_entry.update_records_processed(len(stock_data_list))
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("🎉 快照刷新 & 推荐生成完成")
            logger.info(f"   交易日期: {trade_date}")
            logger.info(f"   快照时间: {snapshot_time}")
            logger.info(f"   处理股票数: {len(stock_data_list)}")
            logger.info("=" * 60)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 刷新快照失败: {e}", exc_info=True)
            return False


if __name__ == '__main__':
    import argparse
    import io
    import contextlib
    
    parser = argparse.ArgumentParser(description='刷新股票快照并生成推荐')
    parser.add_argument(
        '--snapshot-time',
        type=str,
        default=None,
        help='快照时间点（格式：HH:MM），如 09:15'
    )
    parser.add_argument(
        '--suppress-errors',
        action='store_true',
        help='抑制库内部的错误输出（如 easyquotation 的警告）'
    )
    
    args = parser.parse_args()
    
    # 如果指定了抑制错误，重定向 stderr
    if args.suppress_errors:
        with contextlib.redirect_stderr(io.StringIO()):
            success = refresh_snapshot_and_recommendations(snapshot_time=args.snapshot_time)
    else:
        success = refresh_snapshot_and_recommendations(snapshot_time=args.snapshot_time)
    
    sys.exit(0 if success else 1)

