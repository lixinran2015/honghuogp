"""
每日增量更新脚本
用于每日收盘后更新最新数据
"""

import logging
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_warehouse.sources.akshare_client import AkShareClient
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.layers.clean_layer import CleanDataLayer
from data_warehouse.service.warehouse_service import WarehouseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_last_trade_date() -> Optional[date]:
    """
    获取最后一个交易日
    
    Returns:
        date: 最后一个交易日，如果没有数据返回None
    """
    try:
        service = WarehouseService()
        latest = service.get_latest_daily('600519.SH')  # 使用一个常见股票查询
        if latest:
            return latest['trade_date']
        return None
    except Exception as e:
        logger.debug(f"获取最后交易日失败: {e}")
        # 如果查询失败，返回昨天（简化处理）
        yesterday = date.today() - timedelta(days=1)
        # 如果是周末，返回周五
        while yesterday.weekday() >= 5:
            yesterday -= timedelta(days=1)
        return yesterday


def update_daily_prices(target_date: Optional[date] = None, batch_size: int = 50, delay: float = 0.3):
    """
    更新日线数据
    
    Args:
        target_date: 目标日期，如果为None则使用今天
        batch_size: 每批处理的股票数量
        delay: 每只股票之间的延迟（秒）
    """
    from backend.utils.task_logger import task_execution_log
    
    with task_execution_log('daily_update', 'scheduled'):
        if target_date is None:
            target_date = date.today()
        
        logger.info("=" * 60)
        logger.info(f"开始更新日线数据: {target_date}")
        logger.info("=" * 60)
        
        # 初始化客户端和服务（只使用AkShare，不再使用Tushare）
        akshare_client = AkShareClient()
        raw_layer = RawDataLayer()
        clean_layer = CleanDataLayer()
        warehouse_service = WarehouseService()
        
        # 只使用AkShare
        client = akshare_client
        
        if not client.available:
            logger.error("❌ 所有数据源都不可用")
            return False
        
        logger.info(f"使用数据源: {client.source_name}")
        
        # 获取股票列表
        logger.info("从维表获取股票列表...")
        stock_list = warehouse_service.get_stock_list()
        if not stock_list:
            logger.warning("⚠️ 维表中没有股票，请先运行 init_stock_dim.py")
            return False
        
        ts_codes = [s['ts_code'] for s in stock_list]
        logger.info(f"获取到 {len(ts_codes)} 只股票")
        logger.info("")
        
        # 统计信息
        total_stocks = len(ts_codes)
        success_count = 0
        failed_count = 0
        skip_count = 0
        
        # 批量处理
        for batch_idx in range(0, total_stocks, batch_size):
            batch_codes = ts_codes[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            total_batches = (total_stocks + batch_size - 1) // batch_size
            
            logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch_codes)} 只股票")
            
            for i, ts_code in enumerate(batch_codes, 1):
                stock_num = batch_idx + i
                logger.debug(f"  [{stock_num}/{total_stocks}] {ts_code}")
                
                try:
                    # 获取单日数据
                    daily_data = client.get_daily_price(ts_code, target_date, target_date)
                    
                    if not daily_data:
                        # 可能该股票当日停牌或数据不存在
                        skip_count += 1
                        continue
                    
                    # 保存到Raw层
                    raw_saved = 0
                    for data in daily_data:
                        success = raw_layer.save_daily_price(
                            ts_code=data['ts_code'],
                            trade_date=data['trade_date'],
                            data={
                                'open': data.get('open'),
                                'high': data.get('high'),
                                'low': data.get('low'),
                                'close': data.get('close'),
                                'pre_close': data.get('pre_close'),
                                'vol': data.get('vol'),
                                'amount': data.get('amount'),
                                'turnover_rate': data.get('turnover_rate')
                            },
                            source=client.source_name,
                            raw_payload=data
                        )
                        if success:
                            raw_saved += 1
                    
                    if raw_saved == 0:
                        skip_count += 1
                        continue
                    
                    # 合并到Fact层
                    fact_data = clean_layer.merge_daily_prices(
                        ts_code=ts_code,
                        trade_date=target_date
                    )
                    if fact_data:
                        if clean_layer.save_fact_daily_price(fact_data):
                            success_count += 1
                        else:
                            skip_count += 1
                    else:
                        skip_count += 1
                    
                    # 延迟
                    if delay > 0:
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"  ❌ 更新失败 {ts_code}: {e}")
                    failed_count += 1
            
            # 批次之间的延迟
            if batch_idx + batch_size < total_stocks and delay > 0:
                time.sleep(delay * 2)
        
        logger.info("=" * 60)
        logger.info(f"日线数据更新完成: {target_date}")
        logger.info(f"  总计: {total_stocks} 只")
        logger.info(f"  成功: {success_count} 只")
        logger.info(f"  跳过: {skip_count} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info("=" * 60)
        
        return success_count > 0


def update_fundamental(limit: Optional[int] = None, batch_size: int = 120, delay: float = 0.1, task_id: Optional[str] = None, task_type: str = 'scheduled', max_retries: int = 3, max_workers: int = 2, force: bool = False):
    """
    更新财务数据（最新一期，带重试机制）
    
    Args:
        limit: 限制更新的股票数量，如果为None则更新所有
        batch_size: 每批处理的股票数量（默认120，约 480 次/分钟 满负荷）
        delay: 每只股票之间的延迟（秒）
        task_id: 任务ID（可选）
        task_type: 任务类型（'scheduled' 或 'manual'）
        max_retries: 失败重试次数（默认3次）
        max_workers: 最大并发线程数（默认2，配合 Tushare 480次/分钟限速）
        force: 是否强制更新（忽略今日已更新检查，默认False）
    """
    from backend.utils.task_logger import task_execution_log
    from datetime import datetime, date
    
    # 检查今天是否已经更新过（除非强制更新）
    if not force:
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            from data_warehouse.models import TaskExecutionLog
            from sqlalchemy import func
            
            warehouse = PostgresWarehouse()
            if warehouse._initialized and warehouse.warehouse_service:
                session = warehouse.warehouse_service.get_session()
                try:
                    today = date.today()
                    # 查询今天是否有成功执行的记录
                    today_task = session.query(TaskExecutionLog).filter(
                        TaskExecutionLog.task_name == 'fundamental_update',
                        func.date(TaskExecutionLog.started_at) == today,
                        TaskExecutionLog.status == 'success',
                        TaskExecutionLog.records_processed > 0  # 确保有处理记录
                    ).order_by(TaskExecutionLog.started_at.desc()).first()
                    
                    if today_task:
                        logger.info("=" * 60)
                        logger.info(f"✅ 财务数据今天已更新过（任务ID: {today_task.id}）")
                        logger.info(f"   执行时间: {today_task.started_at}")
                        logger.info(f"   处理记录数: {today_task.records_processed}")
                        logger.info(f"   耗时: {today_task.duration_seconds}秒")
                        logger.info("=" * 60)
                        logger.info("💡 如需强制更新，请使用 force=True 参数")
                        logger.info("")
                        return True  # 返回True表示已更新过，不需要重复更新
                except Exception as e:
                    logger.warning(f"⚠️ 检查今日更新记录失败: {e}，将继续执行更新")
                finally:
                    session.close()
        except Exception as e:
            logger.debug(f"无法检查今日更新记录: {e}，将继续执行更新")
    
    with task_execution_log('fundamental_update', task_type, task_id) as log_entry:
        logger.info("=" * 60)
        logger.info("开始更新财务数据")
        if force:
            logger.info("⚠️ 强制更新模式（忽略今日已更新检查）")
        logger.info("=" * 60)
        
        # 初始化客户端和服务（使用Tushare）
        from data_warehouse.sources.tushare_client import TushareClient
        
        tushare_client = TushareClient()
        raw_layer = RawDataLayer()
        clean_layer = CleanDataLayer()
        warehouse_service = WarehouseService()
        
        # 使用Tushare
        client = tushare_client
        if not client.available:
            logger.error("❌ Tushare数据源不可用（接口状态不通）")
            if log_entry:
                log_entry.update_records_processed(0)  # 确保记录数为0
            return False
        
        logger.info(f"使用数据源: {client.source_name} (接口状态: 可用)")
        
        # 获取股票列表
        stock_list = warehouse_service.get_stock_list()
        if not stock_list:
            logger.warning("⚠️ 维表中没有股票")
            return False
        
        ts_codes = [s['ts_code'] for s in stock_list]
        if limit:
            ts_codes = ts_codes[:limit]
        
        logger.info(f"更新 {len(ts_codes)} 只股票的财务数据")
        logger.info("")
        
        # 优化1: 智能跳过已更新的股票（检查最新报告期）
        session = warehouse_service.get_session()
        try:
            from data_warehouse.models.generated_models import FactFundamental
            from sqlalchemy import func
            
            # 获取每只股票的最新报告期
            latest_reports = {}
            if len(ts_codes) > 0:
                subquery = session.query(
                    FactFundamental.ts_code,
                    func.max(FactFundamental.end_date).label('max_date')
                ).filter(
                    FactFundamental.ts_code.in_(ts_codes)
                ).group_by(FactFundamental.ts_code).subquery()
                
                latest_records = session.query(
                    FactFundamental.ts_code,
                    FactFundamental.end_date,
                    FactFundamental.report_type
                ).join(
                    subquery,
                    (FactFundamental.ts_code == subquery.c.ts_code) &
                    (FactFundamental.end_date == subquery.c.max_date)
                ).all()
                
                for record in latest_records:
                    latest_reports[record.ts_code] = {
                        'end_date': record.end_date,
                        'report_type': record.report_type
                    }
            
            logger.info(f"📊 检查到 {len(latest_reports)} 只股票已有财务数据")
        except Exception as e:
            logger.warning(f"⚠️ 检查最新报告期失败，将更新所有股票: {e}")
            latest_reports = {}
        finally:
            session.close()
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        # 只对「数据库中缺失财务数据」的股票请求接口，已有任意报告期的均不请求
        missing_codes = [c for c in ts_codes if c not in latest_reports]
        skipped_count = len(ts_codes) - len(missing_codes)
        if skipped_count > 0:
            logger.info(f"📊 库中已有财务数据: {skipped_count} 只，不请求接口；待补全: {len(missing_codes)} 只")
        if not missing_codes:
            logger.info("✅ 无缺失财务数据，跳过更新")
            if log_entry:
                log_entry.update_records_processed(0)
            return True
        
        total_stocks = len(ts_codes)
        total_batches = (len(missing_codes) + batch_size - 1) // batch_size
        for batch_idx in range(0, len(missing_codes), batch_size):
            batch_codes = missing_codes[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            
            logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch_codes)} 只缺失股票")
            
            batch_results = {}
            try:
                logger.info(f"[批次 {batch_num}/{total_batches}] 📥 批量获取 {len(batch_codes)} 只股票财务数据（限速 480 次/分钟）")
                batch_results = client.batch_get_fundamental(batch_codes, max_workers=max_workers)
            except Exception as batch_error:
                batch_results = {}
                logger.warning(f"⚠️ 本批次批量获取失败: {batch_error}")
            
            try:
                batch_fundamental_data = []  # 本批次需落库的数据
                for idx, ts_code in enumerate(batch_codes):
                    stock_num = skipped_count + batch_idx + idx + 1
                    fundamental_data = batch_results.get(ts_code)
                    
                    if fundamental_data is None:
                        failed_count += 1
                        # 每10只股票更新一次进度
                        if log_entry and (success_count + failed_count + skipped_count) % 10 == 0:
                            log_entry.update_records_processed(success_count)
                            processed_total = success_count + failed_count + skipped_count
                            progress_pct = (processed_total / total_stocks * 100) if total_stocks > 0 else 0
                            logger.info(f"📊 进度: {processed_total}/{total_stocks} ({progress_pct:.1f}%), 成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}")
                        continue
                    
                    # 优化5: 智能跳过（如果数据库中已有相同报告期的数据，且数据完整）
                    latest_report = latest_reports.get(ts_code)
                    if latest_report:
                        latest_end_date = latest_report['end_date']
                        latest_report_type = latest_report['report_type']
                        if (fundamental_data['end_date'] == latest_end_date and 
                            fundamental_data['report_type'] == latest_report_type):
                            # 数据已是最新，跳过保存
                            skipped_count += 1
                            logger.debug(f"  [{stock_num}/{total_stocks}] ⏭️ 跳过 {ts_code}（已有最新数据: {latest_end_date}）")
                            # 每10只股票更新一次进度
                            if log_entry and (success_count + failed_count + skipped_count) % 10 == 0:
                                log_entry.update_records_processed(success_count)
                                processed_total = success_count + failed_count + skipped_count
                                progress_pct = (processed_total / total_stocks * 100) if total_stocks > 0 else 0
                                logger.info(f"📊 进度: {processed_total}/{total_stocks} ({progress_pct:.1f}%), 成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}")
                            continue
                    
                    # 累积到批次数据中
                    batch_fundamental_data.append({
                        'fundamental_data': fundamental_data,
                        'stock_num': stock_num,
                        'ts_code': ts_code
                    })
                
                # 批量保存本批次的数据（优化：使用批量操作）
                if batch_fundamental_data:
                    logger.debug(f"  💾 批量保存本批次 {len(batch_fundamental_data)} 只股票的数据...")
                    
                    # 优化：批量保存，减少数据库操作次数
                    # 使用批量操作提升效率，如果失败则降级为逐条保存
                    for item in batch_fundamental_data:
                        fundamental_data = item['fundamental_data']
                        stock_num = item['stock_num']
                        ts_code = item['ts_code']
                        
                        try:
                            # 保存原始数据
                            raw_layer.save_fundamental(
                                ts_code=fundamental_data['ts_code'],
                                end_date=fundamental_data['end_date'],
                                report_type=fundamental_data['report_type'],
                                data={
                                    'roe': fundamental_data.get('roe'),
                                    'net_margin': fundamental_data.get('net_margin'),
                                    'gross_margin': fundamental_data.get('gross_margin'),
                                    'op_cf': fundamental_data.get('op_cf'),
                                    'total_debt': fundamental_data.get('total_debt'),
                                    'total_asset': fundamental_data.get('total_asset'),
                                    'debt_ratio': fundamental_data.get('debt_ratio'),
                                    'profit_volatility': fundamental_data.get('profit_volatility')
                                },
                                source=client.source_name,
                                raw_payload=fundamental_data
                            )
                            
                            # 清洗并合并到数据仓库
                            fact_data = clean_layer.merge_fundamental(
                                ts_code=fundamental_data['ts_code'],
                                end_date=fundamental_data['end_date'],
                                report_type=fundamental_data['report_type']
                            )
                            if fact_data:
                                clean_layer.save_fact_fundamental(fact_data)
                            
                            success_count += 1
                            
                            # 每10只股票更新一次进度
                            if log_entry and (success_count + failed_count + skipped_count) % 10 == 0:
                                log_entry.update_records_processed(success_count)
                                processed_total = success_count + failed_count + skipped_count
                                progress_pct = (processed_total / total_stocks * 100) if total_stocks > 0 else 0
                                logger.info(f"📊 进度: {processed_total}/{total_stocks} ({progress_pct:.1f}%), 成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}")
                                
                        except Exception as save_error:
                            logger.error(f"  [{stock_num}/{total_stocks}] ❌ 保存财务数据失败 {ts_code}: {save_error}")
                            failed_count += 1
                
                # 批次间延迟（优化：减少延迟时间，因为使用了并发处理）
                # 并发处理已经控制了API调用频率，所以可以减少延迟
                if delay > 0:
                    time.sleep(delay * 0.5)  # 减少延迟到原来的一半
                else:
                    time.sleep(0.1)  # 最小延迟也减少
                    
            except Exception as batch_error:
                # 如果批量获取失败，降级为逐只获取
                logger.warning(f"⚠️ 批量获取失败，降级为逐只获取: {batch_error}")
                
                # 降级：逐只获取
                for idx, ts_code in enumerate(batch_codes):
                    stock_num = batch_idx + idx + 1
                    
                    # 重试机制
                    fundamental_data = None
                    retry_count = 0
                    
                    while retry_count < max_retries and fundamental_data is None:
                        try:
                            logger.debug(f"  [{stock_num}/{total_stocks}] 处理 {ts_code}... (尝试 {retry_count + 1}/{max_retries})")
                            fundamental_data = client.get_fundamental(ts_code)
                            
                            if fundamental_data is None and retry_count < max_retries - 1:
                                wait_time = delay * (retry_count + 1)
                                logger.debug(f"  [{stock_num}/{total_stocks}] {ts_code} 获取失败，等待 {wait_time:.1f}秒后重试...")
                                time.sleep(wait_time)
                                retry_count += 1
                            elif fundamental_data is None:
                                retry_count += 1
                            else:
                                break
                                
                        except Exception as fetch_error:
                            if retry_count < max_retries - 1:
                                wait_time = delay * (retry_count + 1)
                                logger.warning(f"  [{stock_num}/{total_stocks}] ⚠️ 获取财务数据异常 {ts_code} (尝试 {retry_count + 1}/{max_retries}): {fetch_error}")
                                logger.debug(f"  [{stock_num}/{total_stocks}] 等待 {wait_time:.1f}秒后重试...")
                                time.sleep(wait_time)
                                retry_count += 1
                            else:
                                logger.error(f"  [{stock_num}/{total_stocks}] ❌ 获取财务数据最终失败 {ts_code}: {fetch_error}")
                                fundamental_data = None
                                retry_count += 1
                    
                    if fundamental_data is None:
                        failed_count += 1
                        continue
                    
                    # 智能跳过
                    latest_report = latest_reports.get(ts_code)
                    if latest_report:
                        latest_end_date = latest_report['end_date']
                        latest_report_type = latest_report['report_type']
                        if (fundamental_data['end_date'] == latest_end_date and 
                            fundamental_data['report_type'] == latest_report_type):
                            skipped_count += 1
                            logger.debug(f"  [{stock_num}/{total_stocks}] ⏭️ 跳过 {ts_code}（已有最新数据: {latest_end_date}）")
                            if delay > 0:
                                time.sleep(delay)
                            else:
                                time.sleep(0.2)
                            continue
                    
                    # 保存数据
                    try:
                        # 1. 保存到Raw层
                        raw_layer.save_fundamental(
                            ts_code=fundamental_data['ts_code'],
                            end_date=fundamental_data['end_date'],
                            report_type=fundamental_data['report_type'],
                            data={
                                'roe': fundamental_data.get('roe'),
                                'net_margin': fundamental_data.get('net_margin'),
                                'gross_margin': fundamental_data.get('gross_margin'),
                                'op_cf': fundamental_data.get('op_cf'),
                                'total_debt': fundamental_data.get('total_debt'),
                                'total_asset': fundamental_data.get('total_asset'),
                                'debt_ratio': fundamental_data.get('debt_ratio'),
                                'profit_volatility': fundamental_data.get('profit_volatility')
                            },
                            source=client.source_name,
                            raw_payload=fundamental_data
                        )
                        # 2. 合并并保存到Fact层
                        fact_data = clean_layer.merge_fundamental(
                            ts_code=fundamental_data['ts_code'],
                            end_date=fundamental_data['end_date'],
                            report_type=fundamental_data['report_type']
                        )
                        if fact_data:
                            if clean_layer.save_fact_fundamental(fact_data):
                                success_count += 1
                            else:
                                logger.warning(f"  [{stock_num}/{total_stocks}] ⚠️ 保存Fact层财务数据失败 {ts_code}")
                                failed_count += 1
                        else:
                            logger.warning(f"  [{stock_num}/{total_stocks}] ⚠️ 合并财务数据失败 {ts_code}（可能Raw层数据不完整）")
                            failed_count += 1
                    except Exception as save_error:
                        logger.error(f"  [{stock_num}/{total_stocks}] ❌ 保存财务数据失败 {ts_code}: {save_error}", exc_info=True)
                        failed_count += 1
                    
                    # 延迟
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        time.sleep(0.2)
            
            # 优化2: 批量保存本批次的数据（旧代码，已移到上面，此处已删除）
                
                # 每10只股票更新一次进度
                if log_entry and (success_count + failed_count + skipped_count) % 10 == 0:
                    log_entry.update_records_processed(success_count)
                    processed_total = success_count + failed_count + skipped_count
                    progress_pct = (processed_total / total_stocks * 100) if total_stocks > 0 else 0
                    logger.info(f"📊 进度: {processed_total}/{total_stocks} ({progress_pct:.1f}%), 成功: {success_count}, 失败: {failed_count}, 跳过: {skipped_count}")
            
            # 优化6: 移除批次间延迟（Tushare较稳定，不需要额外延迟）
            # 批次之间的延迟已移除
        
        logger.info("=" * 60)
        logger.info(f"财务数据更新完成")
        logger.info(f"  总计: {total_stocks} 只")
        logger.info(f"  成功: {success_count} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info(f"  跳过: {skipped_count} 只（已有最新数据）")
        logger.info(f"  成功率: {(success_count / (total_stocks - skipped_count) * 100) if (total_stocks - skipped_count) > 0 else 0:.1f}%")
        logger.info("=" * 60)
        
        # 更新处理记录数（确保在任务完成前更新，即使没有成功也要更新）
        if log_entry:
            log_entry.update_records_processed(success_count)
            # 立即输出最终进度
            processed_total = success_count + failed_count
            progress_pct = (processed_total / total_stocks * 100) if total_stocks > 0 else 0
            logger.info(f"📊 最终进度: {processed_total}/{total_stocks} ({progress_pct:.1f}%), 成功: {success_count}, 失败: {failed_count}")
        
        # 任务成功判断：接口状态通 + 更新数据完整才算成功
        # 1. 接口状态通：数据源可用（已在前面检查）
        # 2. 更新数据完整：成功数量 > 0 且成功率 >= 50%（财务数据可能部分缺失）
        total_processed = success_count + failed_count
        success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0
        
        is_success = (
            client.available and  # 接口状态通
            success_count > 0 and  # 至少成功处理一条
            success_rate >= 50.0  # 成功率 >= 50%（财务数据可能部分缺失，降低要求）
        )
        
        if not is_success:
            logger.warning(f"⚠️ 任务未完全成功: 接口可用={client.available}, 成功数={success_count}, 成功率={success_rate:.2f}%")
        
        return is_success


def daily_update(target_date: Optional[date] = None, run_fundamental_update: bool = False):
    """
    执行每日增量更新

    Args:
        target_date: 目标日期，如果为None则使用今天
        run_fundamental_update: 是否同时更新财务数据
    """
    logger.info("=" * 60)
    logger.info("开始每日增量更新")
    logger.info("=" * 60)

    if target_date is None:
        target_date = date.today()

    logger.info(f"目标日期: {target_date}")
    logger.info("")

    # 更新日线数据
    logger.info("1. 更新日线数据...")
    price_success = update_daily_prices(target_date)

    # 更新财务数据（可选）
    if run_fundamental_update:
        logger.info("")
        logger.info("2. 更新财务数据...")
        fundamental_success = update_fundamental(limit=100, batch_size=120, delay=0.2)  # 每批120只*4接口≈480次/分钟
    else:
        fundamental_success = True
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("每日增量更新完成")
    logger.info(f"  日线数据: {'✅' if price_success else '❌'}")
    logger.info(f"  财务数据: {'✅' if fundamental_success else '❌'}")
    logger.info("=" * 60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='每日增量更新')
    parser.add_argument('--date', type=str, help='目标日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--fundamental', action='store_true', help='同时更新财务数据')
    parser.add_argument('--prices-only', action='store_true', help='只更新日线数据')
    parser.add_argument('--fundamental-only', action='store_true', help='只更新财务数据')
    parser.add_argument('--force', action='store_true', help='强制更新（忽略今日已更新检查）')
    
    args = parser.parse_args()
    
    # 解析日期
    target_date = None
    if args.date:
        target_date = date.fromisoformat(args.date)
    
    # 执行更新
    if args.fundamental_only:
        update_fundamental(force=args.force)
    elif args.prices_only:
        update_daily_prices(target_date)
    else:
        daily_update(target_date, run_fundamental_update=args.fundamental)

