# 🚀 量化交易系统 - Windows 启动指南

## 项目结构

这是一个量化交易系统，包含：
- **后端**: FastAPI (端口 8000)
- **前端**: Vue 3 + Vite (端口 3000)
- **数据库**: PostgreSQL (需要单独安装和配置)

## 📋 前置要求

### 1. 系统要求
- Python 3.8+
- Node.js 16+
- PostgreSQL 14+ (可选，如果使用数据库功能)

### 2. 检查环境

```powershell
# 检查Python版本
python --version

# 检查Node.js版本
node --version
npm --version
```

## 🔧 安装步骤

### 步骤1: 激活虚拟环境

项目已包含虚拟环境 `venv`，激活它：

```powershell
# 在项目根目录执行
.\venv\Scripts\Activate.ps1

# 如果遇到执行策略错误，先运行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 步骤2: 安装Python依赖

```powershell
# 确保虚拟环境已激活（命令行前应显示 (venv)）
pip install -r requirements.txt
pip install -r backend\requirements.txt
```

### 步骤3: 安装前端依赖

```powershell
cd frontend-vue
npm install
cd ..
```

### 步骤4: 配置数据库（可选）

如果使用数据库功能，需要：
1. 安装并启动 PostgreSQL
2. 创建数据库：`createdb quantitative_trading`
3. 配置 `data_warehouse/config.py` 中的数据库连接

## 🚀 启动方式

### 方式1: 使用批处理脚本（推荐）

#### 启动所有服务（前后端）
```powershell
.\start_all.bat
```

#### 只启动后端
```powershell
.\start_backend.bat
```

#### 只启动前端
```powershell
.\start_frontend.bat
```

### 方式2: 手动启动

#### 启动后端（终端1）
```powershell
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 进入后端目录
cd backend

# 启动后端服务
python run.py
```

后端将在 `http://localhost:8000` 启动
API文档: `http://localhost:8000/docs`

#### 启动前端（终端2）
```powershell
# 进入前端目录
cd frontend-vue

# 启动前端服务
npm run dev
```

前端将在 `http://localhost:3000` 启动

### 方式3: 使用PowerShell脚本

如果安装了Git Bash或WSL，也可以使用原始的 `.sh` 脚本：

```bash
# 在Git Bash中
./start_all.sh
```

## 📍 访问地址

启动成功后，访问以下地址：

- **前端界面**: http://localhost:3000
- **后端API**: http://localhost:8000
- **API文档**: http://localhost:8000/docs

## ⚠️ 常见问题

### 问题1: PowerShell执行策略错误

**错误**: `无法加载文件，因为在此系统上禁止运行脚本`

**解决**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题2: 端口被占用

**错误**: `Address already in use`

**解决**:
```powershell
# 查找占用8000端口的进程
netstat -ano | findstr :8000

# 查找占用3000端口的进程
netstat -ano | findstr :3000

# 结束进程（替换PID为实际进程ID）
taskkill /PID <进程ID> /F
```

### 问题3: 前端无法连接后端

**解决**:
1. 确保后端已启动
2. 检查 `frontend-vue/vite.config.js` 中的代理配置
3. 检查防火墙设置

### 问题4: 数据库连接失败

**解决**:
1. 确保PostgreSQL服务正在运行
2. 检查 `data_warehouse/config.py` 中的数据库连接配置
3. 如果不需要数据库功能，可以跳过数据库配置

### 问题5: 依赖安装失败

**解决**:
```powershell
# Python依赖
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir

# 前端依赖
cd frontend-vue
rm -r -force node_modules
rm package-lock.json
npm install
```

## 📝 注意事项

1. **首次运行**: 系统首次运行后，需要在"数据管理"页面触发数据更新
2. **虚拟环境**: 每次启动前确保激活虚拟环境
3. **数据库**: 如果只使用基础功能，可以不配置数据库
4. **网络**: 系统需要访问互联网以获取股票数据

## 🔄 停止服务

- 在运行服务的终端按 `Ctrl+C` 停止
- 如果使用批处理脚本，关闭命令窗口即可

## 📚 更多信息

- 详细安装指南: `INSTALL.md`
- 项目说明: `README.md`
- API文档: http://localhost:8000/docs (启动后端后访问)

