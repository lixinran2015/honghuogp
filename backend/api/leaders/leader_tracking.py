"""
龙头跟踪池 API
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query, HTTPException

from backend.services.leader_tracking.leader_tracking_pool_service import LeaderTrackingPoolService
from backend.services.leader_tracking.leader_recent_days_service import LeaderRecentDaysService
from backend.services.lstm_mab import LSTMMABModel
from backend.services.data.postgres_warehouse import PostgresWarehouse

router = APIRouter(prefix="/api/leader-tracking", tags=["leader-tracking"])
logger = logging.getLogger(__name__)

# 模型缓存
_model_instance: Optional[LSTMMABModel] = None

# 数据仓库实例
_warehouse_instance: Optional[PostgresWarehouse] = None


def _get_model() -> Optional[LSTMMABModel]:
    """获取或创建模型实例（如果已训练）"""
    global _model_instance
    if _model_instance is None:
        import os
        model_path = os.environ.get(
            'LSTM_MAB_MODEL_PATH',
            'backend/models/lstm_mab/lstm_mab_latest.pkl'
        )
        if os.path.exists(model_path):
            try:
                _model_instance = LSTMMABModel()
                _model_instance.load(model_path)
            except Exception as e:
                logger.error(f"加载LSTM-MAB模型失败: {e}", exc_info=True)
                _model_instance = None
    return _model_instance


def _get_warehouse() -> Optional[PostgresWarehouse]:
    """获取或创建数据仓库实例"""
    global _warehouse_instance
    if _warehouse_instance is None:
        try:
            _warehouse_instance = PostgresWarehouse()
        except Exception as e:
            logger.warning(f"初始化数据仓库失败: {e}")
            _warehouse_instance = None
    return _warehouse_instance


def _get_price_history(ts_code: str, limit: int = 40) -> Optional[Any]:
    """
    从本地数据仓库获取股票历史价格数据

    Args:
        ts_code: 股票代码 (如 '000001.SZ')
        limit: 获取数据天数

    Returns:
        DataFrame with columns [open, high, low, close, volume] or None
    """
    try:
        warehouse = _get_warehouse()
        if warehouse is None:
            logger.warning("数据仓库未初始化")
            return None

        # 计算日期范围
        # TODO: 使用交易日历而非自然日，避免节假日导致数据不足
        end_date = datetime.now()
        # 多取一些天数，确保有足够数据计算指标
        # 注意：如果遇上长假，可能仍不足20个交易日，建议改为交易日历计算
        start_date = end_date - timedelta(days=limit * 2)

        # 使用批量查询方法（传入单只股票）
        df = warehouse.load_history_kline_batch(
            codes=[ts_code],
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d')
        )

        if df is None or df.empty:
            logger.debug(f"未找到 {ts_code} 的历史K线数据")
            return None

        # 确保必要的列存在
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                logger.warning(f"K线数据缺少必要列: {col}")
                return None

        # 按日期排序，取最近 limit 天
        df = df.sort_values('trade_date').tail(limit).reset_index(drop=True)

        return df[required_cols]
    except Exception as e:
        logger.warning(f"获取 {ts_code} 历史价格失败: {e}")
        return None


def _calculate_factor_values(stock_data: Dict[str, Any]) -> Dict[str, float]:
    """
    根据股票数据计算 LSTM-MAB 需要的因子值

    因子:
    - leader_position: 龙头地位 (0-100)
    - technical: 技术形态 (0-100)
    """
    factors = {}

    # 龙头地位因子计算
    leader_score = 0.0

    # 连板高度权重 (40分)
    continuous_limit = stock_data.get('continuous_limit') or 0
    if continuous_limit >= 5:
        leader_score += 40
    elif continuous_limit >= 3:
        leader_score += 30
    elif continuous_limit >= 2:
        leader_score += 20
    elif continuous_limit >= 1:
        leader_score += 10

    # 空间龙头/刚启动类型权重 (30分)
    is_space = stock_data.get('is_space', False)
    is_new = stock_data.get('is_new', False)
    if is_space and is_new:
        leader_score += 30
    elif is_space:
        leader_score += 25
    elif is_new:
        leader_score += 20

    # 板块数量权重 (20分) - 涉及板块越多影响力越大
    sectors = stock_data.get('sectors') or []
    sector_count = len(sectors)
    if sector_count >= 3:
        leader_score += 20
    elif sector_count >= 2:
        leader_score += 15
    elif sector_count >= 1:
        leader_score += 10

    # 在池时间权重 (10分) - 持续跟踪时间越长越稳定
    first_date = stock_data.get('first_space_date') or stock_data.get('first_new_date')
    if first_date:
        leader_score += 10

    factors['leader_position'] = min(100.0, leader_score)

    # 技术形态因子计算
    technical_score = 50.0  # 基础分

    # 可以从 stats 中获取技术数据进行调整
    stats = stock_data.get('stats', {})

    # 20日涨幅调整
    pct20d = stats.get('pct20d')
    if pct20d is not None:
        if pct20d >= 50:
            technical_score += 20
        elif pct20d >= 30:
            technical_score += 15
        elif pct20d >= 20:
            technical_score += 10
        elif pct20d >= 10:
            technical_score += 5
        elif pct20d < -10:
            technical_score -= 15
        elif pct20d < -5:
            technical_score -= 10

    # 基于退潮/强势状态调整
    retreat_label = stats.get('retreat_label', '')
    if retreat_label == '强势':
        technical_score += 15
    elif retreat_label == '震荡':
        technical_score += 5
    elif retreat_label == '退潮风险':
        technical_score -= 20

    # 基于位置调整
    position_tag = stats.get('positionTag', '')
    if '强于20日线' in position_tag:
        technical_score += 10
    elif '跌破20日线' in position_tag:
        technical_score -= 15

    factors['technical'] = max(0.0, min(100.0, technical_score))

    return factors


def _score_stocks(stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对股票列表进行 LSTM-MAB 评分"""
    model = _get_model()
    if model is None:
        # 模型未训练，返回原始数据
        return stocks

    scored_stocks = []
    for stock in stocks:
        try:
            # 计算因子值
            factor_values = _calculate_factor_values(stock)

            # 获取历史价格数据用于 LSTM 预测
            price_history = _get_price_history(stock['ts_code'], limit=40)

            # 调用模型预测
            result = model.predict(
                ts_code=stock['ts_code'],
                factor_values=factor_values,
                price_history=price_history
            )

            # 合并评分结果到股票数据
            scored_stock = {
                **stock,
                'lstm_mab_score': {
                    'total_score': result.total_score,
                    'grade': result.grade,
                    'factor_scores': result.factor_scores,
                    'factor_weights': result.factor_weights,
                    'expected_return': round(result.expected_return * 100, 2),  # 转为百分比
                    'confidence': round(result.confidence * 100, 1),  # 转为百分比
                    'factor_values': factor_values,
                }
            }
            scored_stocks.append(scored_stock)
        except Exception as e:
            # 评分失败，保留原始数据
            scored_stock = {
                **stock,
                'lstm_mab_score': None,
                'score_error': str(e)
            }
            scored_stocks.append(scored_stock)

    # 按评分排序
    scored_stocks.sort(
        key=lambda x: x.get('lstm_mab_score', {}).get('total_score', 0) if x.get('lstm_mab_score') else 0,
        reverse=True
    )

    return scored_stocks


@router.get("/pool")
async def get_leader_tracking_pool(
    trade_date: Optional[str] = Query(
        None,
        description="交易日，YYYY-MM-DD；不传则取最新交易日",
    ),
    min_score: int = Query(60, description="启动得分阈值"),
    stage: str = Query("confirmed", description="阶段过滤：confirmed / started"),
    stable_window_id: str = Query("rolling_30d_v2", description="快照窗口：用于判断空间/刚启动角色的稳定性"),
    bootstrap_days: int = Query(180, description="池为空时的历史补齐天数（只用于首次初始化）"),
    do_bootstrap: bool = Query(True, description="是否在池为空时自动 bootstrap"),
    force_sync: bool = Query(False, description="是否强制重新同步当天（会跳过 sync log）"),
    catch_up_window_trading_days: int = Query(
        30,
        ge=0,
        le=120,
        description="补同步：向前查看多少个交易日内的 sync 缺口（0 表示不补历史，仅同步 end 日）",
    ),
    catch_up_max_syncs: int = Query(
        30,
        ge=0,
        le=30,
        description="补同步：单次请求最多补跑几个缺失交易日（默认与窗口一致，一次补满近 30 个交易日缺口）",
    ),
    replay_sync_days: int = Query(
        0,
        ge=0,
        le=60,
        description="为 >0 时先删除最近 n 个交易日的 sync_log 再补跑（入池规则变更或需重灌历史时用）",
    ),
    with_scores: bool = Query(
        False,
        description="是否使用 LSTM-MAB 模型进行智能评分",
    ),
) -> dict:
    svc = LeaderTrackingPoolService()
    # 简单参数校验
    if stage not in ("confirmed", "started"):
        raise HTTPException(status_code=400, detail="stage 仅支持 confirmed / started")

    td = None
    if trade_date:
        try:
            td = date.fromisoformat(trade_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

    result = svc.get_pool(
        trade_date=td,
        min_score=min_score,
        stage_filter=stage,
        stable_window_id=stable_window_id,
        bootstrap_days=bootstrap_days,
        do_bootstrap=do_bootstrap,
        force_sync=force_sync,
        catch_up_window_trading_days=catch_up_window_trading_days,
        catch_up_max_syncs=catch_up_max_syncs,
        replay_sync_days=replay_sync_days,
    )

    # 如果请求了评分，调用 LSTM-MAB 模型
    if with_scores and result.get('success') and result.get('pool'):
        from backend.services.lstm_mab import get_evolution_service

        pool = result['pool']
        model = _get_model()

        if model is None:
            result['score_warning'] = 'LSTM-MAB 模型未训练或加载失败，返回未评分数据'
        else:
            # 对每只股票进行评分
            scored_stocks = []
            for stock in pool:
                try:
                    factor_values = _calculate_factor_values(stock)

                    # 获取历史价格数据用于 LSTM 预测
                    price_history = _get_price_history(stock['ts_code'], limit=40)

                    prediction = model.predict(
                        ts_code=stock['ts_code'],
                        factor_values=factor_values,
                        price_history=price_history,
                        trade_date=result.get('trade_date')
                    )

                    # 记录预测到数据库（用于模型进化）
                    try:
                        evo_service = get_evolution_service()
                        emotion_cycle = model.mab.current_emotion
                        prediction_id = evo_service.record_prediction(
                            ts_code=stock['ts_code'],
                            result=prediction,
                            factor_values=factor_values,
                            emotion_cycle=emotion_cycle
                        )
                    except Exception:
                        prediction_id = None

                    scored_stock = {
                        **stock,
                        'lstm_mab_score': {
                            'prediction_id': prediction_id,
                            'total_score': round(prediction.total_score, 2),
                            'grade': prediction.grade,
                            'expected_return': round(prediction.expected_return * 100, 2),  # 转为百分比
                            'confidence': round(prediction.confidence * 100, 1),  # 转为百分比
                            'factor_scores': prediction.factor_scores,
                            'factor_weights': prediction.factor_weights,
                            'factor_values': factor_values,
                        }
                    }
                    scored_stocks.append(scored_stock)
                except Exception as e:
                    scored_stocks.append({
                        **stock,
                        'lstm_mab_score': None,
                        'score_error': str(e)
                    })

            # 按总分排序
            scored_stocks.sort(
                key=lambda x: x.get('lstm_mab_score', {}).get('total_score', 0)
                if x.get('lstm_mab_score') else 0,
                reverse=True
            )

            result['pool'] = scored_stocks
            result['model_scored'] = True

    return result


@router.get("/recent-days")
async def get_leader_tracking_recent_days(
    end_date: Optional[str] = Query(
        None,
        description="截止交易日 YYYY-MM-DD；不传则取最近交易日",
    ),
    trading_days: int = Query(10, ge=1, le=60, description="向前取几个交易日（含 end_date）"),
    min_score: int = Query(60, description="启动得分阈值"),
    stage: str = Query("confirmed", description="阶段过滤：confirmed / started"),
    stable_window_id: str = Query("rolling_30d_v2", description="龙头快照窗口"),
    include_status: bool = Query(True, description="是否计算当日强势/震荡/退潮风险（与龙头跟踪页一致）"),
) -> dict:
    if stage not in ("confirmed", "started"):
        raise HTTPException(status_code=400, detail="stage 仅支持 confirmed / started")

    ed: Optional[date] = None
    if end_date:
        try:
            ed = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="end_date 格式错误，应为 YYYY-MM-DD")

    svc = LeaderRecentDaysService()
    return svc.get_recent_days(
        end_date=ed,
        trading_days=trading_days,
        min_score=min_score,
        stage_filter=stage,
        stable_window_id=stable_window_id,
        include_status=include_status,
    )


@router.get("/top-scored")
async def get_top_scored_leaders(
    top_n: int = Query(10, ge=1, le=50, description="返回前N名"),
    min_score: int = Query(60, description="启动得分阈值"),
    stage: str = Query("confirmed", description="阶段过滤：confirmed / started"),
    trade_date: Optional[str] = Query(None, description="交易日，YYYY-MM-DD；不传则取最新交易日"),
) -> dict:
    """
    获取 LSTM-MAB 智能评分最高的龙头股票

    返回按 total_score 排序的前 N 只股票，包含：
    - 基础龙头信息（代码、名称、类型、板块等）
    - LSTM-MAB 评分详情（总分、等级、预期收益、置信度等）
    - 因子得分和权重

    使用示例：
    GET /api/leader-tracking/top-scored?top_n=10
    """
    if stage not in ("confirmed", "started"):
        raise HTTPException(status_code=400, detail="stage 仅支持 confirmed / started")

    td = None
    if trade_date:
        try:
            td = date.fromisoformat(trade_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="trade_date 格式错误，应为 YYYY-MM-DD")

    # 获取池数据
    svc = LeaderTrackingPoolService()
    result = svc.get_pool(
        trade_date=td,
        min_score=min_score,
        stage_filter=stage,
        stable_window_id='rolling_30d_v2',
        bootstrap_days=180,
        do_bootstrap=True,
        force_sync=False,
        catch_up_window_trading_days=30,
        catch_up_max_syncs=30,
        replay_sync_days=0,
    )

    if not result.get('success') or not result.get('pool'):
        return {
            'success': False,
            'error': '获取龙头池失败或池为空',
            'top_stocks': []
        }

    pool = result['pool']
    model = _get_model()

    if model is None:
        return {
            'success': True,
            'warning': 'LSTM-MAB 模型未训练或加载失败，返回未排序数据',
            'model_available': False,
            'trade_date': result.get('trade_date'),
            'top_stocks': pool[:top_n]
        }

    # 对每只股票进行评分
    from backend.services.lstm_mab import get_evolution_service

    scored_stocks = []
    for stock in pool:
        try:
            factor_values = _calculate_factor_values(stock)

            # 获取历史价格数据用于 LSTM 预测
            price_history = _get_price_history(stock['ts_code'], limit=40)

            prediction = model.predict(
                ts_code=stock['ts_code'],
                factor_values=factor_values,
                price_history=price_history,
                trade_date=result.get('trade_date')
            )

            # 记录预测到数据库（用于模型进化）
            try:
                evo_service = get_evolution_service()
                emotion_cycle = model.mab.current_emotion
                prediction_id = evo_service.record_prediction(
                    ts_code=stock['ts_code'],
                    result=prediction,
                    factor_values=factor_values,
                    emotion_cycle=emotion_cycle
                )
            except Exception:
                prediction_id = None

            scored_stock = {
                **stock,
                'lstm_mab_score': {
                    'prediction_id': prediction_id,
                    'total_score': round(prediction.total_score, 2),
                    'grade': prediction.grade,
                    'expected_return': round(prediction.expected_return * 100, 2),
                    'confidence': round(prediction.confidence * 100, 1),
                    'factor_scores': prediction.factor_scores,
                    'factor_weights': prediction.factor_weights,
                    'factor_values': factor_values,
                }
            }
            scored_stocks.append(scored_stock)
        except Exception as e:
            # 评分失败，记录详细错误日志并使用默认低分
            logger.error(f"评分失败 {stock.get('ts_code', 'unknown')}: {e}", exc_info=True)
            scored_stocks.append({
                **stock,
                'lstm_mab_score': {
                    'total_score': 0,
                    'grade': 'D',
                    'expected_return': 0,
                    'confidence': 0,
                    'error': str(e)
                }
            })

    # 按总分排序
    scored_stocks.sort(
        key=lambda x: x.get('lstm_mab_score', {}).get('total_score', 0),
        reverse=True
    )

    return {
        'success': True,
        'model_available': True,
        'trade_date': result.get('trade_date'),
        'emotion_cycle': model.mab.current_emotion,
        'total_count': len(scored_stocks),
        'top_stocks': scored_stocks[:top_n]
    }
