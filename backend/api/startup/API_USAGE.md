# 金叉计算与入库API使用指南

## 概述

本指南介绍如何通过前端调用API，批量计算一段时间范围内的金叉并入库。

## API接口列表

### 1. 批量计算金叉并入库 ⭐ 推荐

**接口地址**：`POST /api/startup/batch-golden-cross`

**功能**：一次性批量处理指定日期范围内的所有交易日，计算金叉并自动入库

**参数**：
- `start_date` (必需): 开始日期，格式 `YYYY-MM-DD`
- `end_date` (可选): 结束日期，格式 `YYYY-MM-DD`，默认今天
- `universe` (可选): 股票池类型，可选值：
  - `mainboard` (主板，默认)
  - `base` (基础池)
  - `all` (全市场)
- `batch_size` (可选): 每批处理的交易日数量，默认20

**示例请求**：
```bash
POST /api/startup/batch-golden-cross?start_date=2024-01-01&end_date=2024-01-31&universe=mainboard
```

**响应示例**：
```json
{
  "success": true,
  "message": "批量计算金叉任务已启动，将在后台执行。日期范围：2024-01-01 至 2024-01-31",
  "period": {
    "start_date": "2024-01-01",
    "end_date": "2024-01-31"
  },
  "universe": "mainboard",
  "batch_size": 20
}
```

**说明**：
- 此接口使用后台任务执行，不会阻塞API响应
- 任务会自动处理指定日期范围内的所有交易日
- 对每个交易日，会扫描股票池中的所有股票，计算金叉并自动保存到数据库
- 只保存得分≥20的记录（包括金叉、确认、完全启动等所有阶段）

### 2. 查询批量计算状态

**接口地址**：`GET /api/startup/batch-golden-cross/status`

**功能**：查询指定日期范围内已保存的金叉记录数量和处理进度

**参数**：
- `start_date` (可选): 开始日期，格式 `YYYY-MM-DD`，默认最近1年
- `end_date` (可选): 结束日期，格式 `YYYY-MM-DD`，默认今天

**示例请求**：
```bash
GET /api/startup/batch-golden-cross/status?start_date=2024-01-01&end_date=2024-01-31
```

**响应示例**：
```json
{
  "success": true,
  "period": {
    "start_date": "2024-01-01",
    "end_date": "2024-01-31"
  },
  "trading_dates": {
    "total": 22,
    "processed": 20,
    "remaining": 2
  },
  "records": {
    "total": 5600,
    "golden_cross": 4000,
    "confirmed": 1200,
    "started": 400
  },
  "progress": {
    "percentage": 90.91
  }
}
```

### 3. 历史数据回填（高级功能）

**接口地址**：`POST /api/startup/backfill-history`

**功能**：批量回填历史数据，包括金叉计算和条件检查

**参数**：
- `start_date` (必需): 开始日期，格式 `YYYY-MM-DD`
- `end_date` (可选): 结束日期，格式 `YYYY-MM-DD`，默认今天
- `universe` (可选): 股票池类型，默认 `mainboard`
- `min_score` (可选): 最低得分，默认20
- `batch_size` (可选): 每批处理的交易日数量，默认20
- `skip_existing` (可选): 是否跳过已有数据的日期，默认 `true`
- `check_missing_conditions` (可选): 是否检查缺少条件，默认 `true`
- `max_trading_days` (可选): 检查缺少条件时，距离金叉日期的最大交易日数，默认6

**示例请求**：
```bash
POST /api/startup/backfill-history?start_date=2024-01-01&end_date=2024-01-31&universe=mainboard&check_missing_conditions=true
```

**说明**：
- 此接口功能更全面，除了计算金叉外，还会检查后续条件（核心、辅助、风险）
- 适用于完整的历史数据回填场景

### 4. 单日扫描（实时计算）

**接口地址**：`GET /api/startup/scan`

**功能**：扫描指定交易日的启动股票（包括金叉计算）

**参数**：
- `universe` (可选): 股票池类型，默认 `mainboard`
- `trade_date` (可选): 交易日期，格式 `YYYY-MM-DD`，默认最新
- `min_score` (可选): 最低启动得分，默认60

**示例请求**：
```bash
GET /api/startup/scan?trade_date=2024-01-15&universe=mainboard&min_score=60
```

**响应示例**：
```json
{
  "success": true,
  "data": [
    {
      "ts_code": "000001.SZ",
      "name": "平安银行",
      "score": 100,
      "stage": "started",
      "signals": ["5日金叉10日", "突破90日高点", "量能放大", "均线多头排列"],
      "trade_date": "2024-01-15"
    }
  ],
  "summary": {
    "total_scanned": 5000,
    "saved_count": 2800,
    "golden_cross_count": 2000,
    "confirmed_count": 600,
    "started_count": 200,
    "returned_count": 200,
    "scan_date": "2024-01-15"
  }
}
```

**说明**：
- 此接口会实时计算并返回结果
- 适用于单日扫描场景
- 会自动保存所有得分≥20的记录到数据库

## 前端调用示例

### JavaScript/Axios

```javascript
// 批量计算金叉并入库
async function batchCalculateGoldenCross(startDate, endDate, universe = 'mainboard') {
  try {
    const response = await axios.post('/api/startup/batch-golden-cross', null, {
      params: {
        start_date: startDate,  // 格式: '2024-01-01'
        end_date: endDate,      // 格式: '2024-01-31'
        universe: universe,
        batch_size: 20
      }
    });
    
    console.log('任务已启动:', response.data);
    return response.data;
  } catch (error) {
    console.error('请求失败:', error);
    throw error;
  }
}

// 查询处理状态
async function getBatchStatus(startDate, endDate) {
  try {
    const response = await axios.get('/api/startup/batch-golden-cross/status', {
      params: {
        start_date: startDate,
        end_date: endDate
      }
    });
    
    console.log('处理状态:', response.data);
    return response.data;
  } catch (error) {
    console.error('查询状态失败:', error);
    throw error;
  }
}

// 使用示例
(async () => {
  // 启动批量计算任务
  await batchCalculateGoldenCross('2024-01-01', '2024-01-31', 'mainboard');
  
  // 轮询查询状态（可选）
  const checkInterval = setInterval(async () => {
    const status = await getBatchStatus('2024-01-01', '2024-01-31');
    console.log(`处理进度: ${status.progress.percentage}%`);
    
    if (status.progress.percentage >= 100) {
      clearInterval(checkInterval);
      console.log('批量计算完成！');
    }
  }, 5000); // 每5秒查询一次
})();
```

### React Hook 示例

```typescript
import { useState, useEffect } from 'react';
import axios from 'axios';

interface BatchStatus {
  success: boolean;
  trading_dates: {
    total: number;
    processed: number;
    remaining: number;
  };
  records: {
    total: number;
    golden_cross: number;
    confirmed: number;
    started: number;
  };
  progress: {
    percentage: number;
  };
}

function useBatchGoldenCross(startDate: string, endDate: string) {
  const [status, setStatus] = useState<BatchStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 启动批量计算任务
  const startBatch = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await axios.post('/api/startup/batch-golden-cross', null, {
        params: {
          start_date: startDate,
          end_date: endDate,
          universe: 'mainboard',
          batch_size: 20
        }
      });
      
      console.log('任务已启动:', response.data);
      return response.data;
    } catch (err: any) {
      setError(err.response?.data?.detail || '启动任务失败');
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // 查询状态
  const fetchStatus = async () => {
    try {
      const response = await axios.get('/api/startup/batch-golden-cross/status', {
        params: {
          start_date: startDate,
          end_date: endDate
        }
      });
      
      setStatus(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || '查询状态失败');
    }
  };

  // 自动轮询状态
  useEffect(() => {
    if (!startDate || !endDate) return;

    fetchStatus(); // 立即查询一次
    
    const interval = setInterval(() => {
      fetchStatus();
    }, 5000); // 每5秒查询一次

    return () => clearInterval(interval);
  }, [startDate, endDate]);

  return {
    status,
    loading,
    error,
    startBatch,
    fetchStatus
  };
}

// 组件使用示例
function BatchGoldenCrossComponent() {
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-01-31');
  
  const { status, loading, error, startBatch } = useBatchGoldenCross(startDate, endDate);

  return (
    <div>
      <div>
        <label>开始日期:</label>
        <input 
          type="date" 
          value={startDate} 
          onChange={(e) => setStartDate(e.target.value)} 
        />
      </div>
      <div>
        <label>结束日期:</label>
        <input 
          type="date" 
          value={endDate} 
          onChange={(e) => setEndDate(e.target.value)} 
        />
      </div>
      
      <button onClick={startBatch} disabled={loading}>
        {loading ? '启动中...' : '批量计算金叉'}
      </button>

      {error && <div style={{color: 'red'}}>{error}</div>}

      {status && (
        <div>
          <h3>处理状态</h3>
          <div>总交易日: {status.trading_dates.total}</div>
          <div>已处理: {status.trading_dates.processed}</div>
          <div>剩余: {status.trading_dates.remaining}</div>
          <div>处理进度: {status.progress.percentage}%</div>
          <div>
            <h4>保存记录</h4>
            <div>总计: {status.records.total}</div>
            <div>金叉: {status.records.golden_cross}</div>
            <div>确认: {status.records.confirmed}</div>
            <div>完全启动: {status.records.started}</div>
          </div>
        </div>
      )}
    </div>
  );
}
```

## 使用建议

### 1. 批量计算场景

**推荐使用**：`POST /api/startup/batch-golden-cross`

**适用场景**：
- 历史数据回填
- 批量计算一段时间范围内的金叉
- 补充缺失的数据

**注意事项**：
- 任务在后台执行，不会阻塞API响应
- 可以通过状态查询接口监控处理进度
- 建议分批处理，每批不超过1个月的数据

### 2. 实时扫描场景

**推荐使用**：`GET /api/startup/scan`

**适用场景**：
- 单日实时扫描
- 查看当前交易日的最新金叉
- 需要立即返回结果的场景

### 3. 完整回填场景

**推荐使用**：`POST /api/startup/backfill-history`

**适用场景**：
- 需要完整的条件检查（不仅计算金叉，还检查后续条件）
- 数据质量要求高的场景

## 性能说明

- **批量计算**：支持并行处理，充分利用CPU多核
- **数据库优化**：使用批量提交，减少数据库I/O
- **预过滤**：自动过滤没有价格数据的股票，减少无效计算
- **建议批处理大小**：默认20个交易日，可根据服务器性能调整

## 错误处理

所有接口都会返回标准的错误响应：

```json
{
  "detail": "错误信息描述"
}
```

常见错误：
- `400`: 参数错误（如日期格式错误、日期范围超过限制）
- `500`: 服务器内部错误

建议前端进行适当的错误处理和用户提示。

