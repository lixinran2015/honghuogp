# S级股票详情抽屉设计文档

## 背景

短线龙头仪表盘（`ShortTermLeaderDashboard.vue`）的 "TOP精选 (S级)" 表格当前仅通过「查看」按钮跳转至不存在的 `/stock-detail/:ts_code` 路由。为了提升用户体验，需要让 S 级股票名称可点击，并在右侧滑出抽屉中展示完整的 AI 评分、买点信号、交易计划等信息。

## 目标

1. 仅当股票评分为 **S 级**时，股票名称在仪表盘表格中可点击。
2. 点击后从右侧滑出详情抽屉，避免离开当前页面。
3. 抽屉内聚合展示：最新行情、因子评分细项、买点信号、板块支撑、交易计划等。
4. 后端提供统一的单只股票详情聚合 API，集中计算并复用现有评分引擎和交易计划工具。

## 非目标

- 不改造非 S 级股票的交互行为。
- 不引入新的 UI 组件库（继续使用 Tailwind + 原生 Vue 实现抽屉）。
- 详情抽屉内的「查看研报」按钮本期只做入口占位，不实现研报内容渲染。

## 交互设计

### 入口

- **位置**：`ShortTermLeaderDashboard.vue` → TOP精选 (S级) 表格 → 股票名称列。
- **条件**：`stock.lstm_mab_score?.grade === 'S'`。
- **效果**：名称文字带 `hover:text-cta hover:underline cursor-pointer` 样式。
- **动作**：`openStockDetailDrawer(stock.ts_code)`。

### 抽屉

- **定位**：Fixed，right-0，top-0，bottom-0。
- **尺寸**：桌面端 `max-w-md w-full`（448px），移动端全宽。
- **遮罩**：左侧 `bg-black/50`，点击遮罩关闭。
- **动画**：300ms `transition-transform`。
- **关闭方式**：点击遮罩、点击顶部 ✕ 按钮、按 ESC 键。

### 抽屉布局（自上而下）

```
┌────────────────────────┐
│ ✕ 奥瑞德 (600666)      │
│ 评分: 92 S级   涨停    │
├────────────────────────┤
│ 【因子评分】             │
│ 4个维度条形图+分数       │
├────────────────────────┤
│ 【买点信号】             │
│ 二板缩量 · 85分 (高)    │
│ 板块支撑: 金融科技 (85)  │
├────────────────────────┤
│ 【交易计划】             │
│ 建议买入: 15.90 (+0.6%) │
│ 止损价: 15.35 (-3%)     │
│ 第一止盈: 17.38 (+10%)  │
│ 第二止盈: 18.17 (+15%)  │
│ 建议仓位: 20%           │
├────────────────────────┤
│ [加入持仓] [查看K线]   │
└────────────────────────┘
```

### 底部按钮行为

| 按钮 | 行为 |
|------|------|
| 加入持仓 | 调用现有持仓追加 API（复用仪表盘一键导入逻辑），成功后显示轻量 toast。 |
| 查看K线 | `router.push('/leader-tracking?code=' + tsCode.split('.')[0])`，在龙头跟踪页自动选中该股票。 |
| 查看研报 | 占位，当前弹出提示"研报功能即将上线"或跳转研报搜索页。 |

## 后端 API 设计

### 路由

```http
GET /api/leader-tracking/stock-detail/{ts_code}
```

### 响应结构

```json
{
  "success": true,
  "data": {
    "ts_code": "600666.SH",
    "name": "奥瑞德",
    "latest_price": 15.80,
    "price_change_pct": 10.02,
    "is_limit_up": true,
    "lstm_mab_score": {
      "total_score": 92,
      "grade": "S",
      "expected_return": 12.5,
      "confidence": 0.88,
      "factor_scores": {
        "龙头地位": 28,
        "技术形态": 22,
        "资金流向": 23,
        "情绪热度": 19
      },
      "factor_weights": {
        "龙头地位": 0.30,
        "技术形态": 0.25,
        "资金流向": 0.25,
        "情绪热度": 0.20
      },
      "recommendation": {
        "action": "强烈推荐",
        "position_size": 20,
        "stop_loss_pct": -3,
        "take_profit_1_pct": 10,
        "take_profit_2_pct": 15
      }
    },
    "buy_signal": {
      "signal_type": "二板缩量",
      "strength_score": 85,
      "quality": "高"
    },
    "sector_support": {
      "name": "金融科技",
      "strength": 85
    },
    "trade_plan": {
      "entry_price": 15.90,
      "entry_pct": 0.6,
      "stop_loss_price": 15.35,
      "stop_loss_pct": -3,
      "take_profit_1": 17.38,
      "take_profit_1_pct": 10,
      "take_profit_2": 18.17,
      "take_profit_2_pct": 15
    }
  }
}
```

### 实现要点

1. **获取最新行情**：从 PostgresWarehouse 取该股票最近一条日线（`close`、`pct_change`、`limit_up`）。
2. **AI 评分**：复用 `UnifiedShortTermScorer`。
   - 先通过 `LeaderTrackingPoolService().get_pool()` 获取当日龙头池；
   - 若目标股票不在池中，尝试从 `StartupSectorAnalyzer` 雷达数据补充基础信息；
   - 调用 `scorer.score_stock()` 单股评分。
3. **买点信号**：复用 `buy_signal_integration.get_buy_signals_for_pool()`（单只股票传 `[stock]` 即可）。
4. **交易计划**：
   - 利用 `trade_plan_utils.compute_trade_plan(latest_price, stock_data)` 计算具体价格；
   - 再与 `lstm_mab_score.recommendation` 中的止盈/止损比例合并，生成最终展示结构。
5. **板块支撑**：取股票 `sectors` 第一项，并关联板块强度数据（若有）。

## 前端实现要点

### 新增状态（`ShortTermLeaderDashboard.vue`）

```javascript
const drawerOpen = ref(false)
const drawerTsCode = ref('')
const drawerStock = ref(null)
const drawerLoading = ref(false)
const drawerError = ref(null)
```

### 核心方法

```javascript
async function openStockDetailDrawer(tsCode) {
  drawerOpen.value = true
  drawerTsCode.value = tsCode
  drawerLoading.value = true
  drawerError.value = null
  drawerStock.value = null
  try {
    const res = await fetch(`/api/leader-tracking/stock-detail/${tsCode}`)
    const data = await res.json()
    if (!data.success) throw new Error(data.error || '获取详情失败')
    drawerStock.value = data.data
  } catch (e) {
    drawerError.value = e.message
  } finally {
    drawerLoading.value = false
  }
}

function closeDrawer() {
  drawerOpen.value = false
  drawerTsCode.value = ''
  drawerStock.value = null
  drawerError.value = null
}
```

### 无障碍与快捷键

- 抽屉打开时，焦点自动移入抽屉顶部关闭按钮。
- 监听 `keydown.esc` 关闭抽屉。

## 错误处理

- **API 失败**：抽屉内显示简短错误文案 + 重试按钮。
- **模型未训练**：若后端返回 `model_available=false`，在评分区域显示提示"模型未训练，评分仅供参考"。
- **缺失买点/板块数据**：对应板块显示 "-"，不阻断整体展示。

## 测试验收标准

- [ ] S 级股票名称可点击，点击后抽屉从右侧滑出。
- [ ] 非 S 级股票名称不可点击。
- [ ] 抽屉内正确显示：最新价、涨跌停状态、4 项因子评分、买点信号、板块支撑、交易计划价格。
- [ ] 交易计划中的买入/止损/止盈价格为基于最新价的实际计算值。
- [ ] 「查看K线」按钮能正确跳转 `LeaderTrackingView` 并自动选中该股票。
- [ ] 点击遮罩或按 ESC 可关闭抽屉。
- [ ] API 对不在龙头池但存在于雷达数据中的股票也能正常返回。
