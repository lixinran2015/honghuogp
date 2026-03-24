"""
推荐结果服务
负责保存和读取推荐结果，以及补充实时数据
"""

import sys
from pathlib import Path
import pandas as pd
from typing import List, Dict, Optional
import logging
from datetime import datetime, date
from sqlalchemy import desc
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_warehouse.models import FactRecommendationResult
from data_warehouse.db import get_shared_engine
# 使用新的统一数据访问层
try:
    from backend.services.market_data_service_v2 import MarketDataService
except ImportError:
    # 降级：使用旧版本
    from backend.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


class RecommendationResultService:
    """推荐结果服务"""
    
    def __init__(self):
        """初始化服务"""
        self.market_service = MarketDataService()
        self.engine = get_shared_engine()
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def save_recommendations(
        self,
        trade_date: str,
        generated_at: datetime,
        recommendation_type: str,
        recommendations: List[Dict]
    ) -> int:
        """
        保存推荐结果到数据库
        
        Args:
            trade_date: 交易日期（格式：YYYY-MM-DD）
            generated_at: 生成时间
            recommendation_type: 推荐类型（today/short/swing/darwin）
            recommendations: 推荐列表，每个元素包含code、score、reason等
            
        Returns:
            int: 保存的记录数
        """
        try:
            session = self.SessionLocal()
            saved_count = 0
            
            try:
                # 删除该日期和类型的旧记录（不限制generated_at，确保去重）
                deleted = session.query(FactRecommendationResult).filter(
                    FactRecommendationResult.trade_date == datetime.strptime(trade_date, '%Y-%m-%d').date(),
                    FactRecommendationResult.recommendation_type == recommendation_type
                ).delete()
                if deleted > 0:
                    logger.info(f"🗑️ 删除 {recommendation_type} 类型的旧记录: {deleted} 条")
                
                # 保存新记录
                for rank, rec in enumerate(recommendations, 1):
                    try:
                        code = str(rec.get('code', '')).strip()
                        if not code:
                            continue
                        
                        # 转换为ts_code格式
                        ts_code = self._convert_to_ts_code(code)
                        if not ts_code:
                            continue
                        
                        result = FactRecommendationResult(
                            ts_code=ts_code,
                            trade_date=datetime.strptime(trade_date, '%Y-%m-%d').date(),
                            generated_at=generated_at,
                            recommendation_type=recommendation_type,
                            strategy_signal=rec.get('strategy_signal', {}),
                            risk_type=rec.get('riskType', rec.get('risk_type', 'stable')),
                            final_score=float(rec.get('score', rec.get('final_score', 0))),
                            rank_order=rank,
                            recommendation_details={
                                'buy_range': rec.get('buyRange', rec.get('buy_range')),
                                'reason': rec.get('reason', ''),
                                'advice': rec.get('advice', ''),
                                'volume_price_pattern': rec.get('volumePricePattern', rec.get('volume_price_pattern')),
                                'tags': rec.get('tags', [])
                            },
                            snapshot_price=float(rec.get('currentPrice', rec.get('snapshot_price', 0))),
                            snapshot_change_pct=float(rec.get('changePct', rec.get('snapshot_change_pct', 0))),
                            snapshot_turnover_rate=self._parse_turnover_rate(rec.get('turnoverRate', rec.get('snapshot_turnover_rate', 0))),
                            snapshot_amount=float(rec.get('amount', rec.get('snapshot_amount', 0)))
                        )
                        
                        session.add(result)
                        saved_count += 1
                        
                    except Exception as e:
                        logger.warning(f"保存推荐记录失败: {rec.get('code', 'unknown')}, {e}")
                        continue
                
                session.commit()
                logger.info(f"✅ 保存推荐结果: {recommendation_type}, {saved_count} 条记录")
                
                return saved_count
                
            except Exception as e:
                session.rollback()
                logger.error(f"❌ 保存推荐结果失败: {e}", exc_info=True)
                raise
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 保存推荐结果异常: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _parse_turnover_rate(value) -> float:
        """
        解析换手率（可能是字符串格式如 '14.78%' 或数值）
        
        Args:
            value: 换手率值（可能是字符串或数值）
            
        Returns:
            float: 换手率数值
        """
        if value is None:
            return 0.0
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # 去除%符号和空格
            value = value.replace('%', '').replace(' ', '').strip()
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        return 0.0
    
    def get_latest_recommendations(
        self,
        recommendation_type: str,
        limit: int = 10,
        trade_date: Optional[str] = None
    ) -> List[Dict]:
        """
        从数据库读取最新推荐结果
        
        Args:
            recommendation_type: 推荐类型（today/short/swing/darwin）
            limit: 返回数量限制
            trade_date: 交易日期（格式：YYYY-MM-DD），默认今天
            
        Returns:
            list: 推荐列表
        """
        try:
            if trade_date is None:
                trade_date = datetime.now().strftime('%Y-%m-%d')
            
            session = self.SessionLocal()
            try:
                # 查询最新推荐结果
                results = session.query(FactRecommendationResult).filter(
                    FactRecommendationResult.trade_date == datetime.strptime(trade_date, '%Y-%m-%d').date(),
                    FactRecommendationResult.recommendation_type == recommendation_type
                ).order_by(
                    desc(FactRecommendationResult.generated_at),
                    FactRecommendationResult.rank_order
                ).limit(limit).all()
                
                if not results:
                    logger.warning(f"⚠️ 未找到 {recommendation_type} 类型的推荐结果")
                    return []
                
                # 获取股票名称
                ts_codes = [r.ts_code for r in results]
                from sqlalchemy import text
                name_query = text("SELECT ts_code, name FROM dim_stock WHERE ts_code = ANY(:codes)")
                name_rows = session.execute(name_query, {'codes': ts_codes}).fetchall()
                name_map = {row[0]: row[1] for row in name_rows}
                
                # 转换为字典列表
                recommendations = []
                for result in results:
                    rec = {
                        'code': result.ts_code.replace('.SH', '').replace('.SZ', '').replace('.BJ', ''),
                        'ts_code': result.ts_code,
                        'name': name_map.get(result.ts_code, ''),  # 从dim_stock获取名称
                        'trade_date': result.trade_date.strftime('%Y-%m-%d'),
                        'generated_at': result.generated_at.isoformat(),
                        'recommendation_type': result.recommendation_type,
                        'riskType': result.risk_type,
                        'score': float(result.final_score) if result.final_score else 0,
                        'rank_order': result.rank_order,
                        'strategy_signal': result.strategy_signal or {},
                        'buyRange': result.recommendation_details.get('buy_range') if result.recommendation_details else None,
                        'reason': result.recommendation_details.get('reason', '') if result.recommendation_details else '',
                        'advice': result.recommendation_details.get('advice', '') if result.recommendation_details else '',
                        'volumePricePattern': result.recommendation_details.get('volume_price_pattern', '') if result.recommendation_details else '',
                        'tags': result.recommendation_details.get('tags', []) if result.recommendation_details else [],
                        # 快照数据（用于降级）
                        'snapshot_price': float(result.snapshot_price) if result.snapshot_price else 0,
                        'snapshot_change_pct': float(result.snapshot_change_pct) if result.snapshot_change_pct else 0,
                        'snapshot_turnover_rate': float(result.snapshot_turnover_rate) if result.snapshot_turnover_rate else 0,
                        'snapshot_amount': float(result.snapshot_amount) if result.snapshot_amount else 0,
                    }
                    recommendations.append(rec)
                
                logger.info(f"✅ 读取推荐结果: {recommendation_type}, {len(recommendations)} 条")
                return recommendations
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"❌ 读取推荐结果失败: {e}", exc_info=True)
            return []
    
    def enrich_with_realtime_data(self, recommendations: List[Dict]) -> List[Dict]:
        """
        补充实时数据（仅对选中股票）
        
        Args:
            recommendations: 推荐列表
            
        Returns:
            list: 补充实时数据后的推荐列表
        """
        try:
            if not recommendations:
                return recommendations
            
            # 提取股票代码
            codes = [rec.get('code', '') for rec in recommendations if rec.get('code')]
            if not codes:
                return recommendations
            
            logger.info(f"🔄 为 {len(codes)} 只股票补充实时数据...")
            
            # 使用新的统一数据访问层进行实时补丁
            try:
                # 检查是否有新的 patch_realtime_to_recommendations 方法
                if hasattr(self.market_service, 'patch_realtime_to_recommendations'):
                    recommendations = self.market_service.patch_realtime_to_recommendations(recommendations)
                    logger.info(f"✅ 使用新架构实时数据补丁完成: {len(recommendations)} 只股票")
                    return recommendations
            except Exception as e:
                logger.warning(f"⚠️ 新架构实时补丁失败，使用旧方法: {e}")
            
            # 降级：使用旧方法（兼容性）
            realtime_df = self.market_service.get_realtime_stocks(
                force_refresh=True,
                use_warehouse=False
            )
            
            if realtime_df.empty:
                logger.warning("⚠️ 无法获取实时数据，使用快照数据")
                # 降级：使用快照数据
                for rec in recommendations:
                    rec['currentPrice'] = rec.get('snapshot_price', 0)
                    rec['changePct'] = rec.get('snapshot_change_pct', 0)
                    rec['turnoverRate'] = f"{rec.get('snapshot_turnover_rate', 0):.2f}%"
                    rec['amount'] = rec.get('snapshot_amount', 0)
                return recommendations
            
            # 创建代码映射
            realtime_map = {}
            code_field = 'code' if 'code' in realtime_df.columns else '代码'
            for _, row in realtime_df.iterrows():
                code = str(row.get(code_field, '')).strip().replace('sh', '').replace('sz', '').replace('bj', '').strip()
                if code:
                    realtime_map[code] = row
            
            # 更新推荐数据
            updated_count = 0
            for rec in recommendations:
                code = str(rec.get('code', '')).strip()
                realtime_info = realtime_map.get(code)
                
                if realtime_info:
                    rec['currentPrice'] = float(realtime_info.get('lastPrice', realtime_info.get('最新价', rec.get('snapshot_price', 0))))
                    rec['changePct'] = float(realtime_info.get('pct_chg', realtime_info.get('涨跌幅', rec.get('snapshot_change_pct', 0))))
                    turnover_rate = float(realtime_info.get('turnover_rate', realtime_info.get('换手率', rec.get('snapshot_turnover_rate', 0))))
                    rec['turnoverRate'] = f"{turnover_rate:.2f}%" if turnover_rate > 0 else "0.00%"
                    rec['amount'] = float(realtime_info.get('amount', realtime_info.get('成交额', rec.get('snapshot_amount', 0))))
                    # 补充名称
                    if not rec.get('name'):
                        rec['name'] = realtime_info.get('name', realtime_info.get('股票名称', ''))
                    updated_count += 1
                else:
                    # 降级：使用快照数据
                    rec['currentPrice'] = rec.get('snapshot_price', 0)
                    rec['changePct'] = rec.get('snapshot_change_pct', 0)
                    rec['turnoverRate'] = f"{rec.get('snapshot_turnover_rate', 0):.2f}%"
                    rec['amount'] = rec.get('snapshot_amount', 0)
            
            logger.info(f"✅ 实时数据补充完成: {updated_count}/{len(recommendations)} 只股票")
            
            # 补充缺失的股票名称（从dim_stock表获取）
            missing_names = [rec for rec in recommendations if not rec.get('name')]
            if missing_names:
                try:
                    from backend.services.data.postgres_warehouse import PostgresWarehouse
                    from sqlalchemy import text
                    pg = PostgresWarehouse()
                    if pg.warehouse_service:
                        session = pg.warehouse_service.get_session()
                        codes = [rec.get('code', '') for rec in missing_names]
                        # 转换代码格式
                        ts_codes = []
                        for code in codes:
                            code_str = str(code).strip()
                            if '.' in code_str:
                                ts_codes.append(code_str)
                            elif code_str.startswith('6'):
                                ts_codes.append(f"{code_str}.SH")
                            else:
                                ts_codes.append(f"{code_str}.SZ")
                        
                        query = text("SELECT ts_code, name FROM dim_stock WHERE ts_code = ANY(:codes)")
                        rows = session.execute(query, {'codes': ts_codes}).fetchall()
                        name_map = {}
                        for row in rows:
                            ts_code, name = row[0], row[1]
                            name_map[ts_code] = name
                            name_map[ts_code.split('.')[0]] = name
                        session.close()
                        
                        # 更新名称
                        for rec in recommendations:
                            if not rec.get('name'):
                                code = str(rec.get('code', '')).strip()
                                rec['name'] = name_map.get(code, '')
                        logger.info(f"📝 从dim_stock补充 {len(rows)} 只股票名称")
                except Exception as e:
                    logger.warning(f"⚠️ 从dim_stock补充名称失败: {e}")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"❌ 补充实时数据失败: {e}", exc_info=True)
            # 降级：使用快照数据
            for rec in recommendations:
                rec['currentPrice'] = rec.get('snapshot_price', 0)
                rec['changePct'] = rec.get('snapshot_change_pct', 0)
                rec['turnoverRate'] = f"{rec.get('snapshot_turnover_rate', 0):.2f}%"
                rec['amount'] = rec.get('snapshot_amount', 0)
            return recommendations
    
    def _convert_to_ts_code(self, code: str) -> Optional[str]:
        """将6位数字代码转换为ts_code格式"""
        code = str(code).strip().replace('sh', '').replace('sz', '').replace('bj', '').strip()
        if len(code) == 6:
            if code.startswith('6'):
                return f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                return f"{code}.SZ"
            elif code.startswith('8') or code.startswith('4'):
                return f"{code}.BJ"
        return None

