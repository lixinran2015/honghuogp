"""
LSTM-MAB 评分引擎 API
Phase 2: 机器学习评分 + 样本外测试
Phase 3: 模型自我进化系统

提供以下端点：
- POST /api/lstm-mab/train - 训练模型
- POST /api/lstm-mab/predict - 预测评分
- POST /api/lstm-mab/test - 样本外测试
- GET /api/lstm-mab/status - 获取模型状态
- POST /api/lstm-mab/feedback - 接收交易反馈
- GET /api/lstm-mab/evolution-report - 进化报告
- POST /api/lstm-mab/save - 保存模型
- GET /api/lstm-mab/performance - 性能监控
"""

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import date
import logging
import os


class PredictRequest(BaseModel):
    ts_code: str
    factor_values: Dict[str, float]


class FeedbackRequest(BaseModel):
    prediction_id: Optional[int] = None
    ts_code: str
    prediction_date: date
    actual_return: float
    holding_days: int = 5


from backend.services.lstm_mab import (
    LSTMMABModel,
    OutOfSampleTester,
    ThompsonSampling,
    UCB,
    get_evolution_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lstm-mab", tags=["lstm-mab"])

# 全局模型实例（生产环境应使用模型服务）
_model_instance: Optional[LSTMMABModel] = None
_model_status = {
    'is_trained': False,
    'training_date': None,
    'performance': {},
}

# 模型文件路径
MODEL_DIR = os.environ.get('LSTM_MAB_MODEL_DIR', 'backend/models/lstm_mab')
MODEL_FILENAME = 'lstm_mab_latest.pkl'


def _get_model() -> LSTMMABModel:
    """获取或创建模型实例"""
    global _model_instance
    if _model_instance is None:
        # 尝试加载已有模型
        model_path = os.path.join(MODEL_DIR, MODEL_FILENAME)
        if os.path.exists(model_path):
            try:
                _model_instance = LSTMMABModel()
                _model_instance.load(model_path)
                _model_status['is_trained'] = True
                logger.info(f"✅ 已加载保存的模型: {model_path}")
            except Exception as e:
                logger.warning(f"⚠️ 加载模型失败，创建新实例: {e}")
                _model_instance = LSTMMABModel()
        else:
            _model_instance = LSTMMABModel()
    return _model_instance


@router.post("/train")
async def train_model(
    background_tasks: BackgroundTasks,
    ts_code: Optional[str] = Query(None, description="训练用的股票代码，默认使用所有股票"),
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    target_horizon: int = Query(5, description="预测未来N日收益", ge=1, le=20),
) -> Dict:
    """
    训练LSTM-MAB模型

    该接口会：
    1. 获取历史价格数据
    2. 训练LSTM特征提取器
    3. 初始化MAB权重分配器

    示例:
    ```
    POST /api/lstm-mab/train?start_date=2023-01-01&end_date=2025-12-31
    ```
    """
    try:
        model = _get_model()
        logger.info(f"开始训练模型: start_date={start_date}, end_date={end_date}, horizon={target_horizon}")

        # 获取训练数据
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()

        try:
            with ws.get_session() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT ts_code, trade_date, open, high, low, close, vol as volume
                    FROM fact_daily_price_qfq
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    ORDER BY ts_code, trade_date
                """)

                import pandas as pd
                import numpy as np

                logger.info("正在查询数据库...")
                price_data = pd.read_sql(
                    query,
                    session.bind,
                    params={
                        'start_date': start_date or '2023-01-01',
                        'end_date': end_date or date.today().isoformat(),
                    }
                )
                logger.info(f"查询完成，获取 {len(price_data)} 条数据，涉及 {price_data['ts_code'].nunique() if len(price_data) > 0 else 0} 只股票")

                if len(price_data) < 100:
                    return {
                        'success': False,
                        'error': f'训练数据不足: {len(price_data)} < 100条',
                    }

        # 按股票分别生成序列，合并训练
        logger.info("开始生成训练序列...")
        X_all, y_all = [], []
        valid_stocks = 0
        for ts_code, group in price_data.groupby('ts_code'):
            group = group.sort_values('trade_date')
            try:
                X, y = model.lstm.prepare_sequences(group, target_horizon)
                if len(X) > 0:
                    X_all.append(X)
                    y_all.append(y)
                    valid_stocks += 1
            except Exception as e:
                logger.warning(f"生成 {ts_code} 序列失败: {e}")

        logger.info(f"序列生成完成: {valid_stocks} 只有效股票")

        if not X_all:
            return {
                'success': False,
                'error': '没有足够的有效训练样本',
            }

        X_all = np.vstack(X_all)
        y_all = np.concatenate(y_all)
        logger.info(f"合并数据: X shape={X_all.shape}, y shape={y_all.shape}")

        # 训练模型
        logger.info("开始训练 LSTM 模型...")
        metrics = model.lstm.train_from_arrays(X_all, y_all)
        logger.info(f"训练完成: {metrics}")

        # 更新状态
        _model_status['is_trained'] = True
        _model_status['training_date'] = date.today().isoformat()
        _model_status['performance'] = metrics

        # 自动保存模型
        try:
            evo_service = get_evolution_service()
            evo_service.save_model(model, metrics)
        except Exception as save_err:
            logger.warning(f"模型自动保存失败: {save_err}")

        return {
            'success': True,
            'message': '模型训练完成',
            'metrics': metrics,
        }

    except Exception as e:
        logger.error(f"模型训练失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"训练失败: {str(e)}")


@router.post("/predict")
async def predict_score(request: PredictRequest) -> Dict:
    """
    使用LSTM-MAB模型预测股票评分

    示例:
    ```
    POST /api/lstm-mab/predict
    {
        "ts_code": "000001.SZ",
        "factor_values": {"leader_position": 80, "technical": 75}
    }
    ```
    """
    try:
        model = _get_model()
        evo_service = get_evolution_service()

        if not _model_status['is_trained']:
            return {
                'success': False,
                'error': '模型未训练，请先调用/train接口',
            }

        # 预测
        result = model.predict(
            ts_code=request.ts_code,
            factor_values=request.factor_values,
        )

        # 记录预测到数据库
        emotion_cycle = model.mab.current_emotion
        prediction_id = evo_service.record_prediction(
            ts_code=request.ts_code,
            result=result,
            factor_values=request.factor_values,
            emotion_cycle=emotion_cycle
        )

        return {
            'success': True,
            'data': {
                'ts_code': result.ts_code,
                'total_score': result.total_score,
                'grade': result.grade,
                'factor_scores': result.factor_scores,
                'factor_weights': result.factor_weights,
                'expected_return': result.expected_return,
                'confidence': result.confidence,
            },
            'prediction_id': prediction_id,
            'emotion_cycle': emotion_cycle,
        }

    except Exception as e:
        logger.error(f"预测失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}")


@router.post("/test")
async def out_of_sample_test(
    start_date: Optional[date] = Query(None, description="测试开始日期"),
    end_date: Optional[date] = Query(None, description="测试结束日期"),
    train_ratio: float = Query(0.6, description="训练集比例", ge=0.5, le=0.8),
    val_ratio: float = Query(0.2, description="验证集比例", ge=0.1, le=0.3),
    test_ratio: float = Query(0.2, description="测试集比例", ge=0.1, le=0.3),
) -> Dict:
    """
    执行样本外测试

    验证模型是否存在过拟合：
    - 测试Sharpe / 训练Sharpe >= 80%
    - 胜率差异 < 5%
    - 最大回撤 < 15%

    示例:
    ```
    POST /api/lstm-mab/test?start_date=2023-01-01&end_date=2025-12-31
    ```
    """
    try:
        model = _get_model()

        if not _model_status['is_trained']:
            return {
                'success': False,
                'error': '模型未训练',
            }

        # 获取数据
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()

        try:
            with ws.get_session() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT trade_date, open, high, low, close, vol as volume
                    FROM fact_daily_price_qfq
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    ORDER BY trade_date
                """)

                import pandas as pd
                price_data = pd.read_sql(
                    query,
                    session.bind,
                    params={
                        'start_date': start_date or '2023-01-01',
                        'end_date': end_date or date.today().isoformat(),
                    }
                )

        # 执行样本外测试
        tester = OutOfSampleTester(
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
        )

        result = tester.test(model, price_data)

        return {
            'success': True,
            'result': result.to_dict(),
            'summary': {
                'pass_criteria': result.pass_criteria,
                'sharpe_ratio': round(result.sharpe_ratio, 4),
                'recommendation': '模型可以部署' if result.pass_criteria else '存在过拟合风险，建议优化',
            },
        }

    except Exception as e:
        logger.error(f"样本外测试失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")


@router.post("/rolling-test")
async def rolling_window_test(
    window_size: int = Query(252, description="窗口大小（交易日）", ge=100),
    step_size: int = Query(20, description="滚动步长", ge=5),
) -> Dict:
    """
    滚动窗口测试

    模拟实际交易中的模型更新过程
    """
    try:
        model = _get_model()

        # 获取数据
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()

        try:
            with ws.get_session() as session:
                from sqlalchemy import text
                import pandas as pd

                query = text("""
                    SELECT trade_date, open, high, low, close, vol as volume
                    FROM fact_daily_price_qfq
                    WHERE trade_date >= '2022-01-01'
                    ORDER BY trade_date
                """)

                price_data = pd.read_sql(query, session.bind)

        # 执行滚动测试
        tester = OutOfSampleTester()
        results = tester.rolling_window_test(model, price_data, window_size, step_size)

        # 统计结果
        pass_count = sum(1 for r in results if r.pass_criteria)

        return {
            'success': True,
            'summary': {
                'total_windows': len(results),
                'pass_count': pass_count,
                'pass_rate': round(pass_count / len(results), 4) if results else 0,
                'avg_sharpe_ratio': round(np.mean([r.sharpe_ratio for r in results]), 4) if results else 0,
            },
            'details': [r.to_dict() for r in results[:10]],  # 只返回前10个
        }

    except Exception as e:
        logger.error(f"滚动测试失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")


@router.get("/status")
async def get_model_status() -> Dict:
    """获取LSTM-MAB模型状态"""
    model = _get_model()

    return {
        'success': True,
        'model_status': _model_status,
        'model_stats': model.get_model_stats() if _model_status['is_trained'] else None,
    }


@router.post("/update-emotion")
async def update_emotion_cycle(
    emotion_cycle: str = Query(..., description="情绪周期", enum=["高涨期", "主升期", "震荡期", "分歧期", "低迷期", "退潮期", "冰点期"]),
) -> Dict:
    """
    更新情绪周期

    情绪周期会影响基础权重配置：
    - 高涨期：龙头地位权重提升至40%
    - 冰点期：技术形态权重提升至35%
    """
    try:
        model = _get_model()
        model.update_emotion_cycle(emotion_cycle)

        return {
            'success': True,
            'message': f'情绪周期已更新为: {emotion_cycle}',
            'current_weights': model.mab.EMOTION_WEIGHTS.get(emotion_cycle, {}),
        }

    except Exception as e:
        logger.error(f"更新情绪周期失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


# ============== Phase 3: 模型自我进化系统 ==============

@router.post("/feedback")
async def receive_feedback(request: FeedbackRequest) -> Dict:
    """
    接收交易反馈，更新MAB权重

    示例:
    ```
    POST /api/lstm-mab/feedback
    {
        "ts_code": "000001.SZ",
        "prediction_date": "2025-03-20",
        "actual_return": 0.05,
        "holding_days": 5
    }
    ```
    """
    try:
        model = _get_model()

        if not _model_status['is_trained']:
            return {
                'success': False,
                'error': '模型未训练',
            }

        # 更新每个因子的性能
        for factor_name in model.factor_names:
            model.update_factor_performance(factor_name, request.actual_return)

        # 自动保存更新后的模型
        try:
            evo_service = get_evolution_service()
            evo_service.save_model(model)
        except Exception as save_err:
            logger.warning(f"反馈后自动保存失败: {save_err}")

        return {
            'success': True,
            'message': '反馈已接收，模型已更新',
            'updated_factors': model.factor_names,
            'actual_return': request.actual_return,
        }

    except Exception as e:
        logger.error(f"接收反馈失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"反馈处理失败: {str(e)}")


@router.post("/save")
async def save_model() -> Dict:
    """
    手动保存当前模型状态

    保存路径: backend/models/lstm_mab/lstm_mab_latest.pkl
    """
    try:
        model = _get_model()
        evo_service = get_evolution_service()

        path = evo_service.save_model(model, _model_status.get('performance'))

        return {
            'success': True,
            'message': '模型已保存',
            'path': path,
        }

    except Exception as e:
        logger.error(f"保存模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")


@router.post("/load")
async def load_model() -> Dict:
    """
    加载保存的模型
    """
    try:
        global _model_instance, _model_status

        evo_service = get_evolution_service()
        loaded_model = evo_service.load_model()

        if loaded_model is None:
            return {
                'success': False,
                'error': '没有找到保存的模型文件',
            }

        _model_instance = loaded_model
        _model_status['is_trained'] = True

        # 获取模型统计信息
        stats = loaded_model.get_model_stats()

        return {
            'success': True,
            'message': '模型已加载',
            'model_stats': stats,
        }

    except Exception as e:
        logger.error(f"加载模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"加载失败: {str(e)}")


@router.get("/evolution-report")
async def get_evolution_report() -> Dict:
    """
    获取模型进化报告

    包含：
    - 模型健康状态
    - 性能汇总
    - 重训练建议
    - 版本历史
    """
    try:
        evo_service = get_evolution_service()
        report = evo_service.get_evolution_report()

        return {
            'success': True,
            'report': report,
        }

    except Exception as e:
        logger.error(f"获取进化报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取报告失败: {str(e)}")


@router.get("/performance")
async def get_performance(
    days: int = Query(30, description="统计天数", ge=7, le=365),
) -> Dict:
    """
    获取模型性能监控数据
    """
    try:
        evo_service = get_evolution_service()
        summary = evo_service.get_performance_summary(days=days)

        return {
            'success': True,
            'summary': summary,
        }

    except Exception as e:
        logger.error(f"获取性能数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取性能数据失败: {str(e)}")


@router.get("/health")
async def get_model_health() -> Dict:
    """
    获取模型健康状态
    """
    try:
        evo_service = get_evolution_service()
        health = evo_service.get_model_health()
        should_retrain, reason = evo_service.should_retrain()

        return {
            'success': True,
            'health': {
                'is_healthy': health.is_healthy,
                'total_predictions': health.total_predictions,
                'recent_hit_rate': health.recent_hit_rate,
                'recent_correlation': health.recent_correlation,
                'last_training_date': health.last_training_date.isoformat() if health.last_training_date else None,
                'recommendations': health.recommendations,
            },
            'should_retrain': should_retrain,
            'retrain_reason': reason,
        }

    except Exception as e:
        logger.error(f"获取健康状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取健康状态失败: {str(e)}")


@router.post("/retrain-check")
async def check_retrain_needed() -> Dict:
    """
    检查是否需要重训练，并返回建议
    """
    try:
        evo_service = get_evolution_service()
        should_retrain, reason = evo_service.should_retrain()

        return {
            'success': True,
            'should_retrain': should_retrain,
            'reason': reason,
            'current_date': date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"检查重训练失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")
