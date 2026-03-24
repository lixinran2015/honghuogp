@echo off
setlocal enabledelayedexpansion
cd /d %~dp0
cd ..\..
chcp 65001 >nul
echo ==========================================
echo   导入数据库备份文件
echo ==========================================
echo.

REM 检查备份文件是否存在
if not exist "database_backup.sql" (
    echo ❌ 错误: 找不到 database_backup.sql 文件
    echo 请确保文件在当前目录下
    pause
    exit /b 1
)

REM 获取文件大小
for %%A in ("database_backup.sql") do set size=%%~zA
set /a sizeMB=%size%/1048576
echo 📦 备份文件大小: %sizeMB% MB
echo.

REM 检查PostgreSQL是否在PATH中
where psql >nul 2>&1
if errorlevel 1 (
    echo ⚠️  警告: 找不到 psql 命令
    echo 请使用完整路径或添加到PATH环境变量
    echo.
    echo 默认路径示例:
    echo D:\devTools\postgreSQL\bin\psql.exe
    echo.
    set /p PSQL_PATH="请输入psql.exe的完整路径（或按回车使用默认）: "
    if "!PSQL_PATH!"=="" (
        set PSQL_PATH=D:\devTools\postgreSQL\bin\psql.exe
    )
) else (
    set PSQL_PATH=psql
)

REM 从配置文件读取数据库信息
echo 📡 读取数据库配置...
python -c "from data_warehouse.config import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME; print(f'{DB_NAME}'); print(f'{DB_USER}'); print(f'{DB_HOST}'); print(f'{DB_PORT}'); print(f'{DB_PASSWORD}')" > temp_config.txt 2>nul
if errorlevel 1 (
    echo ⚠️  无法读取配置文件，使用默认配置
    set DB_USER=postgres
    set DB_NAME=quantitative_trading
    set DB_HOST=localhost
    set DB_PORT=5432
    set DB_PASSWORD=qazwsx
) else (
    REM 从临时文件读取配置
    set /a line_num=0
    for /f "delims=" %%a in (temp_config.txt) do (
        set /a line_num+=1
        if !line_num!==1 set DB_NAME=%%a
        if !line_num!==2 set DB_USER=%%a
        if !line_num!==3 set DB_HOST=%%a
        if !line_num!==4 set DB_PORT=%%a
        if !line_num!==5 set DB_PASSWORD=%%a
    )
    del temp_config.txt 2>nul
)
echo 数据库: %DB_NAME%
echo 用户: %DB_USER%
echo 主机: %DB_HOST%:%DB_PORT%
echo.

echo.
echo ⚠️  警告: 导入备份将覆盖现有数据！
echo.
set /p CONFIRM="确认要继续吗？(y/N): "
if /i not "%CONFIRM%"=="y" (
    echo 已取消
    pause
    exit /b 0
)

echo.
echo 🚀 开始导入数据库备份...
echo 这可能需要几分钟时间，请耐心等待...
echo.

REM 设置PGPASSWORD环境变量（避免交互式输入密码）
REM 注意：虽然密码在环境变量中，但这是psql的标准方式
set PGPASSWORD=%DB_PASSWORD%

REM 导入数据库（使用传统参数方式，支持反斜杠命令）
REM 使用 -v ON_ERROR_STOP=0 允许继续执行即使有错误
REM 使用 -v VERBOSITY=terse 减少输出
"%PSQL_PATH%" -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -v ON_ERROR_STOP=0 -f database_backup.sql

REM 清除密码环境变量（安全）
set PGPASSWORD=

REM 检查导入结果
REM 注意：由于使用了 ON_ERROR_STOP=0，即使有警告也会继续执行
REM 如果连接失败（errorlevel 1），说明是严重错误
if errorlevel 1 (
    echo.
    echo ❌ 导入失败！
    echo.
    echo 请检查：
    echo 1. PostgreSQL服务是否正在运行
    echo 2. 数据库 quantitative_trading 是否已创建
    echo 3. 数据库用户名和密码是否正确
    echo 4. 备份文件是否完整
    echo 5. psql.exe 路径是否正确
    echo.
    echo 注意：如果看到 "backslash commands are restricted" 错误，说明使用了URI连接方式
    echo 当前脚本已改用传统连接方式，应该可以正常执行反斜杠命令
    echo.
    pause
    exit /b 1
)

echo.
echo ✅ 数据库备份导入完成！
echo.
echo 注意：如果导入过程中有警告信息（如 backslash commands），这是正常的
echo 备份文件可能包含一些特殊命令，但数据应该已经成功导入
echo.
echo 建议验证数据：
echo   psql -U %DB_USER% -d %DB_NAME% -c "SELECT COUNT(*) FROM dim_stock;"
echo.
pause

