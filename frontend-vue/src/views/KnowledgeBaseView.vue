<template>
  <div class="container mx-auto px-4 py-6">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">📚 知识库</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">文档、研报、笔记与 AI 问答</p>
    </div>

    <!-- Tab 切换 -->
    <div class="flex gap-2 border-b border-gray-200 mb-4">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        :class="[
          'px-4 py-2 text-sm font-medium border-b-2 transition-colors',
          activeTab === tab.id
            ? 'border-primary-500 text-primary-600'
            : 'border-transparent text-gray-500 hover:text-gray-700'
        ]"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 文档 Tab -->
    <div v-if="activeTab === 'docs'" class="bg-white rounded-lg shadow overflow-hidden" style="min-height: 480px;">
      <div class="p-3 border-b flex items-center gap-3">
        <button
          @click="importToRag"
          :disabled="importing"
          class="px-3 py-1.5 rounded text-sm bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {{ importing ? '导入中...' : '导入文档到 RAG' }}
        </button>
        <button
          @click="importLeadersToRag"
          :disabled="importingLeaders"
          class="px-3 py-1.5 rounded text-sm bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50"
        >
          {{ importingLeaders ? '同步中...' : '同步龙头到 RAG' }}
        </button>
        <span v-if="importMessage" :class="importSuccess ? 'text-green-600' : 'text-red-600'" class="text-sm">
          {{ importMessage }}
        </span>
      </div>
      <div class="flex" style="min-height: 420px;">
        <aside class="w-56 border-r bg-gray-50 overflow-y-auto">
          <div class="p-2">
            <div v-for="cat in categories" :key="cat" class="mb-3">
              <div class="text-xs font-semibold text-gray-500 uppercase px-2 py-1">{{ cat }}</div>
              <button
                v-for="doc in documentsByCategory(cat)"
                :key="doc.id"
                @click="selectDoc(doc)"
                :class="[
                  'w-full text-left px-3 py-1.5 rounded text-sm',
                  selectedPath === doc.path ? 'bg-primary-100 text-primary-800 font-medium' : 'text-gray-700 hover:bg-gray-200'
                ]"
              >
                {{ doc.title }}
              </button>
            </div>
          </div>
        </aside>
        <main class="flex-1 p-4 overflow-y-auto">
          <div v-if="loadingContent" class="text-gray-500 py-8">加载中...</div>
          <div v-else-if="!selectedPath" class="text-gray-400 text-center py-16">请在左侧选择文档</div>
          <div v-else class="prose prose-sm max-w-none" v-html="renderedDocContent"></div>
        </main>
      </div>
    </div>

    <!-- 研报 Tab -->
    <div v-if="activeTab === 'reports'" class="bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-3 mb-4">
        <input v-model="reportStockCode" placeholder="股票代码（可选）" class="border rounded px-3 py-1.5 text-sm w-32" />
        <input v-model="reportDays" type="number" placeholder="天数" class="border rounded px-3 py-1.5 text-sm w-20" />
        <button @click="fetchReports" :disabled="loadingReports" class="px-3 py-1.5 rounded text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
          {{ loadingReports ? '加载中...' : '查询研报' }}
        </button>
        <button @click="importReportsToRag" :disabled="importingReports" class="px-3 py-1.5 rounded text-sm bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
          {{ importingReports ? '导入中...' : '导入到 RAG' }}
        </button>
        <span v-if="reportMessage" :class="reportSuccess ? 'text-green-600' : 'text-red-600'" class="text-sm">{{ reportMessage }}</span>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-3">标题</th>
              <th class="py-2 px-3">来源</th>
              <th class="py-2 px-3">股票</th>
              <th class="py-2 px-3">评级</th>
              <th class="py-2 px-3">日期</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in reports" :key="r.info_code" class="border-b border-gray-50 hover:bg-gray-50">
              <td class="py-2 px-3 max-w-xs truncate">{{ r.title }}</td>
              <td class="py-2 px-3">{{ r.org_name }}</td>
              <td class="py-2 px-3">{{ r.stock_name || r.industry }}</td>
              <td class="py-2 px-3">{{ r.rating }}</td>
              <td class="py-2 px-3 text-gray-500">{{ r.pub_date }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!reports.length && !loadingReports" class="text-center text-gray-400 py-8">暂无研报</div>
      </div>
    </div>

    <!-- 笔记 Tab -->
    <div v-if="activeTab === 'notes'" class="bg-white rounded-lg shadow p-4">
      <div class="flex items-center gap-3 mb-4">
        <select v-model="noteTypeFilter" class="border rounded px-3 py-1.5 text-sm">
          <option value="">全部类型</option>
          <option value="general">一般笔记</option>
          <option value="lesson">教训</option>
          <option value="success">成功经验</option>
          <option value="mistake">错误总结</option>
        </select>
        <button @click="fetchNotes" :disabled="loadingNotes" class="px-3 py-1.5 rounded text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
          刷新
        </button>
        <button @click="showAddNote = true" class="px-3 py-1.5 rounded text-sm bg-green-600 text-white hover:bg-green-700">
          + 新建笔记
        </button>
        <button @click="syncNotesToRag" :disabled="syncingNotes" class="px-3 py-1.5 rounded text-sm bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50">
          {{ syncingNotes ? '同步中...' : '同步到 RAG' }}
        </button>
        <span v-if="noteMessage" :class="noteSuccess ? 'text-green-600' : 'text-red-600'" class="text-sm">{{ noteMessage }}</span>
      </div>
      <div class="space-y-3">
        <div v-for="n in notes" :key="n.id" class="border rounded-lg p-3 hover:bg-gray-50">
          <div class="flex items-center justify-between mb-1">
            <span class="font-medium">{{ n.title }}</span>
            <div class="flex items-center gap-2">
              <span :class="getNoteTypeClass(n.note_type)" class="px-2 py-0.5 rounded text-xs">{{ getNoteTypeLabel(n.note_type) }}</span>
              <button @click="deleteNote(n.id)" class="text-red-500 hover:text-red-700 text-xs">删除</button>
            </div>
          </div>
          <div class="text-sm text-gray-600 line-clamp-2">{{ n.content }}</div>
          <div class="text-xs text-gray-400 mt-1">
            <span v-if="n.stock_name">{{ n.stock_name }} ({{ n.symbol }})</span>
            <span v-if="n.profit_rate !== null" :class="n.profit_rate >= 0 ? 'text-red-500' : 'text-green-500'" class="ml-2">
              {{ n.profit_rate >= 0 ? '+' : '' }}{{ n.profit_rate?.toFixed(1) }}%
            </span>
            <span class="ml-2">{{ n.created_at?.slice(0, 10) }}</span>
          </div>
        </div>
        <div v-if="!notes.length && !loadingNotes" class="text-center text-gray-400 py-8">暂无笔记</div>
      </div>

      <!-- 新建笔记弹窗 -->
      <div v-if="showAddNote" class="fixed inset-0 bg-black/30 flex items-center justify-center z-50" @click.self="showAddNote = false">
        <div class="bg-white rounded-lg shadow-xl p-6 w-full max-w-lg">
          <h3 class="text-lg font-medium mb-4">新建投资笔记</h3>
          <div class="space-y-3">
            <input v-model="newNote.title" placeholder="标题" class="w-full border rounded px-3 py-2" />
            <textarea v-model="newNote.content" placeholder="内容" rows="4" class="w-full border rounded px-3 py-2"></textarea>
            <div class="flex gap-3">
              <input v-model="newNote.symbol" placeholder="股票代码（可选）" class="border rounded px-3 py-2 w-28" />
              <input v-model="newNote.stock_name" placeholder="股票名称（可选）" class="border rounded px-3 py-2 flex-1" />
            </div>
            <div class="flex gap-3">
              <select v-model="newNote.note_type" class="border rounded px-3 py-2">
                <option value="general">一般笔记</option>
                <option value="lesson">教训</option>
                <option value="success">成功经验</option>
                <option value="mistake">错误总结</option>
              </select>
              <input v-model="newNote.profit_rate" type="number" step="0.1" placeholder="盈亏%" class="border rounded px-3 py-2 w-24" />
            </div>
            <input v-model="newNote.tags" placeholder="标签（逗号分隔）" class="w-full border rounded px-3 py-2" />
          </div>
          <div class="flex justify-end gap-3 mt-4">
            <button @click="showAddNote = false" class="px-4 py-2 rounded text-gray-600 hover:bg-gray-100">取消</button>
            <button @click="addNote" :disabled="addingNote" class="px-4 py-2 rounded bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
              {{ addingNote ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- AI 问答 Tab -->
    <div v-if="activeTab === 'chat'" class="bg-white rounded-lg shadow">
      <div class="p-4 border-b flex items-center justify-between">
        <div class="text-sm text-gray-500">
          会话: {{ sessionId || '新会话' }} | 消息数: {{ messageCount }}
        </div>
        <button @click="clearSession" class="text-sm text-gray-500 hover:text-gray-700">清空会话</button>
      </div>
      <div class="p-4 h-96 overflow-y-auto space-y-3" ref="chatContainer">
        <div v-for="(msg, idx) in chatMessages" :key="idx" :class="msg.role === 'user' ? 'text-right' : 'text-left'">
          <div
            :class="[
              'inline-block max-w-[80%] px-3 py-2 rounded-lg text-sm',
              msg.role === 'user' ? 'bg-primary-100 text-primary-800' : 'bg-gray-100 text-gray-800'
            ]"
          >
            <div v-html="renderMd(msg.content)"></div>
          </div>
        </div>
        <div v-if="chatLoading" class="text-left">
          <div class="inline-block px-3 py-2 rounded-lg bg-gray-100 text-gray-500 text-sm">思考中...</div>
        </div>
      </div>
      <div class="p-4 border-t flex gap-3">
        <input
          v-model="chatInput"
          @keyup.enter="sendChat"
          placeholder="输入问题，支持多轮追问..."
          class="flex-1 border rounded-lg px-4 py-2"
        />
        <button
          @click="sendChat"
          :disabled="chatLoading || !chatInput.trim()"
          class="px-4 py-2 rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
        >
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import axios from 'axios'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const tabs = [
  { id: 'docs', label: '📄 文档' },
  { id: 'reports', label: '📊 研报' },
  { id: 'notes', label: '📝 笔记' },
  { id: 'chat', label: '💬 AI 问答' },
]
const activeTab = ref('docs')

// ========== 文档 ==========
const documents = ref([])
const categories = ref([])
const loadingList = ref(true)
const selectedPath = ref(null)
const currentDocContent = ref('')
const loadingContent = ref(false)
const importing = ref(false)
const importingLeaders = ref(false)
const importMessage = ref('')
const importSuccess = ref(false)

function documentsByCategory(cat) {
  return documents.value.filter(d => d.category === cat)
}
function selectDoc(doc) {
  selectedPath.value = doc.path
}

const renderedDocContent = computed(() => {
  if (!currentDocContent.value) return ''
  return DOMPurify.sanitize(marked(currentDocContent.value))
})

async function loadDocList() {
  loadingList.value = true
  try {
    const { data } = await axios.get(`${API_BASE_URL}/api/knowledge-base/documents`)
    documents.value = data.documents || []
    categories.value = data.categories || []
  } catch (e) {
    console.error(e)
  } finally {
    loadingList.value = false
  }
}

async function loadDocContent(path) {
  if (!path) { currentDocContent.value = ''; return }
  loadingContent.value = true
  try {
    const { data } = await axios.get(`${API_BASE_URL}/api/knowledge-base/documents/content`, { params: { path } })
    currentDocContent.value = data.content || ''
  } catch (e) {
    console.error(e)
    currentDocContent.value = ''
  } finally {
    loadingContent.value = false
  }
}

watch(selectedPath, path => loadDocContent(path))

async function importToRag() {
  importing.value = true
  importMessage.value = ''
  try {
    const { data } = await axios.post(`${API_BASE_URL}/api/knowledge-base/import-to-rag`)
    importSuccess.value = data.success
    importMessage.value = data.message || (data.success ? `已导入 ${data.count ?? 0} 个文档` : '导入失败')
  } catch (e) {
    importSuccess.value = false
    importMessage.value = e.message
  } finally {
    importing.value = false
  }
}

async function importLeadersToRag() {
  importingLeaders.value = true
  importMessage.value = ''
  try {
    const { data } = await axios.post(`${API_BASE_URL}/api/knowledge-base/import-industry-leaders-to-rag`)
    importSuccess.value = data.success
    importMessage.value = data.message || '同步完成'
  } catch (e) {
    importSuccess.value = false
    importMessage.value = e.message
  } finally {
    importingLeaders.value = false
  }
}

// ========== 研报 ==========
const reports = ref([])
const loadingReports = ref(false)
const importingReports = ref(false)
const reportStockCode = ref('')
const reportDays = ref(30)
const reportMessage = ref('')
const reportSuccess = ref(false)

async function fetchReports() {
  loadingReports.value = true
  reportMessage.value = ''
  try {
    const params = { days: reportDays.value }
    if (reportStockCode.value) params.stock_code = reportStockCode.value
    const { data } = await axios.get(`${API_BASE_URL}/api/ai-chat/reports`, { params })
    reports.value = data.reports || []
  } catch (e) {
    console.error(e)
  } finally {
    loadingReports.value = false
  }
}

async function importReportsToRag() {
  importingReports.value = true
  reportMessage.value = ''
  try {
    const payload = { days: reportDays.value, max_reports: 20, extract_points: true }
    if (reportStockCode.value) payload.stock_code = reportStockCode.value
    const { data } = await axios.post(`${API_BASE_URL}/api/ai-chat/reports/import`, payload)
    reportSuccess.value = data.success
    reportMessage.value = data.message || '导入完成'
  } catch (e) {
    reportSuccess.value = false
    reportMessage.value = e.message
  } finally {
    importingReports.value = false
  }
}

// ========== 笔记 ==========
const notes = ref([])
const loadingNotes = ref(false)
const syncingNotes = ref(false)
const noteTypeFilter = ref('')
const noteMessage = ref('')
const noteSuccess = ref(false)
const showAddNote = ref(false)
const addingNote = ref(false)
const newNote = ref({
  title: '',
  content: '',
  symbol: '',
  stock_name: '',
  note_type: 'general',
  profit_rate: null,
  tags: '',
})

function getNoteTypeClass(type) {
  const map = {
    general: 'bg-gray-100 text-gray-700',
    lesson: 'bg-yellow-100 text-yellow-700',
    success: 'bg-green-100 text-green-700',
    mistake: 'bg-red-100 text-red-700',
  }
  return map[type] || 'bg-gray-100 text-gray-700'
}

function getNoteTypeLabel(type) {
  const map = { general: '笔记', lesson: '教训', success: '成功', mistake: '错误' }
  return map[type] || type
}

async function fetchNotes() {
  loadingNotes.value = true
  noteMessage.value = ''
  try {
    const params = { limit: 100 }
    if (noteTypeFilter.value) params.note_type = noteTypeFilter.value
    const { data } = await axios.get(`${API_BASE_URL}/api/ai-chat/notes`, { params })
    notes.value = data.notes || []
  } catch (e) {
    console.error(e)
  } finally {
    loadingNotes.value = false
  }
}

async function addNote() {
  if (!newNote.value.title || !newNote.value.content) return
  addingNote.value = true
  try {
    const payload = { ...newNote.value }
    if (payload.profit_rate === '' || payload.profit_rate === null) delete payload.profit_rate
    const { data } = await axios.post(`${API_BASE_URL}/api/ai-chat/notes`, payload)
    if (data.success) {
      showAddNote.value = false
      newNote.value = { title: '', content: '', symbol: '', stock_name: '', note_type: 'general', profit_rate: null, tags: '' }
      fetchNotes()
    }
  } catch (e) {
    console.error(e)
  } finally {
    addingNote.value = false
  }
}

async function deleteNote(noteId) {
  if (!confirm('确定删除这条笔记吗？')) return
  try {
    await axios.delete(`${API_BASE_URL}/api/ai-chat/notes/${noteId}`)
    fetchNotes()
  } catch (e) {
    console.error(e)
  }
}

async function syncNotesToRag() {
  syncingNotes.value = true
  noteMessage.value = ''
  try {
    const { data } = await axios.post(`${API_BASE_URL}/api/ai-chat/notes/sync-to-rag`, { user_id: 1 })
    noteSuccess.value = data.success
    noteMessage.value = data.message || '同步完成'
  } catch (e) {
    noteSuccess.value = false
    noteMessage.value = e.message
  } finally {
    syncingNotes.value = false
  }
}

// ========== AI 问答 ==========
const chatMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const sessionId = ref(null)
const messageCount = ref(0)
const chatContainer = ref(null)

function renderMd(text) {
  return DOMPurify.sanitize(marked(text || ''))
}

async function sendChat() {
  const query = chatInput.value.trim()
  if (!query) return
  chatMessages.value.push({ role: 'user', content: query })
  chatInput.value = ''
  chatLoading.value = true
  await nextTick()
  if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight

  try {
    const payload = { query, use_rag: true, use_history: true, include_lessons: true }
    if (sessionId.value) payload.session_id = sessionId.value
    const { data } = await axios.post(`${API_BASE_URL}/api/ai-chat`, payload)
    if (data.success) {
      chatMessages.value.push({ role: 'assistant', content: data.answer })
      sessionId.value = data.session_id
      messageCount.value = data.message_count || 0
    } else {
      chatMessages.value.push({ role: 'assistant', content: data.message || '请求失败' })
    }
  } catch (e) {
    chatMessages.value.push({ role: 'assistant', content: '请求失败: ' + e.message })
  } finally {
    chatLoading.value = false
    await nextTick()
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function clearSession() {
  if (sessionId.value) {
    try {
      await axios.post(`${API_BASE_URL}/api/ai-chat/sessions/${sessionId.value}/clear`)
    } catch (e) {
      console.error(e)
    }
  }
  chatMessages.value = []
  sessionId.value = null
  messageCount.value = 0
}

// ========== 初始化 ==========
onMounted(() => {
  loadDocList()
})

watch(activeTab, tab => {
  if (tab === 'reports' && !reports.value.length) fetchReports()
  if (tab === 'notes' && !notes.value.length) fetchNotes()
})
</script>
