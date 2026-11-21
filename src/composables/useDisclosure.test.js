import { describe, expect, it, vi, afterEach } from 'vitest'
import { useAccordion, useDisclosure } from './useDisclosure'

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
