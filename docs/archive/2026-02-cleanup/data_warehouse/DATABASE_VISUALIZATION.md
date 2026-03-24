# PostgreSQL 数据库可视化工具指南

## 推荐工具（macOS）

### 1. TablePlus ⭐⭐⭐⭐⭐（最推荐）

**特点：**
- 界面美观，操作简单
- 支持多种数据库（PostgreSQL, MySQL, SQLite等）
- 快速查询和编辑
- 支持多标签页

**安装：**
```bash
brew install --cask tableplus
```

**连接配置：**
- 类型: PostgreSQL
- 主机: `localhost`
- 端口: `5432`
- 用户名: `wuyanze`
- 密码: (留空)
- 数据库: `quantitative_trading`

**下载地址：** https://tableplus.com/

---

### 2. Postico ⭐⭐⭐⭐

**特点：**
- macOS 原生应用，界面精美
- 轻量级，启动快速
- 专为 PostgreSQL 设计
- 简单易用

**安装：**
```bash
brew install --cask postico
```

**连接配置：**
- 主机: `localhost`
- 端口: `5432`
- 用户: `wuyanze`
- 密码: (留空)
- 数据库: `quantitative_trading`

**下载地址：** https://eggerapps.at/postico/

---

### 3. DBeaver ⭐⭐⭐⭐

**特点：**
- 免费开源
- 功能强大，支持多种数据库
- 跨平台（Windows, macOS, Linux）
- 支持 SQL 编辑、数据导出等

**安装：**
```bash
brew install --cask dbeaver-community
```

**连接配置：**
1. 新建连接 → PostgreSQL
2. 主机: `localhost`
3. 端口: `5432`
4. 数据库: `quantitative_trading`
5. 用户名: `wuyanze`
6. 密码: (留空)

**下载地址：** https://dbeaver.io/

---

### 4. pgAdmin ⭐⭐⭐

**特点：**
- PostgreSQL 官方管理工具
- 功能全面（备份、恢复、监控等）
- 界面较复杂，适合高级用户

**安装：**
```bash
brew install --cask pgadmin4
```

**连接配置：**
- 主机: `localhost`
- 端口: `5432`
- 维护数据库: `postgres`
- 用户名: `wuyanze`
- 密码: (留空)

**下载地址：** https://www.pgadmin.org/

---

### 5. DataGrip ⭐⭐⭐⭐

**特点：**
- JetBrains 出品，功能强大
- 智能 SQL 编辑
- 需要付费（有30天试用）

**下载地址：** https://www.jetbrains.com/datagrip/

---

## 当前数据库连接信息

```
连接URL: postgresql://wuyanze@localhost:5432/quantitative_trading

主机: localhost
端口: 5432
用户名: wuyanze
密码: (留空)
数据库: quantitative_trading
```

## 常用查询（在可视化工具中执行）

### 查看所有表
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;
```

### 查看表结构
```sql
-- 查看 dim_stock 表结构
\d dim_stock

-- 或使用 SQL
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'dim_stock'
ORDER BY ordinal_position;
```

### 查看数据统计
```sql
-- 股票维度表数量
SELECT COUNT(*) as stock_count FROM dim_stock;

-- 日线数据统计
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT ts_code) as stock_count,
    MIN(trade_date) as earliest_date,
    MAX(trade_date) as latest_date
FROM fact_daily_price;

-- 财务数据统计
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT ts_code) as stock_count,
    MIN(end_date) as earliest_date,
    MAX(end_date) as latest_date
FROM fact_financial_indicator;
```

### 查看最新数据
```sql
-- 最新交易日
SELECT MAX(trade_date) as latest_date FROM fact_daily_price;

-- 最新交易日的数据量
SELECT COUNT(*) 
FROM fact_daily_price 
WHERE trade_date = (SELECT MAX(trade_date) FROM fact_daily_price);

-- 查看某只股票的最新数据
SELECT * 
FROM fact_daily_price 
WHERE ts_code = '600519.SH' 
ORDER BY trade_date DESC 
LIMIT 10;
```

### 查看数据质量
```sql
-- 数据质量分布
SELECT data_quality, COUNT(*) as count
FROM fact_daily_price
GROUP BY data_quality
ORDER BY data_quality;

-- 查看数据源使用情况
SELECT 
    sources_used,
    COUNT(*) as count
FROM fact_daily_price
GROUP BY sources_used
ORDER BY count DESC;
```

## 快速安装命令

```bash
# 安装 TablePlus（推荐）
brew install --cask tableplus

# 或安装 Postico
brew install --cask postico

# 或安装 DBeaver
brew install --cask dbeaver-community
```

## 使用建议

1. **日常查看数据**：推荐 TablePlus 或 Postico（界面简洁，操作方便）
2. **复杂查询和分析**：推荐 DBeaver 或 DataGrip（SQL 编辑功能强大）
3. **数据库管理**：推荐 pgAdmin（官方工具，功能全面）

