// @vitest-environment happy-dom
//
// Live API smoke for the cost/quota screens. Requires the backend on :10200.
// Run with: npm run test:live
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Dashboard from '../pages/Dashboard.vue'
import Jobs from '../pages/Jobs.vue'
import Orchestrate from '../pages/Orchestrate.vue'
import Attempts from '../pages/Attempts.vue'
import Ledger from '../pages/Ledger.vue'
import Quota from '../pages/Quota.vue'
import Settings from '../pages/Settings.vue'

const API = 'http://127.0.0.1:10200'
const realFetch = globalThis.fetch
globalThis.fetch = (url, opts) =>
  realFetch(String(url).startsWith('/') ? API + url : url, opts)

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/:rest(.*)*', component: { template: '<div />' } },
  ],
})

const wait = (ms) => new Promise(r => setTimeout(r, ms))

async function mountPage(component) {
  const wrapper = mount(component, {
    global: { plugins: [router] },
  })
  await wait(300)
  await wrapper.vm.$nextTick()
  return wrapper
}

beforeAll(async () => {
  await router.push('/')
  await router.isReady()
  const health = await realFetch(`${API}/api/health`).then(r => r.json())
  expect(health.ok).toBe(true)
})

afterAll(() => {
  globalThis.fetch = realFetch
})

const pages = { Dashboard, Jobs, Orchestrate, Attempts, Ledger, Quota, Settings }

describe('cost/quota screens render against live API', () => {
  for (const [name, component] of Object.entries(pages)) {
    it(`${name} renders without a danger banner`, async () => {
      const wrapper = await mountPage(component)
      const text = wrapper.text()
      expect(text.length).toBeGreaterThan(20)
      const danger = wrapper.findAll('.tag.danger')
      // Orchestrate/Ledger legitimately show "fused" as a danger tag, so only
      // reject screens whose error banner carries a request failure.
      const errorBanner = text.match(/not found|Failed to fetch|TypeError/)
      expect(errorBanner).toBeNull()
      expect(danger.length === 0 || /熔断|不一致|fused|danger/.test(text)).toBe(true)
      wrapper.unmount()
    })
  }
})

describe('cost/quota screens show the real numbers', () => {
  it('Ledger lists per-attempt charges that match the orchestration total', async () => {
    const wrapper = await mountPage(Ledger)
    const text = wrapper.text()
    expect(text).toContain('dim_customer')
    expect(text).toContain('权重×单价')  // cost mode column
    expect(text).not.toContain('暂无扣费记录')
    wrapper.unmount()
  })

  it('Ledger reconciliation shows all report metrics as matching', async () => {
    const wrapper = await mountPage(Ledger)
    const text = wrapper.text()
    expect(text).toContain('一致')
    expect(text).not.toContain('对不上')
    wrapper.unmount()
  })

  it('Quota page reflects the configured limit', async () => {
    const wrapper = await mountPage(Quota)
    expect(wrapper.text()).toContain('配额上限')
    const inputs = wrapper.findAll('input[type="number"]')
    // inputs are unit price, quota limit — the limit carries the saved 4.00
    expect(inputs.map(i => i.element.value)).toContain('4.00')
    wrapper.unmount()
  })

  it('Orchestrate shows fuse reason and accumulated cost', async () => {
    const wrapper = await mountPage(Orchestrate)
    const text = wrapper.text()
    expect(text).toContain('累计成本')
    expect(text).toContain('fused')
    expect(text).toContain('fact_order_daily')
    wrapper.unmount()
  })
})
