@echo off
chcp 65001 >nul
echo 🚀 启动FastAPI后端服务...
echo.

REM 检查端口8000是否被占用
netstat -ano | findstr :8000 >nul
if not errorlevel 1 (
    echo ⚠️  检测到端口 8000 已被占用
    echo 🔄 正在查找占用端口的进程...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
        echo 正在结束进程 %%a
        taskkill /PID %%a /F >nul 2>&1
    )
    timeout /t 1 /nobreak >nul
    echo ✅ 端口已释放
    echo.
)

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查依赖
python -c "import fastapi, uvicorn" 2>nul
if errorlevel 1 (
    echo ⚠️  依赖未安装，正在安装...
    pip install -r backend\requirements.txt
)

echo 📍 后端地址: http://localhost:8000
echo 📖 API文档: http://localhost:8000/docs
echo.

REM 启动后端
cd backend
python run.py

