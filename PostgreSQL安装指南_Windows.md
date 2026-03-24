# 📦 PostgreSQL 安装指南 - Windows

## 方法1: 官方安装程序（推荐）

### 步骤1: 下载PostgreSQL

1. 访问PostgreSQL官网：https://www.postgresql.org/download/windows/
2. 点击 **"Download the installer"** 链接
3. 或直接访问：https://www.enterprisedb.com/downloads/postgres-postgresql-downloads
4. 选择最新版本（推荐 PostgreSQL 14 或更高版本）
5. 下载 Windows x86-64 安装程序（约 200MB）

### 步骤2: 运行安装程序

1. 双击下载的 `.exe` 文件（如 `postgresql-14.x-windows-x64.exe`）
2. 点击 **"Next"** 开始安装

### 步骤3: 选择安装目录

- 默认路径：`C:\Program Files\PostgreSQL\14`
- 可以保持默认，或选择其他路径
- 点击 **"Next"**

### 步骤4: 选择组件

确保以下组件被选中：
- ✅ **PostgreSQL Server**（必需）
- ✅ **pgAdmin 4**（图形化管理工具，推荐）
- ✅ **Stack Builder**（可选，用于安装额外工具）
- ✅ **Command Line Tools**（命令行工具，推荐）

点击 **"Next"**

### 步骤5: 选择数据目录

- 默认路径：`C:\Program Files\PostgreSQL\14\data`
- 可以保持默认
- 点击 **"Next"**

### 步骤6: 设置超级用户密码 ⚠️ 重要

- **用户名**: `postgres`（默认，建议保持）qazwsx
- **密码**: 设置一个强密码（请记住这个密码！）
  - 建议：至少8位，包含字母、数字和特殊字符
  - 例如：`Postgres2024!`

⚠️ **重要**: 请务必记住这个密码，后续连接数据库时会用到！

点击 **"Next"**

### 步骤7: 选择端口

- 默认端口：`5432`（建议保持默认）
- 如果5432已被占用，可以改为其他端口（如 5433）
- 点击 **"Next"**

### 步骤8: 选择区域设置

- 选择 **"Chinese, China"** 或保持默认
- 点击 **"Next"**

### 步骤9: 完成安装

- 点击 **"Next"** 开始安装
- 等待安装完成（约2-5分钟）
- 取消勾选 **"Launch Stack Builder"**（如果不需要）
- 点击 **"Finish"** 完成安装

## 方法2: 使用包管理器（可选）

### 使用 Chocolatey

如果你已安装 Chocolatey：

```powershell
# 以管理员身份运行 PowerShell
choco install postgresql14
```

### 使用 Scoop

如果你已安装 Scoop：

```powershell
scoop install postgresql
```

## ✅ 验证安装

### 方法1: 使用命令行

打开 **命令提示符** 或 **PowerShell**：

```powershell
# 检查PostgreSQL版本
psql --version

# 如果提示找不到命令，需要添加到PATH
# 或使用完整路径：
"C:\Program Files\PostgreSQL\14\bin\psql.exe" --version
```

### 方法2: 使用pgAdmin

1. 在开始菜单找到 **pgAdmin 4**
2. 打开 pgAdmin 4
3. 首次打开会要求设置主密码（用于保护保存的密码）
4. 左侧会显示 PostgreSQL 服务器

### 方法3: 检查服务

```powershell
# 检查PostgreSQL服务是否运行
Get-Service -Name postgresql*

# 或使用服务管理器
services.msc
# 查找 "postgresql-x64-14" 服务，状态应为"正在运行"
```

## 🔧 配置环境变量（可选但推荐）

为了在命令行中直接使用 `psql` 命令，建议添加到PATH：

### 自动添加（安装时）

安装程序通常会询问是否添加到PATH，建议选择 **"是"**

### 手动添加

1. 右键 **"此电脑"** → **"属性"**
2. 点击 **"高级系统设置"**
3. 点击 **"环境变量"**
4. 在 **"系统变量"** 中找到 **"Path"**，点击 **"编辑"**
5. 点击 **"新建"**，添加：
   ```
   C:\Program Files\PostgreSQL\14\bin
   ```
6. 点击 **"确定"** 保存
7. 重新打开命令行窗口

## 🗄️ 创建数据库

### 方法1: 使用pgAdmin（图形界面）

1. 打开 **pgAdmin 4**
2. 展开左侧 **"Servers"** → **"PostgreSQL 14"**
3. 输入安装时设置的密码
4. 右键 **"Databases"** → **"Create"** → **"Database..."**
5. 输入数据库名：`quantitative_trading`
6. 点击 **"Save"**

### 方法2: 使用命令行

```powershell
# 打开命令提示符或PowerShell
# 使用postgres用户连接
psql -U postgres

# 输入安装时设置的密码
# 然后执行：
CREATE DATABASE quantitative_trading;

# 退出
\q
```

### 方法3: 使用createdb命令

```powershell
# 直接创建数据库
createdb -U postgres quantitative_trading
# 输入密码
```

## 🔌 配置项目连接

### 编辑配置文件

编辑项目中的 `data_warehouse/config.py`：

```python
# 默认配置（无密码）
DATABASE_URL = "postgresql://postgres@localhost:5432/quantitative_trading"

# 如果有密码
DATABASE_URL = "postgresql://postgres:你的密码@localhost:5432/quantitative_trading"

# 或使用环境变量
import os
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:你的密码@localhost:5432/quantitative_trading"
)
```

### 测试连接

```powershell
# 在项目目录下
python -c "from data_warehouse.config import DATABASE_URL; print(DATABASE_URL)"

# 测试连接
python -c "from sqlalchemy import create_engine; from data_warehouse.config import DATABASE_URL; engine = create_engine(DATABASE_URL); conn = engine.connect(); print('连接成功！'); conn.close()"
```

## 📥 恢复数据库备份（如果项目有备份文件）

如果项目包含 `database_backup.sql` 文件：

```powershell
# 方法1: 使用psql
psql -U postgres -d quantitative_trading < database_backup.sql

# 方法2: 使用pgAdmin
# 1. 右键数据库 → "Restore..."
# 2. 选择备份文件
# 3. 点击 "Restore"
```

## 🛠️ 常用管理命令

### 启动/停止服务

```powershell
# 启动服务
net start postgresql-x64-14

# 停止服务
net stop postgresql-x64-14

# 或使用服务管理器
services.msc
```

### 连接数据库

```powershell
# 连接到默认数据库
psql -U postgres

# 连接到指定数据库
psql -U postgres -d quantitative_trading

# 列出所有数据库
psql -U postgres -l
```

### 常用SQL命令

```sql
-- 列出所有数据库
\l

-- 连接到数据库
\c quantitative_trading

-- 列出所有表
\dt

-- 查看表结构
\d 表名

-- 退出
\q
```

## ⚠️ 常见问题

### 问题1: 安装时提示端口被占用

**解决**:
1. 检查是否有其他PostgreSQL实例在运行
2. 或选择其他端口（如 5433）
3. 修改项目配置中的端口号

### 问题2: 忘记postgres用户密码

**解决**:
1. 编辑 `C:\Program Files\PostgreSQL\14\data\pg_hba.conf`
2. 找到 `host all all 127.0.0.1/32 md5`
3. 改为 `host all all 127.0.0.1/32 trust`
4. 重启PostgreSQL服务
5. 使用 `psql -U postgres` 连接（无需密码）
6. 修改密码：`ALTER USER postgres WITH PASSWORD '新密码';`
7. 恢复 `pg_hba.conf` 为 `md5`
8. 重启服务

### 问题3: 服务无法启动

**解决**:
1. 检查日志文件：`C:\Program Files\PostgreSQL\14\data\log\`
2. 检查数据目录权限
3. 以管理员身份运行服务
4. 检查端口是否被占用

### 问题4: 找不到psql命令

**解决**:
1. 使用完整路径：`"C:\Program Files\PostgreSQL\14\bin\psql.exe"`
2. 或添加到PATH环境变量（见上方"配置环境变量"部分）

### 问题5: 连接被拒绝

**解决**:
1. 检查PostgreSQL服务是否运行
2. 检查防火墙设置
3. 检查 `pg_hba.conf` 配置
4. 确认端口号正确

## 📚 学习资源

- **官方文档**: https://www.postgresql.org/docs/
- **pgAdmin文档**: https://www.pgadmin.org/docs/
- **中文教程**: https://www.postgresql.org/docs/current/tutorial.html

## 🎯 快速检查清单

安装完成后，确认以下项目：

- [ ] PostgreSQL服务正在运行
- [ ] 可以使用 `psql --version` 查看版本
- [ ] 可以使用 `psql -U postgres` 连接
- [ ] pgAdmin 4 可以正常打开
- [ ] 已创建 `quantitative_trading` 数据库
- [ ] 项目配置文件已更新数据库连接信息
- [ ] 可以成功连接数据库

## 💡 提示

1. **密码安全**: postgres用户密码很重要，请妥善保管
2. **定期备份**: 建议定期备份数据库
3. **性能优化**: 对于生产环境，建议调整 `postgresql.conf` 配置
4. **安全设置**: 生产环境建议修改默认端口和限制访问

---

安装完成后，返回项目启动指南继续配置和启动系统！




