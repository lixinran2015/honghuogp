# 统计卡片百分比说明

## 当前实现

统计卡片中的 `change` 属性（百分比）目前是**硬编码的示例数据**：

- **达尔文公司**: `change: 12.5` → 显示 `+12.50%`
- **波段股票**: `change: 8.3` → 显示 `+8.30%`
- **短线股票**: `change: -2.1` → 显示 `-2.10%`

## 百分比应该代表什么？

根据业务逻辑，这个百分比应该表示：

### 选项1：相对于上一次统计的变化
- **计算方式**: `(当前数量 - 上次数量) / 上次数量 * 100`
- **示例**: 如果上次有 10 只达尔文股票，现在有 11 只，则变化为 `(11-10)/10*100 = +10%`
- **需要**: 存储上一次的统计数据（localStorage 或后端）

### 选项2：相对于总股票池的变化
- **计算方式**: `(当前数量 - 基准数量) / 基准数量 * 100`
- **示例**: 如果基准是 100 只股票，现在有 12 只达尔文股票，则变化为 `(12-100)/100*100 = -88%`
- **需要**: 定义基准数量

### 选项3：相对于市场平均的变化
- **计算方式**: `(当前数量 - 市场平均) / 市场平均 * 100`
- **示例**: 如果市场平均推荐 5 只，现在有 10 只，则变化为 `(10-5)/5*100 = +100%`
- **需要**: 计算市场平均推荐数量

## 推荐实现方案

**建议使用选项1**：相对于上一次统计的变化，这样用户可以直观看到推荐数量的增减趋势。

### 实现步骤：

1. **存储上一次统计**（使用 localStorage）：
```javascript
// 保存当前统计
localStorage.setItem('lastStats', JSON.stringify({
  darwin: darwinCount.value,
  swing: swingCount.value,
  short: shortCount.value,
  timestamp: Date.now()
}))
```

2. **计算变化百分比**：
```javascript
// 获取上一次统计
const lastStats = JSON.parse(localStorage.getItem('lastStats') || '{}')

// 计算变化
const darwinChange = lastStats.darwin 
  ? ((darwinCount.value - lastStats.darwin) / lastStats.darwin * 100)
  : undefined

const swingChange = lastStats.swing
  ? ((swingCount.value - lastStats.swing) / lastStats.swing * 100)
  : undefined

const shortChange = lastStats.short
  ? ((shortCount.value - lastStats.short) / lastStats.short * 100)
  : undefined
```

3. **更新 StatCard 组件**：
```vue
<StatCard
  label="达尔文公司"
  :value="darwinCount"
  :change="darwinChange"
  :icon="StarIcon"
/>
```

## 当前状态

目前百分比是**示例数据**，需要根据实际业务需求实现真实的变化计算逻辑。

