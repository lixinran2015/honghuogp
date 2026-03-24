# 数据库优化脚本

## 执行顺序

1. **01_add_primary_keys.sql** - 添加缺失的主键约束
2. **02_create_materialized_view.sql** - 创建物化视图替代冗余表
3. **03_add_foreign_keys.sql** - 外键约束（可选，默认注释）
4. **04_add_indexes.sql** - 添加优化索引

## 执行方式

```bash
# 连接数据库后逐个执行
psql -h localhost -U postgres -d stock_data -f 01_add_primary_keys.sql
psql -h localhost -U postgres -d stock_data -f 02_create_materialized_view.sql
psql -h localhost -U postgres -d stock_data -f 04_add_indexes.sql
```

## 注意事项

1. **主键脚本**：如果表中有重复数据，需要先清理再执行
2. **物化视图**：创建后需要修改代码中对 `fact_base_universe_daily` 的引用
3. **外键约束**：默认注释，因为会影响批量导入性能
4. **索引**：建议在低峰期执行，大表创建索引可能耗时较长

## 物化视图刷新

物化视图需要定期刷新以获取最新数据：

```sql
-- 并发刷新（不锁表）
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_base_universe_daily;

-- 或调用函数
SELECT refresh_mv_base_universe();
```

建议在每日数据更新后自动刷新。

