import { rest } from 'msw'

export const leaderTrackingHandlers = [
  rest.get('/api/startup/sector-strength', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        sectors: [],
        space_leaders_lead: [],
      })
    )
  }),

  rest.get('/api/leader-tracking/pool', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        trade_date: '2026-04-05',
        pool: [
          {
            ts_code: '000001.SZ',
            name: '平安银行',
            is_space: true,
            is_new: false,
            continuous_limit: 2,
            sectors: ['银行'],
            lstm_mab_score: {
              total_score: 88,
              grade: 'A',
              expected_return: 12.5,
              confidence: 78.0,
            },
          },
        ],
      })
    )
  }),

  rest.get('/api/leader-tracking/stock-detail/:tsCode', (req, res, ctx) => {
    const { tsCode } = req.params
    return res(
      ctx.json({
        success: true,
        model_available: true,
        data: {
          ts_code: tsCode,
          name: '平安银行',
          latest_price: 12.5,
          price_change_pct: 3.2,
          is_limit_up: false,
          lstm_mab_score: {
            total_score: 88,
            grade: 'A',
            factor_scores: { 龙头地位: 80, 技术形态: 85, 资金流向: 90, 情绪热度: 75 },
            factor_weights: {},
            recommendation: {},
          },
          buy_signal: { signal_type: '首板放量', strength_score: 75, quality: '高' },
          sector_support: { name: '银行', strength: 15 },
          trade_plan: { entry_price: 12.0, stop_loss_price: 11.5, take_profit_1: 13.2, take_profit_2: 13.8 },
        },
      })
    )
  }),

  rest.get('/api/leader-tracking/top-scored', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        model_available: true,
        top_stocks: [],
      })
    )
  }),

  rest.get('/api/stock/kline-20', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        kline: [
          { close: 10, ma20: 9.5, amount: 100000 },
          { close: 11, ma20: 10, amount: 120000 },
          { close: 12, ma20: 10.5, amount: 130000 },
        ],
      })
    )
  }),

  rest.get('/api/stock/realtime-quotes', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        data: {},
      })
    )
  }),

  rest.get('/api/startup/leader-buy-backtest/summary/by-sector', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        summaries: [],
      })
    )
  }),

  rest.post('/api/watchlist', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
      })
    )
  }),
]

export const monitorHandlers = [
  rest.get('/api/short-term/monitor/performance', (req, res, ctx) => {
    return res(
      ctx.json({
        success: true,
        recent_n: 20,
        performance: { sample_count: 20, win_rate: 0.55, profit_factor: 1.8 },
      })
    )
  }),
]

export const handlers = [...leaderTrackingHandlers, ...monitorHandlers]
