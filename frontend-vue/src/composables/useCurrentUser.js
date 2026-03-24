import { ref } from 'vue'

// 轻量级账号 / 角色管理：后续可替换为真实登录态
// 角色含义：
// - guest: 访客 / 试用用户
// - paid: 已付费用户（普通版）
// - pro: 专业版 / 内部账号

const STORAGE_KEY = 'leader_strategy_current_user_role'

const roleRef = ref(loadInitialRole())

function loadInitialRole() {
  if (typeof window === 'undefined') return 'guest'
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved === 'guest' || saved === 'paid' || saved === 'pro') {
      return saved
    }
  } catch (e) {
    // ignore
  }
  return 'guest'
}

function setRole(nextRole) {
  if (!['guest', 'paid', 'pro'].includes(nextRole)) return
  roleRef.value = nextRole
  try {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, nextRole)
    }
  } catch (e) {
    // ignore
  }
}

export function useCurrentUser() {
  const availableRoles = [
    { value: 'guest', label: '访客 / 试用' },
    { value: 'paid', label: '付费用户' },
    { value: 'pro', label: '专业版' },
  ]

  return {
    currentUserRole: roleRef,
    setCurrentUserRole: setRole,
    availableRoles,
  }
}

