<template>
  <div class="voice-alert-container">
    <!-- 语音提醒开关 -->
    <div class="flex items-center gap-2 mb-4">
      <button
        @click="toggleVoiceAlert"
        :class="[
          'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          isEnabled
            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
            : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
        ]"
      >
        <SpeakerWaveIcon v-if="isEnabled" class="w-4 h-4" />
        <SpeakerXMarkIcon v-else class="w-4 h-4" />
        {{ isEnabled ? '语音提醒开启' : '语音提醒关闭' }}
      </button>
      <span class="text-xs text-gray-500 dark:text-gray-400">
        断板股票上涨2%时语音播报
      </span>
    </div>

    <!-- 最近提醒列表 -->
    <div v-if="recentAlerts.length > 0" class="space-y-2">
      <h4 class="text-sm font-medium text-gray-700 dark:text-gray-300">最近提醒</h4>
      <div class="space-y-2 max-h-48 overflow-y-auto">
        <div
          v-for="alert in recentAlerts"
          :key="alert.id"
          :class="[
            'p-3 rounded-lg text-sm',
            alert.announced
              ? 'bg-gray-50 dark:bg-gray-800/50 text-gray-500'
              : 'bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800'
          ]"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium" :class="alert.announced ? 'text-gray-600' : 'text-orange-700 dark:text-orange-400'">
              {{ alert.name }} ({{ alert.ts_code }})
            </span>
            <span class="text-xs text-gray-400">{{ formatTime(alert.alert_time) }}</span>
          </div>
          <p class="mt-1" :class="alert.announced ? 'text-gray-500' : 'text-orange-600 dark:text-orange-300'">
            {{ alert.message }}
          </p>
        </div>
      </div>
    </div>

    <!-- 测试按钮 -->
    <div class="mt-4 flex gap-2">
      <button
        @click="testVoice"
        class="px-3 py-1.5 text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
      >
        测试语音
      </button>
      <button
        @click="fetchAlerts"
        class="px-3 py-1.5 text-xs bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
      >
        刷新提醒
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { SpeakerWaveIcon, SpeakerXMarkIcon } from '@heroicons/vue/24/outline'

// 状态
const isEnabled = ref(localStorage.getItem('voiceAlertEnabled') === 'true')
const recentAlerts = ref([])
const pollInterval = ref(null)

// 语音合成
const synth = window.speechSynthesis

// 切换语音提醒
function toggleVoiceAlert() {
  isEnabled.value = !isEnabled.value
  localStorage.setItem('voiceAlertEnabled', isEnabled.value)

  if (isEnabled.value) {
    speak('语音提醒已开启')
    startPolling()
  } else {
    stopPolling()
  }
}

// 语音播报
function speak(text) {
  if (!isEnabled.value || !synth) return

  // 取消之前的播报
  synth.cancel()

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  utterance.rate = 1.0
  utterance.pitch = 1.0

  synth.speak(utterance)
}

// 测试语音
function testVoice() {
  speak('断板回调上涨测试：测试股票从断板价 10.00 上涨至 10.25，涨幅 2.50%')
}

// 获取提醒列表
async function fetchAlerts() {
  try {
    const response = await fetch('/api/break-board/voice-alerts?limit=10')
    if (!response.ok) throw new Error('获取提醒失败')

    const alerts = await response.json()

    // 找出新提醒并播报
    const newAlerts = alerts.filter(alert =>
      !recentAlerts.value.some(a => a.id === alert.id)
    )

    // 播报新提醒
    for (const alert of newAlerts) {
      if (isEnabled.value) {
        speak(alert.message)
        // 标记已播报
        await markAnnounced(alert.id)
      }
    }

    recentAlerts.value = alerts.map(alert => ({
      ...alert,
      announced: newAlerts.some(a => a.id === alert.id) || alert.announced
    }))
  } catch (error) {
    console.error('获取语音提醒失败:', error)
  }
}

// 标记已播报
async function markAnnounced(alertId) {
  try {
    await fetch(`/api/break-board/mark-announced/${alertId}`, {
      method: 'POST'
    })
  } catch (error) {
    console.error('标记播报失败:', error)
  }
}

// 开始轮询
function startPolling() {
  stopPolling()
  pollInterval.value = setInterval(fetchAlerts, 10000) // 每10秒轮询一次
}

// 停止轮询
function stopPolling() {
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
  }
}

// 格式化时间
function formatTime(timeStr) {
  const date = new Date(timeStr)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 组件挂载
onMounted(() => {
  fetchAlerts()
  if (isEnabled.value) {
    startPolling()
  }
})

// 组件卸载
onUnmounted(() => {
  stopPolling()
})
</script>
