import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './index.css'

// 路由配置
const routes = [
  { path: '/', component: () => import('./views/portfolio/RecommendationPoolView.vue') },
  { path: '/recommendations', component: () => import('./views/portfolio/RecommendationsView.vue') },
  { path: '/darwin', component: () => import('./views/screening/DarwinView.vue') },
  { path: '/strategy', component: () => import('./views/StrategyView.vue') },
  { path: '/holdings', component: () => import('./views/portfolio/HoldingsView.vue') },
  { path: '/watchlist', component: () => import('./views/WatchlistView.vue') },
  { path: '/data-management', component: () => import('./views/system/DataManagementView.vue') },
  { path: '/monitor-near5', component: () => import('./views/leader/MonitorNear5View.vue') },
  { path: '/high-stocks', component: () => import('./views/screening/HighStocksView.vue') },
  { path: '/high-stocks-broken', component: () => import('./views/screening/HighStocksBrokenView.vue') },
  { path: '/startup', component: () => import('./views/StockStartupView.vue') },
  { path: '/startup-mainline', component: () => import('./views/leader/StartupMainlineRadarView.vue') },
  { path: '/startup-backtest', component: () => import('./views/leader/StartupBacktestView.vue') },
  { path: '/startup-performance', component: () => import('./views/leader/StartupPerformanceView.vue') },
  { path: '/diagnose', component: () => import('./views/portfolio/StockDiagnoseView.vue') },
  { path: '/recommendation-pool', component: () => import('./views/portfolio/RecommendationPoolView.vue') },
  { path: '/stock-selector', component: () => import('./views/screening/StockSelectorView.vue') },
  { path: '/guba-popularity', component: () => import('./views/screening/GubaPopularityView.vue') },
  { path: '/scheduled-task', component: () => import('./views/system/ScheduledTaskView.vue') },
  { path: '/limit-up-2days', component: () => import('./views/leader/LimitUp2DaysView.vue') },
  { path: '/limit-up-today-60d-high', component: () => import('./views/leader/LimitUpToday60dHighView.vue') },
  { path: '/sold-stock', component: () => import('./views/portfolio/SoldStockView.vue') },
  { path: '/hot-sector', component: () => import('./views/leader/HotSectorView.vue') },
  { path: '/hot-sector-stocks', component: () => import('./views/leader/HotSectorStockListView.vue') },
  { path: '/industry-leaders', component: () => import('./views/system/IndustryLeadersView.vue') },
  { path: '/absolute-leaders', component: () => import('./views/leader/AbsoluteLeadersView.vue') },
  { path: '/money-flow-heavy', component: () => import('./views/leader/MoneyFlowHeavyView.vue') },
  { path: '/stable-rise', component: () => import('./views/screening/StableRiseView.vue') },
  { path: '/sector-board-leaders', component: () => import('./views/leader/SectorBoardLeadersView.vue') },
  { path: '/theme-rotation', component: () => import('./views/ThemeRotationView.vue') },
  { path: '/leader-tracking', component: () => import('./views/leader/LeaderTrackingView.vue') },
  { path: '/leader-buy-backtest', component: () => import('./views/leader/LeaderBuyBacktestView.vue') },
  { path: '/leader-strategy-intro', component: () => import('./views/leader/LeaderStrategyIntroView.vue') },
  { path: '/leader-buy-meta', component: () => import('./views/leader/LeaderBuyBacktestMetaView.vue') },
  { path: '/knowledge-base', component: () => import('./views/system/KnowledgeBaseView.vue') },
  { path: '/stock-financial', component: () => import('./views/portfolio/StockFinancialView.vue') },
  { path: '/trade-calendar', component: () => import('./views/TradeCalendarView.vue') },
  { path: '/industry-cycle', component: () => import('./views/screening/IndustryCycleView.vue') },
  { path: '/daily-review', component: () => import('./views/system/DailyReviewView.vue') },
  { path: '/sentiment', component: () => import('./views/system/SentimentAnalysisView.vue') },
  { path: '/backtest', component: () => import('./views/system/BacktestView.vue') },
  { path: '/factor-lab', component: () => import('./views/screening/FactorExperimentView.vue') },
  { path: '/ai-strategy', component: () => import('./views/system/AIStrategyAssistantView.vue') },
  { path: '/leader-optimization', component: () => import('./views/leader/LeaderOptimizationView.vue') },
  { path: '/lstm-mab', component: () => import('./views/system/LSTMMABView.vue') },
  { path: '/lstm-mab-evolution', component: () => import('./views/system/LSTMMABEvolutionView.vue') },
  { path: '/monitor-dashboard', component: () => import('./views/leader/MonitorDashboardView.vue') },
  { path: '/short-term-dashboard', component: () => import('./views/leader/ShortTermLeaderDashboard.vue') },
  { path: '/daily-report', component: () => import('./views/system/DailyReportView.vue') },
  { path: '/long-term-selection', component: () => import('./views/long-term/LongTermSelectionView.vue') },
  { path: '/four-step-selection', component: () => import('./views/long-term/FourStepSelectionView.vue') },
  { path: '/long-term-tracking-pool', component: () => import('./views/long-term/LongTermTrackingPoolView.vue') },
  { path: '/long-term-portfolio', component: () => import('./views/long-term/LongTermPortfolioView.vue') },
  { path: '/long-term-monitoring', component: () => import('./views/long-term/LongTermMonitoringView.vue') },
  { path: '/long-term-journal', component: () => import('./views/long-term/LongTermJournalView.vue') },
  { path: '/long-term-daily-report', component: () => import('./views/long-term/LongTermDailyReportView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

createApp(App).use(router).mount('#app')

