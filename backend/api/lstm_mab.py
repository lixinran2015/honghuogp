"""
LSTM-MAB 评分引擎 API
Phase 2: 机器学习评分 + 样本外测试

提供以下端点：
- POST /api/lstm-mab/train - 训练模型
- POST /api/lstm-mab/predict - 预测评分
- POST /api/lstm-mab/test - 样本外测试
- GET /api/lstm-mab/status - 获取模型状态
"""

from fastapi import APIRouter, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import date
import logging


class PredictRequest(BaseModel):
    ts_code: str
    factor_values: Dict[str, float]


from backend.services.lstm_mab import (
    LSTMMABModel,
    OutOfSampleTester,
    ThompsonSampling,
    UCB,
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


def _get_model() -> LSTMMABModel:
    """获取或创建模型实例"""
    global _model_instance
    if _model_instance is None:
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

        # 获取训练数据
        from data_warehouse.service.warehouse_service import WarehouseService
        ws = WarehouseService()
        session = ws.get_session()

        try:
            from sqlalchemy import text

            query = text("""
                SELECT ts_code, trade_date, open, high, low, close, vol as volume
                FROM fact_daily_price_qfq
                WHERE trade_date BETWEEN :start_date AND :end_date
                ORDER BY ts_code, trade_date
            """)

            import pandas as pd
            import numpy as np

            price_data = pd.read_sql(
                query,
                session.bind,
                params={
                    'start_date': start_date or '2023-01-01',
                    'end_date': end_date or date.today().isoformat(),
                }
            )

            if len(price_data) < 100:
                return {
                    'success': False,
                    'error': f'训练数据不足: {len(price_data)} < 100条',
                }

        finally:
            session.close()

        # 按股票分别生成序列，合并训练
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

        if not X_all:
            return {
                'success': False,
                'error': '没有足够的有效训练样本',
            }

        X_all = np.vstack(X_all)
        y_all = np.concatenate(y_all)

        # 训练模型
        metrics = model.lstm.train_from_arrays(X_all, y_all)

        # 更新状态
        _model_status['is_trained'] = True
        _model_status['training_date'] = date.today().isoformat()
        _model_status['performance'] = metrics

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
        session = ws.get_session()

        try:
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

        finally:
            session.close()

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
        session = ws.get_session()

        try:
            from sqlalchemy import text
            import pandas as pd

            query = text("""
                SELECT trade_date, open, high, low, close, vol as volume
                FROM fact_daily_price_qfq
                WHERE trade_date >= '2022-01-01'
                ORDER BY trade_date
            """)

            price_data = pd.read_sql(query, session.bind)

        finally:
            session.close()

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
