<template>
  <div class="sentiment-analysis">
    <h2 class="page-title">情绪分析</h2>
    
    <!-- 搜索区域 -->
    <div class="search-section">
      <div class="search-box">
        <input 
          v-model="searchSymbol" 
          placeholder="输入股票代码，如 600519"
          @keyup.enter="analyzeStock"
        />
        <button @click="analyzeStock" :disabled="loading">
          {{ loading ? '分析中...' : '分析' }}
        </button>
      </div>
    </div>
    
    <!-- 综合情绪卡片 -->
    <div v-if="comprehensiveResult" class="comprehensive-card">
      <div class="card-header">
        <h3>{{ comprehensiveResult.stock_name || searchSymbol }} 综合情绪</h3>
        <span 
          class="sentiment-badge"
          :class="comprehensiveResult.comprehensive_label"
        >
          {{ getSentimentLabel(comprehensiveResult.comprehensive_label) }}
        </span>
      </div>
      
      <div class="score-display">
        <div class="score-value" :class="getScoreClass(comprehensiveResult.comprehensive_score)">
          {{ (comprehensiveResult.comprehensive_score * 100).toFixed(1) }}
        </div>
        <div class="score-label">综合情绪分</div>
      </div>
      
      <div class="dimension-scores">
        <div class="dimension">
          <span class="dim-label">新闻情绪</span>
          <span class="dim-value" :class="getScoreClass(comprehensiveResult.news_sentiment?.score)">
            {{ ((comprehensiveResult.news_sentiment?.score || 0) * 100).toFixed(0) }}
          </span>
          <span class="dim-count">({{ comprehensiveResult.news_sentiment?.count || 0 }}条)</span>
        </div>
        <div class="dimension">
          <span class="dim-label">公告情绪</span>
          <span class="dim-value" :class="getScoreClass(comprehensiveResult.announcement_sentiment?.score)">
            {{ ((comprehensiveResult.announcement_sentiment?.score || 0) * 100).toFixed(0) }}
          </span>
          <span class="dim-count">({{ comprehensiveResult.announcement_sentiment?.count || 0 }}条)</span>
        </div>
        <div class="dimension">
          <span class="dim-label">股吧舆情</span>
          <span class="dim-value" :class="getScoreClass(comprehensiveResult.guba_sentiment?.score)">
            {{ ((comprehensiveResult.guba_sentiment?.score || 0) * 100).toFixed(0) }}
          </span>
          <span class="dim-count">人气 {{ comprehensiveResult.guba_sentiment?.popularity_score || 0 }}</span>
        </div>
      </div>
      
      <!-- 热门话题 -->
      <div v-if="comprehensiveResult.hot_topics?.length" class="hot-topics">
        <span class="topic-label">热门话题：</span>
        <span v-for="topic in comprehensiveResult.hot_topics" :key="topic" class="topic-tag">
          {{ topic }}
        </span>
      </div>
    </div>
    
    <!-- 标签页 -->
    <div class="tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>
    
    <!-- 新闻列表 -->
    <div v-if="activeTab === 'news'" class="news-list">
      <div v-if="comprehensiveResult?.top_news?.length" class="list-container">
        <div 
          v-for="(news, idx) in comprehensiveResult.top_news" 
          :key="idx"
          class="news-item"
        >
          <div class="news-header">
            <span 
              class="sentiment-tag"
              :class="news.sentiment"
            >
              {{ getSentimentLabel(news.sentiment) }}
            </span>
            <span class="news-time">{{ news.pub_time }}</span>
          </div>
          <div class="news-title">
            <a :href="news.url" target="_blank">{{ news.title }}</a>
          </div>
          <div v-if="news.reason" class="news-reason">
            AI 分析：{{ news.reason }}
          </div>
        </div>
      </div>
      <div v-else class="empty-state">暂无新闻数据</div>
    </div>
    
    <!-- 公告列表 -->
    <div v-if="activeTab === 'announcement'" class="announcement-list">
      <div v-if="comprehensiveResult?.top_announcements?.length" class="list-container">
        <div 
          v-for="(ann, idx) in comprehensiveResult.top_announcements" 
          :key="idx"
          class="announcement-item"
        >
          <div class="ann-header">
            <span class="ann-category">{{ ann.category }}</span>
            <span 
              class="importance-tag"
              :class="ann.importance"
            >
              {{ ann.importance === 'high' ? '重要' : (ann.importance === 'medium' ? '一般' : '普通') }}
            </span>
            <span class="ann-time">{{ ann.pub_time }}</span>
          </div>
          <div class="ann-title">
            <a :href="ann.url" target="_blank">{{ ann.title }}</a>
          </div>
          <div v-if="ann.interpretation" class="ann-interpretation">
            <div><strong>核心信息：</strong>{{ ann.interpretation.summary }}</div>
            <div v-if="ann.interpretation.key_numbers"><strong>关键数据：</strong>{{ ann.interpretation.key_numbers }}</div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">暂无公告数据</div>
    </div>
    
    <!-- 市场情绪 -->
    <div v-if="activeTab === 'market'" class="market-sentiment">
      <div class="market-card">
        <h4>市场整体情绪</h4>
        <div class="market-stats">
          <div class="stat-item">
            <span class="stat-label">新闻情绪</span>
            <span 
              class="stat-value"
              :class="marketNews?.overall_sentiment"
            >
              {{ getSentimentLabel(marketNews?.overall_sentiment) }}
              ({{ ((marketNews?.overall_score || 0) * 100).toFixed(0) }})
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">利好新闻</span>
            <span class="stat-value positive">{{ marketNews?.bullish_count || 0 }} 条</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">利空新闻</span>
            <span class="stat-value negative">{{ marketNews?.bearish_count || 0 }} 条</span>
          </div>
        </div>
        <button @click="loadMarketSentiment" :disabled="loadingMarket" class="refresh-btn">
          {{ loadingMarket ? '加载中...' : '刷新市场情绪' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'

export default {
  name: 'SentimentAnalysisView',
  setup() {
    const searchSymbol = ref('')
    const loading = ref(false)
    const loadingMarket = ref(false)
    const comprehensiveResult = ref(null)
    const marketNews = ref(null)
    const activeTab = ref('news')
    
    const tabs = [
      { id: 'news', label: '新闻情绪' },
      { id: 'announcement', label: '公告解读' },
      { id: 'market', label: '市场情绪' },
    ]
    
    const getSentimentLabel = (sentiment) => {
      const labels = {
        'bullish': '利好',
        'positive': '看涨',
        'bearish': '利空',
        'negative': '看跌',
        'neutral': '中性',
      }
      return labels[sentiment] || '中性'
    }
    
    const getScoreClass = (score) => {
      if (score > 0.15) return 'positive'
      if (score < -0.15) return 'negative'
      return 'neutral'
    }
    
    const analyzeStock = async () => {
      if (!searchSymbol.value) return
      
      loading.value = true
      try {
        const resp = await fetch(`/api/sentiment/comprehensive?symbol=${searchSymbol.value}`)
        const data = await resp.json()
        if (data.success) {
          comprehensiveResult.value = data
        } else {
          alert('分析失败: ' + (data.detail || '未知错误'))
        }
      } catch (e) {
        console.error(e)
        alert('分析失败')
      } finally {
        loading.value = false
      }
    }
    
    const loadMarketSentiment = async () => {
      loadingMarket.value = true
      try {
        const resp = await fetch('/api/sentiment/market-news')
        const data = await resp.json()
        if (data.success) {
          marketNews.value = data
        }
      } catch (e) {
        console.error(e)
      } finally {
        loadingMarket.value = false
      }
    }
    
    onMounted(() => {
      loadMarketSentiment()
    })
    
    return {
      searchSymbol,
      loading,
      loadingMarket,
      comprehensiveResult,
      marketNews,
      activeTab,
      tabs,
      getSentimentLabel,
      getScoreClass,
      analyzeStock,
      loadMarketSentiment,
    }
  }
}
</script>

<style scoped>
.sentiment-analysis {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #1a1a2e;
}

.search-section {
  margin-bottom: 24px;
}

.search-box {
  display: flex;
  gap: 12px;
}

.search-box input {
  flex: 1;
  max-width: 300px;
  padding: 10px 16px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
}

.search-box button {
  padding: 10px 24px;
  background: #4f46e5;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.search-box button:disabled {
  background: #9ca3af;
}

.comprehensive-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
}

.sentiment-badge {
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 500;
}

.sentiment-badge.positive, .sentiment-badge.bullish {
  background: #dcfce7;
  color: #16a34a;
}

.sentiment-badge.negative, .sentiment-badge.bearish {
  background: #fee2e2;
  color: #dc2626;
}

.sentiment-badge.neutral {
  background: #f3f4f6;
  color: #6b7280;
}

.score-display {
  text-align: center;
  margin: 20px 0;
}

.score-value {
  font-size: 48px;
  font-weight: 700;
}

.score-value.positive { color: #16a34a; }
.score-value.negative { color: #dc2626; }
.score-value.neutral { color: #6b7280; }

.score-label {
  color: #6b7280;
  font-size: 14px;
}

.dimension-scores {
  display: flex;
  justify-content: space-around;
  padding: 16px 0;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}

.dimension {
  text-align: center;
}

.dim-label {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 4px;
}

.dim-value {
  font-size: 24px;
  font-weight: 600;
}

.dim-value.positive { color: #16a34a; }
.dim-value.negative { color: #dc2626; }
.dim-value.neutral { color: #6b7280; }

.dim-count {
  display: block;
  font-size: 12px;
  color: #9ca3af;
}

.hot-topics {
  margin-top: 16px;
}

.topic-label {
  color: #6b7280;
  font-size: 14px;
}

.topic-tag {
  display: inline-block;
  padding: 4px 8px;
  margin: 4px;
  background: #f3f4f6;
  border-radius: 4px;
  font-size: 12px;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.tabs button {
  padding: 10px 20px;
  border: 1px solid #e5e7eb;
  background: white;
  border-radius: 8px;
  cursor: pointer;
}

.tabs button.active {
  background: #4f46e5;
  color: white;
  border-color: #4f46e5;
}

.list-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.news-item, .announcement-item {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.news-header, .ann-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.sentiment-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.sentiment-tag.bullish, .sentiment-tag.positive { background: #dcfce7; color: #16a34a; }
.sentiment-tag.bearish, .sentiment-tag.negative { background: #fee2e2; color: #dc2626; }
.sentiment-tag.neutral { background: #f3f4f6; color: #6b7280; }

.news-time, .ann-time {
  color: #9ca3af;
  font-size: 12px;
}

.news-title a, .ann-title a {
  color: #1f2937;
  text-decoration: none;
  font-weight: 500;
}

.news-title a:hover, .ann-title a:hover {
  color: #4f46e5;
}

.news-reason {
  margin-top: 8px;
  padding: 8px;
  background: #f9fafb;
  border-radius: 4px;
  font-size: 13px;
  color: #6b7280;
}

.ann-category {
  padding: 2px 8px;
  background: #e0e7ff;
  color: #4338ca;
  border-radius: 4px;
  font-size: 12px;
}

.importance-tag {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.importance-tag.high { background: #fee2e2; color: #dc2626; }
.importance-tag.medium { background: #fef3c7; color: #d97706; }
.importance-tag.low { background: #f3f4f6; color: #6b7280; }

.ann-interpretation {
  margin-top: 8px;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 4px;
  font-size: 13px;
}

.ann-interpretation div {
  margin-bottom: 4px;
}

.market-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.market-card h4 {
  margin: 0 0 16px 0;
}

.market-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.stat-item {
  text-align: center;
}

.stat-label {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
}

.stat-value.positive, .stat-value.bullish { color: #16a34a; }
.stat-value.negative, .stat-value.bearish { color: #dc2626; }

.refresh-btn {
  width: 100%;
  padding: 10px;
  background: #f3f4f6;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.refresh-btn:hover {
  background: #e5e7eb;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}
</style>
