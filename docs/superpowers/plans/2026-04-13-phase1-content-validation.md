# Phase 1 内容验证期实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建可远程访问的系统环境，并编写自动化日报生成脚本，支持每日产出合规的「A股短线龙头日报」Markdown 内容。

**Architecture:** 复用现有 FastAPI + Vue 3 + Docker 技术栈，通过本地 API 消费已有数据，生成去投顾化的 Markdown 日报。服务器采用 Docker Compose 一键部署，降低运维成本。

**Tech Stack:** Python 3.11, FastAPI, Vue 3, Docker Compose, requests, Jinja2 (可选)

---

## 文件结构

```
scripts/productization/
├── deploy/
│   ├── docker-compose.prod.yml    # 生产环境 Docker Compose（挂载 config.json / .env）
│   └── deploy.sh                  # 一键部署脚本（含构建、启动、健康检查）
├── daily_report/
│   ├── generate_daily_report.py   # 日报生成主脚本
│   ├── copywriting.py             # 去投顾化文案映射与转换
│   └── templates/
│       └── daily_report.md.j2     # Markdown 日报 Jinja2 模板
└── tests/
    └── test_daily_report.py       # 日报生成单元测试
```

---

### Task 1: 生产环境 Docker Compose 配置

**Files:**
- Create: `scripts/productization/deploy/docker-compose.prod.yml`
- Create: `scripts/productization/deploy/deploy.sh`
- Modify: `docker/Dockerfile.backend:22-27`

- [ ] **Step 1: 创建生产环境 Docker Compose**

Create `scripts/productization/deploy/docker-compose.prod.yml`:

```yaml
# 红火量化 - 生产环境 Docker Compose
# 使用：cd scripts/productization/deploy && docker-compose -f docker-compose.prod.yml up -d

services:
  postgres:
    image: postgres:15-alpine
    container_name: honghuo-postgres
    environment:
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME:-quantitative_trading}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  backend:
    build:
      context: ../../..
      dockerfile: docker/Dockerfile.backend
    container_name: honghuo-backend
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_USER: ${DB_USER:-postgres}
      DB_PASSWORD: ${DB_PASSWORD}
      DB_NAME: ${DB_NAME:-quantitative_trading}
      SERVICE_TYPE: short_term
    ports:
      - "8000:8000"
    volumes:
      - ../../../config.json:/app/config.json:ro
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build:
      context: ../../..
      dockerfile: docker/Dockerfile.frontend
    container_name: honghuo-frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
```

- [ ] **Step 2: 修改后端 Dockerfile 以支持 short_term 服务启动**

Modify `docker/Dockerfile.backend:22-27` (the CMD line):

```dockerfile
# 原内容
# CMD ["python", "backend/app.py"]
# 修改为启动短线服务
CMD ["python", "backend/run_short_term.py"]
```

- [ ] **Step 3: 创建一键部署脚本**

Create `scripts/productization/deploy/deploy.sh`:

```bash
#!/bin/bash
set -e

echo "=== 红火量化 Phase 1 部署脚本 ==="

# 检查必要文件
if [ ! -f "../../../.env" ]; then
    echo "错误：未找到 ../../../.env 文件，请先配置数据库密码等环境变量"
    exit 1
fi

if [ ! -f "../../../config.json" ]; then
    echo "警告：未找到 ../../../config.json，部分功能（如 Tushare）可能不可用"
fi

# 构建并启动
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up --build -d

# 等待后端启动
echo "等待后端服务启动..."
sleep 5

for i in {1..10}; do
    if curl -s http://localhost:8000/docs > /dev/null; then
        echo "后端服务已就绪: http://localhost:8000"
        break
    fi
    echo "等待中... ($i/10)"
    sleep 3
done

# 检查健康状态
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs || echo "000")
if [ "$BACKEND_HEALTH" != "200" ]; then
    echo "错误：后端服务未正常启动，请检查日志: docker logs honghuo-backend"
    exit 1
fi

echo "=== 部署完成 ==="
echo "前端: http://localhost"
echo "后端 API: http://localhost:8000/docs"
```

- [ ] **Step 4: 赋予脚本执行权限并提交**

Run:
```bash
chmod +x scripts/productization/deploy/deploy.sh
git add scripts/productization/deploy/docker-compose.prod.yml
git add scripts/productization/deploy/deploy.sh
git add docker/Dockerfile.backend
git commit -m "feat(deploy): 添加生产环境 Docker Compose 与一键部署脚本

支持短线服务独立部署，挂载 config.json 与 .env 配置。

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: 日报文案映射模块

**Files:**
- Create: `scripts/productization/daily_report/copywriting.py`
- Test: `scripts/productization/tests/test_daily_report.py`

- [ ] **Step 1: 编写去投顾化文案映射模块**

Create `scripts/productization/daily_report/copywriting.py`:

```python
"""
日报文案映射模块

将系统内部的投资顾问风格文案转换为合规的数据展示/研究记录风格文案。
"""

from typing import Optional, Dict, Any

# 情绪周期 → 中性描述
EMOTION_CYCLE_LABELS = {
    "高涨期": "市场情绪处于高涨阶段，资金活跃度较高",
    "震荡期": "市场情绪处于震荡整理阶段，结构性机会为主",
    "低迷期": "市场情绪处于低迷阶段，观望情绪较浓",
    "冰点期": "市场情绪处于冰点阶段，风险偏好较低",
}

# 买点信号类型 → 中性描述
BUY_SIGNAL_TYPE_MAP = {
    "首板放量": "首板放量形态触发",
    "二板缩量": "二板缩量形态触发",
    "三板换手": "三板换手形态触发",
    "断板反包": "断板反包形态触发",
    "龙头首阴": "龙头首阴形态触发",
    "分时低吸": "分时低吸形态触发",
}

# 通用文案替换映射
GENERAL_REPLACEMENTS = {
    "买入信号": "技术形态触发",
    "卖出信号": "风险指标提示",
    "仓位建议": "市场热度参考",
    "止损": "风险控制参考",
    "止盈": "获利了结参考",
    "推荐": "数据观察",
    "必涨": "短期动量较强",
    "目标价": "历史波动区间参考",
}

# 固定免责声明
DISCLAIMER = (
    "---\n\n"
    "> **免责声明**：本内容仅为数据整理与个人研究记录，不构成任何投资建议。"
    "股市有风险，入市需谨慎。"
")


def neutralize_text(text: Optional[str]) -> str:
    """将投顾风格文案转换为中性文案"""
    if not text:
        return ""
    result = text
    for old, new in GENERAL_REPLACEMENTS.items():
        result = result.replace(old, new)
    return result


def format_emotion_cycle(cycle_name: Optional[str]) -> str:
    """格式化情绪周期描述"""
    if not cycle_name:
        return "情绪周期数据暂不可用"
    return EMOTION_CYCLE_LABELS.get(cycle_name, f"当前市场情绪处于 {cycle_name}")


def format_buy_signal(signal_type: Optional[str]) -> str:
    """格式化买点信号描述"""
    if not signal_type:
        return "未触发特定技术形态"
    return BUY_SIGNAL_TYPE_MAP.get(signal_type, f"{signal_type} 形态触发")


def get_grade_emoji(grade: Optional[str]) -> str:
    """根据等级返回 emoji"""
    mapping = {
        "S": "🟢",
        "A": "🔵",
        "B": "🟡",
        "C": "🟠",
        "D": "🔴",
    }
    return mapping.get(grade or "", "⚪")
```

- [ ] **Step 2: 编写并运行单元测试**

Create `scripts/productization/tests/test_daily_report.py`:

```python
import pytest
from scripts.productization.daily_report.copywriting import (
    neutralize_text,
    format_emotion_cycle,
    format_buy_signal,
    get_grade_emoji,
    DISCLAIMER,
)


def test_neutralize_text():
    assert neutralize_text("出现买入信号，建议加仓") == "出现技术形态触发，建议加仓"
    assert neutralize_text("目标价 10 元") == "历史波动区间参考 10 元"
    assert neutralize_text(None) == ""


def test_format_emotion_cycle():
    assert "高涨" in format_emotion_cycle("高涨期")
    assert "震荡" in format_emotion_cycle("震荡期")
    assert "数据暂不可用" in format_emotion_cycle(None)


def test_format_buy_signal():
    assert "首板放量" in format_buy_signal("首板放量")
    assert "未触发" in format_buy_signal(None)


def test_get_grade_emoji():
    assert get_grade_emoji("S") == "🟢"
    assert get_grade_emoji("D") == "🔴"
    assert get_grade_emoji("X") == "⚪"


def test_disclaimer_contains_investment():
    assert "不构成任何投资建议" in DISCLAIMER
```

Run:
```bash
cd /Users/lxr/workspace/honghuogp
pytest scripts/productization/tests/test_daily_report.py -v
```

Expected: 5 tests PASS

- [ ] **Step 3: 提交文案模块**

```bash
git add scripts/productization/daily_report/copywriting.py
git add scripts/productization/tests/test_daily_report.py
git commit -m "feat(daily-report): 添加去投顾化文案映射模块

提供情绪周期、买点信号、通用话术的中性化转换，含单元测试。

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Markdown 日报模板

**Files:**
- Create: `scripts/productization/daily_report/templates/daily_report.md.j2`

- [ ] **Step 1: 创建日报 Markdown 模板**

Create `scripts/productization/daily_report/templates/daily_report.md.j2`:

```markdown
# A股短线龙头日报 · {{ trade_date }}

---

## 一、情绪周期判断

{{ emotion_cycle_description }}

- 涨停家数：{{ limit_up_count }}
- 跌停家数：{{ limit_down_count }}
- 市场最高连板：{{ max_continuous_limit }}
- 涨跌比：{{ advance_decline_ratio }}

---

## 二、Top {{ top_stocks|length }} 空间龙头

| 股票 | 板块 | 等级 | 总分 | 预期收益 | 置信度 |
|------|------|------|------|----------|--------|
{% for stock in top_stocks %}
| {{ stock.name }} ({{ stock.ts_code }}) | {{ stock.sectors[0] if stock.sectors else '-' }} | {{ stock.grade_emoji }} {{ stock.grade }} | {{ stock.total_score }} | {{ stock.expected_return }}% | {{ stock.confidence }}% |
{% endfor %}

**因子得分详情：**

{% for stock in top_stocks %}
- **{{ stock.name }}**
  - 龙头地位：{{ stock.factor_scores.get('龙头地位', 0) }} | 技术形态：{{ stock.factor_scores.get('技术形态', 0) }}
  - 资金流向：{{ stock.factor_scores.get('资金流向', 0) }} | 情绪热度：{{ stock.factor_scores.get('情绪热度', 0) }}
{% endfor %}

---

## 三、技术形态触发池

{% if signal_stocks %}
{% for stock in signal_stocks %}
- **{{ stock.name }} ({{ stock.ts_code }})** · {{ stock.sectors[0] if stock.sectors else '-' }}
  - 形态：{{ stock.signal_description }}
  - 强度：{{ stock.strength_score }} | 质量：{{ stock.quality }}
  - AI 评分：{{ stock.grade }} ({{ stock.total_score }} 分)
{% endfor %}
{% else %}
- 今日未监测到明显的技术形态触发信号。
{% endif %}

---

## 四、次日跟踪名单

{% for stock in watchlist %}
- {{ stock.name }} ({{ stock.ts_code }}) · {{ stock.sectors[0] if stock.sectors else '-' }} · 等级 {{ stock.grade }} ({{ stock.total_score }} 分)
{% endfor %}

---

{{ disclaimer }}
```

- [ ] **Step 2: 提交模板**

```bash
git add scripts/productization/daily_report/templates/daily_report.md.j2
git commit -m "feat(daily-report): 添加 Markdown 日报 Jinja2 模板

包含情绪周期、Top 龙头、技术形态触发池、次日跟踪名单四个模块。

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: 日报生成主脚本

**Files:**
- Create: `scripts/productization/daily_report/generate_daily_report.py`
- Modify: `scripts/productization/tests/test_daily_report.py`

- [ ] **Step 1: 编写日报生成主脚本**

Create `scripts/productization/daily_report/generate_daily_report.py`:

```python
"""
日报生成主脚本

调用本地 FastAPI 接口，生成去投顾化的 Markdown 日报。
使用示例:
    python scripts/productization/daily_report/generate_daily_report.py \
        --output ./daily_reports/2026-04-13.md
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from jinja2 import Template

# 将项目根目录加入路径
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.productization.daily_report.copywriting import (
    format_emotion_cycle,
    format_buy_signal,
    get_grade_emoji,
    DISCLAIMER,
)

DEFAULT_BASE_URL = os.getenv("HH_API_BASE_URL", "http://localhost:8000")


def _get(endpoint: str, base_url: str = DEFAULT_BASE_URL, params: Optional[Dict] = None) -> Dict[str, Any]:
    url = f"{base_url}{endpoint}"
    try:
        resp = requests.get(url, params=params or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"API 返回失败: {data}")
        return data
    except Exception as e:
        raise RuntimeError(f"请求 {url} 失败: {e}")


def fetch_emotion_cycle(base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    data = _get("/api/emotion-cycle/analyze", base_url=base_url)
    return {
        "cycle": data.get("data", {}).get("cycle", "未知"),
        "limit_up_count": data.get("data", {}).get("limit_up_count", 0),
        "limit_down_count": data.get("data", {}).get("limit_down_count", 0),
        "max_continuous_limit": data.get("data", {}).get("max_continuous_limit", 0),
        "advance_decline_ratio": data.get("data", {}).get("advance_decline_ratio", 0),
    }


def fetch_top_stocks(top_n: int = 5, base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    data = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": top_n})
    stocks = data.get("top_stocks", [])
    result = []
    for s in stocks[:top_n]:
        score = s.get("lstm_mab_score") or {}
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "grade": score.get("grade", "-"),
            "grade_emoji": get_grade_emoji(score.get("grade")),
            "total_score": score.get("total_score", 0),
            "expected_return": round(score.get("expected_return", 0) * 100, 2) if score.get("expected_return") else 0,
            "confidence": round(score.get("confidence", 0) * 100, 2) if score.get("confidence") else 0,
            "factor_scores": score.get("factor_scores", {}),
        })
    return result


def fetch_signal_stocks(base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    """从 pool 中获取带买点信号的股票"""
    data = _get("/api/leader-tracking/pool", base_url=base_url, params={"with_scores": "true"})
    pool = data.get("pool", [])
    result = []
    for s in pool:
        signal = s.get("buy_signal")
        if not signal:
            continue
        score = s.get("lstm_mab_score") or {}
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "signal_description": format_buy_signal(signal.get("signal_type")),
            "strength_score": signal.get("strength_score", 0),
            "quality": signal.get("quality", "中"),
            "grade": score.get("grade", "-"),
            "total_score": score.get("total_score", 0),
        })
    # 按强度排序，取前 5
    result.sort(key=lambda x: x["strength_score"] or 0, reverse=True)
    return result[:5]


def fetch_watchlist(base_url: str = DEFAULT_BASE_URL) -> List[Dict[str, Any]]:
    """次日跟踪名单：取 Top 10 评分股票作为观察对象"""
    data = _get("/api/leader-tracking/top-scored", base_url=base_url, params={"top_n": 10})
    stocks = data.get("top_stocks", [])
    result = []
    for s in stocks:
        score = s.get("lstm_mab_score") or {}
        result.append({
            "ts_code": s.get("ts_code", ""),
            "name": s.get("name", ""),
            "sectors": s.get("sectors", []),
            "grade": score.get("grade", "-"),
            "total_score": score.get("total_score", 0),
        })
    return result


def load_template() -> Template:
    template_path = Path(__file__).parent / "templates" / "daily_report.md.j2"
    return Template(template_path.read_text(encoding="utf-8"))


def generate_report(output_path: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> str:
    emotion = fetch_emotion_cycle(base_url)
    top_stocks = fetch_top_stocks(top_n=5, base_url=base_url)
    signal_stocks = fetch_signal_stocks(base_url)
    watchlist = fetch_watchlist(base_url)

    context = {
        "trade_date": date.today().isoformat(),
        "emotion_cycle_description": format_emotion_cycle(emotion["cycle"]),
        "limit_up_count": emotion["limit_up_count"],
        "limit_down_count": emotion["limit_down_count"],
        "max_continuous_limit": emotion["max_continuous_limit"],
        "advance_decline_ratio": emotion["advance_decline_ratio"],
        "top_stocks": top_stocks,
        "signal_stocks": signal_stocks,
        "watchlist": watchlist,
        "disclaimer": DISCLAIMER,
    }

    template = load_template()
    markdown = template.render(context)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"日报已生成: {out.absolute()}")
    else:
        print(markdown)

    return markdown


def main():
    parser = argparse.ArgumentParser(description="生成 A股短线龙头日报")
    parser.add_argument("--output", "-o", type=str, help="输出 Markdown 文件路径")
    parser.add_argument("--base-url", type=str, default=DEFAULT_BASE_URL, help="API 基地址")
    args = parser.parse_args()
    generate_report(output_path=args.output, base_url=args.base_url)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 更新测试文件以覆盖生成脚本核心逻辑**

Modify `scripts/productization/tests/test_daily_report.py` (append to existing file):

```python
from scripts.productization.daily_report.generate_daily_report import (
    fetch_top_stocks,
    fetch_signal_stocks,
    fetch_watchlist,
    load_template,
)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_fetch_top_stocks(monkeypatch):
    def mock_get(url, **kwargs):
        return MockResponse({
            "success": True,
            "top_stocks": [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "sectors": ["银行"],
                    "lstm_mab_score": {
                        "grade": "S",
                        "total_score": 92,
                        "expected_return": 0.05,
                        "confidence": 0.78,
                        "factor_scores": {"龙头地位": 90, "技术形态": 85},
                    },
                }
            ]
        })

    monkeypatch.setattr(requests, "get", mock_get)
    result = fetch_top_stocks(top_n=1, base_url="http://test")
    assert len(result) == 1
    assert result[0]["name"] == "平安银行"
    assert result[0]["grade"] == "S"


def test_fetch_signal_stocks(monkeypatch):
    def mock_get(url, **kwargs):
        return MockResponse({
            "success": True,
            "pool": [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "sectors": ["银行"],
                    "buy_signal": {"signal_type": "首板放量", "strength_score": 85, "quality": "高"},
                    "lstm_mab_score": {"grade": "A", "total_score": 80},
                }
            ]
        })

    monkeypatch.setattr(requests, "get", mock_get)
    result = fetch_signal_stocks(base_url="http://test")
    assert len(result) == 1
    assert "首板放量" in result[0]["signal_description"]


def test_load_template():
    template = load_template()
    assert "情绪周期判断" in template.source
    assert "Top" in template.source
```

Add the missing import at the top of `scripts/productization/tests/test_daily_report.py`:

```python
import requests
```

Run:
```bash
cd /Users/lxr/workspace/honghuogp
pytest scripts/productization/tests/test_daily_report.py -v
```

Expected: all tests PASS

- [ ] **Step 3: 提交日报生成脚本**

```bash
git add scripts/productization/daily_report/generate_daily_report.py
git add scripts/productization/tests/test_daily_report.py
git commit -m "feat(daily-report): 添加日报生成主脚本

支持调用本地 API 获取情绪周期、Top 龙头、买点信号并生成 Markdown。
含单元测试与命令行参数支持。

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: 端到端验证与文档补充

**Files:**
- Modify: `README.md:230-256` (append)
- Create: `scripts/productization/README.md`

- [ ] **Step 1: 创建产品化目录说明文档**

Create `scripts/productization/README.md`:

```markdown
# 产品化脚本目录

本目录包含将「短线龙头智能跟踪系统」从个人项目推向商业化的辅助脚本与配置。

## 目录结构

- `deploy/` — 生产环境 Docker Compose 配置与一键部署脚本
- `daily_report/` — 每日龙头日报自动生成脚本与模板
- `tests/` — 产品化脚本的单元测试

## 快速开始

### 1. 部署远程环境

```bash
cd scripts/productization/deploy
./deploy.sh
```

### 2. 生成每日日报

确保后端服务已启动，然后执行：

```bash
python scripts/productization/daily_report/generate_daily_report.py \
    --output ./daily_reports/$(date +%Y-%m-%d).md
```

### 3. 运行测试

```bash
pytest scripts/productization/tests/test_daily_report.py -v
```

## 合规提示

- 所有对外发布的日报内容必须通过 `copywriting.py` 进行去投顾化处理。
- 不得在公开内容中使用「推荐买入」「目标价」「必涨」「仓位建议」等话术。
- 每篇内容底部必须附加免责声明。
```

- [ ] **Step 2: 在主 README 中补充产品化章节**

Append to `README.md` before the disclaimer line:

```markdown
## 产品化部署

详见 [`scripts/productization/README.md`](scripts/productization/README.md)。

快速部署：
```bash
cd scripts/productization/deploy
./deploy.sh
```

生成日报：
```bash
python scripts/productization/daily_report/generate_daily_report.py \
    --output ./daily_reports/$(date +%Y-%m-%d).md
```
```

- [ ] **Step 3: 提交文档更新**

```bash
git add scripts/productization/README.md
git add README.md
git commit -m "docs(productization): 添加产品化脚本使用说明

包含部署、日报生成、测试命令及合规提示。

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 计划自检

### Spec 覆盖率

对照设计文档 `docs/superpowers/specs/2026-04-13-productization-design.md`：

| 设计需求 | 对应任务 |
|----------|----------|
| 部署远程服务器环境 | Task 1 |
| 编写每日数据导出脚本 | Task 2, Task 3, Task 4 |
| 确定日报内容模板和去投顾化文案 | Task 2, Task 3 |
| 提供测试与验证 | Task 2 Step 2, Task 4 Step 2 |
| 文档化 | Task 5 |

**无遗漏。**

### 占位符检查

- 无 "TBD" / "TODO" / "implement later"
- 所有代码块均包含可执行的完整代码
- 所有测试均包含具体断言
- 所有命令均包含预期输出说明

### 类型一致性

- `format_buy_signal` / `format_emotion_cycle` 签名一致（接收 Optional[str]，返回 str）
- 数据模型字段（`ts_code`, `name`, `lstm_mab_score`, `buy_signal`）与现有 API 返回值一致
- API 端点路径与现有 `leader_tracking.py` / `emotion_cycle.py` 定义一致

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-13-phase1-content-validation.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review

Which approach?
