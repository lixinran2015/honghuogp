@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ==========================================
echo   导入 database_backup.sql
echo ==========================================
echo.

REM 检查备份文件是否存在
if not exist "database_backup.sql" (
    echo ❌ 错误: 找不到 database_backup.sql 文件
    echo 请确保文件在当前目录下
    pause
    exit /b 1
)

REM 检查PostgreSQL是否在PATH中
where psql >nul 2>&1
if errorlevel 1 (
    echo ⚠️  警告: 找不到 psql 命令
    echo 请使用完整路径或添加到PATH环境变量
    echo and not use URI connection
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
echo ⚠️  警告: 导入备份将创建/覆盖表结构！
echo.
set /p CONFIRM="确认要继续吗？(y/N): "
if /i not "%CONFIRM%"=="y" (
    echo 已取消
    pause
    exit /b 0
)

echo.
echo 🚀 开始导入 database_backup.sql...
echo 这可能需要较长时间，请耐心等待...
echo.

REM 设置PGPASSWORD环境变量
set PGPASSWORD=%DB_PASSWORD%

REM 处理SQL文件：移除restrict、替换OWNER、添加DROP TABLE
echo 📦 正在处理SQL文件...
powershell -ExecutionPolicy Bypass -File process_backup_file.ps1 -InputFile "database_backup.sql" -OutputFile "database_backup_clean.sql" -AddDropTables

if not exist "database_backup_clean.sql" (
    echo ❌ 错误: 无法创建清理后的SQL文件
    pause
    exit /b 1
)

echo ✅ SQL文件处理完成
echo.

REM 导入前记录行数
echo 📊 导入前数据统计:
"%PSQL_PATH%" -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -c "SELECT 'fact_daily_price' as table_name, COUNT(*) as row_count FROM fact_daily_price UNION ALL SELECT 'fact_daily_fundamental', COUNT(*) FROM fact_daily_fundamental UNION ALL SELECT 'fact_base_universe_daily', COUNT(*) FROM fact_base_universe_daily;" 2>nul
echo.

echo 开始导入数据库（显示详细输出）...
echo 注意: 如果看到 'invalid command \N' 错误，这些可以忽略，是 COPY 数据中的 NULL 值
echo.

REM 导入数据库（显示详细输出，过滤 \N 错误）
"%PSQL_PATH%" -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -v ON_ERROR_STOP=0 -f database_backup_clean.sql 2>&1 | findstr /V /C:"invalid command \N"

REM 清除密码环境变量
set PGPASSWORD=

echo.
echo ==========================================
echo   导入完成
echo ==========================================
echo.

echo 📊 导入后数据统计:
"%PSQL_PATH%" -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% -c "SELECT 'dim_stock' as table_name, COUNT(*) as row_count FROM dim_stock UNION ALL SELECT 'dim_sector', COUNT(*) FROM dim_sector UNION ALL SELECT 'fact_daily_price', COUNT(*) FROM fact_daily_price UNION ALL SELECT 'fact_daily_fundamental', COUNT(*) FROM fact_daily_fundamental UNION ALL SELECT 'fact_base_universe_daily', COUNT(*) FROM fact_base_universe_daily;" 2>nul

echo.
echo 如果行数增加了，说明数据已成功导入
echo.

REM 清理临时文件
del database_backup_clean.sql 2>nul

echo.
pause
