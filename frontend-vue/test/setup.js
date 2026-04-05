import { setupServer } from 'msw/node'
import { handlers } from './msw/handlers.js'

// 为 undici fetch 设置全局 origin，使相对 URL 在 jsdom 中可用
const undiciOriginSymbol = Symbol.for('undici.globalOrigin.1')
if (globalThis[undiciOriginSymbol] === undefined) {
  globalThis[undiciOriginSymbol] = new URL('http://localhost:3000')
}

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
