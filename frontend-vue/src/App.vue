<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <!-- 左侧边栏（大屏常驻，小屏抽屉） -->
    <Sidebar />
    
    <!-- 移动端遮罩 -->
    <div
      v-show="sidebarOpen"
      class="fixed inset-0 bg-black/40 z-30 lg:hidden"
      aria-hidden="true"
      @click="closeSidebar"
    />
    
    <!-- 顶部操作栏 -->
    <TopBar @open-command-palette="commandPaletteOpen = true" />
    
    <!-- 全局命令面板 Cmd/Ctrl+K -->
    <CommandPalette :is-open="commandPaletteOpen" @close="commandPaletteOpen = false" />
    
    <!-- 主内容区 -->
    <main class="lg:ml-64 pt-16 min-h-screen">
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
import { useTheme } from './composables/useTheme'
import { provideLayout } from './composables/useLayout'

useTheme() // 应用主题（页面加载时）
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

