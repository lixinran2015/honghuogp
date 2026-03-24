# 📝 开发任务清单

## 任务1：后端服务层重构

### 1.1 创建服务目录结构

**任务描述**：
在 `backend/services/` 目录下创建服务模块

**文件清单**：
- [ ] `backend/services/__init__.py`
- [ ] `backend/services/stock_filter.py`
- [ ] `backend/services/stock_scorer.py`
- [ ] `backend/services/market_data_service.py`
- [ ] `backend/services/ai_analysis_service.py`

### 1.2 实现股票筛选服务

**文件**: `backend/services/stock_filter.py`

**需要实现**：
- [ ] `StockFilter` 类
- [ ] `filter_short_term()` 方法
  - 筛选条件：涨幅1%-5%，换手率≥8%，成交额≥2亿
  - 排除：科创板、北交所、ST股票、指数
- [ ] `filter_swing_term()` 方法
  - 筛选条件：涨幅-1%~2%，换手率1%-4%，成交额≥5000万
  - 排除：科创板、北交所、ST股票、指数
- [ ] `filter_long_term()` 方法（待实现）
  - 筛选条件：ROE≥12%，行业集中度高，供需向上

**参考代码**：
- `app.py` 第956行开始的 `_get_real_stock_recommendations` 方法
- `app.py` 第1120-1270行的筛选逻辑

### 1.3 实现股票评分服务

**文件**: `backend/services/stock_scorer.py`

**需要实现**：
- [ ] `StockScorer` 类
- [ ] `score_short_term()` 方法
  - 题材强度（30%）：基于月度题材配置
  - 板块热度（20%）：基于板块涨幅
  - 换手强度（20%）：换手率/10.0
  - 成交额权重（10%）：成交额/5亿
  - 连板强度（20%）：需要历史数据（暂时为0）
- [ ] `score_swing_term()` 方法
  - 趋势强度（40%）：基于涨幅和换手率
  - 缩量回踩结构（30%）：需要技术指标（暂时简化）
  - 主力吸筹程度（20%）：基于成交额
  - 行业热度（10%）：需要板块数据（暂时为0）
- [ ] `score_long_term()` 方法（待实现）
  - 达尔文评分体系

**参考代码**：
- `app.py` 第1258-1300行的评分逻辑
- `config/monthly_theme.yaml` 月度题材配置

### 1.4 实现市场数据服务

**文件**: `backend/services/market_data_service.py`

**需要实现**：
- [ ] `MarketDataService` 类
- [ ] `get_realtime_stocks()` 方法
  - 调用 `akshare_safe_wrapper.fetch_realtime_a_stock()`
  - 支持缓存和强制刷新
- [ ] `get_market_summary()` 方法
  - 调用 `akshare_safe_wrapper.fetch_index_data_safe()`
  - 提取上证指数、深证成指、创业板指

**参考代码**：
- `app.py` 第2093行的指数数据获取
- `akshare_safe_wrapper.py` 的数据获取函数

### 1.5 实现AI分析服务

**文件**: `backend/services/ai_analysis_service.py`

**需要实现**：
- [ ] `AIAnalysisService` 类
- [ ] `analyze_stock()` 方法
  - 调用 OpenAI API
  - 调用 Deepseek API
  - 返回分析结果

**参考代码**：
- `app.py` 第1791行的 `_get_ai_stock_analysis` 方法
- `app.py` 第1637行的 `_update_ai_analysis_async` 方法

---

## 任务2：数据模型定义

### 2.1 创建模型目录结构

**文件清单**：
- [ ] `backend/models/__init__.py`
- [ ] `backend/models/stock.py`
- [ ] `backend/models/recommendation.py`

### 2.2 实现股票数据模型

**文件**: `backend/models/stock.py`

**需要实现**：
- [ ] `Stock` 数据类（使用 `@dataclass`）
  - `code`: 股票代码
  - `name`: 股票名称
  - `current_price`: 当前价格
  - `change_pct`: 涨跌幅
  - `turnover_rate`: 换手率
  - `amount`: 成交额
  - `sector`: 所属行业

### 2.3 实现推荐结果模型

**文件**: `backend/models/recommendation.py`

**需要实现**：
- [ ] `StockRecommendation` 数据类
  - `code`: 股票代码
  - `name`: 股票名称
  - `type`: 策略类型（"short" | "swing" | "long"）
  - `current_price`: 当前价格
  - `change_pct`: 涨跌幅
  - `buy_range`: 入手价格区间
  - `reason`: 推荐理由
  - `score`: 综合得分
  - `ai_score`: AI评分（可选）
  - `ai_analysis`: AI分析（可选）

---

## 任务3：API接口优化

### 3.1 创建API目录结构

**文件清单**：
- [ ] `backend/api/__init__.py`
- [ ] `backend/api/recommendations.py`
- [ ] `backend/api/market.py`

### 3.2 实现推荐接口

**文件**: `backend/api/recommendations.py`

**需要实现**：
- [ ] `router = APIRouter(prefix="/api/recommendations")`
- [ ] `GET /api/recommendations` 接口
  - 参数：`type`（short/swing/long/all）、`limit`、`date`
  - 使用 `StockFilter` 和 `StockScorer` 服务
  - 返回格式化的推荐结果
- [ ] `GET /api/recommendations/short` 接口（可选）
- [ ] `GET /api/recommendations/swing` 接口（可选）

**参考代码**：
- `backend/app.py` 第145行的 `get_mixed_recommendations` 接口

### 3.3 实现市场数据接口

**文件**: `backend/api/market.py`

**需要实现**：
- [ ] `router = APIRouter(prefix="/api/market")`
- [ ] `GET /api/market/summary` 接口
  - 使用 `MarketDataService` 服务
  - 返回市场概况数据

**参考代码**：
- `backend/app.py` 第184行的 `get_market_data` 接口

### 3.4 注册路由

**文件**: `backend/app.py`

**需要修改**：
- [ ] 导入新的路由模块
- [ ] 使用 `app.include_router()` 注册路由

---

## 任务4：前端数据对接

### 4.1 修改API调用

**文件**: `frontend/src/App.jsx`

**需要修改**：
- [ ] 修改 `fetchStocks` 函数
  - 调用新的 `/api/recommendations?type=all` 接口
  - 处理返回的 `data.short` 和 `data.swing`
- [ ] 修改 `fetchMarketData` 函数
  - 调用新的 `/api/market/summary` 接口
  - 处理返回的数据格式

### 4.2 更新数据结构

**文件**: `frontend/src/components/StockCard.jsx`

**需要检查**：
- [ ] 确保所有字段正确映射
- [ ] 处理可选字段（如 `ai_score`、`ai_analysis`）
- [ ] 格式化显示（价格、百分比等）

---

## 任务5：测试和验证

### 5.1 单元测试

**需要创建**：
- [ ] `backend/tests/test_stock_filter.py`
- [ ] `backend/tests/test_stock_scorer.py`
- [ ] `backend/tests/test_market_data_service.py`

### 5.2 集成测试

**需要创建**：
- [ ] `backend/tests/test_recommendations_api.py`
- [ ] `backend/tests/test_market_api.py`

### 5.3 手动测试

**测试清单**：
- [ ] 测试短线票筛选功能
- [ ] 测试波段票筛选功能
- [ ] 测试评分算法
- [ ] 测试API接口返回格式
- [ ] 测试前端数据展示
- [ ] 测试AI分析集成

---

## 任务6：文档更新

### 6.1 代码文档

**需要更新**：
- [ ] 所有服务类的文档字符串
- [ ] 所有方法的参数和返回值说明
- [ ] API接口的文档字符串

### 6.2 用户文档

**需要创建**：
- [ ] `docs/API_USAGE.md` - API使用说明
- [ ] `docs/DEVELOPMENT_GUIDE.md` - 开发指南

---

## 实施顺序

### 第一阶段（本周）
1. ✅ 创建目录结构
2. ✅ 实现 `StockFilter` 服务
3. ✅ 实现 `StockScorer` 服务（基础版）
4. ✅ 实现 `MarketDataService` 服务
5. ✅ 创建API接口
6. ✅ 更新前端调用

### 第二阶段（下周）
1. ⚠️ 完善评分算法
2. ⚠️ 集成月度题材加分
3. ⚠️ 优化AI分析服务
4. ⚠️ 添加单元测试

### 第三阶段（后续）
1. 📅 实现长线投公司模型
2. 📅 实现指数基金定投策略
3. 📅 实现自动报告生成

---

## 注意事项

1. **保持向后兼容**：新接口不影响现有功能
2. **错误处理**：所有服务都要有完善的错误处理
3. **日志记录**：关键操作都要记录日志
4. **性能优化**：注意数据获取的缓存策略
5. **代码规范**：遵循PEP 8规范，添加类型提示

