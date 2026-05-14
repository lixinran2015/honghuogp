# 日报页面生成按钮设计文档

**日期**: 2026-04-14  
**功能**: 在 `/daily-report` 页面增加「生成日报」按钮，点击后生成新的日报并自动展示。

---

## 1. 前端改动

### 1.1 页面: `frontend-vue/src/views/DailyReportView.vue`

- 在标题栏右侧、日期选择器和「加载日报」按钮旁边，新增一个「生成日报」按钮。
- 按钮样式与现有按钮保持一致，使用主色调（`bg-cta`）。
- 按钮具备独立的 `generating` 加载状态：
  - 请求期间按钮禁用并显示转圈动画。
  - 防止用户重复点击。
- 点击后调用后端 API：`POST /api/short-term/dashboard/generate-daily-report`。
- API 返回成功时：
  - 将 `selectedDate` 更新为返回的 `trade_date`。
  - 自动调用 `loadReport()` 重新加载并展示最新日报。
- API 返回失败时：
  - 在页面现有错误提示区域展示错误信息（复用 `error` 状态和样式）。

---

## 2. 后端改动

### 2.1 API 端点: `backend/api/short_term/dashboard.py`

新增 `POST /api/short-term/dashboard/generate-daily-report` 端点：

```python
@router.post("/generate-daily-report")
async def generate_daily_report():
    """生成每日短线龙头日报 HTML 文件。"""
```

**处理逻辑：**
1. 导入 `scripts.productization.daily_report.generate_daily_report` 中的 `generate_report` 函数。
2. 调用 `generate_report()`，不传入 `output_path` 先获取 `trade_date` 和 HTML 内容；或者先获取 `trade_date`，再计算 `output_path` 重新生成/直接写入。
   - 实际上更优做法：直接 import `generate_report`，传入计算好的 `output_path`。
   - `output_path` = `<project_root>/frontend-vue/public/daily-reports/{trade_date}.html`
3. 若生成成功，返回：
   ```json
   {"success": true, "data": {"trade_date": "2026-04-14", "file_path": "2026-04-14.html"}}
   ```
4. 若生成过程抛出异常，捕获后返回 HTTP 500 并附带错误详情。

---

## 3. 数据流

```
用户点击「生成日报」
    ↓
前端发送 POST /api/short-term/dashboard/generate-daily-report
    ↓
后端调用 generate_daily_report.generate_report(output_path=...)
    ↓
脚本生成 HTML 并写入 frontend-vue/public/daily-reports/{date}.html
    ↓
后端返回 {trade_date, file_path}
    ↓
前端更新 selectedDate 并调用 loadReport()
    ↓
页面展示最新日报
```

---

## 4. 错误处理

| 场景 | 行为 |
|------|------|
| 日报生成脚本异常 | 后端返回 500，前端展示错误提示 |
| 网络请求失败 | 前端展示 `error` 信息 |
| 生成中用户再次点击 | 按钮禁用，防止重复请求 |

---

## 5. 依赖与限制

- 后端生成脚本依赖 `HH_API_BASE_URL` 环境变量（默认 `http://localhost:8000`），确保后端在生成时能访问自身 API。
- 生成的 HTML 文件直接写入前端 public 目录，适用于当前开发/部署模式（前后端同仓库）。
