# 脚本使用指南

本文档说明 `backend/scripts/` 目录下的重要脚本及其用途。

---

## 📊 行业和板块数据

### 1. 行业简称设置
```bash
python backend/scripts/add_industry_simple_field.py
```
**功能**：
- 添加 `dim_stock.industry_simple` 字段
- 将长行业名称简化（如 "C39计算机、通信..." → "电子"）
- 保留原始名称，便于追溯

**使用场景**：
- 首次设置行业简称
- 补充新的行业映射

---

### 2. 更新完整板块数据（Baostock）
```bash
python backend/scripts/update_sector_complete.py
```
**功能**：
- 使用 baostock 更新行业分类
- 更新 `dim_stock.industry`
- 更新 `dim_sector` 表（行业板块）
- 更新 `fact_stock_sector` 关联表

**数据来源**：Baostock（免费，无需token）

---

### 3. 添加概念板块（Tushare Pro）⭐ 推荐
```bash
python backend/scripts/add_concept_sectors_tushare.py
```
**功能**：
- 获取所有概念板块列表（879个）
- 获取每个概念的成分股
- 建立股票-概念板块关联

**要求**：
- Tushare Pro token（已配置在 config.json）
- 2000积分以上
- 耗时约15-30分钟

**数据来源**：Tushare Pro

---

### 4. 添加板块数据（东方财富个股接口）
```bash
python backend/scripts/add_sectors_from_eastmoney_direct.py
```
**功能**：
- 直接查询每只股票的所属板块
- 不需要遍历所有概念（比Tushare快）
- 数据更全面

**优势**：
- 速度相对快（直接查询）
- 数据全面（行业+概念）

**缺点**：
- 耗时较长（5000只股票 × 0.5秒 ≈ 41分钟）
- 依赖东方财富接口稳定性

---

## 🔍 数据检查工具

### 检查行业数据
```bash
python backend/scripts/check_industry_data.py
```
**功能**：
- 检查 `dim_stock.industry` 的完整性
- 显示行业分布
- 查看示例数据

---

## 📝 辅助工具

### 检查板块数据
```bash
python backend/scripts/check_sector.py
```
**功能**：
- 检查板块维表数据
- 查看板块关联情况

---

## 🗑️ 已删除的临时文件

以下文件为临时调试文件，已清理：
- `debug_realtime_amount.py` - 调试成交额字段
- `debug_sikejishu_amount.py` - 调试思看科技数据
- `debug_tencent_api.py` - 测试腾讯接口
- `debug_sector_relations.py` - 调试板块关联
- `test_data_sources.py` - 测试数据源
- `test_stock_sector_sources.py` - 测试板块数据源
- `check_missing_industry_simple.py` - 检查缺失简称
- `check_dim_sector_data.py` - 检查板块维表
- `check_s1_universe_data.py` - 检查S1池数据
- `check_trading_day.py` - 检查交易日
- `simplify_industry_names.py` - 简化行业名称（已被替代）
- `add_concept_sectors.py` - AkShare版本（已有Tushare版本）
- `add_concept_sectors_tencent.py` - 腾讯版本（接口不可用）
- `cleanup_dim_sector_industry.py` - 清理脚本
- `apply_sector_constraint.py` - 一次性约束脚本
- `fix_dim_sector_constraint.sql` - 一次性SQL脚本

---

## 📦 保留的重要脚本

### 行业数据
- ✅ `add_industry_simple_field.py` - 添加行业简称
- ✅ `update_sector_complete.py` - 更新行业数据（Baostock）
- ✅ `update_industry_baostock.py` - 更新行业（旧版本）
- ✅ `check_industry_data.py` - 检查行业数据

### 板块数据
- ✅ `add_concept_sectors_tushare.py` - 添加概念板块（推荐）
- ✅ `add_sectors_from_eastmoney_direct.py` - 添加板块（东财）
- ✅ `complete_sector_setup.py` - 完整板块设置

### 数据检查
- ✅ `check_sector.py` - 检查板块数据
- ✅ `check_stock.py` - 检查股票数据
- ✅ `check_st.py` - 检查ST股票

---

## 💡 使用建议

### 首次设置（推荐顺序）

1. **更新行业数据**：
   ```bash
   python backend/scripts/update_sector_complete.py
   ```

2. **添加行业简称**：
   ```bash
   python backend/scripts/add_industry_simple_field.py
   ```

3. **添加概念板块**（二选一）：
   - **方案A（推荐）**：使用Tushare Pro
     ```bash
     python backend/scripts/add_concept_sectors_tushare.py
     ```
   - **方案B（备选）**：使用东方财富
     ```bash
     python backend/scripts/add_sectors_from_eastmoney_direct.py
     ```

4. **验证数据**：
   ```bash
   python backend/scripts/check_industry_data.py
   python backend/scripts/check_sector.py
   ```

### 日常维护

- **更新行业数据**：每季度运行一次 `update_sector_complete.py`
- **更新概念板块**：每月运行一次 `add_concept_sectors_tushare.py`
- **数据检查**：随时使用 `check_*.py` 系列脚本

---

## 📁 目录结构

```
backend/scripts/
├── add_industry_simple_field.py        # 行业简称设置
├── add_concept_sectors_tushare.py      # 概念板块（Tushare）
├── add_sectors_from_eastmoney_direct.py # 板块数据（东财）
├── update_sector_complete.py           # 行业数据更新（Baostock）
├── check_industry_data.py              # 检查行业数据
├── check_sector.py                     # 检查板块数据
├── complete_sector_setup.py            # 完整板块设置
├── data_update/                        # 数据更新脚本
│   ├── refresh_stock_snapshot.py       # 刷新股票快照
│   ├── update_daily_from_snapshot.py   # 更新日线数据
│   └── ...
├── calculation/                        # 计算相关脚本
└── tools/                              # 工具脚本
```

---

最后更新：2025-12-02

