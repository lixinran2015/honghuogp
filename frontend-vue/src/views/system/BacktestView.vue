<template>
  <div class="backtest-view">
    <h2 class="page-title">量化回测</h2>
    
    <!-- 回测配置 -->
    <div class="config-section">
      <div class="config-card">
        <h3>回测配置</h3>
        <div class="config-form">
          <div class="form-row">
            <div class="form-group">
              <label>股票代码</label>
              <input v-model="config.symbol" placeholder="如 600519" />
            </div>
            <div class="form-group">
              <label>策略选择</label>
              <select v-model="config.strategyId">
                <option v-for="s in strategies" :key="s.id" :value="s.id">
                  {{ s.name }}
                </option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>开始日期</label>
              <input type="date" v-model="config.startDate" />
            </div>
            <div class="form-group">
              <label>结束日期</label>
              <input type="date" v-model="config.endDate" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>初始资金</label>
              <input type="number" v-model="config.initialCapital" />
            </div>
            <div class="form-group">
              <label>仓位比例</label>
              <input type="number" v-model="config.positionSize" min="0.1" max="1" step="0.1" />
            </div>
          </div>
          <div class="form-actions">
            <button @click="runBacktest" :disabled="loading" class="btn-primary">
              {{ loading ? '回测中...' : '运行回测' }}
            </button>
            <button @click="compareStrategies" :disabled="loading" class="btn-secondary">
              策略对比
            </button>
            <button @click="quickTest" :disabled="loading" class="btn-secondary">
              快速测试
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 回测结果 -->
    <div v-if="result" class="result-section">
      <div class="result-header">
        <h3>回测结果 - {{ result.strategy_name }}</h3>
        <span class="period">{{ result.start_date }} ~ {{ result.end_date }}</span>
      </div>
      
      <!-- 核心指标 -->
      <div class="metrics-grid">
        <div class="metric-card">
          <span class="metric-value" :class="result.total_return >= 0 ? 'positive' : 'negative'">
            {{ result.total_return }}%
          </span>
          <span class="metric-label">总收益率</span>
        </div>
        <div class="metric-card">
          <span class="metric-value" :class="result.annual_return >= 0 ? 'positive' : 'negative'">
            {{ result.annual_return }}%
          </span>
          <span class="metric-label">年化收益</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ result.sharpe_ratio }}</span>
          <span class="metric-label">夏普比率</span>
        </div>
        <div class="metric-card">
          <span class="metric-value negative">{{ result.max_drawdown }}%</span>
          <span class="metric-label">最大回撤</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ result.win_rate }}%</span>
          <span class="metric-label">胜率</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ result.profit_factor }}</span>
          <span class="metric-label">盈亏比</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ result.total_trades }}</span>
          <span class="metric-label">交易次数</span>
        </div>
        <div class="metric-card">
          <span class="metric-value">{{ result.avg_holding_days }}天</span>
          <span class="metric-label">平均持仓</span>
        </div>
      </div>
      
      <!-- 净值曲线 -->
      <div class="chart-section">
        <h4>净值曲线</h4>
        <div class="chart-container">
          <canvas ref="chartCanvas"></canvas>
        </div>
      </div>
      
      <!-- 交易记录 -->
      <div class="trades-section">
        <h4>最近交易记录</h4>
        <table class="trades-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>类型</th>
              <th>价格</th>
              <th>股数</th>
              <th>金额</th>
              <th>原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(trade, idx) in result.trades" :key="idx">
              <td>{{ trade.date }}</td>
              <td>
                <span :class="trade.signal === 'buy' ? 'buy-tag' : 'sell-tag'">
                  {{ trade.signal === 'buy' ? '买入' : '卖出' }}
                </span>
              </td>
              <td>{{ trade.price.toFixed(2) }}</td>
              <td>{{ trade.shares }}</td>
              <td>{{ trade.amount.toFixed(0) }}</td>
              <td>{{ trade.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    
    <!-- 策略对比结果 -->
    <div v-if="compareResults && compareResults.length" class="compare-section">
      <h3>策略对比结果</h3>
      <table class="compare-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>策略</th>
            <th>总收益</th>
            <th>年化收益</th>
            <th>夏普比率</th>
            <th>最大回撤</th>
            <th>胜率</th>
            <th>交易次数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, idx) in compareResults" :key="idx">
            <td>{{ idx + 1 }}</td>
            <td>{{ r.strategy_name }}</td>
            <td :class="r.total_return >= 0 ? 'positive' : 'negative'">{{ r.total_return }}%</td>
            <td :class="r.annual_return >= 0 ? 'positive' : 'negative'">{{ r.annual_return }}%</td>
            <td>{{ r.sharpe_ratio }}</td>
            <td class="negative">{{ r.max_drawdown }}%</td>
            <td>{{ r.win_rate }}%</td>
            <td>{{ r.total_trades }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, nextTick } from 'vue'

export default {
  name: 'BacktestView',
  setup() {
    const loading = ref(false)
    const strategies = ref([])
    const result = ref(null)
    const compareResults = ref(null)
    const chartCanvas = ref(null)
    let chartInstance = null
    
    const today = new Date()
    const oneYearAgo = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())
    
    const config = ref({
      symbol: '600519',
      strategyId: 'ma_5_20',
      startDate: oneYearAgo.toISOString().split('T')[0],
      endDate: today.toISOString().split('T')[0],
      initialCapital: 100000,
      positionSize: 1.0,
    })
    
    const loadStrategies = async () => {
      try {
        const resp = await fetch('/api/backtest/strategies')
        const data = await resp.json()
        if (data.success) {
          strategies.value = data.strategies
        }
      } catch (e) {
        console.error(e)
      }
    }
    
    const runBacktest = async () => {
      loading.value = true
      compareResults.value = null
      try {
        const resp = await fetch('/api/backtest/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategy_id: config.value.strategyId,
            symbol: config.value.symbol,
            start_date: config.value.startDate,
            end_date: config.value.endDate,
            initial_capital: config.value.initialCapital,
            position_size: config.value.positionSize,
          }),
        })
        const data = await resp.json()
        if (data.success) {
          result.value = data
          await nextTick()
          drawChart(data.daily_values)
        } else {
          alert('回测失败: ' + (data.detail || '未知错误'))
        }
      } catch (e) {
        console.error(e)
        alert('回测失败')
      } finally {
        loading.value = false
      }
    }
    
    const compareStrategies = async () => {
      loading.value = true
      result.value = null
      try {
        const resp = await fetch('/api/backtest/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: config.value.symbol,
            start_date: config.value.startDate,
            end_date: config.value.endDate,
            initial_capital: config.value.initialCapital,
          }),
        })
        const data = await resp.json()
        if (data.success) {
          compareResults.value = data.results
        } else {
          alert('对比失败: ' + (data.detail || '未知错误'))
        }
      } catch (e) {
        console.error(e)
        alert('对比失败')
      } finally {
        loading.value = false
      }
    }
    
    const quickTest = async () => {
      loading.value = true
      result.value = null
      try {
        const resp = await fetch(`/api/backtest/quick-test?symbol=${config.value.symbol}&days=365`)
        const data = await resp.json()
        if (data.success) {
          compareResults.value = data.all_results
          if (data.best_strategy) {
            result.value = data.best_strategy
            await nextTick()
            drawChart(data.best_strategy.daily_values)
          }
        } else {
          alert('测试失败: ' + (data.detail || '未知错误'))
        }
      } catch (e) {
        console.error(e)
        alert('测试失败')
      } finally {
        loading.value = false
      }
    }
    
    const drawChart = (dailyValues) => {
      if (!chartCanvas.value || !dailyValues?.length) return
      
      const ctx = chartCanvas.value.getContext('2d')
      const width = chartCanvas.value.parentElement.clientWidth
      const height = 300
      
      chartCanvas.value.width = width
      chartCanvas.value.height = height
      
      // 清空
      ctx.clearRect(0, 0, width, height)
      
      // 数据处理
      const values = dailyValues.map(d => d.value)
      const minVal = Math.min(...values) * 0.98
      const maxVal = Math.max(...values) * 1.02
      const range = maxVal - minVal
      
      // 绘制背景
      ctx.fillStyle = '#f9fafb'
      ctx.fillRect(0, 0, width, height)
      
      // 绘制网格
      ctx.strokeStyle = '#e5e7eb'
      ctx.lineWidth = 1
      for (let i = 0; i <= 4; i++) {
        const y = (height / 4) * i
        ctx.beginPath()
        ctx.moveTo(50, y)
        ctx.lineTo(width - 20, y)
        ctx.stroke()
        
        // Y轴标签
        const val = maxVal - (range / 4) * i
        ctx.fillStyle = '#6b7280'
        ctx.font = '12px sans-serif'
        ctx.textAlign = 'right'
        ctx.fillText(val.toFixed(0), 45, y + 4)
      }
      
      // 绘制净值曲线
      ctx.beginPath()
      ctx.strokeStyle = '#4f46e5'
      ctx.lineWidth = 2
      
      const xStep = (width - 70) / (values.length - 1)
      
      values.forEach((val, i) => {
        const x = 50 + i * xStep
        const y = height - ((val - minVal) / range) * height
        
        if (i === 0) {
          ctx.moveTo(x, y)
        } else {
          ctx.lineTo(x, y)
        }
      })
      ctx.stroke()
      
      // 绘制初始资金基准线
      const baseY = height - ((config.value.initialCapital - minVal) / range) * height
      ctx.setLineDash([5, 5])
      ctx.strokeStyle = '#9ca3af'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(50, baseY)
      ctx.lineTo(width - 20, baseY)
      ctx.stroke()
      ctx.setLineDash([])
    }
    
    onMounted(() => {
      loadStrategies()
    })
    
    return {
      loading,
      strategies,
      config,
      result,
      compareResults,
      chartCanvas,
      runBacktest,
      compareStrategies,
      quickTest,
    }
  }
}
</script>

<style scoped>
.backtest-view {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #1a1a2e;
}

.config-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  margin-bottom: 24px;
}

.config-card h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 14px;
  color: #6b7280;
}

.form-group input,
.form-group select {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.btn-primary {
  padding: 12px 24px;
  background: #4f46e5;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary:disabled {
  background: #9ca3af;
}

.btn-secondary {
  padding: 12px 24px;
  background: #f3f4f6;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.result-header h3 {
  margin: 0;
}

.period {
  color: #6b7280;
  font-size: 14px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.metric-value {
  display: block;
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
}

.metric-value.positive { color: #16a34a; }
.metric-value.negative { color: #dc2626; }

.metric-label {
  color: #6b7280;
  font-size: 14px;
}

.chart-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.chart-section h4 {
  margin: 0 0 16px 0;
}

.chart-container {
  width: 100%;
  height: 300px;
}

.trades-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.trades-section h4 {
  margin: 0 0 16px 0;
}

.trades-table, .compare-table {
  width: 100%;
  border-collapse: collapse;
}

.trades-table th, .trades-table td,
.compare-table th, .compare-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.trades-table th, .compare-table th {
  background: #f9fafb;
  font-weight: 500;
  color: #6b7280;
}

.buy-tag {
  padding: 4px 8px;
  background: #dcfce7;
  color: #16a34a;
  border-radius: 4px;
  font-size: 12px;
}

.sell-tag {
  padding: 4px 8px;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 4px;
  font-size: 12px;
}

.compare-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-top: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.compare-section h3 {
  margin: 0 0 16px 0;
}

.positive { color: #16a34a; }
.negative { color: #dc2626; }

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }
  
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
