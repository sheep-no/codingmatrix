import { describe, expect, it, vi, afterEach } from 'vitest'
import { useAccordion, useDisclosure, usePressAction } from './useDisclosure'

afterEach(() => {
  vi.useRealTimers()
})

describe('useDisclosure', () => {
  it('opens on the first click and ignores a rapid second click', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const { isOpen, toggle } = useDisclosure()

    toggle()
    expect(isOpen.value).toBe(true)

    vi.setSystemTime(new Date('2026-01-01T00:00:00.100Z'))
    toggle()
    expect(isOpen.value).toBe(true)

    vi.setSystemTime(new Date('2026-01-01T00:00:01.000Z'))
    toggle()
    expect(isOpen.value).toBe(false)
  })

  it('lets an explicit close run immediately and reopen after the guard window', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const { isOpen, open, close, toggle } = useDisclosure()

    open()
    close()
    expect(isOpen.value).toBe(false)

    vi.setSystemTime(new Date('2026-01-01T00:00:00.100Z'))
    toggle()
    expect(isOpen.value).toBe(true)
  })
})

describe('useAccordion', () => {
  it('toggles a section once per guard window and allows switching sections', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const { activeKey, toggle } = useAccordion()

    toggle('faq-1')
    expect(activeKey.value).toBe('faq-1')

    toggle('faq-1')
    expect(activeKey.value).toBe('faq-1')

    vi.setSystemTime(new Date('2026-01-01T00:00:01.000Z'))
    toggle('faq-1')
    expect(activeKey.value).toBe(null)

    vi.setSystemTime(new Date('2026-01-01T00:00:02.000Z'))
    toggle('faq-2')
    expect(activeKey.value).toBe('faq-2')
  })
})

describe('press handlers fallback', () => {
  function press(el, type, props = {}) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerType: 'mouse', clientX: 10, clientY: 10, detail: 1 }, props)
    el.dispatchEvent(event)
  }

  it('runs the action once when a normal click follows pointerdown', () => {
    const action = vi.fn()
    const el = document.createElement('button')
    document.body.appendChild(el)
    const handlers = usePressAction(action)
    el.addEventListener('pointerdown', handlers.pointerdown)
    el.addEventListener('click', handlers.click)

    vi.useFakeTimers()
    press(el, 'pointerdown')
    window.dispatchEvent(new Event('pointerup'))
    press(el, 'click')
    vi.runAllTimers()

    expect(action).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    el.remove()
  })

  it('still runs the action when the browser never dispatches click', () => {
    const action = vi.fn()
    const el = document.createElement('button')
    document.body.appendChild(el)
    const handlers = usePressAction(action)
    el.addEventListener('pointerdown', handlers.pointerdown)
    el.addEventListener('click', handlers.click)

    vi.useFakeTimers()
    press(el, 'pointerdown')
    window.dispatchEvent(new Event('pointerup'))
    vi.runAllTimers()

    expect(action).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    el.remove()
  })

  it('ignores a drag that moves too far before release', () => {
    const action = vi.fn()
    const el = document.createElement('button')
    document.body.appendChild(el)
    const handlers = usePressAction(action)
    el.addEventListener('pointerdown', handlers.pointerdown)
    el.addEventListener('click', handlers.click)

    vi.useFakeTimers()
    press(el, 'pointerdown')
    const up = new Event('pointerup')
    Object.assign(up, { clientX: 200, clientY: 200 })
    window.dispatchEvent(up)
    vi.runAllTimers()

    expect(action).not.toHaveBeenCalled()
    vi.useRealTimers()
    el.remove()
  })

  it('runs from a keyboard click without any pointer events', () => {
    const action = vi.fn()
    const el = document.createElement('button')
    document.body.appendChild(el)
    el.addEventListener('click', usePressAction(action).click)

    press(el, 'click', { detail: 0 })
    expect(action).toHaveBeenCalledTimes(1)
    el.remove()
  })
})
