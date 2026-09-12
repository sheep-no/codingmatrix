const THEME_KEY = 'app-theme'
const TRANSITION_CLASS = 'theme-transitioning'
const DAY_START_HOUR = 6
const DAY_END_HOUR = 18

export const validThemes = ['theme-light', 'theme-dark', 'theme-auto']

let stopAutoFollow = () => {}

function normalizeTheme(theme) {
  if (theme === 'theme-default') return 'theme-light'
  if (validThemes.includes(theme)) return theme
  return 'theme-light'
}

export function getTimeBasedTheme(date = new Date()) {
  const hour = date.getHours()
  return hour >= DAY_START_HOUR && hour < DAY_END_HOUR ? 'theme-light' : 'theme-dark'
}

export function getPreferredSystemTheme() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return getTimeBasedTheme()
  }

  const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const lightQuery = window.matchMedia('(prefers-color-scheme: light)')
  if (darkQuery.matches) return 'theme-dark'
  if (lightQuery.matches) return 'theme-light'
  return getTimeBasedTheme()
}

export function getStoredTheme() {
  return normalizeTheme(localStorage.getItem(THEME_KEY))
}

export function applyTheme(theme, withTransition = false) {
  theme = normalizeTheme(theme)
  const resolvedTheme = theme === 'theme-auto' ? getPreferredSystemTheme() : theme

  if (withTransition) {
    document.documentElement.classList.add(TRANSITION_CLASS)
    setTimeout(() => {
      document.documentElement.classList.remove(TRANSITION_CLASS)
    }, 350)
  }

  ;['theme-light', 'theme-default', 'theme-dark', 'theme-auto'].forEach(name => {
    document.documentElement.classList.remove(name)
  })
  document.documentElement.classList.add(resolvedTheme)
  localStorage.setItem(THEME_KEY, theme)
}

export function initTheme() {
  stopAutoFollow()
  const stored = getStoredTheme()
  applyTheme(stored, false)

  if (stored !== 'theme-auto') {
    return () => {}
  }

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const handleChange = () => applyTheme('theme-auto', true)
  mediaQuery.addEventListener('change', handleChange)
  const timer = window.setInterval(() => applyTheme('theme-auto', false), 60 * 1000)

  stopAutoFollow = () => {
    mediaQuery.removeEventListener('change', handleChange)
    window.clearInterval(timer)
  }
  return stopAutoFollow
}

export function cycleTheme() {
  const current = getStoredTheme()
  const idx = validThemes.indexOf(current)
  const next = validThemes[(idx + 1) % validThemes.length]
  applyTheme(next, true)
  return next
}
