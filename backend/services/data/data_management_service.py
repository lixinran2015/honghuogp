"""
数据管理服务
用于监控数据源健康状态、定时任务执行状态、数据质量指标等
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta, date
from pathlib import Path
import re

from backend.services.service_manager import get_service_manager

logger = logging.getLogger(__name__)


def _convert_to_ts_codes(codes: List[str]) -> List[str]:
    """将股票代码转换为Tushare格式（使用统一的工具函数）"""
    from backend.utils.stock_code_utils import convert_codes_to_ts_codes
    return convert_codes_to_ts_codes(codes)


def _format_date(d) -> Optional[str]:
    """格式化日期为字符串"""
    if d is None:
        return None
    if isinstance(d, date):
        return d.strftime('%Y-%m-%d')
    if hasattr(d, 'strftime'):
        return d.strftime('%Y-%m-%d')
    return str(d)[:10]


class DataManagementService:
    """数据管理服务"""
    
    # 所有支持的任务类型（含已下线仅跳过的 limit_up_volume_shrink）
    ALL_TASK_TYPES = [
        'daily_update',
        'fundamental_update',
        'refresh_snapshot',
        'sector_heat_update',
        'sector_leaders_update',
        'sync_stock',
        'sync_industry',          # 申万行业同步（dim_stock.industry 统一为申万一级）
        'moneyflow_update',       # 资金流向（行业/板块，Tushare moneyflow_ind_ths）
        's1_universe_update',
        'industry_cycle_collect',  # 行业周期数据采集（含申万行业同步）
        'industry_cycle_suggest',  # 行业周期建议生成（suggest_YYYYMMDD.json）
        'pe_pb_update',  # 从 Tushare daily_basic 更新 fact_daily_price_qfq 的 PE/PB
        'abnormal_analysis_scan',  # 异动分析扫描（收盘后自动扫描异动股票）
        'recommendation_daily',        # 推荐系统日终维护（追踪+自动平仓）
        'recommendation_daily_track',  # 已合并到 recommendation_daily
        'recommendation_auto_close',   # 已合并到 recommendation_daily
        'moneyflow_update',            # 资金流向（行业/板块）
        'money_flow_update',           # 个股主力资金 fact_money_flow
        'north_money_update',          # 北向资金数据（持股+净流入）
        'north_holding_update',        # 已合并到 north_money_update
        'north_flow_update',           # 已合并到 north_money_update
        'sector_daily_maintenance',    # 板块日终维护（热度+龙头+日线）
        'sector_heat_update',          # 已合并到 sector_daily_maintenance
        'sector_leaders_update',       # 已合并到 sector_daily_maintenance
        'sector_daily_update',         # 已合并到 sector_daily_maintenance
        'limit_up_emotion_update',     # 涨停板+市场情绪更新
    ]
    
    def __init__(self):
        """初始化服务（使用单例）"""
        self._service_manager = get_service_manager()
        self.warehouse = self._service_manager.get_postgres_warehouse()
        self.market_service = self._service_manager.get_market_data_service()
        self.universe_service = self._service_manager.get_stock_universe_service()
    
    def _check_data_source(self, source_key: str, source_name: str, source_type: str, check_func) -> Dict:
        """
        检查单个数据源的健康状态（统一处理模式）
        
        Args:
            source_key: 数据源键名
            source_name: 数据源显示名称
            source_type: 数据源类型（daily/realtime/warehouse）
            check_func: 检查函数，返回 {'available': bool, 'error': str, **extra}
        
        Returns:
            数据源健康状态字典
        """
        try:
            check_result = check_func()
            return {
                'name': source_name,
                'type': source_type,
                'available': check_result.get('available', False),
                'error': check_result.get('error'),
                **{k: v for k, v in check_result.items() if k not in ('available', 'error')}
            }
        except Exception as e:
            logger.warning("数据源 %s 检查异常: %s", source_name, e)
            return {
                'name': source_name,
                'type': source_type,
                'available': False,
                'error': '检查失败'
            }
    
    def check_data_source_health(self) -> Dict:
        """
        检查数据源健康状态
        
        Returns:
            dict: 包含各个数据源的健康状态
        """
        result = {
            'check_time': datetime.now().isoformat(),
            'sources': {}
        }
        
        # 1. 检查 Baostock
        def check_baostock():
            try:
                import baostock as bs
                lg = bs.login()
                if lg.error_code != "0":
                    raise RuntimeError(f"Baostock 登录失败: {lg.error_msg}")
                bs.logout()
                from backend.services.data_sources.baostock_source import BaostockDailySource
                baostock = BaostockDailySource()
                return {'available': baostock.available, 'error': None}
            except ImportError:
                raise RuntimeError("需要安装 baostock: pip install baostock")
        
        result['sources']['baostock'] = self._check_data_source(
            'baostock', 'Baostock', 'daily', check_baostock
        )
        
        # 2. 检查 AkShare
        def check_akshare():
            from backend.services.data_sources.akshare_daily_source import AkshareDailySource
            akshare = AkshareDailySource()
            return {'available': akshare.available, 'error': None}
        
        result['sources']['akshare'] = self._check_data_source(
            'akshare', 'AkShare', 'daily', check_akshare
        )
        
        # 3. 检查 EasyQuotation（新浪）
        def check_sina():
            from backend.services.data_sources.realtime_source import SinaRealtimeSource
            sina = SinaRealtimeSource()
            return {'available': sina.available, 'error': None}
        
        result['sources']['easyquotation_sina'] = self._check_data_source(
            'easyquotation_sina', 'EasyQuotation (Sina)', 'realtime', check_sina
        )
        
        # 4. 检查 PostgreSQL 数据仓库
        def check_postgresql():
            try:
                wh = self.warehouse
                if wh is None or not getattr(wh, '_initialized', False):
                    return {'available': False, 'error': '数据仓库未初始化'}
                latest_date = wh.get_latest_stocks_date()
                return {'available': True, 'latest_date': latest_date, 'error': None}
            except Exception as e:
                logger.warning("PostgreSQL 健康检查异常: %s", e)
                return {'available': False, 'error': '健康检查失败'}

        result['sources']['postgresql'] = self._check_data_source(
            'postgresql', 'PostgreSQL Data Warehouse', 'warehouse', check_postgresql
        )
        
        return result
    
    # 允许通过 API 手动触发的任务类型（ALL_TASK_TYPES 的子集）
    TRIGGERABLE_TASK_TYPES = [
        'daily_update', 'fundamental_update', 'refresh_snapshot',
        'sector_heat_update', 'sector_leaders_update', 'sector_daily_update',
        'sync_stock', 'sync_industry', 'moneyflow_update', 'industry_cycle_collect',
    ]

    def get_task_by_id(self, task_id: int) -> Optional[Dict]:
        """
        根据 ID 查询任务执行记录。
        Returns: 可序列化的任务字典，不存在时返回 None。
        """
        if not self.warehouse or not getattr(self.warehouse, "_initialized", False) or not self.warehouse.warehouse_service:
            return None
        try:
            from data_warehouse.models import TaskExecutionLog
            session = self.warehouse.warehouse_service.get_session()
            try:
                task = session.query(TaskExecutionLog).filter(TaskExecutionLog.id == task_id).first()
                if not task:
                    return None
                return {
                    "id": task.id,
                    "task_name": task.task_name,
                    "task_type": task.task_type,
                    "status": task.status,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                    "duration_seconds": float(task.duration_seconds) if task.duration_seconds else None,
                    "error_message": task.error_message,
                    "records_processed": task.records_processed,
                }
            finally:
                session.close()
        except Exception as e:
            logger.error(f"查询任务执行记录失败: {e}", exc_info=True)
            return None

    def get_task_execution_status(self, limit: int = 50, task_name: Optional[str] = None) -> Dict:
        """
        获取定时任务执行状态
        
        Args:
            limit: 每个任务类型返回记录数限制
            task_name: 任务名称筛选（可选）
            
        Returns:
            dict: 包含任务执行记录的列表
        """
        result = {
            'tasks': [],
            'total': 0
        }
        
        # 从数据库查询
        if self.warehouse and self.warehouse._initialized and self.warehouse.warehouse_service:
            try:
                from data_warehouse.models import TaskExecutionLog
                session = self.warehouse.warehouse_service.get_session()
                try:
                    # 如果指定了任务名称，只查询该任务
                    if task_name:
                        query = session.query(TaskExecutionLog).filter(
                            TaskExecutionLog.task_name == task_name
                        ).order_by(TaskExecutionLog.started_at.desc()).limit(limit)
                        tasks = query.all()
                    else:
                        # 否则，为每个任务类型查询最近的记录
                        tasks = []
                        for task_type in self.ALL_TASK_TYPES:
                            query = session.query(TaskExecutionLog).filter(
                                TaskExecutionLog.task_name == task_type
                            ).order_by(TaskExecutionLog.started_at.desc()).limit(limit)
                            type_tasks = query.all()
                            tasks.extend(type_tasks)
                    
                    for task in tasks:
                        result['tasks'].append({
                            'id': task.id,
                            'task_name': task.task_name,
                            'task_type': task.task_type,
                            'status': task.status,
                            'started_at': task.started_at.isoformat() if task.started_at else None,
                            'finished_at': task.finished_at.isoformat() if task.finished_at else None,
                            'duration_seconds': float(task.duration_seconds) if task.duration_seconds else None,
                            'error_message': task.error_message,
                            'records_processed': task.records_processed
                        })
                    result['total'] = len(result['tasks'])
                finally:
                    session.close()
            except Exception as e:
                logger.error(f"查询任务执行记录失败: {e}", exc_info=True)
        
        # 如果数据库记录不足，从日志文件补充
        expected_count = limit * len(self.ALL_TASK_TYPES) if not task_name else limit
        if len(result['tasks']) < expected_count:
            log_tasks = self._parse_log_files(expected_count - len(result['tasks']), task_name)
            # 去重（避免数据库和日志文件重复）
            existing_ids = {t.get('id') for t in result['tasks'] if t.get('id')}
            for log_task in log_tasks:
                if log_task.get('id') not in existing_ids and log_task.get('started_at'):
                    result['tasks'].append(log_task)
            result['total'] = len(result['tasks'])
        
        return result
    
    def _parse_log_files(self, limit: int, task_name: Optional[str] = None) -> List[Dict]:
        """
        解析日志文件，提取任务执行记录
        
        Args:
            limit: 返回记录数限制
            task_name: 任务名称筛选（可选）
            
        Returns:
            list: 任务执行记录列表
        """
        tasks = []
        log_dir = Path(__file__).parent.parent.parent / "logs"
        
        if not log_dir.exists():
            return tasks
        
        # 任务名称到日志关键词的映射
        task_keywords = {
            'daily_update': ['更新日线数据', 'daily_update'],
            'refresh_stock_snapshot': ['刷新快照', 'refresh_stock_snapshot'],
            'sector_heat_update': ['更新板块热度', 'sector_heat'],
            'sector_leaders_update': ['更新板块龙头', 'sector_leaders'],
            'sector_daily_update': ['板块日线更新完成', 'sector_daily_update'],
            'fundamental_update': ['更新财务数据', 'fundamental']
        }
        
        # 获取最近的日志文件
        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        for log_file in log_files[:5]:  # 只检查最近5个日志文件
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    
                # 查找任务开始和结束的记录
                for i, line in enumerate(lines):
                    # 检查是否匹配任务名称
                    matched_task = None
                    for tname, keywords in task_keywords.items():
                        if task_name and tname != task_name:
                            continue
                        if any(kw in line for kw in keywords):
                            matched_task = tname
                            break
                    
                    if not matched_task:
                        continue
                    
                    # 查找开始时间
                    start_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not start_match:
                        continue
                    
                    started_at = datetime.strptime(start_match.group(1), '%Y-%m-%d %H:%M:%S')
                    
                    # 查找结束状态（成功或失败）
                    status = 'running'
                    finished_at = None
                    duration_seconds = None
                    error_message = None
                    records_processed = 0
                    
                    # 在后续行中查找结束信息
                    for j in range(i + 1, min(i + 100, len(lines))):
                        next_line = lines[j]
                        if '✅' in next_line or '成功' in next_line or '完成' in next_line:
                            status = 'success'
                            end_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', next_line)
                            if end_match:
                                finished_at = datetime.strptime(end_match.group(1), '%Y-%m-%d %H:%M:%S')
                                duration_seconds = (finished_at - started_at).total_seconds()
                            break
                        elif '❌' in next_line or '失败' in next_line or '错误' in next_line:
                            status = 'failed'
                            end_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', next_line)
                            if end_match:
                                finished_at = datetime.strptime(end_match.group(1), '%Y-%m-%d %H:%M:%S')
                                duration_seconds = (finished_at - started_at).total_seconds()
                            error_message = next_line.strip()
                            break
                    
                    tasks.append({
                        'id': None,
                        'task_name': matched_task,
                        'task_type': 'scheduled',
                        'status': status,
                        'started_at': started_at.isoformat(),
                        'finished_at': finished_at.isoformat() if finished_at else None,
                        'duration_seconds': duration_seconds,
                        'error_message': error_message,
                        'records_processed': records_processed
                    })
                    
                    if len(tasks) >= limit:
                        break
                    
            except Exception as e:
                logger.debug(f"解析日志文件失败 {log_file}: {e}")
                continue
            
            if len(tasks) >= limit:
                break
        
        return tasks
    
    def get_data_quality_metrics(self) -> Dict:
        """
        获取数据质量指标（按数据维度分类）
        
        Returns:
            dict: 包含各数据维度质量指标的字典
        """
        result = {
            'data_dimensions': {
                'daily_price': {
                    'name': '日线数据',
                    'target_count': 0,  # 目标数量（基础股票池数量）
                    'updated_count': 0,  # 更新数量（有数据的股票数）
                    'completeness': 0.0,  # 完整性（百分比）
                    'update_date': None  # 更新日期
                },
                'fundamental': {
                    'name': '财务数据',
                    'target_count': 0,  # 目标数量（基础股票池数量）
                    'updated_count': 0,  # 更新数量（有财务数据的股票数）
                    'completeness': 0.0,  # 完整性（百分比）
                    'update_date': None  # 更新日期（最新报告期）
                },
                'stock_info': {
                    'name': '公司基础信息',
                    'target_count': 0,  # 目标数量（全量股票数，约5000+）
                    'updated_count': 0,  # 更新数量（有基础信息的股票数）
                    'completeness': 0.0,  # 完整性（百分比）
                    'update_date': None  # 更新日期
                },
                'sector': {
                    'name': '板块数据',
                    'target_count': 0,  # 目标数量（板块总数）
                    'updated_count': 0,  # 更新数量（有板块数据的板块数）
                    'completeness': 0.0,  # 完整性（百分比）
                    'update_date': None  # 更新日期
                },
                'realtime': {
                    'name': '实时数据',
                    'available': False,
                    'last_check': None
                },
                'new_high_strategy': {
                    'name': '30日新高策略',
                    'target_count': 0,  # 目标数量（基础股票池数量）
                    'valid_count': 0,  # 符合条件的股票数
                    'abnormal_count': 0,  # 异常股票数（涨幅>300%）
                    'completeness': 0.0,  # 数据完整性（百分比）
                    'update_date': None  # 更新日期
                }
            },
            'universe_stats': {}
        }
        
        if not self.warehouse or not self.warehouse._initialized or not self.warehouse.warehouse_service:
            return result
        
        try:
            session = self.warehouse.warehouse_service.get_session()
            try:
                from data_warehouse.models import FactDailyPriceQfq
                from data_warehouse.models import FactFundamental
                from data_warehouse.models import DimStock
                from data_warehouse.models import DimSector
                from sqlalchemy import func, distinct
                
                # 获取基础股票池数量
                universe_stats = self.universe_service.get_universe_stats()
                base_count = universe_stats.get('base', 0)
                result['universe_stats'] = universe_stats
                
                # ✅ 优化：获取基础股票池列表（只获取一次，后续复用）
                latest_date = session.query(func.max(FactDailyPriceQfq.trade_date)).scalar()
                if latest_date:
                    # 获取基础股票池的股票代码列表（用于日线数据检查）
                    base_codes = self.universe_service.get_universe_stocks(
                        universe_type='base',
                        trade_date=latest_date.strftime('%Y-%m-%d') if isinstance(latest_date, date) else None,
                        active_only=True
                    )
                    ts_codes = _convert_to_ts_codes(base_codes) if base_codes else []
                else:
                    base_codes = []
                    ts_codes = []
                
                # 如果没有获取到基础池，尝试获取一次（不依赖日期）
                if not base_codes:
                    base_codes = self.universe_service.get_universe_stocks(
                        universe_type='base',
                        trade_date=None,
                        active_only=True
                    )
                    ts_codes = _convert_to_ts_codes(base_codes) if base_codes else []
                
                # 1. 日线数据质量（只统计基础股票池的数据）
                result['data_dimensions']['daily_price']['target_count'] = base_count
                if latest_date:
                    result['data_dimensions']['daily_price']['update_date'] = _format_date(latest_date)
                    
                    # 统计基础股票池中有数据的股票数量（使用已获取的ts_codes）
                    if ts_codes and base_count > 0:
                        data_count = session.query(func.count(distinct(FactDailyPriceQfq.ts_code))).filter(
                            FactDailyPriceQfq.trade_date == latest_date,
                            FactDailyPriceQfq.ts_code.in_(ts_codes)
                        ).scalar() or 0
                        
                        result['data_dimensions']['daily_price']['updated_count'] = data_count
                        result['data_dimensions']['daily_price']['completeness'] = round((data_count / base_count) * 100, 2) if base_count > 0 else 0
                    elif base_count > 0:
                        # 如果没有基础股票池列表，统计所有数据（但完整性基于基础池）
                        total_daily = session.query(func.count(distinct(FactDailyPriceQfq.ts_code))).filter(
                            FactDailyPriceQfq.trade_date == latest_date
                        ).scalar() or 0
                        result['data_dimensions']['daily_price']['updated_count'] = total_daily
                        result['data_dimensions']['daily_price']['completeness'] = round((min(total_daily, base_count) / base_count) * 100, 2) if base_count > 0 else 0
                    else:
                        # 基础池为空，统计所有数据
                        total_daily = session.query(func.count(distinct(FactDailyPriceQfq.ts_code))).filter(
                            FactDailyPriceQfq.trade_date == latest_date
                        ).scalar() or 0
                        result['data_dimensions']['daily_price']['updated_count'] = total_daily
                        result['data_dimensions']['daily_price']['completeness'] = 0.0
                
                # 2. 财务数据质量（只统计基础股票池的数据，复用已获取的base_codes和ts_codes）
                result['data_dimensions']['fundamental']['target_count'] = base_count
                
                if ts_codes and base_count > 0:
                    # 统计基础池中有财务数据的股票（使用最近有数据的日期，不限制报告期）
                    # 对于每只股票，找到它最近的一个报告期（复用已转换的ts_codes）
                    data_count = session.query(func.count(distinct(FactFundamental.ts_code))).filter(
                        FactFundamental.ts_code.in_(ts_codes)
                    ).scalar() or 0
                    
                    # 获取基础池中所有股票最近有数据的报告期（用于显示）
                    # 查询基础池中每只股票最近的一个报告期，然后取这些报告期中的最大值
                    from sqlalchemy import select, func as sql_func
                    subquery = select(
                        FactFundamental.ts_code,
                        sql_func.max(FactFundamental.end_date).label('max_date')
                    ).filter(
                        FactFundamental.ts_code.in_(ts_codes)  # 复用已转换的ts_codes
                    ).group_by(FactFundamental.ts_code).subquery()
                    
                    latest_report_date = session.query(sql_func.max(subquery.c.max_date)).scalar()
                    if latest_report_date:
                        result['data_dimensions']['fundamental']['update_date'] = _format_date(latest_report_date)
                    else:
                        # 如果没有数据，使用全局最新报告期
                        latest_report_date = session.query(func.max(FactFundamental.end_date)).scalar()
                        if latest_report_date:
                            result['data_dimensions']['fundamental']['update_date'] = _format_date(latest_report_date)
                    
                    result['data_dimensions']['fundamental']['updated_count'] = data_count
                    result['data_dimensions']['fundamental']['completeness'] = round((data_count / base_count) * 100, 2) if base_count > 0 else 0
                elif base_count > 0:
                    # 如果没有基础股票池列表，统计所有数据（但完整性基于基础池）
                    latest_report_date = session.query(func.max(FactFundamental.end_date)).scalar()
                    result['data_dimensions']['fundamental']['update_date'] = _format_date(latest_report_date)
                    total_fundamental = session.query(func.count(distinct(FactFundamental.ts_code))).scalar() or 0
                    result['data_dimensions']['fundamental']['updated_count'] = total_fundamental
                    result['data_dimensions']['fundamental']['completeness'] = round((min(total_fundamental, base_count) / base_count) * 100, 2) if base_count > 0 else 0
                else:
                    # 基础池为空，统计所有数据
                    latest_report_date = session.query(func.max(FactFundamental.end_date)).scalar()
                    result['data_dimensions']['fundamental']['update_date'] = _format_date(latest_report_date)
                    
                    total_fundamental = session.query(func.count(distinct(FactFundamental.ts_code))).scalar() or 0
                    result['data_dimensions']['fundamental']['updated_count'] = total_fundamental
                    result['data_dimensions']['fundamental']['completeness'] = 0.0
                
                # 3. 公司基础信息完整性（基于总股票数，不是基础池）
                stock_count = session.query(func.count(DimStock.ts_code)).scalar()
                result['data_dimensions']['stock_info']['target_count'] = stock_count
                result['data_dimensions']['stock_info']['updated_count'] = stock_count
                # 公司基础信息的完整性应该是100%（因为stock_count就是总数）
                result['data_dimensions']['stock_info']['completeness'] = 100.0
                # 获取最新更新时间（只显示日期，不显示时间）
                result['data_dimensions']['stock_info']['update_date'] = datetime.now().strftime('%Y-%m-%d')
                
                # 4. 板块数据完整性（基于基础股票池的板块覆盖）
                sector_count = session.query(func.count(distinct(DimSector.sector_id))).scalar()
                result['data_dimensions']['sector']['target_count'] = sector_count
                result['data_dimensions']['sector']['updated_count'] = sector_count
                # 板块数据的完整性暂时不计算，因为板块数量与股票池大小没有直接关系
                result['data_dimensions']['sector']['completeness'] = 100.0  # 板块数据完整性暂时设为100%
                # 获取最新更新时间（只显示日期，不显示时间）
                result['data_dimensions']['sector']['update_date'] = datetime.now().strftime('%Y-%m-%d')
                
                # 5. 实时数据可用性（从数据源健康检查获取，延迟加载避免影响性能）
                try:
                    health = self.check_data_source_health()
                    easyquotation_sina = health.get('sources', {}).get('easyquotation_sina', {})
                    result['data_dimensions']['realtime']['available'] = easyquotation_sina.get('available', False)
                    result['data_dimensions']['realtime']['last_check'] = health.get('check_time')
                except Exception as e:
                    logger.debug(f"实时数据检查失败: {e}")
                    result['data_dimensions']['realtime']['available'] = False
                    result['data_dimensions']['realtime']['last_check'] = None
                
                # 6. 30日新高策略数据质量（✅ 优化：从S1股票池中筛选，而不是从基础池）
                if latest_date and base_count > 0:
                    from sqlalchemy import text
                    
                    # ✅ 优化：先从S1股票池获取股票列表（而不是从基础池）
                    # 30日新高策略的股票一定是S1股票池的子集（S1允许回踩5%，30日新高要求严格新高）
                    s1_codes = self.universe_service.get_universe_stocks(
                        universe_type='s1',
                        trade_date=latest_date.strftime('%Y-%m-%d') if isinstance(latest_date, date) else None,
                        active_only=True
                    )
                    
                    # target_count使用S1股票池数量（更准确）
                    s1_count = len(s1_codes) if s1_codes else 0
                    result['data_dimensions']['new_high_strategy']['target_count'] = s1_count
                    
                    if not s1_codes:
                        # 如果S1股票池为空，返回空结果
                        logger.debug("S1股票池为空，30日新高策略结果为空")
                        result['data_dimensions']['new_high_strategy']['valid_count'] = 0
                        result['data_dimensions']['new_high_strategy']['abnormal_count'] = 0
                        result['data_dimensions']['new_high_strategy']['completeness'] = 0.0
                        result['data_dimensions']['new_high_strategy']['update_date'] = _format_date(latest_date)
                        result['data_dimensions']['new_high_strategy']['valid_stocks'] = []
                    else:
                        # 只检查S1股票池中的股票（100-300只，而不是1946只基础池）
                        s1_ts_codes = _convert_to_ts_codes(s1_codes)
                        logger.debug(f"从S1股票池（{len(s1_ts_codes)}只）中筛选30日新高策略股票")
                        
                        # ✅ 使用批量SQL查询替代循环查询（从5,838次查询减少到1次）
                        # ✅ 优化：只查询S1股票池的股票，减少查询范围85-90%
                        # 使用窗口函数和CTE一次性获取所有股票的数据
                        # 使用PostgreSQL的ANY数组参数，避免SQL注入风险
                        query = text("""
                            WITH latest_data AS (
                                SELECT 
                                    ts_code,
                                    close as today_close,
                                    amount as today_amount
                                FROM fact_daily_price_qfq
                                WHERE trade_date = :latest_date
                                  AND ts_code = ANY(:s1_ts_codes)
                            ),
                        prev_30_max AS (
                            SELECT 
                                ts_code,
                                MAX(close) as max_30d_close
                            FROM fact_daily_price_qfq
                            WHERE trade_date < :latest_date
                              AND ts_code = ANY(:s1_ts_codes)
                            GROUP BY ts_code
                            HAVING COUNT(DISTINCT trade_date) >= 30
                        ),
                        prev_180_data AS (
                            SELECT 
                                ts_code,
                                close as close_180d_ago
                            FROM (
                                SELECT 
                                    ts_code,
                                    close,
                                    ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) as rn
                                FROM fact_daily_price_qfq
                                WHERE trade_date < :latest_date
                                  AND ts_code = ANY(:s1_ts_codes)
                            ) ranked
                            WHERE rn = 180
                        )
                        SELECT 
                            l.ts_code,
                            l.today_close,
                            l.today_amount,
                            p30.max_30d_close,
                            p180.close_180d_ago,
                            CASE 
                                WHEN l.today_close > p30.max_30d_close 
                                     AND (p180.close_180d_ago IS NULL OR (l.today_close - p180.close_180d_ago) / p180.close_180d_ago <= 3.0)
                                     AND l.today_amount > 200000000
                                THEN TRUE
                                ELSE FALSE
                            END as is_valid,
                            CASE 
                                WHEN p180.close_180d_ago IS NOT NULL 
                                     AND p180.close_180d_ago > 0
                                     AND (l.today_close - p180.close_180d_ago) / p180.close_180d_ago > 3.0
                                THEN TRUE
                                ELSE FALSE
                            END as is_abnormal
                        FROM latest_data l
                        INNER JOIN prev_30_max p30 ON l.ts_code = p30.ts_code
                        LEFT JOIN prev_180_data p180 ON l.ts_code = p180.ts_code
                        WHERE l.today_close IS NOT NULL
                          AND p30.max_30d_close IS NOT NULL
                    """)
                    
                        try:
                            query_result = session.execute(query, {
                                'latest_date': latest_date,
                                's1_ts_codes': s1_ts_codes  # 只传入S1股票池的代码
                            }).fetchall()
                            
                            valid_stocks = []
                            valid_count = 0
                            abnormal_count = 0
                            
                            for row in query_result:
                                ts_code = row[0]
                                is_valid = row[5]
                                is_abnormal = row[6]
                                
                                if is_abnormal:
                                    abnormal_count += 1
                                
                                if is_valid:
                                    valid_count += 1
                                    valid_stocks.append(ts_code)
                            
                            result['data_dimensions']['new_high_strategy']['valid_count'] = valid_count
                            result['data_dimensions']['new_high_strategy']['abnormal_count'] = abnormal_count
                            # 完整性基于S1股票池数量（而不是基础池）
                            result['data_dimensions']['new_high_strategy']['completeness'] = round((valid_count / s1_count) * 100, 2) if s1_count > 0 else 0
                            result['data_dimensions']['new_high_strategy']['update_date'] = _format_date(latest_date)
                            result['data_dimensions']['new_high_strategy']['valid_stocks'] = valid_stocks
                            
                        except Exception as e:
                            logger.error(f"批量查询30日新高策略失败: {e}", exc_info=True)
                            # 降级：返回空结果，避免影响其他数据质量指标
                            result['data_dimensions']['new_high_strategy']['valid_count'] = 0
                            result['data_dimensions']['new_high_strategy']['abnormal_count'] = 0
                            result['data_dimensions']['new_high_strategy']['completeness'] = 0.0
                            result['data_dimensions']['new_high_strategy']['update_date'] = _format_date(latest_date) if latest_date else None
                            result['data_dimensions']['new_high_strategy']['valid_stocks'] = []
                
            finally:
                session.close()
        except Exception as e:
            logger.error(f"获取数据质量指标失败: {e}", exc_info=True)
        
        return result

    def get_latest_daily_date(self) -> Optional[str]:
        """获取数据库中最新日线数据日期（YYYY-MM-DD），无数据返回 None。"""
        if self.warehouse and hasattr(self.warehouse, 'get_latest_stocks_date'):
            return self.warehouse.get_latest_stocks_date()
        try:
            from backend.services.data.postgres_warehouse import PostgresWarehouse
            pg = PostgresWarehouse()
            if pg._initialized:
                return pg.get_latest_stocks_date()
        except Exception as e:
            logger.warning("获取最新日线日期失败: %s", e)
        return None

    def check_missing_data(self, days: int = 5) -> List[str]:
        """检查最近 N 天缺失的交易日（委托 DataScheduler）。失败时返回空列表并打日志。"""
        try:
            scheduler = self._service_manager.get_data_scheduler()
            return scheduler.check_missing_data(days=days)
        except Exception as e:
            logger.warning("检查缺失数据失败，返回空列表: %s", e, exc_info=True)
            return []

    def compute_force_update_dates(self, days: int) -> List[str]:
        """计算强制更新时的日期列表（最近 N 天内的交易日，排除今天）。"""
        today = datetime.now().date()
        out = []
        for i in range(days):
            d = today - timedelta(days=i)
            if d.weekday() >= 5 or d == today:
                continue
            out.append(d.strftime("%Y-%m-%d"))
        out.sort()
        return out

    def start_update_missing_background(self, days: int = 5, force: bool = True) -> Dict:
        """在后台线程启动增量/强制更新，立即返回。"""
        import threading
        scheduler = self._service_manager.get_data_scheduler()
        if force:
            update_dates = self.compute_force_update_dates(days)
            message = f"已启动强制更新任务，将更新最近 {days} 天的 {len(update_dates)} 个交易日"
        else:
            update_dates = self.check_missing_data(days)
            message = f"已启动增量更新任务，将更新 {len(update_dates)} 个缺失日期"

        def _run():
            scheduler.update_missing_dates(days=days, force=force)

        threading.Thread(target=_run, daemon=True).start()
        return {"message": message, "update_dates": update_dates, "force": force}

    def fill_missing_daily(self, days: int = 5) -> Dict:
        """
        补缺失日线（与 scripts/tools/update_missing_dates.py 同一套逻辑）：
        用文件仓库检查近 N 天、今天之前的缺失日期，再在后台执行补数。
        不依赖 DataScheduler/Postgres 做缺失检查，避免初始化卡住。
        """
        from backend.scripts.data_update.update_missing_dates_core import (
            compute_update_dates,
            run_incremental_update,
        )
        import threading

        latest_date = self.get_latest_daily_date()
        missing_dates = compute_update_dates(days, force=False)
        if not missing_dates:
            return {
                "latest_date": latest_date,
                "missing_dates": [],
                "message": "数据已完整，无需补充",
                "started": False,
            }

        def _run():
            run_incremental_update(days=days, force=False)

        threading.Thread(target=_run, daemon=True).start()
        return {
            "latest_date": latest_date,
            "missing_dates": missing_dates,
            "message": f"已启动补充 {len(missing_dates)} 个缺失日期（与脚本 update_missing_dates 一致）",
            "started": True,
        }

    def add_new_high_stocks_to_watchlist(self) -> Dict:
        """
        将30日新高策略的有效股票添加到股票跟踪池
        
        Returns:
            dict: 包含添加结果的字典
        """
        try:
            # 先获取数据质量指标，计算30日新高股票
            metrics = self.get_data_quality_metrics()
            valid_stocks = metrics.get('data_dimensions', {}).get('new_high_strategy', {}).get('valid_stocks', [])
            
            if not valid_stocks:
                return {
                    'success': True,
                    'added_count': 0,
                    'message': '没有符合30日新高策略的股票'
                }
            
            from data_warehouse.models import FactStockWatchlist
            
            if not self.warehouse or not self.warehouse.warehouse_service:
                return {
                    'success': False,
                    'message': '数据库服务未初始化'
                }
            
            session = self.warehouse.warehouse_service.get_session()
            
            try:
                # 获取当前日期作为备注的一部分
                today = datetime.now().strftime('%Y-%m-%d')
                note = f"{today} 30日新高"
                
                added_count = 0
                existing_count = 0
                
                for ts_code in valid_stocks:
                    # 检查是否已存在
                    existing = session.query(FactStockWatchlist).filter(
                        FactStockWatchlist.ts_code == ts_code
                    ).first()
                    
                    if existing:
                        existing_count += 1
                        continue
                    
                    # 添加新记录
                    watchlist_item = FactStockWatchlist(
                        ts_code=ts_code,
                        note=note,
                        added_at=datetime.now()
                    )
                    session.add(watchlist_item)
                    added_count += 1
                
                session.commit()
                
                logger.info(f"✅ 将 {added_count} 只30日新高股票添加到跟踪列表（已存在 {existing_count} 只）")
                
                return {
                    'success': True,
                    'added_count': added_count,
                    'existing_count': existing_count,
                    'total_valid': len(valid_stocks),
                    'message': f'成功添加 {added_count} 只股票到跟踪列表（{existing_count} 只已存在）'
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"添加30日新高股票到跟踪列表失败: {e}", exc_info=True)
            return {
                'success': False,
                'message': '操作失败，请稍后重试'
            }

    def trigger_data_update(self, task_type: str) -> Dict:
        """
        触发数据更新（异步执行）
        
        Args:
            task_type: 任务类型（daily_update, fundamental_update, refresh_snapshot, sector_heat_update, sector_leaders_update, sync_stock）
            
        Returns:
            dict: 包含任务ID和执行状态
        """
        import threading
        import uuid
        
        # 验证任务类型
        if task_type not in self.ALL_TASK_TYPES:
            raise ValueError(f"未知的任务类型: {task_type}，支持的类型: {self.ALL_TASK_TYPES}")
        
        # 任务类型到执行函数的映射
        task_handlers = {
            'daily_update': lambda tid: self._run_daily_update(tid),
            'fundamental_update': lambda tid: self._run_fundamental_update(tid),
            'refresh_snapshot': lambda tid: self._run_refresh_snapshot(),
            'sync_stock': lambda tid: self._run_sync_stock(),
            'sync_industry': lambda tid: self._run_sync_industry(),
            'moneyflow_update': lambda tid: self._run_moneyflow_update(),
            'money_flow_update': lambda tid: self._run_money_flow_update(),
            's1_universe_update': lambda tid: self._run_s1_universe_update(),
            'industry_cycle_collect': lambda tid: self._run_industry_cycle_collect(tid),
            'industry_cycle_suggest': lambda tid: self._run_industry_cycle_suggest(),
            'pe_pb_update': lambda tid: self._run_pe_pb_update(),
            'abnormal_analysis_scan': lambda tid: self._run_abnormal_analysis_scan(),
            'recommendation_daily': lambda tid: self._run_recommendation_daily(),
            'recommendation_daily_track': lambda tid: self._run_recommendation_daily(),  # deprecated
            'recommendation_auto_close': lambda tid: self._run_recommendation_daily(),   # deprecated
            'north_money_update': lambda tid: self._run_north_money_update(),
            'north_holding_update': lambda tid: self._run_north_money_update(),          # deprecated
            'north_flow_update': lambda tid: self._run_north_money_update(),             # deprecated
            'sector_daily_maintenance': lambda tid: self._run_sector_daily_maintenance(),
            'sector_heat_update': lambda tid: self._run_sector_daily_maintenance(),      # deprecated
            'sector_leaders_update': lambda tid: self._run_sector_daily_maintenance(),   # deprecated
            'sector_daily_update': lambda tid: self._run_sector_daily_maintenance(),     # deprecated
            'limit_up_emotion_update': lambda tid: self._run_limit_up_emotion_update(),
        }
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 异步执行任务
        def run_task():
            try:
                handler = task_handlers.get(task_type)
                if handler:
                    handler(task_id)
                else:
                    raise ValueError(f"未找到任务处理器: {task_type}")
            except Exception as e:
                logger.error(f"执行任务失败 {task_type}: {e}", exc_info=True)
        
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        return {
            'success': True,
            'task_id': task_id,
            'task_type': task_type,
            'message': f'任务 {task_type} 已启动'
        }
    
    def _run_daily_update(self, task_id: str):
        """执行日线数据更新"""
        from backend.scripts.data_update.update_daily_from_snapshot import update_daily_prices_from_snapshot
        update_daily_prices_from_snapshot(task_type='manual', task_id=task_id)
    
    def _run_fundamental_update(self, task_id: str):
        """执行财务数据更新"""
        from data_warehouse.etl.daily_update import update_fundamental
        update_fundamental(limit=None, task_id=task_id, task_type='manual', batch_size=120, delay=0.2, max_retries=3)

    def _run_pe_pb_update(self):
        """从 Tushare daily_basic 更新 fact_daily_price_qfq 的 PE/PB（建议 17:30 后执行）"""
        from backend.scripts.data_update.update_pe_pb_from_tushare import update_pe_pb_from_tushare
        result = update_pe_pb_from_tushare(
            trade_date=None,
            also_update_fact_daily_fundamental=True,
            task_type='scheduled',
        )
        if not result.get('success'):
            raise RuntimeError(result.get('message', 'PE/PB 更新失败'))
        logger.info(f"PE/PB 更新完成: {result.get('message')}")

    def _run_refresh_snapshot(self):
        """执行快照刷新"""
        from backend.scripts.data_update.refresh_stock_snapshot import refresh_snapshot_and_recommendations
        refresh_snapshot_and_recommendations(task_type='manual')
    
    def _run_sector_heat_update(self):
        """执行板块热度更新"""
        from backend.scripts.data_update.update_sector_heat_snapshot import update_sector_heat_snapshot
        update_sector_heat_snapshot(task_type='manual')
    
    def _run_sector_leaders_update(self):
        """执行板块龙头更新"""
        from backend.scripts.data_update.update_sector_leaders import update_sector_leaders
        update_sector_leaders(task_type='manual')
    
    def _run_sync_stock(self):
        """执行股票基础信息同步"""
        from backend.scripts.data_update.sync_dim_stock import sync_dim_stock
        sync_dim_stock()

    def _run_sync_industry(self):
        """执行申万行业同步（dim_stock.industry 统一为申万一级）"""
        from backend.scripts.data_update.sync_industry_from_sw import sync_industry_from_sw
        sync_industry_from_sw()

    def _run_recommendation_daily(self):
        """执行推荐系统日终维护：效果追踪 + 自动平仓"""
        self._run_recommendation_daily_track()
        self._run_recommendation_auto_close()

    def _run_north_money_update(self):
        """更新北向资金数据：持股 + 市场净流入"""
        self._run_north_holding_update()
        self._run_north_flow_update()

    def _run_sector_daily_maintenance(self):
        """执行板块日终维护：热度 + 龙头 + 日线"""
        self._run_sector_heat_update()
        self._run_sector_leaders_update()
        self._run_sector_daily_update()

    def _run_money_flow_update(self):
        """从 Tushare moneyflow 更新 fact_money_flow（个股主力资金）"""
        from backend.scripts.data_update.update_money_flow_from_tushare import update_money_flow_from_tushare
        result = update_money_flow_from_tushare(trade_date=None, task_type='scheduled')
        if not result.get('success'):
            raise RuntimeError(result.get('message', '个股主力资金更新失败'))
        logger.info(f"个股主力资金更新完成: {result.get('message')}")

    def _run_north_holding_update(self):
        """从 Tushare hk_hold 更新 fact_north_holding（北向持股）"""
        from backend.scripts.data_update.update_north_holding_from_tushare import update_north_holding_from_tushare
        result = update_north_holding_from_tushare(trade_date=None, task_type='scheduled')
        if not result.get('success'):
            raise RuntimeError(result.get('message', '北向持股更新失败'))
        logger.info(f"北向持股更新完成: {result.get('message')}")

    def _run_north_flow_update(self):
        """从 Tushare moneyflow_hsgt 更新 fact_north_flow（北向资金市场净流入）"""
        from backend.scripts.data_update.update_north_flow_from_tushare import update_north_flow_from_tushare
        result = update_north_flow_from_tushare(trade_date=None, task_type='scheduled')
        if not result.get('success'):
            raise RuntimeError(result.get('message', '北向资金净流入更新失败'))
        logger.info(f"北向资金净流入更新完成: {result.get('message')}")

    def _run_sector_daily_update(self):
        """更新 fact_sector_daily（Tushare 申万行业日线），用于主题轮动/明日预测"""
        from datetime import date as date_type
        from data_warehouse.service.warehouse_service import WarehouseService
        from backend.utils.trade_date_utils import get_latest_trade_date, is_trade_date
        from backend.services.sector.sector_service import update_sector_daily_tushare
        today = date_type.today()
        ws = WarehouseService()
        if datetime.now().hour >= 15 and is_trade_date(ws, today):
            target_date = today
        else:
            target_date = get_latest_trade_date(ws, 10, today - timedelta(days=1)) or (today - timedelta(days=1))
        try:
            update_sector_daily_tushare(target_date)
            logger.info(f"板块日线更新完成: {target_date}")
        except Exception as e:
            logger.error(f"板块日线更新失败: {e}", exc_info=True)
            raise RuntimeError(f"板块日线更新失败: {e}")

    def _run_limit_up_emotion_update(self):
        """更新涨停板明细和市场情绪数据（收盘后执行）"""
        from datetime import date as date_type
        from data_warehouse.service.warehouse_service import WarehouseService
        from backend.utils.trade_date_utils import get_latest_trade_date, is_trade_date
        from backend.scripts.data_fill.fill_limitup_emotion import fill_limit_up_daily, calculate_market_emotion

        today = date_type.today()
        ws = WarehouseService()
        try:
            if is_trade_date(ws, today):
                target_date_str = today.strftime('%Y-%m-%d')
            else:
                latest = get_latest_trade_date(ws, 10, today)
                target_date_str = latest.strftime('%Y-%m-%d') if latest else today.strftime('%Y-%m-%d')
        finally:
            ws.get_session().close()

        logger.info(f"开始更新涨停板与情绪数据: {target_date_str}")
        limitup_ok = fill_limit_up_daily(target_date_str)
        emotion_ok = calculate_market_emotion(target_date_str)

        if not limitup_ok:
            raise RuntimeError(f"{target_date_str} 涨停数据更新失败")
        if not emotion_ok:
            raise RuntimeError(f"{target_date_str} 市场情绪计算失败")

    def _run_moneyflow_update(self):
        """执行资金流向更新（Tushare 行业 moneyflow_ind_ths + 板块/概念），写入 data_warehouse/moneyflow/*.json"""
        logger.info("🔄 资金流向更新任务已启动（后台线程）")
        try:
            scheduler = self._service_manager.get_data_scheduler()
            scheduler.update_moneyflow_data()
        except Exception as e:
            logger.error(f"资金流向更新任务异常: {e}", exc_info=True)

    def _run_industry_cycle_collect(self, task_id: str):
        """执行行业周期数据采集（Tushare+Warehouse），复用 DataScheduler 单例；定时任务用子进程执行避免卡住"""
        scheduler = self._service_manager.get_data_scheduler()
        scheduler.update_industry_cycle_data(use_subprocess=True)

    def _run_industry_cycle_suggest(self):
        """执行行业周期建议生成（industry_cycle_update.py --mode suggest）"""
        import sys
        import subprocess
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / "scripts" / "tools" / "industry_cycle_update.py"
        if not script_path.exists():
            raise FileNotFoundError(f"脚本不存在: {script_path}")
        proc = subprocess.run(
            [sys.executable, str(script_path), "--mode", "suggest"],
            cwd=str(project_root),
            timeout=300,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"行业周期 suggest 执行失败: {proc.stderr or proc.stdout or proc.returncode}")
    
    def _run_limit_up_volume_shrink(self):
        """涨停缩量功能已下线，仅记录并跳过"""
        logger.info("涨停缩量功能已下线，跳过执行")
    
    def _run_s1_universe_update(self):
        """执行S1股票池更新"""
        from datetime import datetime
        
        try:
            trade_date = datetime.now().strftime('%Y-%m-%d')
            logger.info("=" * 60)
            logger.info(f"🚀 开始更新S1股票池")
            logger.info(f"   交易日期: {trade_date}")
            logger.info("=" * 60)
            
            # 更新S1股票池
            result = self.universe_service.update_universe(
                universe_type='s1',
                trade_date=trade_date,
                force_refresh=False
            )
            
            # update_universe 返回格式: {'total': int, 'filtered': int, 'added': int, ...}
            if result.get('error'):
                logger.error(f"❌ S1股票池更新失败: {result.get('error')}")
            elif result.get('added', 0) > 0 or result.get('total', 0) > 0:
                logger.info(f"✅ S1股票池更新完成")
                logger.info(f"   更新统计: 总数={result.get('total', 0)}, 筛选后={result.get('filtered', 0)}, 新增={result.get('added', 0)}")
                
                # 验证更新后的数量
                s1_codes = self.universe_service.get_universe_stocks('s1', trade_date)
                logger.info(f"   当前S1股票池数量: {len(s1_codes)} 只")
                
                # 如果数量异常，记录警告
                if len(s1_codes) > 200:
                    logger.warning(f"⚠️ S1股票池数量异常: {len(s1_codes)} 只（预期100-300只）")
                    logger.warning(f"   建议检查S1股票池筛选条件和实时数据")
                elif len(s1_codes) == 0:
                    logger.warning(f"⚠️ S1股票池为空，请检查基础池和筛选条件")
            else:
                logger.warning(f"⚠️ S1股票池更新结果异常: {result}")
                
        except Exception as e:
            logger.error(f"执行S1股票池更新失败: {e}", exc_info=True)
            raise

    def _run_abnormal_analysis_scan(self):
        """执行异动分析扫描（收盘后自动扫描异动股票）"""
        try:
            from backend.services.news.abnormal_analysis_service import AbnormalAnalysisService
            abnormal_svc = AbnormalAnalysisService()
            result = abnormal_svc.run_daily_scan(max_stocks=30)
            logger.info(f"✅ 异动分析扫描完成: 分析 {result.get('analyzed', 0)} 只, 保存 {result.get('saved', 0)} 只")
        except Exception as e:
            logger.error(f"执行异动分析扫描失败: {e}", exc_info=True)
            raise
    
    def _run_recommendation_daily_track(self):
        """执行推荐效果追踪（每日更新推荐表现）"""
        try:
            from backend.services.recommendation.recommendation_tracker import RecommendationTracker
            tracker = RecommendationTracker()
            result = tracker.track_daily()
            logger.info(f"✅ 推荐效果追踪完成: 追踪 {result.get('tracked', 0)} 只")
        except Exception as e:
            logger.error(f"执行推荐效果追踪失败: {e}", exc_info=True)
            raise
    
    def _run_recommendation_auto_close(self):
        """执行推荐自动平仓（触及止损/止盈）"""
        try:
            from backend.services.recommendation.recommendation_tracker import RecommendationTracker
            tracker = RecommendationTracker()
            result = tracker.auto_close()
            logger.info(f"✅ 推荐自动平仓完成: 平仓 {result.get('closed', 0)} 只")
        except Exception as e:
            logger.error(f"执行推荐自动平仓失败: {e}", exc_info=True)
            raise

