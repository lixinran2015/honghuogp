# 产品化脚本目录

本目录包含将「短线龙头智能跟踪系统」从个人项目推向商业化的辅助脚本与配置。

## 目录结构

- `deploy/` — 生产环境 Docker Compose 配置与一键部署脚本
- `daily_report/` — 每日龙头日报自动生成脚本与模板
- `tests/` — 产品化脚本的单元测试

## 快速开始

> 以下命令假设你当前位于项目根目录，且虚拟环境为 `.venv/`。

### 1. 部署远程环境

```bash
cd scripts/productization/deploy
./deploy.sh
```

### 2. 生成每日日报

确保后端服务已启动，然后执行：

```bash
../../.venv/bin/python scripts/productization/daily_report/generate_daily_report.py \
    --output ./daily_reports/$(date +%Y-%m-%d).md
```

### 3. 运行测试

```bash
../../.venv/bin/python -m pytest scripts/productization/tests/test_daily_report.py -v
```

## 合规提示

- 所有对外发布的日报内容必须通过 `copywriting.py` 进行去投顾化处理。
- 不得在公开内容中使用「推荐买入」「目标价」「必涨」「仓位建议」等话术。
- 每篇内容底部必须附加免责声明。
