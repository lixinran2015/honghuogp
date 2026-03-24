<template>
  <!-- 智能问答按钮（浮动按钮，非外部打开时显示） -->
  <button
    v-if="!showChat && !open"
    @click="openChat()"
    class="fixed bottom-6 right-6 w-14 h-14 bg-purple-600 text-white rounded-full shadow-lg hover:bg-purple-700 transition-all flex items-center justify-center z-40"
    title="智能问答"
  >
    <span class="text-2xl">💬</span>
  </button>

  <!-- 智能问答弹窗 -->
  <div v-if="showChat || open" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] flex flex-col">
      <!-- 头部 -->
      <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-lg">
        <h2 class="text-xl font-bold text-gray-800">💬 智能问答</h2>
        <button
          @click="closeChat"
          class="text-gray-500 hover:text-gray-700 text-2xl"
          type="button"
        >
          ×
        </button>
      </div>

      <!-- 常见问题快捷按钮 -->
      <div class="px-6 py-3 bg-gray-50 border-b border-gray-200">
        <div class="text-xs text-gray-600 mb-2">常见问题：</div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="(question, idx) in quickQuestions"
            :key="idx"
            @click="sendQuickQuestion(question)"
            class="px-3 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-100 transition-colors"
          >
            {{ question }}
          </button>
        </div>
      </div>

      <!-- 对话历史 -->
      <div class="flex-1 overflow-y-auto p-6 space-y-4">
        <div v-if="messages.length === 0" class="text-center text-gray-500 py-8">
          <div class="text-lg mb-2">👋 你好！我是AI助手</div>
          <div class="text-sm">可以问我关于股票投资、系统功能等问题</div>
        </div>

        <div v-for="(msg, idx) in messages" :key="idx" class="space-y-2">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="flex justify-end">
            <div class="max-w-[80%] bg-blue-600 text-white rounded-lg px-4 py-2">
              {{ msg.content }}
            </div>
          </div>

          <!-- AI消息 -->
          <div v-else class="flex justify-start">
            <div class="max-w-[80%] bg-gray-100 text-gray-800 rounded-lg px-4 py-2 whitespace-pre-wrap">
              {{ msg.content }}
              <div v-if="msg.used_rag" class="mt-2 text-xs text-gray-500">
                📚 已使用知识库
              </div>
            </div>
          </div>
        </div>

        <!-- 加载状态 -->
        <div v-if="loading" class="flex justify-start">
          <div class="bg-gray-100 rounded-lg px-4 py-2">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
              <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.4s"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入框 -->
      <div class="sticky bottom-0 bg-white border-t border-gray-200 px-6 py-4 rounded-b-lg">
        <div class="flex items-center gap-2">
          <input
            v-model="inputText"
            @keyup.enter="sendMessage"
            type="text"
            placeholder="输入您的问题..."
            class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            :disabled="loading"
          />
          <button
            @click="sendMessage"
            :disabled="loading || !inputText.trim()"
            class="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ loading ? '发送中...' : '发送' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  /** 外部控制打开（v-model:open） */
  open: { type: Boolean, default: false },
  /** 打开时预填的问题（如选股页传入当前筛选条件） */
  initialQuestion: { type: String, default: '' },
})

const emit = defineEmits(['update:open'])

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const showChat = ref(false)
const inputText = ref('')
const loading = ref(false)
const messages = ref([])

function openChat(question = '') {
  showChat.value = true
  if (question || props.initialQuestion) {
    inputText.value = question || props.initialQuestion
  }
  emit('update:open', true)
}

function closeChat() {
  showChat.value = false
  emit('update:open', false)
}

// 外部 v-model:open 打开时，预填问题
watch(() => props.open, (val) => {
  if (val) {
    showChat.value = true
    if (props.initialQuestion) {
      inputText.value = props.initialQuestion
    }
  }
})

defineExpose({ openChat })

const quickQuestions = [
  '什么是多级漏斗框架？',
  '如何判断股票是否启动？',
  '量化模型的局限性是什么？',
  '如何设置止损？',
  '什么是龙头诊断？'
]

function sendQuickQuestion(question) {
  inputText.value = question
  sendMessage()
}

async function sendMessage() {
  if (!inputText.value.trim() || loading.value) {
    return
  }

  const userMessage = inputText.value.trim()
  inputText.value = ''
  
  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userMessage
  })

  loading.value = true

  try {
    const response = await axios.post(
      `${API_BASE_URL}/api/ai-chat`,
      {
        query: userMessage,
        use_rag: true
      }
    )

    if (response.data.success) {
      messages.value.push({
        role: 'assistant',
        content: response.data.answer,
        used_rag: response.data.used_rag
      })
    } else {
      messages.value.push({
        role: 'assistant',
        content: `抱歉，回答失败：${response.data.message || '未知错误'}`
      })
    }
  } catch (error) {
    messages.value.push({
      role: 'assistant',
      content: `抱歉，请求失败：${error.response?.data?.message || error.message || '网络错误'}`
    })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 滚动条样式 */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #555;
}
</style>
