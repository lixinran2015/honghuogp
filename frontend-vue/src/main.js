import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './index.css'

// 路由配置
const routes = [
  { path: '/', component: () => import('./views/RecommendationPoolView.vue') },
  { path: '/recommendations', component: () => import('./views/RecommendationsView.vue') },
  { path: '/darwin', component: () => import('./views/DarwinView.vue') },
  { path: '/strategy', component: () => import('./views/StrategyView.vue') },
  { path: '/holdings', component: () => import('./views/HoldingsView.vue') },
  { path: '/watchlist', component: () => import('./views/WatchlistView.vue') },
  { path: '/data-management', component: () => import('./views/DataManagementView.vue') },
  { path: '/monitor-near5', component: () => import('./views/MonitorNear5View.vue') },
  { path: '/high-stocks', component: () => import('./views/HighStocksView.vue') },
  { path: '/high-stocks-broken', component: () => import('./views/HighStocksBrokenView.vue') },
  { path: '/startup', component: () => import('./views/StockStartupView.vue') },
  { path: '/startup-mainline', component: () => import('./views/StartupMainlineRadarView.vue') },
  { path: '/startup-backtest', component: () => import('./views/StartupBacktestView.vue') },
  { path: '/startup-performance', component: () => import('./views/StartupPerformanceView.vue') },
  { path: '/diagnose', component: () => import('./views/StockDiagnoseView.vue') },
  { path: '/recommendation-pool', component: () => import('./views/RecommendationPoolView.vue') },
  { path: '/stock-selector', component: () => import('./views/StockSelectorView.vue') },
  { path: '/guba-popularity', component: () => import('./views/GubaPopularityView.vue') },
  { path: '/scheduled-task', component: () => import('./views/ScheduledTaskView.vue') },
  { path: '/limit-up-2days', component: () => import('./views/LimitUp2DaysView.vue') },
  { path: '/limit-up-today-60d-high', component: () => import('./views/LimitUpToday60dHighView.vue') },
  { path: '/sold-stock', component: () => import('./views/SoldStockView.vue') },
  { path: '/hot-sector', component: () => import('./views/HotSectorView.vue') },
  { path: '/hot-sector-stocks', component: () => import('./views/HotSectorStockListView.vue') },
  { path: '/industry-leaders', component: () => import('./views/IndustryLeadersView.vue') },
  { path: '/absolute-leaders', component: () => import('./views/AbsoluteLeadersView.vue') },
  { path: '/money-flow-heavy', component: () => import('./views/MoneyFlowHeavyView.vue') },
  { path: '/stable-rise', component: () => import('./views/StableRiseView.vue') },
  { path: '/sector-board-leaders', component: () => import('./views/SectorBoardLeadersView.vue') },
  { path: '/theme-rotation', component: () => import('./views/ThemeRotationView.vue') },
  { path: '/leader-tracking', component: () => import('./views/LeaderTrackingView.vue') },
  { path: '/leader-buy-backtest', component: () => import('./views/LeaderBuyBacktestView.vue') },
  { path: '/leader-strategy-intro', component: () => import('./views/LeaderStrategyIntroView.vue') },
  { path: '/leader-buy-meta', component: () => import('./views/LeaderBuyBacktestMetaView.vue') },
  { path: '/knowledge-base', component: () => import('./views/KnowledgeBaseView.vue') },
  { path: '/stock-financial', component: () => import('./views/StockFinancialView.vue') },
  { path: '/trade-calendar', component: () => import('./views/TradeCalendarView.vue') },
  { path: '/industry-cycle', component: () => import('./views/IndustryCycleView.vue') },
  { path: '/daily-review', component: () => import('./views/DailyReviewView.vue') },
  { path: '/sentiment', component: () => import('./views/SentimentAnalysisView.vue') },
  { path: '/backtest', component: () => import('./views/BacktestView.vue') },
  { path: '/factor-lab', component: () => import('./views/FactorExperimentView.vue') },
  { path: '/ai-strategy', component: () => import('./views/AIStrategyAssistantView.vue') },
  { path: '/leader-optimization', component: () => import('./views/LeaderOptimizationView.vue') },
  { path: '/lstm-mab', component: () => import('./views/LSTMMABView.vue') },
  { path: '/lstm-mab-evolution', component: () => import('./views/LSTMMABEvolutionView.vue') },
  { path: '/monitor-dashboard', component: () => import('./views/MonitorDashboardView.vue') },
  { path: '/short-term-dashboard', component: () => import('./views/ShortTermLeaderDashboard.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

createApp(App).use(router).mount('#app')

