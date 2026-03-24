# Scripts 目录说明

## 📁 目录结构

```
scripts/
├── backup/              # 过时的文档和脚本备份
├── data_fill/           # 数据填充脚本（一次性或补数据用）
├── data_check/          # 数据检查脚本（检查数据完整性、质量等）
├── data_update/         # 数据更新脚本（定时任务、日常更新）
├── calculation/         # 计算脚本（评分、指标计算等）
├── test/                # 测试脚本（临时测试、快速验证）
└── tools/               # 工具脚本（诊断、监控、辅助工具）
```

## 📂 各目录说明

### backup/
存放过时的文档和不再使用的脚本，保留作为历史参考。

### data_fill/
**用途**：一次性数据填充或补数据脚本
- `fill_*.py` - 各种数据填充脚本
- 通常用于：
  - 补充缺失的历史数据
  - 修复数据问题
  - 初始化数据

**使用场景**：
- 数据迁移
- 数据修复
- 历史数据补充

### data_check/
**用途**：数据检查和验证脚本
- `check_*.py` - 各种数据检查脚本
- 通常用于：
  - 检查数据完整性
  - 验证数据质量
  - 查找缺失数据

**使用场景**：
- 数据质量监控
- 问题排查
- 数据验证

### data_update/
**用途**：数据更新脚本（定时任务、日常更新）
- `update_*.py` - 数据更新脚本
- `refresh_*.py` - 数据刷新脚本
- `sync_*.py` - 数据同步脚本
- `init_*.py` - 初始化脚本
- `create_*.py` - 表创建脚本

**使用场景**：
- 定时任务（cron）
- 日常数据更新
- 数据同步

**重要脚本**：
- `update_daily_from_snapshot.py` - 每日数据更新（主要）
- `update_sector_heat_snapshot.py` - 板块热度更新
- `update_sector_leaders.py` - 板块龙头更新
- `refresh_stock_snapshot.py` - 股票快照刷新

### calculation/
**用途**：计算脚本（评分、指标计算等）
- `calculate_*.py` - 各种计算脚本
- `darwin_score_*.py` - 达尔文评分脚本
- `darwin_data_quality_report.py` - 数据质量报告

**使用场景**：
- 策略计算
- 评分计算
- 指标计算

### test/
**用途**：测试脚本（临时测试、快速验证）
- `test_*.py` - 各种测试脚本

**使用场景**：
- 功能测试
- 快速验证
- 调试

### tools/
**用途**：工具脚本（诊断、监控、辅助工具）
- `diagnose_*.py` - 诊断脚本
- `monitor_*.py` - 监控脚本
- `verify_*.py` - 验证脚本
- `swing_*.py` - 波段选股工具
- `import_*.py` - 数据导入脚本
- `run_*.py` - 运行脚本
- `add_*.py` - 添加数据脚本
- `fix_*.py` - 修复脚本

**使用场景**：
- 问题诊断
- 系统监控
- 辅助工具

## 🚀 常用脚本

### 数据更新（定时任务）
```bash
# 每日数据更新
python backend/scripts/data_update/update_daily_from_snapshot.py

# 板块热度更新
python backend/scripts/data_update/update_sector_heat_snapshot.py

# 板块龙头更新
python backend/scripts/data_update/update_sector_leaders.py

# 股票快照刷新
python backend/scripts/data_update/refresh_stock_snapshot.py
```

### 数据检查
```bash
# 检查数据进度
python backend/scripts/data_check/check_data_progress.py

# 检查填充进度
python backend/scripts/data_check/check_fill_progress.py

# 检查S1数据
python backend/scripts/data_check/check_s1_missing_data.py
```

### 工具脚本
```bash
# 诊断短线推荐
python backend/scripts/tools/diagnose_short_recommendations.py

# 监控填充进度
python backend/scripts/tools/monitor_fill_progress.py
```

## 📝 注意事项

1. **data_fill/** 中的脚本通常是一次性的，使用前请确认是否需要
2. **test/** 中的脚本是临时测试用的，可以随时删除
3. **backup/** 中的文件是历史备份，可以定期清理
4. 运行脚本前，请确认：
   - 脚本的用途
   - 是否需要参数
   - 是否会影响现有数据

## 🔄 维护建议

1. **定期清理**：
   - 删除 `test/` 中不再需要的测试脚本
   - 清理 `backup/` 中过时的备份文件

2. **文档更新**：
   - 新增脚本时，更新本README
   - 重要脚本添加使用说明

3. **分类原则**：
   - 如果脚本用途不明确，放在 `tools/`
   - 如果是一次性脚本，放在 `data_fill/`
   - 如果是测试脚本，放在 `test/`

