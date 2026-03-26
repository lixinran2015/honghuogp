<template>
  <div class="min-h-screen bg-warm-50 text-warmgray-800">
    <!-- 左侧边栏（大屏常驻，小屏抽屉） -->
    <Sidebar />

    <!-- 移动端遮罩 -->
    <div
      v-show="sidebarOpen"
      class="fixed inset-0 bg-warmgray-900/40 z-30 lg:hidden backdrop-blur-sm"
      aria-hidden="true"
      @click="closeSidebar"
    />

    <!-- 顶部操作栏 -->
    <TopBar @open-command-palette="commandPaletteOpen = true" />

    <!-- 全局命令面板 Cmd/Ctrl+K -->
    <CommandPalette :is-open="commandPaletteOpen" @close="commandPaletteOpen = false" />

    <!-- 主内容区 -->
    <main class="lg:ml-64 pt-16 min-h-screen bg-warm-50">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import Sidebar from './components/layout/Sidebar.vue'
import TopBar from './components/layout/TopBar.vue'
import CommandPalette from './components/CommandPalette.vue'
import { preloadAllData } from './services/dataPreloader'
import { provideLayout } from './composables/useLayout'

const { sidebarOpen, closeSidebar } = provideLayout()
const commandPaletteOpen = ref(false)

function onKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    commandPaletteOpen.value = true
  }
}

onMounted(() => {
  preloadAllData()
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<style>
/* 全局样式覆盖 */
html {
  font-family: 'Nunito Sans', system-ui, sans-serif;
}

/* 滚动条样式 - 暖色调 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #F5F5F4;
}

::-webkit-scrollbar-thumb {
  background: #D6D3D1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #A8A29E;
}

/* 选中文字样式 */
::selection {
  background: rgba(217, 119, 6, 0.25);
  color: #1C1917;
}

/* 数字字体 */
.font-data {
  font-family: 'Fira Code', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}

/* Glassmorphism 效果 - 暖色调 */
.glass {
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(231, 229, 228, 0.8);
}

.glass-strong {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(231, 229, 228, 0.9);
}

/* 股票涨跌颜色 */
.stock-up {
  color: #059669;
}

.stock-up-bg {
  background-color: rgba(5, 150, 105, 0.12);
}

.stock-down {
  color: #DC2626;
}

.stock-down-bg {
  background-color: rgba(220, 38, 38, 0.12);
}

.stock-neutral {
  color: #78716C;
}

/* 实时数据更新动画 */
.data-updated {
  animation: dataUpdate 1s ease-out;
}

@keyframes dataUpdate {
  0% { background-color: rgba(217, 119, 6, 0.25); }
  100% { background-color: transparent; }
}

/* 脉冲动画 - 实时指示器 */
.live-indicator {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

/* 卡片悬停效果 */
.card-hover {
  transition: all 0.2s ease-out;
}

.card-hover:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.08), 0 2px 4px 0 rgba(0, 0, 0, 0.04);
}
</style>

