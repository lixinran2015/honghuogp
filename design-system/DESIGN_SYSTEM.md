# 短线龙头量化交易系统 - 设计系统

## 概述

基于 UI UX Pro Max Skill 生成的专业金融交易系统设计系统。

## 设计理念

- **风格**: Data-Dense Dashboard + Financial Dashboard + Glassmorphism
- **目标**: 专业、高效、数据密集、实时感
- **适用场景**: 股票交易、量化分析、实时行情监控

## 配色方案

### 主色调 (Navy Professional)

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-primary` | `#0F172A` | 主色（深蓝） |
| `--color-primary-light` | `#1E3A5F` | 主色亮版 |
| `--color-secondary` | `#334155` | 次要色 |
| `--color-accent` | `#0369A1` | 强调色（亮蓝） |
| `--color-accent-orange` | `#F97316` | CTA/操作按钮 |

### 功能色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-profit` | `#22C55E` | 盈利/上涨 |
| `--color-loss` | `#EF4444` | 亏损/下跌 |
| `--color-warning` | `#F59E0B` | 警告/注意 |
| `--color-info` | `#3B82F6` | 信息 |

### 背景色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-bg-primary` | `#0B0F19` | 深色主背景 |
| `--color-bg-secondary` | `#111827` | 次要背景 |
| `--color-bg-card` | `#1F2937` | 卡片背景 |
| `--color-bg-elevated` | `#374151` | 悬浮层背景 |

### 文字色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-text-primary` | `#F9FAFB` | 主要文字 |
| `--color-text-secondary` | `#9CA3AF` | 次要文字 |
| `--color-text-muted` | `#6B7280` | 弱化文字 |

### 边框色

| Token | Hex | 用途 |
|-------|-----|------|
| `--color-border` | `rgba(255,255,255,0.1)` | 细边框 |
| `--color-border-light` | `rgba(255,255,255,0.05)` | 更淡边框 |

## 字体系统

### 字体选择

- **标题**: IBM Plex Sans (Bold)
- **正文**: IBM Plex Sans (Regular/Medium)
- **数据/数字**: Fira Code (Monospace)

### Google Fonts 导入

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500;600;700&display=swap');
```

### Tailwind 配置

```javascript
fontFamily: {
  sans: ['IBM Plex Sans', 'sans-serif'],
  mono: ['Fira Code', 'monospace'],
}
```

### 字号规范

| 级别 | 大小 | 字重 | 行高 | 用途 |
|------|------|------|------|------|
| H1 | 24px | 700 | 1.2 | 页面标题 |
| H2 | 20px | 600 | 1.3 | 区块标题 |
| H3 | 16px | 600 | 1.4 | 卡片标题 |
| Body | 14px | 400 | 1.5 | 正文 |
| Small | 12px | 400 | 1.4 | 辅助文字 |
| Data | 14px | 500 | 1 | 数据/数字 |
| Label | 11px | 500 | 1 | 标签（大写） |

## 间距系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--space-xs` | 4px | 紧凑间距 |
| `--space-sm` | 8px | 小组件内边距 |
| `--space-md` | 12px | 标准内边距 |
| `--space-lg` | 16px | 卡片内边距 |
| `--space-xl` | 24px | 区块间距 |
| `--space-2xl` | 32px | 大区块间距 |

## 圆角系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-sm` | 4px | 小按钮、标签 |
| `--radius-md` | 6px | 输入框、卡片 |
| `--radius-lg` | 8px | 大卡片、弹窗 |
| `--radius-xl` | 12px | 特殊容器 |

## 效果与动画

### Glassmorphism 效果

```css
.glass {
  background: rgba(31, 41, 55, 0.7);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}
```

### 实时数据动画

```css
/* 数据更新闪烁 */
@keyframes dataUpdate {
  0% { background-color: rgba(34, 197, 94, 0.3); }
  100% { background-color: transparent; }
}

.data-updated {
  animation: dataUpdate 1s ease-out;
}

/* 实时指示器脉冲 */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.live-indicator {
  animation: pulse 2s infinite;
}
```

### 过渡效果

| 属性 | 时长 | 缓动 |
|------|------|------|
| Hover | 150ms | ease-out |
| Focus | 200ms | ease-out |
| Modal | 300ms | cubic-bezier(0.4, 0, 0.2, 1) |
| Data Update | 500ms | ease-out |

## 组件规范

### 按钮

**主按钮 (Primary)**
- 背景: `#F97316`
- 文字: `#FFFFFF`
- 圆角: 6px
- 内边距: 8px 16px
- Hover: 背景变亮 10%

**次按钮 (Secondary)**
- 背景: `rgba(255,255,255,0.1)`
- 文字: `#F9FAFB`
- 边框: 1px solid rgba(255,255,255,0.2)
- Hover: 背景变亮

**文字按钮 (Ghost)**
- 背景: transparent
- 文字: `#9CA3AF`
- Hover: 文字变白

### 卡片

**标准卡片**
- 背景: `#1F2937`
- 边框: 1px solid rgba(255,255,255,0.1)
- 圆角: 8px
- 内边距: 16px
- 可选: Glassmorphism 效果

**数据卡片 (KPI)**
- 背景: `#1F2937`
- 圆角: 8px
- 内边距: 12px
- 标题: 11px 大写, `#6B7280`
- 数值: 24px, Fira Code, 白色
- 变化: 12px, 涨跌色

### 表格

- 表头背景: `#111827`
- 表头文字: `#9CA3AF`, 11px 大写
- 行高: 40px
- 行边框: 1px solid rgba(255,255,255,0.05)
- Hover 行: `rgba(255,255,255,0.03)`
- 选中行: `rgba(3, 105, 161, 0.2)`

### 输入框

- 背景: `#111827`
- 边框: 1px solid rgba(255,255,255,0.1)
- 圆角: 6px
- 内边距: 8px 12px
- Focus: 边框色 `#0369A1`

### 标签/徽章

**状态标签**
- 内边距: 4px 8px
- 圆角: 4px
- 字号: 11px
- 字重: 500

| 状态 | 背景 | 文字 |
|------|------|------|
| 涨停 | `rgba(34, 197, 94, 0.2)` | `#22C55E` |
| 跌停 | `rgba(239, 68, 68, 0.2)` | `#EF4444` |
| 警示 | `rgba(245, 158, 11, 0.2)` | `#F59E0B` |
| 正常 | `rgba(59, 130, 246, 0.2)` | `#3B82F6` |

## 布局规范

### 整体布局

- 侧边栏: 260px 固定
- 顶部栏: 64px 固定
- 主内容区: 流式布局
- 最大内容宽度: 1920px

### 网格系统

- 12 列网格
- 间距: 16px
- 响应式断点:
  - Mobile: < 768px
  - Tablet: 768px - 1024px
  - Desktop: 1024px - 1440px
  - Large: > 1440px

### 数据密度

- 卡片间距: 12px
- 表格紧凑模式: 行高 32px
- 边距最小化以最大化数据展示

## 股票专用样式

### 涨跌颜色

```css
/* 上涨 */
.stock-up { color: #22C55E; }
.stock-up-bg { background-color: rgba(34, 197, 94, 0.1); }

/* 下跌 */
.stock-down { color: #EF4444; }
.stock-down-bg { background-color: rgba(239, 68, 68, 0.1); }

/* 平盘 */
.stock-neutral { color: #9CA3AF; }
```

### 价格显示

- 当前价: 18px, Fira Code, 白色
- 涨跌幅: 14px, 涨跌色
- 涨跌额: 12px, 次要文字色

### 迷你走势图

- 高度: 40px
- 上涨线: `#22C55E`
- 下跌线: `#EF4444`
- 填充: 对应颜色 20% 透明度

## 响应式适配

### 移动端 (< 768px)

- 侧边栏: 抽屉式
- 卡片: 单列堆叠
- 表格: 横向滚动
- 字号: 整体缩小 10%

### 平板 (768px - 1024px)

- 侧边栏: 可折叠
- 卡片: 2 列网格
- 表格: 自适应列宽

### 桌面端 (> 1024px)

- 侧边栏: 常驻
- 卡片: 3-4 列网格
- 表格: 完整展示

## 暗色模式

本设计系统默认为暗色主题，所有颜色已针对暗色环境优化。

## 无障碍要求

- 文字对比度: 至少 4.5:1
- 焦点状态: 清晰可见
- 动画: 支持 `prefers-reduced-motion`
- 图标: 配合文字标签

## 实现检查清单

- [ ] 无表情符号作为图标（使用 SVG: Heroicons/Lucide）
- [ ] 所有可点击元素有 `cursor-pointer`
- [ ] Hover 状态有平滑过渡 (150-300ms)
- [ ] 文字对比度符合 WCAG AA
- [ ] 焦点状态对键盘导航可见
- [ ] 支持 `prefers-reduced-motion`
- [ ] 响应式: 375px, 768px, 1024px, 1440px
