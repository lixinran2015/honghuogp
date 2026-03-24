# 智能选股系统 - Vue3 + Tailwind 版本

参考 Linear、Stripe、Notion 设计风格的响应式 Web 界面。

## 设计特点

### 布局结构
- **顶部导航栏**：固定顶部，包含 Logo、标题和操作按钮
- **左侧菜单**：固定左侧，宽度 256px，包含主要导航项
- **主内容区**：自适应宽度，卡片式布局

### 配色方案
- **背景**：极浅灰色 (`gray-50`)
- **卡片**：纯白色背景，细边框 (`border-gray-200`)
- **主色**：蓝色 (`primary-500`)，用于强调和交互
- **文字**：深灰色 (`gray-900`) 主文字，`gray-500` 辅助文字

### 组件设计
- **可复用组件**：Button、Card、Table、StatCard、FilterBar 等
- **统一间距**：使用 Tailwind 的 spacing scale
- **统一圆角**：`rounded-lg` (12px) 和 `rounded-xl` (16px)
- **统一阴影**：双层阴影效果，参考 Stripe

## 项目结构

```
frontend-vue/
├── src/
│   ├── components/
│   │   ├── layout/          # 布局组件
│   │   │   ├── AppHeader.vue
│   │   │   ├── Sidebar.vue
│   │   │   └── NavItem.vue
│   │   └── ui/              # UI 组件
│   │       ├── Button.vue
│   │       ├── Card.vue
│   │       ├── StatCard.vue
│   │       ├── Table.vue
│   │       ├── TableRow.vue
│   │       ├── TableCell.vue
│   │       ├── FilterBar.vue
│   │       └── FilterButton.vue
│   ├── views/               # 页面视图
│   │   ├── RecommendationsView.vue
│   │   ├── MonthlyHotspotsView.vue
│   │   ├── DarwinView.vue
│   │   └── StrategyView.vue
│   ├── App.vue
│   ├── main.js
│   └── index.css
├── package.json
├── tailwind.config.js
├── vite.config.js
└── README.md
```

## 安装和运行

```bash
cd frontend-vue
npm install
npm run dev
```

## 设计原则

1. **极简风格**：参考 Linear/Stripe，减少视觉噪音
2. **充足留白**：卡片间距、内边距充足
3. **清晰层级**：标题、正文、辅助文字层次分明
4. **统一组件**：所有 UI 元素使用统一的设计语言
5. **响应式设计**：适配不同屏幕尺寸

