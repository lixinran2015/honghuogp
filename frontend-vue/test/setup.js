import { setupServer } from 'msw/node'
import { handlers } from './msw/handlers.js'

// 为 undici fetch 设置全局 origin，使相对 URL 在 jsdom 中可用
// 注意：这是 undici 内部实现细节，升级 Node/Vitest 版本时可能需要重新评估
const undiciOriginSymbol = Symbol.for('undici.globalOrigin.1')
if (globalThis[undiciOriginSymbol] === undefined) {
  globalThis[undiciOriginSymbol] = new URL('http://localhost:3000')
}

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
