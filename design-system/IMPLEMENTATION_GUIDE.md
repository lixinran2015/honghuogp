# 短线龙头前端页面重新设计 - 实施指南

## 已完成的设计系统更新

### 1. Tailwind 配置更新 ✅
- 添加了专业金融配色系统（深色主题）
- 添加了股票专用颜色（profit/loss/warning/info）
- 添加了数据字体（Fira Code）
- 添加了动画效果（data-update, flash-green, flash-red）

### 2. 全局样式更新 ✅
- `App.vue`: 应用深色主题背景
- `index.html`: 添加 Google Fonts（IBM Plex Sans + Fira Code）
- `Sidebar.vue`: 更新为深色主题样式
- `TopBar.vue`: 更新为 Glassmorphism 效果

### 3. 新增 UI 组件 ✅
- `DataCard.vue`: 数据卡片容器
- `KPICard.vue`: KPI 指标卡片（带涨跌趋势）
- `StatusBadge.vue`: 状态标签组件
- `FilterPanel.vue`: 过滤面板组件
- `DataTable.vue`: 数据表格组件

## 页面级样式更新指南

### 页面容器

```vue
<template>
  <div class="p-4 lg:p-6 bg-dark-900 min-h-screen">
    <!-- 页面内容 -->
  </div>
</template>
```

### 页面标题区

```vue
<!-- 旧样式 -->
<div class="mb-6 flex items-center justify-between">
  <div>
    <h1 class="text-2xl font-bold text-gray-800">龙头跟踪</h1>
    <p class="text-sm text-gray-500 mt-1">描述文字</p>
  </div>
  <button class="px-4 py-2 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700">
    刷新
  </button>
</div>

<!-- 新样式 -->
<div class="mb-6 flex items-center justify-between">
  <div>
    <h1 class="text-xl font-bold text-white">龙头跟踪</h1>
    <p class="text-sm text-dark-400 mt-1">描述文字</p>
  </div>
  <button class="px-4 py-2 rounded-md text-sm font-medium text-white bg-cta hover:bg-cta-hover transition-colors">
    刷新
  </button>
</div>
```

### KPI 卡片区

```vue
<!-- 新增 KPI 卡片展示关键指标 -->
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
  <KPICard
    label="涨停家数"
    :value="stats.limitUpCount"
    :change="stats.limitUpChange"
    trend="up"
  />
  <KPICard
    label="跌停家数"
    :value="stats.limitDownCount"
    :change="stats.limitDownChange"
    trend="down"
  />
  <KPICard
    label="成交额"
    :value="stats.totalAmount"
    :change="stats.amountChange"
    suffix="亿"
  />
  <KPICard
    label="涨跌比"
    :value="stats.upDownRatio"
    :decimals="2"
  />
</div>
```

### 过滤面板

```vue
<!-- 旧样式 -->
<div class="bg-white rounded-xl shadow border border-gray-100 p-3 flex flex-wrap items-center gap-3 text-xs">
  <div class="flex items-center gap-2">
    <span class="text-gray-500">筛选</span>
    <input class="px-2 py-1 border border-gray-200 rounded-md" />
  </div>
</div>

<!-- 新样式 -->
<FilterPanel
  v-model="filters"
  v-model:search-value="keyword"
  :filters="[
    { key: 'status', label: '状态', options: [...] },
    { key: 'type', label: '类型', options: [...] }
  ]"
  :checkboxes="[
    { key: 'onlyBuy', label: '只看买点候选' }
  ]"
  :refreshing="loading"
  @refresh="fetchData"
  @reset="resetFilters"
/>
```

### 数据表格

```vue
<!-- 旧样式 -->
<table class="min-w-full divide-y divide-gray-200">
  <thead class="bg-gray-50">
    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">股票</th>
  </thead>
  <tbody class="bg-white divide-y divide-gray-200">
    <tr>
      <td class="px-4 py-3 text-sm text-gray-900">{{ stock.name }}</td>
    </tr>
  </tbody>
</table>

<!-- 新样式 -->
<DataTable
  :data="leaders"
  :columns="[
    { key: 'name', title: '股票', sortable: true },
    { key: 'price', title: '最新价', align: 'right', type: 'price', sortable: true },
    { key: 'change', title: '涨跌幅', align: 'right', type: 'percent', sortable: true, color: getChangeColor },
    { key: 'amount', title: '成交额', align: 'right', sortable: true }
  ]"
  :clickable="true"
  @row-click="handleRowClick"
>
  <template #cell-name="{ row }">
    <div class="flex items-center gap-2">
      <span class="font-medium text-white">{{ row.name }}</span>
      <span class="text-2xs text-dark-400">{{ row.code }}</span>
      <StatusBadge v-if="row.isLimitUp" variant="success" size="sm">涨停</StatusBadge>
    </div>
  </template>
</DataTable>
```

### 状态标签

```vue
<!-- 旧样式 -->
<span class="px-2 py-1 text-xs rounded-full bg-green-100 text-green-800">强势</span>
<span class="px-2 py-1 text-xs rounded-full bg-red-100 text-red-800">退潮</span>

<!-- 新样式 -->
<StatusBadge variant="success" dot>强势</StatusBadge>
<StatusBadge variant="warning" dot>震荡</StatusBadge>
<StatusBadge variant="danger" dot>退潮风险</StatusBadge>
<StatusBadge variant="neutral">观察</StatusBadge>
```

### 涨跌颜色

```vue
<!-- 使用全局样式类 -->
<span :class="change > 0 ? 'stock-up' : change < 0 ? 'stock-down' : 'stock-neutral'">
  {{ change }}%
</span>

<!-- 或使用 Tailwind 类 -->
<span :class="[
  change > 0 && 'text-profit',
  change < 0 && 'text-loss',
  change === 0 && 'text-dark-400'
]">
  {{ change }}%
</span>
```

### 数据卡片

```vue
<DataCard title="龙头股列表" :icon="ChartBarIcon">
  <template #header-action>
    <button class="text-2xs text-cta hover:text-cta-hover">查看全部</button>
  </template>

  <!-- 卡片内容 -->
  <DataTable ... />
</DataCard>
```

### 错误提示

```vue
<!-- 旧样式 -->
<div class="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
  {{ error }}
</div>

<!-- 新样式 -->
<div class="mb-4 bg-loss/10 border border-loss/30 text-loss text-sm px-4 py-3 rounded-lg">
  <div class="flex items-center gap-2">
    <ExclamationCircleIcon class="w-4 h-4" />
    {{ error }}
  </div>
</div>
```

### 加载状态

```vue
<!-- 骨架屏 -->
<div class="animate-pulse space-y-3">
  <div class="h-8 bg-dark-700 rounded w-1/4"></div>
  <div class="h-32 bg-dark-700 rounded"></div>
</div>

<!-- 或加载指示器 -->
<div class="flex items-center justify-center py-12">
  <div class="w-8 h-8 border-2 border-cta border-t-transparent rounded-full animate-spin"></div>
  <span class="ml-2 text-dark-400">加载中...</span>
</div>
```

## 响应式断点

```css
/* 移动端 */
@media (max-width: 768px) {
  .container { padding: 0.75rem; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
}

/* 平板 */
@media (min-width: 768px) and (max-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}

/* 桌面 */
@media (min-width: 1024px) {
  .kpi-grid { grid-template-columns: repeat(4, 1fr); }
}
```

## 性能优化建议

1. **使用 `font-mono` 显示数字**，确保对齐
2. **使用 `tabular-nums` 字体特性**，数字等宽
3. **动画使用 GPU 加速**：`transform` 和 `opacity`
4. **大数据表格使用虚拟滚动**
5. **实时数据更新使用 `requestAnimationFrame`**

## 无障碍要求

1. 所有交互元素有 `cursor-pointer`
2. Hover 状态有 150ms 过渡动画
3. 焦点状态可见（`focus:ring`）
4. 支持 `prefers-reduced-motion`
5. 文字对比度至少 4.5:1

## 下一步实施建议

1. 逐个页面应用新样式
2. 先更新容器和布局
3. 再更新表格和列表
4. 最后更新表单和交互组件
5. 每页更新后测试响应式
