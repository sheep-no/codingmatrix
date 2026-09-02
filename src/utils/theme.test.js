import { beforeEach, describe, expect, it } from 'vitest'

import {
  applyTheme,
  cycleTheme,
  getStoredTheme,
  initTheme,
} from './theme'

describe('theme utilities', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
  })

  it('stores and applies a valid theme', () => {
    applyTheme('theme-dark')

    expect(getStoredTheme()).toBe('theme-dark')
    expect(document.documentElement.classList.contains('theme-dark')).toBe(true)
  })

  it('falls back to the default theme for invalid values', () => {
    applyTheme('unknown-theme')

    expect(getStoredTheme()).toBe('theme-default')
    expect(document.documentElement.classList.contains('theme-default')).toBe(true)
  })

  it('initializes from local storage and cycles to the next theme', () => {
    localStorage.setItem('app-theme', 'theme-light')

    initTheme()
    const nextTheme = cycleTheme()

    expect(nextTheme).toBe('theme-default')
    expect(getStoredTheme()).toBe('theme-default')
  })
})
