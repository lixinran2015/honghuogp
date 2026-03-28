"""
LSTM 特征提取器（简化版）

使用 MLP + 时序窗口 模拟 LSTM 功能
如果系统安装了 TensorFlow/PyTorch，可替换为完整 LSTM 实现
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import date
import pandas as pd
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
import joblib
import os

logger = logging.getLogger(__name__)


@dataclass
class LSTMPrediction:
    """LSTM预测结果"""
    expected_return: float  # 预期收益
    uncertainty: float      # 不确定性（标准差）
    hidden_state: np.ndarray  # 隐藏状态向量


class LSTMFeatureExtractor:
    """
    LSTM特征提取器

    使用方式：
        extractor = LSTMFeatureExtractor(
            sequence_length=20,  # 使用20天历史
            hidden_units=128,
        )

        # 训练
        extractor.train(training_data)

        # 预测
        prediction = extractor.predict(sequence)
    """

    def __init__(
        self,
        sequence_length: int = 20,
        feature_dim: int = 5,  # O, H, L, C, V
        hidden_units: int = 128,
        dropout_rate: float = 0.3,
        model_path: Optional[str] = None,
    ):
        self.sequence_length = sequence_length
        self.feature_dim = feature_dim
        self.hidden_units = hidden_units
        self.dropout_rate = dropout_rate
        self.model_path = model_path or "backend/models/lstm_features.pkl"

        # 初始化模型
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def _build_model(self) -> MLPRegressor:
        """构建MLP模型（简化版LSTM）"""
        # 使用2层隐藏层模拟LSTM效果
        return MLPRegressor(
            hidden_layer_sizes=(self.hidden_units, self.hidden_units // 2),
            activation='tanh',
            solver='adam',
            alpha=0.001,  # L2正则化
            batch_size='auto',
            learning_rate='adaptive',
            max_iter=500,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=10,
            verbose=False,
        )

    def prepare_sequences(
        self,
        price_data: pd.DataFrame,
        target_horizon: int = 5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        准备时序序列数据

        Args:
            price_data: DataFrame with columns [open, high, low, close, volume]
            target_horizon: 预测未来N日收益

        Returns:
            X: 输入序列 (samples, sequence_length * features)
            y: 目标收益 (samples,)
        """
        # 计算技术指标作为特征
        df = price_data.copy()

        # 基础价格特征
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

        # 波动率特征
        df['volatility'] = df['returns'].rolling(window=20).std()

        # 移动平均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma_ratio'] = df['ma5'] / df['ma20']

        # 成交量特征
        df['volume_ma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 价格位置
        df['price_position'] = (df['close'] - df['low'].rolling(20).min()) / \
                               (df['high'].rolling(20).max() - df['low'].rolling(20).min())

        # 选择特征列
        feature_cols = [
            'returns', 'log_returns', 'volatility',
            'ma_ratio', 'volume_ratio', 'price_position'
        ]

        # 去除NA
        df = df.dropna()

        # 创建序列
        X, y = [], []
        for i in range(len(df) - self.sequence_length - target_horizon + 1):
            # 输入序列
            seq = df[feature_cols].iloc[i:i + self.sequence_length].values
            X.append(seq.flatten())

            # 目标：未来N日收益
            future_return = (df['close'].iloc[i + self.sequence_length + target_horizon - 1] /
                           df['close'].iloc[i + self.sequence_length - 1] - 1)
            y.append(future_return)

        return np.array(X), np.array(y)

    def train(
        self,
        training_data: pd.DataFrame,
        target_horizon: int = 5,
        validation_split: float = 0.2,
    ) -> Dict[str, float]:
        """
        训练LSTM模型

        Args:
            training_data: 训练数据
            target_horizon: 预测 horizon
            validation_split: 验证集比例

        Returns:
            训练指标
        """
        logger.info("开始训练LSTM特征提取器...")

        # 准备数据
        X, y = self.prepare_sequences(training_data, target_horizon)

        if len(X) < 100:
            raise ValueError(f"训练样本不足: {len(X)} < 100")

        # 标准化
        X_scaled = self.scaler.fit_transform(X)

        # 划分训练验证集
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X_scaled[:split_idx], X_scaled[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # 构建并训练模型
        self.model = self._build_model()
        self.model.fit(X_train, y_train)

        # 评估
        train_score = self.model.score(X_train, y_train)
        val_score = self.model.score(X_val, y_val)

        # 计算预测不确定性（使用验证集残差的标准差）
        y_val_pred = self.model.predict(X_val)
        residuals = y_val - y_val_pred
        self.prediction_std = np.std(residuals)

        self.is_trained = True

        logger.info(f"训练完成: 训练集R²={train_score:.4f}, 验证集R²={val_score:.4f}")

        return {
            'train_r2': train_score,
            'val_r2': val_score,
            'prediction_std': self.prediction_std,
            'n_samples': len(X),
        }

    def predict(self, sequence: np.ndarray) -> LSTMPrediction:
        """
        预测未来收益

        Args:
            sequence: 输入序列 (sequence_length, features)

        Returns:
            LSTMPrediction
        """
        if not self.is_trained:
            raise RuntimeError("模型未训练")

        # 扁平化并标准化
        X = sequence.flatten().reshape(1, -1)
        X_scaled = self.scaler.transform(X)

        # 预测
        expected_return = self.model.predict(X_scaled)[0]

        # 获取隐藏状态（使用倒数第二层的激活值）
        hidden_state = self._get_hidden_state(X_scaled)

        return LSTMPrediction(
            expected_return=expected_return,
            uncertainty=self.prediction_std,
            hidden_state=hidden_state,
        )

    def _get_hidden_state(self, X: np.ndarray) -> np.ndarray:
        """获取隐藏层状态（用于MAB输入）"""
        # 使用MLP的中间层输出作为隐藏状态
        activations = X
        for i, (weights, intercepts) in enumerate(zip(
            self.model.coefs_[:-1],
            self.model.intercepts_[:-1]
        )):
            activations = np.tanh(activations @ weights + intercepts)
        return activations.flatten()

    def extract_features_batch(
        self,
        price_data_dict: Dict[str, pd.DataFrame],
    ) -> Dict[str, np.ndarray]:
        """
        批量提取多只股票的特征

        Args:
            price_data_dict: {ts_code: price_dataframe}

        Returns:
            {ts_code: hidden_state_vector}
        """
        features = {}
        for ts_code, price_data in price_data_dict.items():
            try:
                X, _ = self.prepare_sequences(price_data)
                if len(X) > 0:
                    # 取最后一个序列的特征
                    last_seq = X[-1].reshape(1, -1)
                    X_scaled = self.scaler.transform(last_seq)
                    hidden_state = self._get_hidden_state(X_scaled)
                    features[ts_code] = hidden_state
            except Exception as e:
                logger.warning(f"提取{ts_code}特征失败: {e}")

        return features

    def save_model(self, path: Optional[str] = None):
        """保存模型"""
        path = path or self.model_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'prediction_std': getattr(self, 'prediction_std', 0.05),
            'sequence_length': self.sequence_length,
            'feature_dim': self.feature_dim,
        }
        joblib.dump(model_data, path)
        logger.info(f"模型已保存到: {path}")

    def load_model(self, path: Optional[str] = None):
        """加载模型"""
        path = path or self.model_path

        if not os.path.exists(path):
            raise FileNotFoundError(f"模型文件不存在: {path}")

        model_data = joblib.load(path)
        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.prediction_std = model_data.get('prediction_std', 0.05)
        self.sequence_length = model_data.get('sequence_length', self.sequence_length)
        self.feature_dim = model_data.get('feature_dim', self.feature_dim)
        self.is_trained = True

        logger.info(f"模型已从{path}加载")
