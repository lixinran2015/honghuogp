@echo off
cd /d %~dp0
cd ..\..
chcp 65001 >nul
echo ==========================================
echo   初始化数据库表结构
echo ==========================================
echo.

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 检查数据库连接
echo 📡 检查数据库连接...
python -c "from data_warehouse.config import DATABASE_URL; print('数据库连接URL:', DATABASE_URL.replace('qazwsx', '****'))" 2>nul
if errorlevel 1 (
    echo ❌ 无法读取数据库配置，请检查 data_warehouse/config.py
    pause
    exit /b 1
)

echo.
echo 🗄️  开始初始化数据库表结构...
echo.

REM 运行数据库初始化
python -m data_warehouse.db_init

if errorlevel 1 (
    echo.
    echo ❌ 数据库初始化失败！
    echo.
    echo 请检查：
    echo 1. PostgreSQL服务是否正在运行
    echo 2. 数据库 quantitative_trading 是否已创建
    echo 3. 数据库用户名和密码是否正确
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ 数据库表结构初始化完成！
echo.
echo 下一步：可以运行数据回补脚本来填充初始数据
echo.
pause

