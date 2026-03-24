# 股票量化系统 Skills

本项目包含以下 Cursor Skills，用于提升开发效率和代码质量。

## 已安装的 Skills

### 1. api-rate-limiter
**用途**: 处理 API 限流，特别是 Tushare API（每分钟200次限制）

**使用场景**:
- 实现 API 客户端时
- 批量获取数据时
- 遇到限流错误时

**关键特性**:
- 令牌桶算法实现
- 线程安全的速率限制
- 自动重试机制

### 2. financial-data-validator
**用途**: 验证财务数据的完整性和质量

**使用场景**:
- 处理财务指标时
- 处理利润表/现金流量表时
- 数据完整性检查时

**关键特性**:
- 必需字段验证
- 数据质量检查（NaN/Inf处理）
- 报告期格式验证
- 安全的数值转换

### 3. batch-data-processing
**用途**: 优化批量数据处理，适用于 ETL 管道

**使用场景**:
- 处理大量数据时
- 实现批量更新时
- 优化数据仓库操作时

**关键特性**:
- 批量处理模式
- 数据库批量操作
- 并发批量处理
- 进度跟踪

### 4. performance-optimizer
**用途**: 优化代码性能，特别是数据处理和数据库查询

**使用场景**:
- 代码运行缓慢时
- 处理大数据集时
- 优化 ETL 管道时

**关键特性**:
- 数据库查询优化
- API 调用优化
- 内存优化
- 代码性能分析

### 5. etl-pipeline
**用途**: 设计和实现 ETL（提取、转换、加载）管道

**使用场景**:
- 构建数据仓库操作时
- 每日数据更新时
- 数据迁移任务时

**关键特性**:
- 三层架构（Raw/Clean/Warehouse）
- 增量更新模式
- 错误处理机制
- 数据验证流程

## 如何使用

### 自动使用
Cursor Agent 会在相关场景自动应用这些 Skills。

### 手动调用
在 Cursor 的 Agent 模式中，可以使用 `@skill-name` 语法：

```
@api-rate-limiter 帮我实现Tushare API的限流处理
@financial-data-validator 验证这段财务数据的完整性
@batch-data-processing 优化这个批量处理函数
@performance-optimizer 优化这段代码的性能
@etl-pipeline 设计一个财务数据的ETL流程
```

## 技能位置

- **项目级别**: `.cursor/skills/` - 与项目一起版本控制
- **全局级别**: `~/.cursor/skills/` - 所有项目可用

## 更新和维护

这些 Skills 会根据项目需求持续更新。建议：
1. 定期检查 Skills 是否需要更新
2. 根据实际使用情况调整 Skills
3. 添加新的 Skills 以覆盖更多场景
