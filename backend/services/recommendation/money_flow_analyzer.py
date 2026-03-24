"""
资金流向分析模块
分析主力资金、北向资金、筹码集中度
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, date, timedelta

from backend.utils.trade_date_utils import get_trade_date_or_latest
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 表缺失时仅记录一次，避免批量分析刷屏
_table_missing_logged = {"fact_money_flow": False, "fact_north_holding": False}


@dataclass
class MoneyFlowData:
    """资金流向数据"""
    ts_code: str
    main_flow_days: int           # 主力资金连续净流入天数（负数表示流出）
    main_flow_amount: float       # 近5日主力净流入金额（万）
    main_flow_pct: float          # 主力净流入占比
    north_change_pct: float       # 北向资金近5日持仓变化比例
    north_hold_pct: float         # 北向资金持仓占比
    chip_concentration: float     # 筹码集中度（90%成本集中度）
    main_cost_price: float        # 主力成本价估算
    current_vs_cost: str          # 当前价相对主力成本位置：above/near/below
    score: float                  # 资金面综合得分 0-100


class MoneyFlowAnalyzer:
    """资金流向分析器"""
    
    def __init__(self, warehouse_service=None):
        self.ws = warehouse_service
        if not self.ws:
            from data_warehouse.service.warehouse_service import WarehouseService
            self.ws = WarehouseService()
    
    def analyze_stock(self, ts_code: str, trade_date: Optional[str] = None) -> Dict:
        """
        分析个股资金流向
        
        Args:
            ts_code: 股票代码
            trade_date: 交易日期
            
        Returns:
            Dict: 资金流向分析结果
        """
        try:
            resolved = get_trade_date_or_latest(self.ws, trade_date)
            trade_date = resolved.strftime('%Y-%m-%d') if resolved else (trade_date or date.today().isoformat())
            
            session = self.ws.get_session()
            try:
                # 获取主力资金数据
                main_flow = self._get_main_flow(session, ts_code, trade_date)
                
                # 获取北向资金数据
                north_data = self._get_north_holding(session, ts_code, trade_date)
                
                # 计算筹码集中度和主力成本
                chip_data = self._calc_chip_analysis(session, ts_code, trade_date)
                
                # 获取当前价格
                current_price = self._get_current_price(session, ts_code, trade_date)
                
                # 判断当前价相对主力成本位置
                main_cost = chip_data.get('main_cost_price', 0)
                if main_cost > 0 and current_price > 0:
                    ratio = current_price / main_cost
                    if ratio > 1.1:
                        current_vs_cost = 'above'  # 高于成本10%以上
                    elif ratio < 0.95:
                        current_vs_cost = 'below'  # 低于成本5%以上
                    else:
                        current_vs_cost = 'near'   # 接近成本
                else:
                    current_vs_cost = 'unknown'
                
                # 计算综合得分
                score = self._calc_money_flow_score(
                    main_flow, north_data, chip_data, current_vs_cost
                )
                
                result = MoneyFlowData(
                    ts_code=ts_code,
                    main_flow_days=main_flow.get('continuous_days', 0),
                    main_flow_amount=main_flow.get('total_amount_5d', 0),
                    main_flow_pct=main_flow.get('flow_pct', 0),
                    north_change_pct=north_data.get('change_pct_5d', 0),
                    north_hold_pct=north_data.get('hold_pct', 0),
                    chip_concentration=chip_data.get('concentration', 0),
                    main_cost_price=main_cost,
                    current_vs_cost=current_vs_cost,
                    score=score
                )
                
                return {
                    'success': True,
                    'data': result.__dict__
                }
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"分析资金流向失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': '操作失败',
                'data': self._get_default_flow(ts_code).__dict__
            }
    
    def analyze_batch(self, ts_codes: List[str], trade_date: Optional[str] = None) -> Dict:
        """
        批量分析资金流向
        
        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期
            
        Returns:
            Dict: {ts_code: MoneyFlowData}
        """
        results = {}
        for ts_code in ts_codes:
            result = self.analyze_stock(ts_code, trade_date)
            if result['success']:
                results[ts_code] = result['data']
            else:
                results[ts_code] = self._get_default_flow(ts_code).__dict__
        
        return {'success': True, 'data': results}
    
    def _get_main_flow(self, session, ts_code: str, trade_date: str) -> Dict:
        """获取主力资金流向数据"""
        try:
            from sqlalchemy import text
            
            # 查询近10日资金流向
            result = session.execute(
                text("""
                    SELECT trade_date, main_net_inflow, main_net_inflow_rate
                    FROM fact_money_flow
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 10
                """),
                {'ts_code': ts_code, 'trade_date': trade_date}
            )
            rows = result.fetchall()
            
            if not rows:
                return self._estimate_main_flow(session, ts_code, trade_date)
            
            # 计算连续净流入天数
            continuous_days = 0
            direction = None
            for row in rows:
                net_inflow = float(row[1]) if row[1] else 0
                if direction is None:
                    direction = 1 if net_inflow > 0 else -1
                    continuous_days = direction
                elif (direction > 0 and net_inflow > 0) or (direction < 0 and net_inflow < 0):
                    continuous_days += direction
                else:
                    break
            
            # 计算近5日累计
            total_5d = sum(float(r[1]) if r[1] else 0 for r in rows[:5])
            avg_pct = sum(float(r[2]) if r[2] else 0 for r in rows[:5]) / min(5, len(rows))
            
            return {
                'continuous_days': continuous_days,
                'total_amount_5d': total_5d / 10000,  # 转为万
                'flow_pct': avg_pct
            }
            
        except Exception as e:
            # 表不存在时仅记录一次，避免批量分析刷屏
            is_table_missing = "does not exist" in str(e) or "UndefinedTable" in str(e)
            if is_table_missing and not _table_missing_logged["fact_money_flow"]:
                _table_missing_logged["fact_money_flow"] = True
                logger.debug("fact_money_flow 表不存在，使用成交量估算主力资金")
            elif not is_table_missing:
                logger.warning(f"获取主力资金数据失败: {e}")
            try:
                session.rollback()
            except Exception:
                pass
            return self._estimate_main_flow(session, ts_code, trade_date)
    
    def _estimate_main_flow(self, session, ts_code: str, trade_date: str) -> Dict:
        """通过成交量估算主力资金流向"""
        try:
            from sqlalchemy import text
            
            # 使用 fact_daily_price_qfq 成交量变化估算（fact_daily_price 可能不存在）
            result = session.execute(
                text("""
                    SELECT trade_date, vol, amount, change_pct
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 30
                """),
                {'ts_code': ts_code, 'trade_date': trade_date}
            )
            rows = result.fetchall()
            
            if len(rows) < 5:
                return {'continuous_days': 0, 'total_amount_5d': 0, 'flow_pct': 0}
            
            # 计算平均成交量
            avg_vol = sum(float(r[1]) if r[1] else 0 for r in rows[5:25]) / 20 if len(rows) >= 25 else 1
            
            # 近5日成交量相对变化
            recent_vols = [float(r[1]) if r[1] else 0 for r in rows[:5]]
            recent_changes = [float(r[3]) if r[3] else 0 for r in rows[:5]]
            
            # 估算连续天数（量增价涨认为是流入）
            continuous_days = 0
            direction = None
            for i, (vol, change) in enumerate(zip(recent_vols, recent_changes)):
                vol_ratio = vol / avg_vol if avg_vol > 0 else 1
                is_inflow = vol_ratio > 1.2 and change > 0  # 放量上涨
                is_outflow = vol_ratio > 1.2 and change < -2  # 放量下跌
                
                if direction is None:
                    if is_inflow:
                        direction = 1
                        continuous_days = 1
                    elif is_outflow:
                        direction = -1
                        continuous_days = -1
                elif direction > 0 and is_inflow:
                    continuous_days += 1
                elif direction < 0 and is_outflow:
                    continuous_days -= 1
                else:
                    break
            
            # 估算流入金额
            total_amount = sum(float(r[2]) if r[2] else 0 for r in rows[:5])
            estimated_flow = total_amount * 0.3 if continuous_days > 0 else -total_amount * 0.3
            
            return {
                'continuous_days': continuous_days,
                'total_amount_5d': estimated_flow / 10000,  # 万
                'flow_pct': continuous_days * 2  # 估算占比
            }
            
        except Exception as e:
            logger.warning(f"估算主力资金失败: {e}")
            try:
                session.rollback()
            except Exception:
                pass
            return {'continuous_days': 0, 'total_amount_5d': 0, 'flow_pct': 0}
    
    def _get_north_holding(self, session, ts_code: str, trade_date: str) -> Dict:
        """获取北向资金持仓数据"""
        try:
            from sqlalchemy import text
            
            # 查询北向持仓
            result = session.execute(
                text("""
                    SELECT trade_date, hold_vol, hold_ratio
                    FROM fact_north_holding
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 10
                """),
                {'ts_code': ts_code, 'trade_date': trade_date}
            )
            rows = result.fetchall()
            
            if not rows:
                return {'change_pct_5d': 0, 'hold_pct': 0}
            
            current_hold = float(rows[0][1]) if rows[0][1] else 0
            current_pct = float(rows[0][2]) if rows[0][2] else 0
            
            # 计算5日变化
            if len(rows) >= 5:
                old_hold = float(rows[4][1]) if rows[4][1] else 0
                change_pct = ((current_hold - old_hold) / old_hold * 100) if old_hold > 0 else 0
            else:
                change_pct = 0
            
            return {
                'change_pct_5d': change_pct,
                'hold_pct': current_pct
            }
            
        except Exception as e:
            # 表不存在时仅记录一次，避免批量分析刷屏
            is_table_missing = "does not exist" in str(e) or "UndefinedTable" in str(e)
            if is_table_missing and not _table_missing_logged["fact_north_holding"]:
                _table_missing_logged["fact_north_holding"] = True
                logger.debug("fact_north_holding 表不存在，使用默认值")
            elif not is_table_missing:
                logger.warning(f"获取北向资金数据失败: {e}")
            try:
                session.rollback()
            except Exception:
                pass
            return {'change_pct_5d': 0, 'hold_pct': 0}
    
    def _calc_chip_analysis(self, session, ts_code: str, trade_date: str) -> Dict:
        """计算筹码集中度和主力成本"""
        try:
            from sqlalchemy import text
            
            # 获取近60日成交数据计算筹码分布（使用 fact_daily_price_qfq）
            result = session.execute(
                text("""
                    SELECT trade_date, close, vol, amount, high, low
                    FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code
                      AND trade_date <= :trade_date
                    ORDER BY trade_date DESC
                    LIMIT 60
                """),
                {'ts_code': ts_code, 'trade_date': trade_date}
            )
            rows = result.fetchall()
            
            if len(rows) < 20:
                return {'concentration': 0, 'main_cost_price': 0}
            
            # 简化的筹码成本计算：成交量加权平均价
            total_vol = sum(float(r[2]) if r[2] else 0 for r in rows[:30])
            if total_vol == 0:
                return {'concentration': 0, 'main_cost_price': 0}
            
            weighted_price = sum(
                (float(r[1]) if r[1] else 0) * (float(r[2]) if r[2] else 0) 
                for r in rows[:30]
            ) / total_vol
            
            # 计算筹码集中度（使用价格波动率近似）
            closes = [float(r[1]) for r in rows[:30] if r[1]]
            if closes:
                avg_price = sum(closes) / len(closes)
                variance = sum((c - avg_price) ** 2 for c in closes) / len(closes)
                std_dev = variance ** 0.5
                concentration = (1 - std_dev / avg_price) * 100 if avg_price > 0 else 0
                concentration = max(0, min(100, concentration))
            else:
                concentration = 0
            
            return {
                'concentration': round(concentration, 2),
                'main_cost_price': round(weighted_price, 2)
            }
            
        except Exception as e:
            logger.warning(f"计算筹码分析失败: {e}")
            try:
                session.rollback()
            except Exception:
                pass
            return {'concentration': 0, 'main_cost_price': 0}
    
    def _get_current_price(self, session, ts_code: str, trade_date: str) -> float:
        """获取当前价格"""
        try:
            from sqlalchemy import text
            
            result = session.execute(
                text("""
                    SELECT close FROM fact_daily_price_qfq
                    WHERE ts_code = :ts_code AND trade_date <= :trade_date
                    ORDER BY trade_date DESC LIMIT 1
                """),
                {'ts_code': ts_code, 'trade_date': trade_date}
            )
            row = result.fetchone()
            return float(row[0]) if row and row[0] else 0
        except Exception:
            return 0
    
    def _calc_money_flow_score(self, main_flow: Dict, north_data: Dict, 
                                chip_data: Dict, current_vs_cost: str) -> float:
        """计算资金流向综合得分"""
        score = 50  # 基准分
        
        # 主力资金贡献（40%权重）
        continuous_days = main_flow.get('continuous_days', 0)
        if continuous_days >= 3:
            score += 20
        elif continuous_days >= 1:
            score += 10
        elif continuous_days <= -3:
            score -= 20
        elif continuous_days <= -1:
            score -= 10
        
        flow_pct = main_flow.get('flow_pct', 0)
        if flow_pct > 5:
            score += 10
        elif flow_pct > 2:
            score += 5
        elif flow_pct < -5:
            score -= 10
        
        # 北向资金贡献（30%权重）
        north_change = north_data.get('change_pct_5d', 0)
        if north_change > 10:
            score += 15
        elif north_change > 5:
            score += 8
        elif north_change < -10:
            score -= 15
        elif north_change < -5:
            score -= 8
        
        # 筹码集中度贡献（15%权重）
        concentration = chip_data.get('concentration', 0)
        if concentration > 80:
            score += 10
        elif concentration > 60:
            score += 5
        elif concentration < 30:
            score -= 5
        
        # 当前价相对成本位置（15%权重）
        if current_vs_cost == 'near':
            score += 10  # 接近成本，安全边际高
        elif current_vs_cost == 'below':
            score += 5   # 低于成本，可能有支撑
        elif current_vs_cost == 'above':
            score -= 5   # 高于成本，获利盘压力
        
        return max(0, min(100, round(score, 1)))
    
    def _get_default_flow(self, ts_code: str) -> MoneyFlowData:
        """获取默认资金流向数据"""
        return MoneyFlowData(
            ts_code=ts_code,
            main_flow_days=0,
            main_flow_amount=0,
            main_flow_pct=0,
            north_change_pct=0,
            north_hold_pct=0,
            chip_concentration=50,
            main_cost_price=0,
            current_vs_cost='unknown',
            score=50
        )
