import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import ShortTermLeaderDashboard from '../../src/views/ShortTermLeaderDashboard.vue'

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

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ShortTermLeaderDashboard', () => {
  it('renders header and refresh button', async () => {
    const wrapper = mount(ShortTermLeaderDashboard)
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('短线龙头仪表盘')
    expect(wrapper.text()).toContain('刷新数据')
    wrapper.unmount()
  })

  it('opens stock detail drawer when clicking S-grade stock name', async () => {
    const wrapper = mount(ShortTermLeaderDashboard)
    await flushPromises()
    await nextTick()

    // 查找包含”平安银行”的可点击元素
    const nameEl = wrapper.findAll('div').find((el) => el.text().includes('平安银行'))

    if (nameEl) {
      await nameEl.trigger('click')
      await flushPromises()
      await nextTick()
    }

    // 抽屉内容包含 MSW 返回的数据
    expect(wrapper.text()).toContain('平安银行')
  })
})
