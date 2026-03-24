# 错误信息说明

## 已知的库内部错误

脚本运行结束时可能会看到以下错误信息：

```
logout success!
[Errno 9] Bad file descriptor
接收数据异常，请稍后再试。
```

### 原因

这些错误来自第三方库的内部实现：

1. **`[Errno 9] Bad file descriptor`** - 来自 `baostock` 库，在登出时网络连接关闭时的正常现象
2. **`接收数据异常，请稍后再试。`** - 来自 `easyquotation` 库，内部网络连接处理的警告

### 影响

**这些错误不影响功能**：
- ✅ 数据已成功获取
- ✅ 策略计算已完成
- ✅ 推荐结果已保存到数据库

### 解决方案

#### 方案1：使用 `--suppress-errors` 参数（推荐）

```bash
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 15:00 --suppress-errors
```

这会抑制库内部的错误输出。

#### 方案2：重定向错误输出

```bash
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 15:00 2>/dev/null
```

#### 方案3：保存到日志文件

```bash
python backend/scripts/refresh_stock_snapshot.py --snapshot-time 15:00 > logs/refresh.log 2>&1
```

### 验证功能是否正常

检查数据库中的推荐结果：

```sql
SELECT 
    recommendation_type,
    COUNT(*) as count,
    MAX(generated_at) as latest_time
FROM fact_recommendation_result
WHERE trade_date = CURRENT_DATE
GROUP BY recommendation_type;
```

如果看到推荐记录，说明功能正常，可以忽略这些错误信息。

