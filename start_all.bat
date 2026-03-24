@echo off
chcp 65001 >nul
echo 🚀 启动量化交易系统（FastAPI + React）
echo.

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查后端依赖
echo 📡 检查后端环境...
cd backend
python -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo ⚠️  后端依赖未安装，正在安装...
    pip install -r requirements.txt
)
cd ..

REM 检查前端依赖
echo 🎨 检查前端环境...
cd frontend-vue
if not exist "node_modules" (
    echo 📦 首次运行，正在安装前端依赖...
    call npm install
)
cd ..

REM 启动后端（后台运行）
echo.
echo 📡 启动后端服务...
start "后端服务" cmd /k "cd /d %~dp0 && venv\Scripts\activate.bat && cd backend && python run.py"

REM 等待后端启动
timeout /t 3 /nobreak >nul

REM 启动前端
echo 🎨 启动前端服务...
start "前端服务" cmd /k "cd /d %~dp0\frontend-vue && npm run dev"

echo.
echo ✅ 服务已启动！
echo 📍 后端API: http://localhost:8000
echo 📍 前端界面: http://localhost:3000
echo 📖 API文档: http://localhost:8000/docs
echo.
echo 按任意键关闭此窗口（服务将继续运行）...
pause >nul

