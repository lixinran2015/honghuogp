/**
 * 主题切换：light / dark / system
 * 通过 html.classList 和 localStorage 持久化
 *
 * 注意：theme ref 和 matchMedia 监听器均为模块级单例，
 * 所有调用 useTheme() 的组件共享同一状态，避免重复注册监听器。
 */
import { ref, watch } from 'vue'

const THEME_KEY = 'app_theme'
const THEMES = ['light', 'dark', 'system']

// 模块级单例状态
const theme = ref(
  typeof localStorage !== 'undefined' ? (localStorage.getItem(THEME_KEY) || 'system') : 'system'
)

function applyTheme(val) {
  const html = document.documentElement
  let effective = val
  if (val === 'system') {
    effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  if (effective === 'dark') {
    html.classList.add('dark')
  } else {
    html.classList.remove('dark')
  }
}

// 注册一次 matchMedia 监听器（模块加载时）
if (typeof window !== 'undefined') {
  applyTheme(theme.value)
  const _mq = window.matchMedia('(prefers-color-scheme: dark)')
  _mq.addEventListener('change', () => {
    if (theme.value === 'system') applyTheme('system')
  })
}

watch(theme, applyTheme)

export function useTheme() {
  function setTheme(val) {
    if (!THEMES.includes(val)) return
    theme.value = val
    localStorage.setItem(THEME_KEY, val)
    applyTheme(val)
  }

  function toggleTheme() {
    const idx = (THEMES.indexOf(theme.value) + 1) % THEMES.length
    setTheme(THEMES[idx])
  }

  function getThemeLabel() {
    const labels = { light: '浅色', dark: '深色', system: '跟随系统' }
    return labels[theme.value] || theme.value
  }

  return { theme, setTheme, toggleTheme, getThemeLabel }
}
