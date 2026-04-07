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

  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: originalLocalStorage,
    writable: true,
  })

  document.body.innerHTML = ''
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
    await flushPromises()
    await nextTick()
    expect(wrapper.text()).toContain('平安银行')
    expect(wrapper.text()).toContain('000001.SZ')
    wrapper.unmount()
  })

  it('selects a stock row and opens the detail drawer', async () => {
    const wrapper = mount(LeaderTrackingView)
    await flushPromises()
    await nextTick()

    // 1. Click the row containing 平安银行
    const row = wrapper.find('[data-testid="leader-row-000001.SZ"]')
    expect(row.exists()).toBe(true)
    await row.trigger('click')
    await flushPromises()
    await nextTick()

    // 2. Assert internal state updated
    expect(wrapper.vm.selectedTsCode).toBe('000001.SZ')
    expect(wrapper.vm.selectedName).toBe('平安银行')

    // 3. Assert the row gets the selected highlight class
    expect(row.classes()).toContain('bg-indigo-50')
    expect(row.classes()).toContain('border-indigo-200')

    // 4. Assert drawer opened and data loaded (MSW returns 12.5 as latest_price)
    expect(wrapper.vm.drawerOpen).toBe(true)
    expect(wrapper.vm.drawerStock).not.toBeNull()
    expect(wrapper.vm.drawerStock.latest_price).toBe(12.5)

    // 5. Assert drawer content rendered in Teleport body
    expect(document.body.textContent).toContain('平安银行')
    expect(document.body.textContent).toContain('12.50')
    expect(document.body.textContent).toContain('首板放量')
    expect(document.body.textContent).toContain('银行')
    expect(document.body.textContent).toContain('12.00')
    expect(document.body.textContent).toContain('止损价')

    wrapper.unmount()
  })
})
