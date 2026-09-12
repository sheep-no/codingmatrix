import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  applyTheme,
  cycleTheme,
  getStoredTheme,
  getTimeBasedTheme,
  initTheme,
} from './theme'

function stubMatchMedia(isDark) {
  vi.stubGlobal('matchMedia', query => ({
    matches: query.includes('dark') ? isDark : !isDark && query.includes('light'),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
}

describe('theme utilities', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    stubMatchMedia(false)
  })

  it('stores and applies a valid theme', () => {
    applyTheme('theme-dark')

    expect(getStoredTheme()).toBe('theme-dark')
    expect(document.documentElement.classList.contains('theme-dark')).toBe(true)
  })

  it('maps the legacy default theme to daytime', () => {
    applyTheme('theme-default')

    expect(getStoredTheme()).toBe('theme-light')
    expect(document.documentElement.classList.contains('theme-light')).toBe(true)
  })

  it('falls back to daytime for invalid values', () => {
    applyTheme('unknown-theme')

    expect(getStoredTheme()).toBe('theme-light')
    expect(document.documentElement.classList.contains('theme-light')).toBe(true)
  })

  it('cycles daytime, night and system follow', () => {
    localStorage.setItem('app-theme', 'theme-light')

    initTheme()
    expect(cycleTheme()).toBe('theme-dark')
    expect(cycleTheme()).toBe('theme-auto')
    expect(getStoredTheme()).toBe('theme-auto')
  })

  it('auto follows the system color scheme', () => {
    stubMatchMedia(true)
    applyTheme('theme-auto')

    expect(getStoredTheme()).toBe('theme-auto')
    expect(document.documentElement.classList.contains('theme-dark')).toBe(true)
  })

  it('uses daytime hours as the time-based fallback', () => {
    expect(getTimeBasedTheme(new Date('2026-09-10T09:00:00'))).toBe('theme-light')
    expect(getTimeBasedTheme(new Date('2026-09-10T21:00:00'))).toBe('theme-dark')
  })
})
