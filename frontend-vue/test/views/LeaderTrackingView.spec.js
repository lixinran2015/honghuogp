import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import LeaderTrackingView from '../../src/views/LeaderTrackingView.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// Stub echarts
vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
}))

let originalLocalStorage
let consoleSilencer

beforeEach(() => {
  originalLocalStorage = window.localStorage
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
    writable: true,
  })

  consoleSilencer = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: originalLocalStorage,
    writable: true,
  })

  vi.restoreAllMocks()
})

describe('LeaderTrackingView', () => {
  it('renders header and refresh button', async () => {
    const wrapper = mount(LeaderTrackingView)
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('龙头跟踪')
    expect(wrapper.text()).toContain('刷新数据')
    wrapper.unmount()
  })

  it('displays leader rows after fetch', async () => {
    const wrapper = mount(LeaderTrackingView)
    // 组件 onMounted 会自动调用 fetchData，MSW  intercepts
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('000001.SZ')
    wrapper.unmount()
  })
})
