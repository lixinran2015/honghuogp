# PostgreSQL 安装和配置指南

## macOS 安装 PostgreSQL

### 方式1：使用 Homebrew（推荐）

```bash
# 安装 PostgreSQL 14
brew install postgresql@14

# 启动服务
brew services start postgresql@14

# 添加到 PATH（如果还没有）
echo 'export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 方式2：使用 Postgres.app

1. 下载并安装 [Postgres.app](https://postgresapp.com/)
2. 启动应用
3. 数据库会自动创建在默认位置

## 创建数据库

```bash
# 创建数据库
createdb quantitative_trading

# 或使用 psql
psql postgres
CREATE DATABASE quantitative_trading;
\q
```

## 配置数据库连接

### 方式1：环境变量（推荐）

```bash
# 默认配置（postgres用户，无密码）
export DATABASE_URL="postgresql://postgres@localhost:5432/quantitative_trading"

# 或使用密码
export DATABASE_URL="postgresql://postgres:your_password@localhost:5432/quantitative_trading"
```

### 方式2：修改配置文件

编辑 `data_warehouse/config.py`，修改 `DATABASE_URL`

## 验证连接

```bash
# 测试连接
psql -d quantitative_trading -c "SELECT version();"
```

## 初始化数据仓库

```bash
cd /Users/wuyanze/quantitative_trading
python -m data_warehouse.db_init
```

## 常见问题

### 问题1：`createdb: command not found`

**解决**：PostgreSQL 未安装或不在 PATH 中

```bash
# 检查是否安装
brew list postgresql@14

# 添加到 PATH
export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"
```

### 问题2：`psql: FATAL: database "quantitative_trading" does not exist`

**解决**：先创建数据库

```bash
createdb quantitative_trading
```

### 问题3：`psql: FATAL: password authentication failed`

**解决**：检查数据库用户和密码配置

```bash
# 查看当前用户
whoami

# 使用当前系统用户连接（如果Postgres.app）
psql -d quantitative_trading
```

### 问题4：`could not connect to server`

**解决**：确保 PostgreSQL 服务正在运行

```bash
# 检查服务状态
brew services list

# 启动服务
brew services start postgresql@14
```

