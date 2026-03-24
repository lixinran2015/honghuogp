# 打包内容清单

## 打包时间
20251124_204525

## 包含内容

### 核心代码
- `backend/` - 后端代码（FastAPI）
- `frontend-vue/` - 前端代码（Vue.js，不包含node_modules）
- `data_warehouse/` - 数据仓库代码
- `config/` - 配置文件
- `utils/` - 工具函数

### 配置文件
- `config.json` - 主配置文件
- `requirements.txt` - Python依赖
- `backend/requirements.txt` - 后端依赖
- `frontend-vue/package.json` - 前端依赖

### 启动脚本
- `start_all.sh` - 启动前后端
- `start_backend.sh` - 启动后端
- `start_frontend.sh` - 启动前端
- `quick_start.sh` - 快速启动（自动安装依赖）

### 数据库
- `database_backup.sql` - PostgreSQL数据库备份

### 文档
- `INSTALL.md` - 安装指南
- `README.md` - 项目说明
- `docs/` - 技术文档

## 排除内容

以下内容未包含在打包中（需要用户自行生成）：
- `node_modules/` - 前端依赖（运行 `npm install` 安装）
- `__pycache__/` - Python缓存
- `.venv/` - Python虚拟环境（需要用户创建）
- `logs/` - 日志文件
- `archive/` - 归档文件
- `*.log` - 日志文件
- `.git/` - Git版本控制

## 文件大小

```
8.9G
```

## 安装后需要执行

1. 安装Python依赖: `pip install -r requirements.txt`
2. 安装前端依赖: `cd frontend-vue && npm install`
3. 恢复数据库: `psql -d quantitative_trading < database_backup.sql`
4. 配置数据库连接: 编辑 `data_warehouse/config.py`
5. 启动系统: `./start_all.sh`
