body"` 要求 Vue 3 有 `<teleport>` 支持——项目使用 Vue 3，无需额外依赖。

- [ ] **Step 4.2: 验证编译**

Run:
```bash
cd /Users/lxr/workspace/honghuogp/frontend-vue
npm run build 2>&1 | tail -20
```

Expected: 无语法错误，build 成功（或至少没有 `ShortTermLeaderDashboard.vue` 相关报错）。

- [ ] **Step 4.3: Commit**

```bash
git add frontend-vue/src/views/ShortTermLeaderDashboard.vue
git commit -m "feat(dashboard): add right-side detail drawer for S-grade stocks"
```

---

## Spec 自检对照

| 设计文档要求 | 对应任务/步骤 |
|--------------|---------------|
| 仅 S 级股票名称可点击 | Task 3 Step 3.1 |
| 右侧滑出抽屉 | Task 4 Step 4.1 （抽屉面板 + 遮罩 + transition） |
| 后端统一聚合 API | Task 1 Step 1.1 ~ 1.3 |
| AI 评分/买点/交易计划/板块支撑 | Task 1 Step 1.2 `_build_stock_detail_response` |
| 查看K线跳转 | Task 4 Step 4.1 底部按钮 `@click="$router.push('/leader-tracking?code=...')"` |
| ESC/遮罩关闭 | Task 3 Step 3.4 + Task 4 Step 4.1 遮罩 `@click="closeDrawer"` |
| 单元测试覆盖 | Task 2 Step 2.1 ~ 2.2 |

---

## 执行方式选择

**Plan complete and saved to `docs/superpowers/plans/2026-04-05-s-level-stock-detail-drawer.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
