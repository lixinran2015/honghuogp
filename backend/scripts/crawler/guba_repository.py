"""
股吧人气榜数据持久化
"""
import logging
from datetime import date, datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


def save_popularity_ranks(data: List[Dict]) -> bool:
    """
    保存人气榜数据到数据库。
    按 ts_code 去重，先删今日旧记录再插入。
    """
    if not data:
        logger.warning("没有数据需要保存")
        return False

    try:
        from data_warehouse.service.warehouse_service import WarehouseService
        from data_warehouse.models.guba_popularity import FactGubaPopularityRank, FactGubaRankHistory
        from sqlalchemy.exc import IntegrityError
    except ImportError as e:
        logger.error(f"导入数据库模块失败: {e}")
        return False

    data = _deduplicate_by_ts_code(data)
    if not data:
        logger.warning("去重后无有效数据")
        return False

    warehouse = WarehouseService()
    session = warehouse.get_session()
    crawl_date = date.today()
    crawl_time = datetime.now()

    try:
        deleted = session.query(FactGubaPopularityRank).filter(
            FactGubaPopularityRank.crawl_date == crawl_date
        ).delete()
        if deleted > 0:
            logger.info(f"🗑️ 已删除今日旧记录 {deleted} 条")

        saved, history_new, history_updated, failed = 0, 0, 0, 0
        for item in data:
            try:
                if not item.get('ts_code') or not item.get('stock_name'):
                    failed += 1
                    continue

                record = FactGubaPopularityRank(
                    crawl_date=crawl_date,
                    crawl_time=crawl_time,
                    rank_position=item['rank_position'],
                    rank_change=item.get('rank_change', 0),
                    ts_code=item['ts_code'],
                    stock_name=item['stock_name'],
                    latest_price=item.get('latest_price'),
                    change_amount=item.get('change_amount'),
                    change_pct=item.get('change_pct'),
                    new_fans=item.get('new_fans'),
                    loyal_fans=item.get('loyal_fans'),
                )
                session.add(record)
                saved += 1

                history_new_delta, history_updated_delta = _upsert_history(
                    session, item, crawl_date
                )
                history_new += history_new_delta
                history_updated += history_updated_delta

            except IntegrityError as e:
                logger.warning(f"唯一约束冲突 {item.get('ts_code')}: {e}")
                session.rollback()
                raise
            except Exception as e:
                logger.warning(f"保存失败 {item.get('ts_code')}: {e}")
                failed += 1

        if saved == 0 and failed > 0:
            session.rollback()
            return False

        session.commit()
        logger.info(f"✅ 保存成功: 主表 {saved} 条, 历史表 +{history_new} 更新{history_updated}, 失败 {failed}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"保存失败: {e}", exc_info=True)
        raise
    finally:
        session.close()


def _deduplicate_by_ts_code(data: List[Dict]) -> List[Dict]:
    """按 ts_code 去重，保留最后一条"""
    seen = {item['ts_code']: item for item in data if item.get('ts_code')}
    result = list(seen.values())
    if len(result) < len(data):
        logger.info(f"去重: {len(data)} → {len(result)} 条")
    return result


def _upsert_history(session, item: Dict, trade_date: date) -> tuple:
    """更新或插入历史表，返回 (新增数, 更新数)"""
    from data_warehouse.models.guba_popularity import FactGubaRankHistory
    with session.no_autoflush:
        existing = session.query(FactGubaRankHistory).filter(
            FactGubaRankHistory.ts_code == item['ts_code'],
            FactGubaRankHistory.trade_date == trade_date,
        ).first()

    if not existing:
        session.add(FactGubaRankHistory(
            ts_code=item['ts_code'],
            trade_date=trade_date,
            rank_position=item['rank_position'],
        ))
        return (1, 0)
    if existing.rank_position != item['rank_position']:
        existing.rank_position = item['rank_position']
        return (0, 1)
    return (0, 0)
