# 量化交易系统安装指南

## 系统要求

- **操作系统**: macOS / Linux / Windows (WSL)
- **Python**: 3.8+
- **Node.js**: 16+ (用于前端)
- **PostgreSQL**: 14+ (用于数据存储)
- **内存**: 建议 4GB+

## 安装步骤

### 1. 安装系统依赖

#### macOS
```bash
# 安装 PostgreSQL
brew install postgresql@14
brew services start postgresql@14

# 安装 Node.js (如果未安装)
brew install node
```

#### Linux (Ubuntu/Debian)
```bash
# 安装 PostgreSQL
sudo apt-get update
sudo apt-get install postgresql-14 postgresql-contrib

# 安装 Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 2. 创建数据库

```bash
# 创建数据库
createdb quantitative_trading

# 或使用 psql
psql -U postgres
CREATE DATABASE quantitative_trading;
\q
```

### 3. 恢复数据库

```bash
# 恢复数据库备份
psql -d quantitative_trading < database_backup.sql

# 或使用 postgres 用户
psql -U postgres -d quantitative_trading < database_backup.sql
```

### 4. 配置环境

#### 4.1 配置数据库连接

编辑 `data_warehouse/config.py`，修改 `DATABASE_URL`：

```python
DATABASE_URL = "postgresql://your_user@localhost:5432/quantitative_trading"
```

或使用环境变量：

```bash
export DATABASE_URL="postgresql://your_user@localhost:5432/quantitative_trading"
```

#### 4.2 配置API密钥（可选）

编辑 `config.json`，配置以下API密钥（如果需要）：

- **Tushare Token**: 用于财务数据（可选，系统主要使用AkShare）
- **OpenAI API Key**: 用于AI分析（可选）
- **Deepseek API Key**: 用于AI分析（可选）

### 5. 安装Python依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

### 6. 安装前端依赖

```bash
cd frontend-vue
npm install
cd ..
```

### 7. 初始化数据仓库（如果需要）

```bash
# 初始化数据库表结构（如果数据库是空的）
python -m data_warehouse.db_init

# 初始化股票维表
python -m data_warehouse.etl.init_stock_dim
```

### 8. 启动系统

#### 方式1: 使用启动脚本（推荐）

```bash
# 启动前后端
./start_all.sh

# 或分别启动
./start_backend.sh  # 后端: http://localhost:8000
./start_frontend.sh # 前端: http://localhost:3000
```

#### 方式2: 手动启动

```bash
# 启动后端
cd backend
python run.py

# 启动前端（新终端）
cd frontend-vue
npm run dev
```

### 9. 访问系统

- **前端地址**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

## 常见问题

### 问题1: 数据库连接失败

**解决**:
1. 确保PostgreSQL服务正在运行
2. 检查 `data_warehouse/config.py` 中的数据库连接配置
3. 确保数据库已创建: `createdb quantitative_trading`

### 问题2: 前端无法连接后端

**解决**:
1. 确保后端已启动: `./start_backend.sh`
2. 检查 `frontend-vue/vite.config.js` 中的代理配置
3. 检查防火墙设置

### 问题3: 数据源API错误

**解决**:
1. 检查网络连接
2. 某些API可能需要VPN（如Tushare）
3. 系统主要使用AkShare，无需配置即可使用

### 问题4: 前端依赖安装失败

**解决**:
```bash
# 清除缓存重新安装
cd frontend-vue
rm -rf node_modules package-lock.json
npm install
```

## 数据更新

系统首次运行后，需要更新数据：

1. 访问 **数据管理** 页面
2. 点击 **触发更新** 按钮，选择要更新的数据类型
3. 等待任务完成

或使用命令行：

```bash
# 更新日线数据
python backend/scripts/data_update/update_daily_from_snapshot.py

# 更新财务数据
python backend/scripts/data_update/run_fundamental_update_complete.py --limit 1000
```

## 目录结构说明

```
quantitative_trading/
├── backend/              # 后端代码
│   ├── api/             # API路由
│   ├── services/        # 业务逻辑
│   ├── models/          # 数据模型
│   ├── strategy/        # 策略引擎
│   └── scripts/         # 脚本工具
├── frontend-vue/         # 前端代码
│   └── src/             # Vue源码
├── data_warehouse/      # 数据仓库
│   ├── models/          # 数据库模型
│   ├── etl/             # ETL脚本
│   └── sources/         # 数据源客户端
├── config/              # 配置文件
├── utils/               # 工具函数
├── config.json          # 主配置文件
├── requirements.txt     # Python依赖
└── database_backup.sql  # 数据库备份
```

## 技术支持

如遇问题，请检查：
1. 日志文件: `logs/backend.log`
2. 后端日志: `backend/logs/`
3. 数据库连接状态
4. 网络连接状态

## 许可证

MIT License
