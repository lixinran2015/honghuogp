# 项目脚本说明

根目录下的可执行脚本已整理到此目录，按用途分类。

## 目录结构

```
scripts/
├── backfill/       # 数据回填
│   ├── backfill_startup_history.py    # 回填启动候选历史
│   ├── backfill_high_history.py       # 回填新高策略历史(60/180日)
│   └── backfill_high180d_history.py   # 回填180日新高历史
├── check/          # 各类检查脚本
│   ├── check_confirmed_stocks.py
│   ├── check_dajin.py
│   ├── check_financial_data.py
│   ├── check_golden_cross_1205.py
│   ├── check_import.py
│   ├── check_ma10_data.py
│   ├── check_recommendation_table.py
│   ├── check_started_stocks.py
│   ├── check_startup_data.py
│   ├── check_stock_record.py
│   ├── check_stock_score.py
│   ├── check_xiyegufen.py
│   ├── check_yingweike_status.py
│   └── check_zhiguang_status.py
├── manual/         # 手动操作脚本
│   └── add_yingweike_to_started.py
├── fix/            # 修复脚本
│   └── fix_confirmed_stage_error.py
├── analyze/        # 日志/数据分析
│   ├── analyze_broken_ma.py
│   ├── analyze_log_differences.py
│   └── analyze_tonghuashun_calls.py
├── test/           # API/功能测试
│   ├── test_dajin_startup.py
│   ├── test_daoming.py
│   ├── test_data_management_api.py
│   ├── test_diagnose_api.py
│   └── test_watch_api.py
├── tools/          # 通用工具
│   ├── find_stock.py
│   └── update_missing_dates.py
├── batch/          # 批处理脚本
│   ├── generate_startup_data.bat
│   ├── init_database.bat
│   ├── import_database.bat
│   ├── import_backup_part_aa_522.bat
│   └── process_backup_file.ps1
└── diagnose_startup.py   # 启动诊断（可直接放在 scripts 根下）
```

## 使用方式

在**项目根目录**下执行：

```bash
# 回填示例
python scripts/backfill/backfill_startup_history.py --days 10

# 检查示例
python scripts/check/check_started_stocks.py

# 批处理（Windows）
scripts\batch\generate_startup_data.bat
scripts\batch\init_database.bat
```

脚本会自动将项目根目录加入 `sys.path`，无需额外配置。
