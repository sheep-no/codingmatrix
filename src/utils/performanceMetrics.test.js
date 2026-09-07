import { describe, expect, it, vi } from 'vitest'
import { createClsTracker, createInpTracker, installPerformanceMetrics, PERFORMANCE_SNAPSHOT_EVENT } from './performanceMetrics.js'

function createHarness() {
  const beforeEachHandlers = []
  const afterEachHandlers = []
  const removeBeforeEach = vi.fn()
  const removeAfterEach = vi.fn()
  const router = {
    currentRoute: { value: { fullPath: '/' } },
    beforeEach: vi.fn(handler => {
      beforeEachHandlers.push(handler)
      return removeBeforeEach
    }),
    afterEach: vi.fn(handler => {
      afterEachHandlers.push(handler)
      return removeAfterEach
    })
  }
  const observerInstances = []
  class MockPerformanceObserver {
    static supportedEntryTypes = ['largest-contentful-paint', 'layout-shift', 'event']

    constructor(callback) {
      this.callback = callback
      this.disconnect = vi.fn()
      observerInstances.push(this)
    }

    observe(options) {
      this.options = options
    }
  }
  class MockCustomEvent {
    constructor(type, init) {
      this.type = type
      this.detail = init.detail
    }
  }
  const target = {
    location: { pathname: '/' },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  }
  const clock = { now: vi.fn(), interactionCount: 0 }

  return {
    router,
    beforeEachHandlers,
    afterEachHandlers,
    removeBeforeEach,
    removeAfterEach,
    observerInstances,
    target,
    clock,
    options: {
      target,
      performance: clock,
      PerformanceObserver: MockPerformanceObserver,
      CustomEvent: MockCustomEvent,
      buildVersion: 'test-build'
    }
  }
}

describe('performance metrics', () => {
  it('calculates CLS with session windows and ignores recent input', () => {
    const trackCls = createClsTracker()

    expect(trackCls([
      { startTime: 100, value: 0.05, hadRecentInput: false },
      { startTime: 700, value: 0.04, hadRecentInput: false },
      { startTime: 900, value: 0.8, hadRecentInput: true },
      { startTime: 7000, value: 0.2, hadRecentInput: false }
    ])).toBe(0.2)
  })

  it('groups interaction events and calculates the INP percentile', () => {
    const trackInp = createInpTracker()
    const entries = Array.from({ length: 50 }, (_, index) => ({
      interactionId: index + 1,
      duration: 200 - index
    }))
    entries.push({ interactionId: 2, duration: 240 }, { interactionId: 0, duration: 500 })

    expect(trackInp(entries, 50)).toBe(200)
  })

  it('publishes vitals and successful route navigation timing', () => {
    const harness = createHarness()
    harness.clock.now.mockReturnValueOnce(10).mockReturnValueOnce(47.126)
    const collector = installPerformanceMetrics(harness.router, harness.options)
    const observerFor = type => harness.observerInstances.find(observer => observer.options.type === type)

    observerFor('largest-contentful-paint').callback({ getEntries: () => [{ startTime: 2300.556 }] })
    observerFor('layout-shift').callback({ getEntries: () => [{ startTime: 100, value: 0.08, hadRecentInput: false }] })
    harness.clock.interactionCount = 1
    observerFor('event').callback({ getEntries: () => [{ interactionId: 7, duration: 125.432 }] })
    harness.beforeEachHandlers[0]({ fullPath: '/agent' })
    harness.afterEachHandlers[0]({ fullPath: '/agent' }, { fullPath: '/' })

    expect(collector.getSnapshot()).toMatchObject({
      schemaVersion: 1,
      buildVersion: 'test-build',
      route: '/agent',
      navigationMs: 37.13,
      lcp: 2300.56,
      inp: 125.43,
      cls: 0.08
    })
    expect(harness.target.__performanceSnapshot).toBe(collector.getSnapshot())
    expect(harness.target.dispatchEvent).toHaveBeenLastCalledWith(expect.objectContaining({ type: PERFORMANCE_SNAPSHOT_EVENT }))
  })

  it('ignores failed navigations and releases observers and hooks', () => {
    const harness = createHarness()
    harness.clock.now.mockReturnValue(20)
    const collector = installPerformanceMetrics(harness.router, harness.options)

    harness.beforeEachHandlers[0]({ fullPath: '/settings' })
    harness.afterEachHandlers[0]({ fullPath: '/settings' }, { fullPath: '/' }, new Error('cancelled'))
    expect(collector.getSnapshot().route).toBe('/')

    collector.stop()
    expect(harness.observerInstances.every(observer => observer.disconnect.mock.calls.length === 1)).toBe(true)
    expect(harness.removeBeforeEach).toHaveBeenCalledOnce()
    expect(harness.removeAfterEach).toHaveBeenCalledOnce()
    expect(harness.target.removeEventListener).toHaveBeenCalledWith('pagehide', expect.any(Function))
  })
})
