"""
补充每日基本面指标（fact_daily_fundamental）
从Tushare获取财务指标（ROE、毛利率、净利率、现金流）并计算TTM值
"""

import sys
import logging
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.data.postgres_warehouse import PostgresWarehouse
from backend.services.tushare_service import TushareService
from data_warehouse.models import FactDailyFundamental
from data_warehouse.models import DimStock
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_latest_trade_date(warehouse: PostgresWarehouse) -> Optional[date]:
    """获取最新的交易日期"""
    if not warehouse.warehouse_service:
        return None
    
    session = warehouse.warehouse_service.get_session()
    try:
        query = text("""
            SELECT MAX(trade_date) as latest_date
            FROM fact_daily_price_qfq
        """)
        result = session.execute(query).scalar()
        return result if result else None
    finally:
        session.close()


def get_stock_list(warehouse: PostgresWarehouse, limit: Optional[int] = None) -> List[str]:
    """获取股票代码列表"""
    if not warehouse.warehouse_service:
        return []
    
    session = warehouse.warehouse_service.get_session()
    try:
        query = session.query(DimStock.ts_code)
        if limit:
            query = query.limit(limit)
        results = query.all()
        return [r[0] for r in results]
    finally:
        session.close()


def calculate_ttm_from_quarters(quarters_data: List[Dict]) -> Dict:
    """
    从最近4个季度数据计算TTM值
    
    Args:
        quarters_data: 季度数据列表，按日期倒序排列
    
    Returns:
        dict: TTM指标
    """
    if not quarters_data:
        return {}
    
    # 取最近4个季度
    recent_quarters = quarters_data[:4]
    
    # 计算TTM（简单平均，实际应该加权）
    roe_values = [float(q.get('roe', 0) or 0) for q in recent_quarters if q.get('roe')]
    net_margin_values = [float(q.get('netprofit_margin', 0) or 0) for q in recent_quarters if q.get('netprofit_margin')]
    gross_margin_values = [float(q.get('grossprofit_margin', 0) or 0) for q in recent_quarters if q.get('grossprofit_margin')]
    op_cf_values = [float(q.get('n_cashflow_act', 0) or 0) for q in recent_quarters if q.get('n_cashflow_act')]
    
    result = {}
    
    if roe_values:
        result['roe_ttm'] = sum(roe_values) / len(roe_values)
    
    if net_margin_values:
        result['net_margin_ttm'] = sum(net_margin_values) / len(net_margin_values)
    
    if gross_margin_values:
        result['gross_margin_ttm'] = sum(gross_margin_values) / len(gross_margin_values)
    
    if op_cf_values:
        result['op_cf_ttm'] = sum(op_cf_values)
    
    return result


def get_financial_indicators_ttm(tushare_service: TushareService, ts_code: str) -> Optional[Dict]:
    """
    从Tushare获取财务指标并计算TTM值
    
    Args:
        tushare_service: Tushare服务
        ts_code: 股票代码（Tushare格式）
    
    Returns:
        dict: TTM财务指标
    """
    if not tushare_service.available:
        return None
    
    try:
        # 获取最近4个季度的财务指标
        df = tushare_service.pro.fina_indicator(
            ts_code=ts_code,
            period='',  # 空字符串表示获取所有
            fields='ts_code,end_date,roe,netprofit_margin,grossprofit_margin'
        )
        
        if df is None or df.empty:
            logger.debug(f"  Tushare未返回财务指标数据: {ts_code}")
            return None
        
        # 按日期倒序排列
        df = df.sort_values('end_date', ascending=False)
        
        # 获取最近4个季度数据
        quarters_data = []
        for _, row in df.head(4).iterrows():
            quarters_data.append({
                'roe': row.get('roe'),
                'netprofit_margin': row.get('netprofit_margin'),
                'grossprofit_margin': row.get('grossprofit_margin'),
            })
        
        # 获取现金流量数据
        cashflow_df = tushare_service.pro.cashflow(
            ts_code=ts_code,
            period='',
            fields='ts_code,end_date,n_cashflow_act'
        )
        
        if cashflow_df is not None and not cashflow_df.empty:
            cashflow_df = cashflow_df.sort_values('end_date', ascending=False)
            for i, (_, row) in enumerate(cashflow_df.head(4).iterrows()):
                if i < len(quarters_data):
                    quarters_data[i]['n_cashflow_act'] = row.get('n_cashflow_act')
        
        # 计算TTM值
        ttm_data = calculate_ttm_from_quarters(quarters_data)
        
        # 如果TTM计算失败，使用最新一期数据
        if not ttm_data and not df.empty:
            latest = df.iloc[0]
            ttm_data = {
                'roe_ttm': float(latest.get('roe', 0) or 0),
                'net_margin_ttm': float(latest.get('netprofit_margin', 0) or 0),
                'gross_margin_ttm': float(latest.get('grossprofit_margin', 0) or 0),
            }
            
            if cashflow_df is not None and not cashflow_df.empty:
                latest_cf = cashflow_df.iloc[0]
                ttm_data['op_cf_ttm'] = float(latest_cf.get('n_cashflow_act', 0) or 0)
        
        # 处理百分比转换（Tushare可能返回百分比或小数）
        if ttm_data.get('roe_ttm', 0) < 1:
            ttm_data['roe_ttm'] = ttm_data.get('roe_ttm', 0) * 100
        
        if ttm_data.get('net_margin_ttm', 0) < 1:
            ttm_data['net_margin_ttm'] = ttm_data.get('net_margin_ttm', 0) * 100
        
        if ttm_data.get('gross_margin_ttm', 0) < 1:
            ttm_data['gross_margin_ttm'] = ttm_data.get('gross_margin_ttm', 0) * 100
        
        return ttm_data
        
    except Exception as e:
        logger.debug(f"获取 {ts_code} 财务指标失败: {e}")
        return None


def update_daily_fundamental(
    warehouse: PostgresWarehouse,
    ts_code: str,
    trade_date: date,
    financial_data: Dict
) -> bool:
    """
    更新fact_daily_fundamental表
    
    Args:
        warehouse: 数据仓库
        ts_code: 股票代码
        trade_date: 交易日期
        financial_data: 财务数据
    
    Returns:
        bool: 是否成功
    """
    if not warehouse.warehouse_service:
        return False
    
    session = warehouse.warehouse_service.get_session()
    try:
        # 查询或创建记录
        existing = session.query(FactDailyFundamental).filter(
            FactDailyFundamental.ts_code == ts_code,
            FactDailyFundamental.trade_date == trade_date
        ).first()
        
        if existing:
            # 更新现有记录
            if financial_data.get('roe_ttm') is not None:
                existing.roe_ttm = financial_data['roe_ttm']
            if financial_data.get('net_margin_ttm') is not None:
                existing.net_margin_ttm = financial_data['net_margin_ttm']
            if financial_data.get('gross_margin_ttm') is not None:
                existing.gross_margin_ttm = financial_data['gross_margin_ttm']
            if financial_data.get('op_cf_ttm') is not None:
                existing.op_cf_ttm = financial_data['op_cf_ttm']
        else:
            # 创建新记录
            new_record = FactDailyFundamental(
                ts_code=ts_code,
                trade_date=trade_date,
                roe_ttm=financial_data.get('roe_ttm'),
                net_margin_ttm=financial_data.get('net_margin_ttm'),
                gross_margin_ttm=financial_data.get('gross_margin_ttm'),
                op_cf_ttm=financial_data.get('op_cf_ttm'),
                source='tushare_fill'
            )
            session.add(new_record)
        
        session.commit()
        return True
        
    except Exception as e:
        logger.error(f"更新 {ts_code} 财务数据失败: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def fill_daily_fundamental(
    limit: Optional[int] = None,
    batch_size: int = 20,
    delay: float = 0.5
):
    """
    补充每日基本面指标
    
    Args:
        limit: 限制处理的股票数量
        batch_size: 每批处理的股票数量
        delay: 每只股票之间的延迟（秒）
    """
    logger.info("=" * 60)
    logger.info("开始补充每日基本面指标（ROE、毛利率、净利率、现金流）")
    logger.info("=" * 60)
    
    # 初始化服务
    warehouse = PostgresWarehouse()
    tushare_service = TushareService()
    
    if not tushare_service.available:
        logger.error("❌ Tushare服务不可用")
        return
    
    # 获取最新交易日期
    latest_date = get_latest_trade_date(warehouse)
    if not latest_date:
        logger.error("❌ 无法获取最新交易日期")
        return
    
    logger.info(f"📅 目标交易日期: {latest_date}")
    
    # 获取股票列表
    stock_codes = get_stock_list(warehouse, limit=limit)
    if not stock_codes:
        logger.error("❌ 没有股票代码")
        return
    
    logger.info(f"📊 共 {len(stock_codes)} 只股票需要处理")
    logger.info("")
    
    success_count = 0
    failed_count = 0
    skip_count = 0
    
    # 批量处理
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(stock_codes) + batch_size - 1) // batch_size
        
        logger.info(f"[批次 {batch_num}/{total_batches}] 处理 {len(batch)} 只股票")
        
        for idx, ts_code in enumerate(batch, 1):
            try:
                # 获取财务指标TTM值
                financial_data = get_financial_indicators_ttm(tushare_service, ts_code)
                
                if not financial_data:
                    if idx <= 3:  # 前3只股票输出详细日志
                        logger.warning(f"  ⚠️ {ts_code} 未获取到财务数据")
                    skip_count += 1
                    continue
                
                # 更新到数据库
                success = update_daily_fundamental(
                    warehouse,
                    ts_code,
                    latest_date,
                    financial_data
                )
                
                if success:
                    success_count += 1
                    if idx % 5 == 0:
                        logger.info(f"  进度: {idx}/{len(batch)} - {ts_code}: ROE={financial_data.get('roe_ttm', 0):.2f}%, 毛利率={financial_data.get('gross_margin_ttm', 0):.2f}%")
                else:
                    failed_count += 1
                
                # 延迟，避免请求过快
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"  ❌ 处理 {ts_code} 失败: {e}")
                failed_count += 1
                continue
        
        logger.info(f"  ✅ 批次 {batch_num} 完成")
        
        # 批次间延迟
        if i + batch_size < len(stock_codes):
            time.sleep(2)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✅ 补充完成")
    logger.info(f"  成功: {success_count} 只")
    logger.info(f"  失败: {failed_count} 只")
    logger.info(f"  跳过: {skip_count} 只")
    logger.info("=" * 60)


if __name__ == '__main__':
    try:
        # 补充前200只股票的财务数据（避免频繁调用API）
        fill_daily_fundamental(limit=200, batch_size=20, delay=0.5)
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断")
    except Exception as e:
        logger.error(f"❌ 补充失败: {e}", exc_info=True)
        sys.exit(1)

