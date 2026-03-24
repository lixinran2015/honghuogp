@echo off
cd /d %~dp0
cd ..\..
chcp 65001 >nul
echo 正在生成启动候选股票数据...
echo.

REM 激活虚拟环境
call venv\Scripts\activate.bat

REM 运行回填脚本（回填最近10天）
python scripts\backfill\backfill_startup_history.py --days 10

echo.
echo 完成！
pause

