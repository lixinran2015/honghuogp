# LSTM-MAB 模型训练实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Phase 1 因子验证结论注入 LSTM-MAB 训练流程，修复训练接口数据 Bug，创建端到端训练脚本并完成一次真实模型训练。

**Architecture:** 默认仅启用验证通过的因子（leader_position、technical）；修复 `/train` 端点让所有股票按 ts_code 分别生成时序样本后合并训练；提供独立 CLI 脚本进行模型训练和保存。

**Tech Stack:** Python, FastAPI, scikit-learn (MLPRegressor), pandas, numpy, SQLAlchemy, joblib

---

## 文件改动清单

- `backend/services/lstm_mab/mab_weight_allocator.py` - 让 `ThompsonSampling`/`UCB` 严格使用传入的 `factor_names`；让 `EmotionAdaptiveAllocator` 动态过滤情绪权重表
- `backend/services/lstm_mab/lstm_mab_model.py` - 默认 `factor_names` 改为 `['leader_position', 'technical']`；修复 `load()` 中 MAB 重建以匹配保存的因子列表
- `backend/api/lstm_mab.py` - 修复 `/train` SQL 按股票分组训练；`predict` 参数动态化；新增 `/train-script` 或直接用脚本
- `backend/scripts/train_lstm_mab.py` - 新建端到端训练脚本

---

### Task 1: 修复 MAB 权重分配器以支持动态因子列表

**Files:**
- Modify: `backend/services/lstm_mab/mab_weight_allocator.py`

- [ ] **Step 1: 修改 EmotionAdaptiveAllocator 的 allocate 方法**

在 `allocate()` 中，过滤 `EMOTION_WEIGHTS` 里实际存在的因子，缺失的因子用等权重 fallback，避免 KeyError。

```python
# 在 EmotionAdaptiveAllocator.allocate() 中，替换融合权重的逻辑为：
base_weights = self.EMOTION_WEIGHTS.get(self.current_emotion, self.EMOTION_WEIGHTS['震荡期'])
final_weights = {}
for name in mab_weights:
    base = base_weights.get(name, 1.0 / len(mab_weights))
    final_weights[name] = 0.5 * mab_weights[name] + 0.5 * base
```

- [ ] **Step 2: 运行快速检查确保没有硬编码 4 因子引用**

Run:
```bash
grep -n "leader_position" backend/services/lstm_mab/mab_weight_allocator.py
```

Expected: 只出现在 `EMOTION_WEIGHTS` 字典中，不在算法逻辑里硬编码循环。

- [ ] **Step 3: Commit**

```bash
git add backend/services/lstm_mab/mab_weight_allocator.py
git commit -m "feat: make EmotionAdaptiveAllocator support dynamic factor lists"
```

---

### Task 2: 更新 LSTMMABModel 默认因子并修复 load

**Files:**
- Modify: `backend/services/lstm_mab/lstm_mab_model.py`

- [ ] **Step 1: 修改默认 factor_names**

```python
self.factor_names = factor_names or [
    'leader_position',
    'technical',
]
```

- [ ] **Step 2: 在 load() 中重建 MAB 时使用保存的 factor_names**

```python
saved_factors = model_data.get('factor_names', self.factor_names)
self.factor_names = saved_factors

from .mab_weight_allocator import ThompsonSampling, UCB
if isinstance(model_data['mab_base'], ThompsonSampling):
    self.mab.base_allocator = ThompsonSampling(saved_factors)
    self.mab.base_allocator.successes = model_data['mab_base'].successes
    self.mab.base_allocator.failures = model_data['mab_base'].failures
    self.mab.base_allocator.total_pulls = model_data['mab_base'].total_pulls
elif isinstance(model_data['mab_base'], UCB):
    self.mab.base_allocator = UCB(saved_factors)
    self.mab.base_allocator.total_rewards = model_data['mab_base'].total_rewards
    self.mab.base_allocator.pull_counts = model_data['mab_base'].pull_counts
    self.mab.base_allocator.reward_history = model_data['mab_base'].reward_history
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/lstm_mab/lstm_mab_model.py
git commit -m "feat: default to validated factors and fix model load"
```

---

### Task 3: 修复 /train API — 按股票分组训练

**Files:**
- Modify: `backend/api/lstm_mab.py`

- [ ] **Step 1: 修复 train_model 中的 SQL 和训练逻辑**

将原有：`price_data = pd.read_sql(...)` 后直接 `model.train(price_data)` 的代码改为：

```python
# 读取数据后添加 ts_code
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

# 按股票分别生成序列，合并训练
X_all, y_all = [], []
for ts_code, group in price_data.groupby('ts_code'):
    group = group.sort_values('trade_date')
    try:
        X, y = model.lstm.prepare_sequences(group, target_horizon)
        if len(X) > 0:
            X_all.append(X)
            y_all.append(y)
    except Exception as e:
        logger.warning(f"生成 {ts_code} 序列失败: {e}")

if not X_all:
    return {
        'success': False,
        'error': '没有足够的有效训练样本',
    }

X_all = np.vstack(X_all)
y_all = np.concatenate(y_all)

# 训练
metrics = model.lstm.train_from_arrays(X_all, y_all)
```

- [ ] **Step 2: 在 LSTMFeatureExtractor 中新增 train_from_arrays**

Modify: `backend/services/lstm_mab/lstm_feature_extractor.py`，在 `train()` 方法下面添加：

```python
def train_from_arrays(
    self,
    X: np.ndarray,
    y: np.ndarray,
    validation_split: float = 0.2,
) -> Dict[str, float]:
    """直接从已经准备好的 X, y 数组训练"""
    if len(X) < 100:
        raise ValueError(f"训练样本不足: {len(X)} < 100")

    X_scaled = self.scaler.fit_transform(X)
    split_idx = int(len(X) * (1 - validation_split))
    X_train, X_val = X_scaled[:split_idx], X_scaled[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    self.model = self._build_model()
    self.model.fit(X_train, y_train)

    train_score = self.model.score(X_train, y_train)
    val_score = self.model.score(X_val, y_val)

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
```

- [ ] **Step 3: 修改 predict_score API 参数为动态**

将 `/predict` 端点从固定的 4 个 Query 参数改为接收单个 JSON body：

```python
from pydantic import BaseModel

class PredictRequest(BaseModel):
    ts_code: str
    factor_values: Dict[str, float]

@router.post("/predict")
async def predict_score(request: PredictRequest) -> Dict:
    try:
        model = _get_model()
        if not _model_status['is_trained']:
            return {'success': False, 'error': '模型未训练，请先调用/train接口'}
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/api/lstm_mab.py backend/services/lstm_mab/lstm_feature_extractor.py
git commit -m "fix: group training by ts_code and add train_from_arrays; make predict params dynamic"
```

---

### Task 4: 创建端到端训练脚本

**Files:**
- Create: `backend/scripts/train_lstm_mab.py`

- [ ] **Step 1: 编写训练脚本**

```python
"""
LSTM-MAB 模型训练脚本
Usage:
    python backend/scripts/train_lstm_mab.py --start-date 2023-01-01 --end-date 2026-03-29
"""

import argparse
import logging
import sys
import os
from datetime import date

# 添加项目根目录到路径
project_root = os.path.join(os.path.dirname(__file__), '../..')
sys.path.insert(0, os.path.abspath(project_root))

import numpy as np
import pandas as pd
from sqlalchemy import text

from data_warehouse.service.warehouse_service import WarehouseService
from backend.services.lstm_mab import LSTMMABModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fetch_price_data(start_date: str, end_date: str):
    ws = WarehouseService()
    session = ws.get_session()
    try:
        query = text("""
            SELECT ts_code, trade_date, open, high, low, close, vol as volume
            FROM fact_daily_price_qfq
            WHERE trade_date BETWEEN :start_date AND :end_date
            ORDER BY ts_code, trade_date
        """)
        df = pd.read_sql(query, session.bind, params={'start_date': start_date, 'end_date': end_date})
        return df
    finally:
        session.close()


def train_model(start_date: str, end_date: str, factors=None):
    factors = factors or ['leader_position', 'technical']
    logger.info(f"开始训练 LSTM-MAB 模型，因子: {factors}")

    price_df = fetch_price_data(start_date, end_date)
    if len(price_df) < 100:
        logger.error("价格数据不足")
        return False

    model = LSTMMABModel(factor_names=factors)

    X_all, y_all = [], []
    valid_stocks = 0
    for ts_code, group in price_df.groupby('ts_code'):
        group = group.sort_values('trade_date')
        try:
            X, y = model.lstm.prepare_sequences(group, target_horizon=5)
            if len(X) > 0:
                X_all.append(X)
                y_all.append(y)
                valid_stocks += 1
        except Exception as e:
            logger.warning(f"生成 {ts_code} 序列失败: {e}")

    if not X_all:
        logger.error("没有生成任何有效训练样本")
        return False

    X_all = np.vstack(X_all)
    y_all = np.concatenate(y_all)
    logger.info(f"合并训练样本: {len(X_all)} 条，来自 {valid_stocks} 只股票")

    metrics = model.lstm.train_from_arrays(X_all, y_all)
    logger.info(f"训练完成: train_r2={metrics['train_r2']:.4f}, val_r2={metrics['val_r2']:.4f}, n_samples={metrics['n_samples']}")

    # 保存模型
    os.makedirs('backend/models', exist_ok=True)
    model_path = f"backend/models/lstm_mab_{date.today().strftime('%Y%m%d')}.pkl"
    model.save(model_path)
    logger.info(f"模型已保存: {model_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Train LSTM-MAB model")
    parser.add_argument("--start-date", default="2023-01-01", help="训练开始日期")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="训练结束日期")
    parser.add_argument("--factors", nargs="+", default=None, help="要使用的因子列表")
    args = parser.parse_args()

    success = train_model(args.start_date, args.end_date, args.factors)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/train_lstm_mab.py
git commit -m "feat: add end-to-end LSTM-MAB training script"
```

---

### Task 5: 运行训练并验证

**Files:**
- Modify: `_model_status` / `model.save` 路径间接相关
- Test: CLI 验证 + API 验证

- [ ] **Step 1: 执行训练脚本**

Run:
```bash
source .env && ./venv/bin/python backend/scripts/train_lstm_mab.py --start-date 2023-01-01 --end-date 2026-03-29
```

Expected: 输出 `训练完成: train_r2=..., val_r2=..., n_samples=...` 且无异常，模型文件保存到 `backend/models/lstm_mab_20260329.pkl`

- [ ] **Step 2: 验证模型可加载且 predict 正常**

新建验证脚本 `backend/scripts/verify_lstm_mab.py`（可直接在 python 命令行跑）：

```python
import sys
sys.path.insert(0, '.')
from backend.services.lstm_mab import LSTMMABModel
from datetime import date

model = LSTMMABModel(factor_names=['leader_position', 'technical'])
model.load(f"backend/models/lstm_mab_{date.today().strftime('%Y%m%d')}.pkl")
print("模型加载成功，因子:", model.factor_names)

result = model.predict(
    ts_code='000001.SZ',
    factor_values={'leader_position': 80, 'technical': 75}
)
print("预测结果:", result)
```

- [ ] **Step 3: 快速 API 测试**

启动短线服务后发送请求（可用 curl 或 httpie）：

```bash
curl -X POST "http://localhost:8000/api/lstm-mab/predict" \
  -H "Content-Type: application/json" \
  -d '{"ts_code":"000001.SZ","factor_values":{"leader_position":80,"technical":75}}'
```

Expected: 返回 JSON 包含 `total_score`、`grade`、`factor_weights`（只有 leader_position 和 technical）

- [ ] **Step 4: Commit 最终报告（可选）**

如果一切正常：
```bash
git add backend/scripts/verify_lstm_mab.py
# 或仅做 git status 确认
```

---

## Spec Coverage Check

| Spec 要求 | 对应任务 |
|-----------|----------|
| 默认仅使用验证通过因子 | Task 2 |
| MAB 动态适配因子列表 | Task 1 |
| 修复 train 不按 ts_code 分组 | Task 3 |
| 端到端训练脚本 | Task 4 |
| 执行一次真实训练并验证 predict | Task 5 |

## Placeholder Scan

计划内无 "TBD"、"TODO"、"implement later" 或模糊描述。所有步骤包含可直接运行的代码和命令。

## Type Consistency Check

- `train_from_arrays` 返回 `Dict[str, float]`，键为 `train_r2`, `val_r2`, `prediction_std`, `n_samples`，与 `_model_status['performance']` 结构兼容。
- `LSTMMABModel.load()` 重建 MAB 的因子列表与保存的 `factor_names` 一致，避免运行时类型不匹配。
