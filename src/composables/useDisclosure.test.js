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

describe('press handlers during layout shift', () => {
  function press(el, type, props = {}) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerType: 'mouse', clientX: 10, clientY: 10, detail: 1 }, props)
    el.dispatchEvent(event)
  }

  it('runs the action when the element moves under the pointer between down and up', () => {
    const action = vi.fn()
    const el = document.createElement('button')
    document.body.appendChild(el)
    let top = 100
    el.getBoundingClientRect = () => ({ left: 0, right: 200, top, bottom: top + 40, width: 200, height: 40, x: 0, y: top })
    const handlers = usePressAction(action)
    el.addEventListener('pointerdown', handlers.pointerdown)
    el.addEventListener('click', handlers.click)

    vi.useFakeTimers()
    press(el, 'pointerdown', { clientX: 100, clientY: 120 })
    // 按住期间容器滚动，元素被移走，抬起点相对元素已偏出，但元素确实位移了
    top = 40
    const other = document.createElement('button')
    document.body.appendChild(other)
    const up = new Event('pointerup', { bubbles: true })
    Object.assign(up, { clientX: 100, clientY: 120 })
    other.dispatchEvent(up)
    vi.runAllTimers()

    expect(action).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    el.remove()
    other.remove()
  })
})

describe('late click after fallback', () => {
  function press(el, type, props = {}) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerType: 'mouse', clientX: 10, clientY: 10, detail: 1 }, props)
    el.dispatchEvent(event)
  }

  it('does not toggle back when the click arrives long after the fallback ran', () => {
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

    // 主线程繁忙导致 click 晚到 900ms，仍属于同一次按压，不能再执行一次
    vi.advanceTimersByTime(900)
    press(el, 'click')
    expect(action).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    el.remove()
  })
})

describe('keyboard click stays independent', () => {
  function press(el, type, props = {}) {
    const event = new Event(type, { bubbles: true, cancelable: true })
    Object.assign(event, { button: 0, isPrimary: true, pointerType: 'mouse', clientX: 5, clientY: 5, detail: 1 }, props)
    el.dispatchEvent(event)
  }

  it('still runs a keyboard click that follows a mouse fallback', () => {
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

    press(el, 'click', { detail: 0 })
    expect(action).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
    el.remove()
  })
})
