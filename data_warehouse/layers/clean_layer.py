"""
标准数据层（Clean Layer）
负责多源合并和数据质量评估
"""

import logging
from typing import List, Dict, Optional
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import sessionmaker, Session

from data_warehouse.config import DATABASE_URL, SOURCE_PRIORITY, MAX_ALLOWED_DIFF_PCT, DATA_QUALITY_A, DATA_QUALITY_B, DATA_QUALITY_C
from data_warehouse.db import get_shared_engine
from data_warehouse.layers.raw_layer import RawDataLayer
from data_warehouse.models import FactDailyPrice
from data_warehouse.models import FactFundamental

logger = logging.getLogger(__name__)


class CleanDataLayer:
    """标准数据层"""
    
    def __init__(self, database_url: Optional[str] = None, raw_layer: Optional[RawDataLayer] = None):
        """
        初始化标准数据层
        
        Args:
            database_url: 数据库连接URL
            raw_layer: Raw数据层实例，如果为None则自动创建
        """
        self.database_url = database_url or DATABASE_URL
        self.engine = get_shared_engine()
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.raw_layer = raw_layer or RawDataLayer(database_url)
        logger.info(f"✅ CleanDataLayer已初始化")
    
    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()
    
    def merge_daily_prices(self, ts_code: str, trade_date: date) -> Optional[Dict]:
        """
        合并多源日线数据
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期
        
        Returns:
            Dict: 合并后的标准日线数据，如果失败返回None
        """
        # 1. 从raw层获取所有数据源的数据
        raw_data_list = self.raw_layer.get_raw_daily_price(ts_code, trade_date)
        
        if not raw_data_list:
            logger.debug(f"没有原始数据可合并: {ts_code} {trade_date}")
            return None
        
        # 2. 按优先级排序
        def get_priority(raw_item):
            source = raw_item.source
            try:
                return SOURCE_PRIORITY.index(source)
            except ValueError:
                return len(SOURCE_PRIORITY)  # 未知数据源排在最后
        
        sorted_data = sorted(raw_data_list, key=get_priority)
        
        # 3. 选择主数据源（优先级最高的）
        base_data = sorted_data[0]
        
        # 4. 对比其他数据源，评估数据质量
        quality = DATA_QUALITY_B  # 默认B级（单源）
        sources_used = [base_data.source]
        
        if len(sorted_data) > 1:
            # 多源数据，进行一致性检查
            base_close = float(base_data.close) if base_data.close else 0
            
            if base_close > 0:
                max_diff_pct = 0.0
                for other_data in sorted_data[1:]:
                    other_close = float(other_data.close) if other_data.close else 0
                    if other_close > 0:
                        diff_pct = abs(other_close - base_close) / base_close * 100
                        max_diff_pct = max(max_diff_pct, diff_pct)
                        sources_used.append(other_data.source)
                
                # 根据差异评估质量
                if max_diff_pct <= MAX_ALLOWED_DIFF_PCT:
                    quality = DATA_QUALITY_A  # 多源一致
                elif max_diff_pct <= MAX_ALLOWED_DIFF_PCT * 2:
                    quality = DATA_QUALITY_B  # 差异较小
                else:
                    quality = DATA_QUALITY_C  # 差异较大
                    logger.warning(f"数据质量较低（差异{max_diff_pct:.2f}%）: {ts_code} {trade_date}")
        
        # 5. 生成fact数据
        fact_data = {
            'ts_code': ts_code,
            'trade_date': trade_date,
            'open': base_data.open,
            'high': base_data.high,
            'low': base_data.low,
            'close': base_data.close,
            'pre_close': base_data.pre_close,
            'vol': base_data.vol,
            'amount': base_data.amount,
            'turnover_rate': base_data.turnover_rate,
            'data_quality': quality,
            'sources_used': sources_used
        }
        
        return fact_data
    
    def save_fact_daily_price(self, fact_data: Dict) -> bool:
        """
        保存标准日线数据
        
        Args:
            fact_data: 标准日线数据字典
        
        Returns:
            bool: 是否保存成功
        """
        session = self.get_session()
        try:
            # 检查是否已存在
            existing = session.query(FactDailyPrice).filter(
                FactDailyPrice.ts_code == fact_data['ts_code'],
                FactDailyPrice.trade_date == fact_data['trade_date']
            ).first()
            
            if existing:
                # 更新现有记录
                existing.open = fact_data.get('open')
                existing.high = fact_data.get('high')
                existing.low = fact_data.get('low')
                existing.close = fact_data.get('close')
                existing.pre_close = fact_data.get('pre_close')
                existing.vol = fact_data.get('vol')
                existing.amount = fact_data.get('amount')
                existing.turnover_rate = fact_data.get('turnover_rate')
                existing.data_quality = fact_data.get('data_quality', DATA_QUALITY_B)
                existing.sources_used = fact_data.get('sources_used', [])
                logger.debug(f"更新Fact日线数据: {fact_data['ts_code']} {fact_data['trade_date']}")
            else:
                # 创建新记录
                fact_price = FactDailyPrice(
                    ts_code=fact_data['ts_code'],
                    trade_date=fact_data['trade_date'],
                    open=fact_data.get('open'),
                    high=fact_data.get('high'),
                    low=fact_data.get('low'),
                    close=fact_data.get('close'),
                    pre_close=fact_data.get('pre_close'),
                    vol=fact_data.get('vol'),
                    amount=fact_data.get('amount'),
                    turnover_rate=fact_data.get('turnover_rate'),
                    data_quality=fact_data.get('data_quality', DATA_QUALITY_B),
                    sources_used=fact_data.get('sources_used', [])
                )
                session.add(fact_price)
                logger.debug(f"新增Fact日线数据: {fact_data['ts_code']} {fact_data['trade_date']}")
            
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存Fact日线数据失败: {fact_data.get('ts_code')} {fact_data.get('trade_date')}: {e}", exc_info=True)
            return False
        finally:
            session.close()
    
    def save_fact_daily_price_qfq(self, fact_data: Dict) -> bool:
        """
        保存前复权日线数据到 fact_daily_price_qfq 表
        
        Args:
            fact_data: 标准日线数据字典
        
        Returns:
            bool: 是否保存成功
        """
        from data_warehouse.models import FactDailyPriceQfq
        
        session = self.get_session()
        try:
            # 预先计算涨跌幅（若可能）
            change_pct_value = None
            try:
                close_val = fact_data.get('close')
                pre_close_val = fact_data.get('pre_close')
                if close_val is not None and pre_close_val is not None:
                    close_f = float(close_val)
                    pre_close_f = float(pre_close_val)
                    if pre_close_f != 0:
                        change_pct_value = (close_f - pre_close_f) / pre_close_f * 100
            except Exception as e:
                logger.debug("计算涨跌幅失败，跳过: %s", e)
                change_pct_value = None

            # 检查是否已存在
            existing = session.query(FactDailyPriceQfq).filter(
                FactDailyPriceQfq.ts_code == fact_data['ts_code'],
                FactDailyPriceQfq.trade_date == fact_data['trade_date']
            ).first()
            
            if existing:
                # 更新现有记录
                existing.open = fact_data.get('open')
                existing.high = fact_data.get('high')
                existing.low = fact_data.get('low')
                existing.close = fact_data.get('close')
                existing.pre_close = fact_data.get('pre_close')
                existing.vol = fact_data.get('vol')
                existing.amount = fact_data.get('amount')
                existing.turnover_rate = fact_data.get('turnover_rate')
                # 更新涨跌幅（若已成功计算）
                if change_pct_value is not None:
                    existing.change_pct = change_pct_value
                logger.debug(f"更新前复权日线数据: {fact_data['ts_code']} {fact_data['trade_date']}")
            else:
                # 创建新记录
                qfq_price = FactDailyPriceQfq(
                    ts_code=fact_data['ts_code'],
                    trade_date=fact_data['trade_date'],
                    open=fact_data.get('open'),
                    high=fact_data.get('high'),
                    low=fact_data.get('low'),
                    close=fact_data.get('close'),
                    pre_close=fact_data.get('pre_close'),
                    vol=fact_data.get('vol'),
                    amount=fact_data.get('amount'),
                    turnover_rate=fact_data.get('turnover_rate'),
                    change_pct=change_pct_value
                )
                session.add(qfq_price)
                logger.debug(f"新增前复权日线数据: {fact_data['ts_code']} {fact_data['trade_date']}")
            
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存前复权日线数据失败: {fact_data.get('ts_code')} {fact_data.get('trade_date')}: {e}")
            return False
        finally:
            session.close()
    
    def merge_fundamental(
        self,
        ts_code: str,
        end_date: date,
        report_type: str
    ) -> Optional[Dict]:
        """
        合并多源财务数据
        
        Args:
            ts_code: 股票代码
            end_date: 报告期
            report_type: 报告类型
        
        Returns:
            Dict: 合并后的标准财务数据
        """
        # 1. 从raw层获取所有数据源的数据
        raw_data_list = self.raw_layer.get_raw_fundamental(ts_code, end_date, report_type)
        
        if not raw_data_list:
            logger.debug(f"没有原始财务数据可合并: {ts_code} {end_date} {report_type}")
            return None
        
        # 2. 按优先级排序，优先选择有数据的源
        def get_priority(raw_item):
            source = raw_item.source
            # 计算优先级：先按数据源优先级，再按数据完整性
            try:
                source_priority = SOURCE_PRIORITY.index(source)
            except ValueError:
                source_priority = len(SOURCE_PRIORITY)  # 未知数据源排在最后
            
            # 数据完整性评分：有负债率、毛利率、经营现金流等关键字段的数据优先级更高
            data_completeness = 0
            if raw_item.debt_ratio is not None and raw_item.debt_ratio > 0:
                data_completeness += 10
            if raw_item.gross_margin is not None and raw_item.gross_margin > 0:
                data_completeness += 10
            if raw_item.op_cf is not None and raw_item.op_cf != 0:
                data_completeness += 10
            if raw_item.roe is not None and raw_item.roe > 0:
                data_completeness += 5
            
            # 优先级 = 数据源优先级 * 1000 - 数据完整性（数据完整性越高，优先级越高）
            return source_priority * 1000 - data_completeness
        
        sorted_data = sorted(raw_data_list, key=get_priority)
        
        # 3. 选择主数据源（优先级最高的，即数据最完整的）
        base_data = sorted_data[0]
        quality = DATA_QUALITY_B
        sources_used = [base_data.source]
        
        # 4. 评估数据质量（简化处理，财务数据差异容忍度更高）
        if len(sorted_data) > 1:
            quality = DATA_QUALITY_A  # 多源一致
            sources_used = [d.source for d in sorted_data]
        
        # 5. 从raw_payload中提取额外字段（如果存在）
        revenue = None
        revenue_growth = None
        net_profit = None
        ocf_to_revenue = None

        def _extract_from_payload(payload: dict) -> tuple:
            r, rg, np_val, ocf = None, None, None, None
            op_profit, fin_ex, good, equity, audit, deduct_nm = None, None, None, None, None, None
            if payload and isinstance(payload, dict):
                if 'revenue' in payload:
                    r = payload.get('revenue')
                if 'yoy_sales' in payload:
                    v = payload.get('yoy_sales')
                    if v is not None:
                        rg = v
                if 'net_profit' in payload:
                    np_val = payload.get('net_profit')
                if 'ocf_to_revenue' in payload:
                    ocf_val = payload.get('ocf_to_revenue')
                    if ocf_val is not None:
                        ocf = ocf_val / 100 if ocf_val > 1 else ocf_val
                op_profit = payload.get('operate_profit')
                fin_ex = payload.get('fin_exp')
                good = payload.get('goodwill')
                equity = payload.get('total_equity')
                audit = payload.get('audit_result')
                if 'deduct_net_margin' in payload and payload.get('deduct_net_margin') is not None:
                    val = payload['deduct_net_margin']
                    try:
                        deduct_nm = float(val) / 100 if abs(float(val)) > 1 else float(val)
                    except (ValueError, TypeError):
                        pass
            return r, rg, np_val, ocf, op_profit, fin_ex, good, equity, audit, deduct_nm

        op_profit = fin_exp_val = goodwill_val = total_equity_val = audit_result_val = deduct_net_margin_val = None
        if base_data.raw_payload:
            revenue, revenue_growth, net_profit, ocf_to_revenue, op_profit, fin_exp_val, goodwill_val, total_equity_val, audit_result_val, deduct_net_margin_val = _extract_from_payload(base_data.raw_payload)
        # 主数据源缺 revenue/yoy_sales 等时，尝试从其他 raw 源补充
        op_cf_candidate = base_data.op_cf
        if len(sorted_data) > 1:
            for other in sorted_data[1:]:
                if other.raw_payload:
                    r, rg, np_val, ocf, opp, fe, gw, te, ar, dnm = _extract_from_payload(other.raw_payload)
                    if revenue is None and r is not None:
                        revenue = r
                    if revenue_growth is None and rg is not None:
                        revenue_growth = rg
                    if net_profit is None and np_val is not None:
                        net_profit = np_val
                    if ocf_to_revenue is None and ocf is not None:
                        ocf_to_revenue = ocf
                    if op_profit is None and opp is not None:
                        op_profit = opp
                    if fin_exp_val is None and fe is not None:
                        fin_exp_val = fe
                    if goodwill_val is None and gw is not None:
                        goodwill_val = gw
                    if total_equity_val is None and te is not None:
                        total_equity_val = te
                    if audit_result_val is None and ar is not None:
                        audit_result_val = ar
                    if deduct_net_margin_val is None and dnm is not None:
                        deduct_net_margin_val = dnm
                if op_cf_candidate is None and other.op_cf is not None:
                    op_cf_candidate = other.op_cf

        def _normalize_op_cf_to_yuan(op_cf_val, revenue_val):
            """将经营现金流标准化为元。若疑似万元（op_cf 过小而 revenue 较大），则 *1e4"""
            if op_cf_val is None:
                return None
            try:
                ocf_f = float(op_cf_val)
                if revenue_val is not None and (rev_f := float(revenue_val)) > 1e7:
                    # 典型公司 op_cf/revenue 约 0.05~0.4，若 op_cf/revenue < 1e-6 则疑似 op_cf 为万元
                    if abs(ocf_f) > 0 and rev_f > 0 and abs(ocf_f / rev_f) < 1e-6:
                        ocf_f *= 1e4
                        logger.debug(f"op_cf 单位矫正（万元→元）: {op_cf_val} -> {ocf_f:,.0f} (revenue={rev_f:,.0f})")
                return ocf_f
            except (ValueError, TypeError):
                return op_cf_val

        op_cf_final = _normalize_op_cf_to_yuan(op_cf_candidate, revenue)
        
        # 6. 生成fact数据
        fact_data = {
            'ts_code': ts_code,
            'end_date': end_date,
            'report_type': report_type,
            'roe': base_data.roe,
            'net_margin': base_data.net_margin,
            'deduct_net_margin': deduct_net_margin_val,
            'gross_margin': base_data.gross_margin,
            'op_cf': op_cf_final if op_cf_final is not None else op_cf_candidate,
            'total_debt': base_data.total_debt,
            'total_asset': base_data.total_asset,
            'debt_ratio': base_data.debt_ratio,
            'profit_volatility': base_data.profit_volatility,
            'revenue': revenue,
            'revenue_growth': revenue_growth,
            'net_profit': net_profit,
            'ocf_to_revenue': ocf_to_revenue,
            'operate_profit': op_profit,
            'fin_exp': fin_exp_val,
            'goodwill': goodwill_val,
            'total_equity': total_equity_val,
            'audit_result': audit_result_val,
            'data_quality': quality,
            'sources_used': sources_used
        }
        
        return fact_data
    
    def save_fact_fundamental(self, fact_data: Dict) -> bool:
        """
        保存标准财务数据
        
        Args:
            fact_data: 标准财务数据字典
        
        Returns:
            bool: 是否保存成功
        """
        session = self.get_session()
        try:
            # 检查是否已存在
            existing = session.query(FactFundamental).filter(
                FactFundamental.ts_code == fact_data['ts_code'],
                FactFundamental.end_date == fact_data['end_date'],
                FactFundamental.report_type == fact_data['report_type']
            ).first()
            
            if existing:
                # 更新现有记录
                existing.roe = fact_data.get('roe')
                existing.net_margin = fact_data.get('net_margin')
                existing.gross_margin = fact_data.get('gross_margin')
                existing.op_cf = fact_data.get('op_cf')
                existing.total_debt = fact_data.get('total_debt')
                existing.total_asset = fact_data.get('total_asset')
                existing.debt_ratio = fact_data.get('debt_ratio')
                existing.profit_volatility = fact_data.get('profit_volatility')
                existing.revenue = fact_data.get('revenue')
                existing.revenue_growth = fact_data.get('revenue_growth')
                existing.net_profit = fact_data.get('net_profit')
                if 'deduct_net_margin' in fact_data:
                    existing.deduct_net_margin = fact_data.get('deduct_net_margin')
                existing.ocf_to_revenue = fact_data.get('ocf_to_revenue')
                existing.data_quality = fact_data.get('data_quality', DATA_QUALITY_B)
                existing.sources_used = fact_data.get('sources_used', [])
                if 'operate_profit' in fact_data:
                    existing.operate_profit = fact_data.get('operate_profit')
                if 'fin_exp' in fact_data:
                    existing.fin_exp = fact_data.get('fin_exp')
                if 'goodwill' in fact_data:
                    existing.goodwill = fact_data.get('goodwill')
                if 'total_equity' in fact_data:
                    existing.total_equity = fact_data.get('total_equity')
                if 'audit_result' in fact_data:
                    existing.audit_result = fact_data.get('audit_result')
            else:
                # 创建新记录
                fact_fundamental = FactFundamental(
                    ts_code=fact_data['ts_code'],
                    end_date=fact_data['end_date'],
                    report_type=fact_data['report_type'],
                    roe=fact_data.get('roe'),
                    net_margin=fact_data.get('net_margin'),
                    gross_margin=fact_data.get('gross_margin'),
                    op_cf=fact_data.get('op_cf'),
                    total_debt=fact_data.get('total_debt'),
                    total_asset=fact_data.get('total_asset'),
                    debt_ratio=fact_data.get('debt_ratio'),
                    profit_volatility=fact_data.get('profit_volatility'),
                    revenue=fact_data.get('revenue'),
                    revenue_growth=fact_data.get('revenue_growth'),
                    net_profit=fact_data.get('net_profit'),
                    deduct_net_margin=fact_data.get('deduct_net_margin'),
                    ocf_to_revenue=fact_data.get('ocf_to_revenue'),
                    operate_profit=fact_data.get('operate_profit'),
                    fin_exp=fact_data.get('fin_exp'),
                    goodwill=fact_data.get('goodwill'),
                    total_equity=fact_data.get('total_equity'),
                    audit_result=fact_data.get('audit_result'),
                    data_quality=fact_data.get('data_quality', DATA_QUALITY_B),
                    sources_used=fact_data.get('sources_used', [])
                )
                session.add(fact_fundamental)
            
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"保存Fact财务数据失败: {fact_data.get('ts_code')} {fact_data.get('end_date')}: {e}", exc_info=True)
            return False
        finally:
            session.close()

