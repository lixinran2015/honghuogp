@echo off
chcp 65001 >nul
echo 🎨 启动Vue前端服务...
echo.

REM 进入前端目录
cd frontend-vue

REM 检查依赖
if not exist "node_modules" (
    echo 📦 首次运行，正在安装依赖...
    call npm install
)

echo 📍 前端地址: http://localhost:3000
echo.

REM 启动前端
call npm run dev

