/**
 * Tushare ts_code 转换为 TradingView 交易所格式
 * 参考：https://www.tradingview.com/widget-docs/markets/asia-pacific/
 * - 600519.SH → SSE:600519 (上海)
 * - 000001.SZ → SZSE:000001 (深圳)
 * - 430047.BJ → BSE:430047 (北交所，若 TradingView 支持)
 */
export function tsCodeToTradingView(tsCode) {
  if (!tsCode || typeof tsCode !== 'string') return null
  const s = tsCode.trim().toUpperCase()
  const m = s.match(/^(\d{6})\.(SH|SZ|BJ)$/)
  if (!m) return null
  const [, code, exchange] = m
  const map = {
    SH: 'SSE',
    SZ: 'SZSE',
    BJ: 'BSE',
  }
  const exchangeCode = map[exchange] || exchange
  return `${exchangeCode}:${code}`
}
