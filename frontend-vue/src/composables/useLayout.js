/**
 * 响应式布局：侧边栏展开/折叠状态
 * 大屏(lg+)侧边栏常驻，小屏为抽屉式
 */
import { ref, provide, inject } from 'vue'

const LAYOUT_KEY = Symbol('layout')

export function provideLayout() {
  const sidebarOpen = ref(false)
  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }
  function closeSidebar() {
    sidebarOpen.value = false
  }
  provide(LAYOUT_KEY, { sidebarOpen, toggleSidebar, closeSidebar })
  return { sidebarOpen, toggleSidebar, closeSidebar }
}

export function useLayout() {
  const layout = inject(LAYOUT_KEY)
  if (!layout) {
    return {
      sidebarOpen: ref(false),
      toggleSidebar: () => {},
      closeSidebar: () => {},
    }
  }
  return layout
}
