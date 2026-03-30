"""
LSTM-MAB 模型进化服务

提供：
1. 模型自动保存/加载
2. 预测记录追踪
3. 性能监控和告警
4. 自动重训练触发
"""

import os
import json
import re
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from sqlalchemy import text

from backend.services.lstm_mab import LSTMMABModel
from data_warehouse.service.warehouse_service import WarehouseService

logger = logging.getLogger(__name__)

# 模型配置
MODEL_DIR = os.environ.get('LSTM_MAB_MODEL_DIR', 'backend/models/lstm_mab')
MODEL_FILENAME = 'lstm_mab_latest.pkl'
MIN_PREDICTIONS_FOR_RETRAIN = 100  # 最少预测记录数触发重训练
ACCURACY_THRESHOLD = 0.5  # 命中率低于此值触发告警


@dataclass
class ModelHealth:
    """模型健康状态"""
    is_healthy: bool
    total_predictions: int
    recent_hit_rate: float
    recent_correlation: float
    last_training_date: Optional[date]
    recommendations: List[str]


class ModelEvolutionService:
    """
    LSTM-MAB 模型进化服务

    负责模型的全生命周期管理：
    - 训练后自动保存
    - 预测时自动记录
    - 定期性能评估
    - 智能重训练建议
    """

    def __init__(self):
        self.ws = WarehouseService()
        self._ensure_model_dir()

    def _ensure_model_dir(self):
        """确保模型目录存在"""
        os.makedirs(MODEL_DIR, exist_ok=True)

    def _validate_version(self, version: str) -> None:
        """验证版本号格式，防止注入攻击"""
        if not re.match(r'^v_\d{4}-\d{2}-\d{2}_\d{6}$', version):
            raise ValueError(f"Invalid version format: {version}")

    def get_model_path(self) -> str:
        """获取模型文件路径"""
        return os.path.join(MODEL_DIR, MODEL_FILENAME)

    def save_model(self, model: LSTMMABModel, metrics: Optional[Dict] = None) -> str:
        """
        保存模型并记录版本

        Returns:
            保存的模型路径
        """
        self._ensure_model_dir()

        # 保存主模型文件
        model_path = self.get_model_path()
        model.save(model_path)

        # 创建版本备份
        version = f"v_{date.today().isoformat()}_{datetime.now().strftime('%H%M%S')}"
        version_path = os.path.join(MODEL_DIR, f"lstm_mab_{version}.pkl")
        model.save(version_path)

        # 记录到数据库
        self._record_version(version, version_path, metrics)

        logger.info(f"💾 模型已保存: {model_path} (版本: {version})")
        return model_path

    def load_model(self) -> Optional[LSTMMABModel]:
        """
        加载最新模型

        Returns:
            加载的模型实例，如果失败返回 None
        """
        model_path = self.get_model_path()

        if not os.path.exists(model_path):
            logger.warning(f"⚠️ 模型文件不存在: {model_path}")
            return None

        try:
            model = LSTMMABModel()
            model.load(model_path)
            logger.info(f"✅ 模型已加载: {model_path}")
            return model
        except Exception as e:
            logger.error(f"❌ 加载模型失败: {e}")
            return None

    def _record_version(self, version: str, path: str, metrics: Optional[Dict] = None):
        """记录模型版本到数据库"""
        # 验证版本号格式
        self._validate_version(version)

        session = self.ws.get_session()
        try:
            query = text("""
                INSERT INTO lstm_mab_model_versions
                (version, trained_date, train_r2, val_r2, n_samples,
                 model_path, is_active, performance_summary)
                VALUES (:version, :date, :train_r2, :val_r2, :n_samples,
                        :path, TRUE, :summary)
                ON CONFLICT (version) DO UPDATE SET
                    model_path = EXCLUDED.model_path,
                    is_active = TRUE,
                    performance_summary = EXCLUDED.performance_summary,
                    train_r2 = EXCLUDED.train_r2,
                    val_r2 = EXCLUDED.val_r2,
                    n_samples = EXCLUDED.n_samples
            """)

            session.execute(query, {
                'version': version,
                'date': date.today(),
                'train_r2': metrics.get('train_r2') if metrics else None,
                'val_r2': metrics.get('val_r2') if metrics else None,
                'n_samples': metrics.get('n_samples') if metrics else None,
                'path': path,
                'summary': json.dumps(metrics) if metrics else None
            })

            # 将其他版本标记为非活跃
            session.execute(text("""
                UPDATE lstm_mab_model_versions
                SET is_active = FALSE
                WHERE version != :version
            """), {'version': version})

            session.commit()
            logger.info(f"📝 模型版本已记录: {version}")

        except Exception as e:
            logger.error(f"❌ 记录模型版本失败: {e}")
            session.rollback()
        finally:
            session.close()

    def record_prediction(
        self,
        ts_code: str,
        result,
        factor_values: Dict,
        emotion_cycle: str,
        model_version: Optional[str] = None
    ) -> int:
        """
        记录预测到数据库

        Returns:
            预测记录ID
        """
        session = self.ws.get_session()
        try:
            query = text("""
                INSERT INTO lstm_mab_predictions
                (prediction_date, ts_code, total_score, grade,
                 expected_return, confidence, factor_scores, factor_weights,
                 emotion_cycle, model_version)
                VALUES (:pred_date, :ts_code, :score, :grade,
                        :expected_return, :confidence, :factor_scores, :factor_weights,
                        :emotion_cycle, :version)
                RETURNING id
            """)

            result_db = session.execute(query, {
                'pred_date': date.today(),
                'ts_code': ts_code,
                'score': result.total_score,
                'grade': result.grade,
                'expected_return': result.expected_return,
                'confidence': result.confidence,
                'factor_scores': json.dumps(factor_values),
                'factor_weights': json.dumps(result.factor_weights),
                'emotion_cycle': emotion_cycle,
                'version': model_version or 'latest'
            })

            prediction_id = result_db.fetchone()[0]
            session.commit()

            return prediction_id

        except Exception as e:
            logger.error(f"❌ 记录预测失败: {e}")
            session.rollback()
            return -1
        finally:
            session.close()

    def get_model_health(self) -> ModelHealth:
        """检查模型健康状态"""
        session = self.ws.get_session()
        try:
            # 获取最近7天的性能数据
            query = text("""
                SELECT
                    COALESCE(SUM(total_predictions), 0) as total,
                    AVG(hit_rate) as avg_hit_rate,
                    AVG(prediction_correlation) as avg_corr
                FROM lstm_mab_performance
                WHERE date >= :start_date
            """)

            result = session.execute(query, {
                'start_date': date.today() - timedelta(days=7)
            }).fetchone()

            total_predictions = result[0] or 0
            recent_hit_rate = result[1] or 0
            recent_correlation = result[2] or 0

            # 获取最后训练日期
            version_query = text("""
                SELECT trained_date
                FROM lstm_mab_model_versions
                WHERE is_active = TRUE
                ORDER BY trained_date DESC
                LIMIT 1
            """)

            version_result = session.execute(version_query).fetchone()
            last_training_date = version_result[0] if version_result else None

            # 生成建议
            recommendations = []

            if total_predictions < MIN_PREDICTIONS_FOR_RETRAIN:
                recommendations.append(f"预测数据不足 ({total_predictions}/{MIN_PREDICTIONS_FOR_RETRAIN})，继续收集数据")

            if recent_hit_rate < ACCURACY_THRESHOLD and total_predictions > 0:
                recommendations.append(f"命中率过低 ({recent_hit_rate:.1%})，建议重新训练模型")

            if last_training_date and (date.today() - last_training_date).days > 30:
                recommendations.append(f"模型已过期 ({(date.today() - last_training_date).days} 天)，建议重新训练")

            is_healthy = (
                total_predictions >= MIN_PREDICTIONS_FOR_RETRAIN and
                recent_hit_rate >= ACCURACY_THRESHOLD and
                (not last_training_date or (date.today() - last_training_date).days <= 30)
            )

            return ModelHealth(
                is_healthy=is_healthy,
                total_predictions=total_predictions,
                recent_hit_rate=recent_hit_rate,
                recent_correlation=recent_correlation,
                last_training_date=last_training_date,
                recommendations=recommendations if recommendations else ["模型状态良好"]
            )

        except Exception as e:
            logger.error(f"❌ 检查模型健康状态失败: {e}")
            return ModelHealth(
                is_healthy=False,
                total_predictions=0,
                recent_hit_rate=0,
                recent_correlation=0,
                last_training_date=None,
                recommendations=[f"检查失败: {str(e)}"]
            )
        finally:
            session.close()

    def should_retrain(self) -> Tuple[bool, str]:
        """
        判断是否应该重新训练

        Returns:
            (是否应该训练, 原因)
        """
        health = self.get_model_health()

        if not health.is_healthy:
            return True, "; ".join(health.recommendations)

        return False, "模型状态良好，无需重训练"

    def get_performance_summary(self, days: int = 30) -> Dict:
        """获取性能汇总"""
        session = self.ws.get_session()
        try:
            # 整体性能趋势
            query = text("""
                SELECT
                    date,
                    total_predictions,
                    avg_actual_return,
                    hit_rate,
                    prediction_correlation,
                    rmse
                FROM lstm_mab_performance
                WHERE date >= :start_date
                ORDER BY date
            """)

            df = pd.read_sql(query, session.bind, params={
                'start_date': date.today() - timedelta(days=days)
            })

            if df.empty:
                return {"message": "暂无性能数据"}

            # 按情绪周期统计
            emotion_query = text("""
                SELECT
                    p.emotion_cycle,
                    COUNT(*) as count,
                    AVG(f.actual_return) as avg_return,
                    AVG(f.prediction_accuracy) as avg_accuracy
                FROM lstm_mab_predictions p
                JOIN lstm_mab_feedback f ON p.id = f.prediction_id
                WHERE p.prediction_date >= :start_date
                GROUP BY p.emotion_cycle
            """)

            emotion_df = pd.read_sql(emotion_query, session.bind, params={
                'start_date': date.today() - timedelta(days=days)
            })

            # 因子性能
            factor_query = text("""
                SELECT
                    factor_name,
                    AVG(avg_weight) as avg_weight,
                    AVG(hit_rate) as avg_hit_rate,
                    AVG(cumulative_reward) as total_reward
                FROM lstm_mab_factor_performance
                WHERE date >= :start_date
                GROUP BY factor_name
            """)

            factor_df = pd.read_sql(factor_query, session.bind, params={
                'start_date': date.today() - timedelta(days=days)
            })

            return {
                "period_days": days,
                "total_predictions": int(df['total_predictions'].sum()),
                "avg_daily_predictions": float(df['total_predictions'].mean()),
                "overall_hit_rate": float(df['hit_rate'].mean()),
                "avg_correlation": float(df['prediction_correlation'].mean()),
                "avg_rmse": float(df['rmse'].mean()),
                "trend": df.to_dict('records'),
                "by_emotion_cycle": emotion_df.to_dict('records') if not emotion_df.empty else [],
                "by_factor": factor_df.to_dict('records') if not factor_df.empty else []
            }

        except Exception as e:
            logger.error(f"❌ 获取性能汇总失败: {e}")
            return {"error": str(e)}
        finally:
            session.close()

    def get_evolution_report(self) -> Dict:
        """获取模型进化报告"""
        health = self.get_model_health()
        performance = self.get_performance_summary(days=30)
        should_retrain, retrain_reason = self.should_retrain()

        # 获取版本历史
        session = self.ws.get_session()
        try:
            version_query = text("""
                SELECT version, trained_date, train_r2, val_r2, n_samples, is_active
                FROM lstm_mab_model_versions
                ORDER BY trained_date DESC
                LIMIT 10
            """)

            versions = pd.read_sql(version_query, session.bind)

            return {
                "generated_at": datetime.now().isoformat(),
                "model_health": {
                    "is_healthy": health.is_healthy,
                    "total_predictions": health.total_predictions,
                    "recent_hit_rate": health.recent_hit_rate,
                    "recent_correlation": health.recent_correlation,
                    "last_training_date": health.last_training_date.isoformat() if health.last_training_date else None,
                    "recommendations": health.recommendations
                },
                "performance_summary": performance,
                "retrain_recommendation": {
                    "should_retrain": should_retrain,
                    "reason": retrain_reason
                },
                "version_history": versions.to_dict('records') if not versions.empty else []
            }

        except Exception as e:
            logger.error(f"❌ 获取进化报告失败: {e}")
            return {"error": str(e)}
        finally:
            session.close()


# 全局服务实例（单例模式）
_evolution_service: Optional[ModelEvolutionService] = None


def get_evolution_service() -> ModelEvolutionService:
    """获取进化服务实例"""
    global _evolution_service
    if _evolution_service is None:
        _evolution_service = ModelEvolutionService()
    return _evolution_service
