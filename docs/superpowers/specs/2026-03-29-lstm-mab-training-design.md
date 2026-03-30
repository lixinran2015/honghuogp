# LSTM-MAB 模型训练设计文档

## 目标
将 Phase 1 因子验证结论注入 Phase 2 的 LSTM-MAB 训练流程，修复现有训练接口的数据组织 Bug，并提供可独立运行的端到端训练脚本。

## 背景
Phase 1 验证结果显示：
- `leader_position`：A 级（IC=0.1435，单调性=0.70）→ 有效
- `technical`：B 级（IC=0.1074）→ 有效
- `money_flow`：C 级（IC=-0.0437，单调性=0.00）→ 无效
- `sentiment`：C 级（IC=-0.0706，单调性=0.00）→ 无效

继续在训练中使用全部 4 个因子会降低模型质量，因此模型应仅使用验证通过的因子子集。

## 架构改动

### 1. 因子筛选机制
- `LSTMMABModel.__init__` 接受 `factor_names` 参数，默认改为 `['leader_position', 'technical']`
- `MABWeightAllocator` 子类（ThompsonSampling、UCB）及 `EmotionAdaptiveAllocator` 情绪权重表动态适配实际传入的因子列表
- API `/predict` 参数改为动态：仅要求传入当前启用因子的得分

### 2. 修复 `/api/lstm-mab/train` 数据 Bug
- **现状**：SQL 未按 `ts_code` 分组，导致多只股票价格混为一条序列
- **修复**：查询后按 `ts_code` groupby，每只股票分别调用 `prepare_sequences()`，合并所有样本后统一训练一个通用 LSTM 模型

### 3. 端到端训练脚本 `backend/scripts/train_lstm_mab.py`
- 从数据库读取日线 QFQ 数据
- 按股票分组合并训练样本
- 训练并保存模型到 `backend/models/lstm_mab_YYYYMMDD.pkl`
- 输出训练指标报告（R²、样本数、预测标准差）
- CLI 参数：`--start-date`, `--end-date`, `--factors`

### 4. 执行真实训练
- 使用最近 ~2 年历史数据完成一次训练
- 验证模型文件可被加载
- 验证 `/predict` 正常输出评分

## 数据流
```
DB (fact_daily_price_qfq)
    ↓
按 ts_code 分组 → 逐股生成 (X_seq, y_return)
    ↓
合并所有样本 → 训练 LSTMFeatureExtractor
    ↓
保存模型文件 + MAB 初始化状态
    ↓
API /predict（仅使用 leader_position, technical）
```

## 依赖文件
- `backend/services/lstm_mab/lstm_mab_model.py`
- `backend/services/lstm_mab/mab_weight_allocator.py`
- `backend/services/lstm_mab/lstm_feature_extractor.py`
- `backend/api/lstm_mab.py`
- `backend/scripts/train_lstm_mab.py`（新建）
