const THEME_KEY = 'app-theme'
const TRANSITION_CLASS = 'theme-transitioning'

const validThemes = ['theme-light', 'theme-default', 'theme-dark', 'theme-auto']

export function getPreferredSystemTheme() {
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'theme-dark'
  }
  return 'theme-light'
}

export function getStoredTheme() {
  return localStorage.getItem(THEME_KEY) || 'theme-default'
}

export function applyTheme(theme, withTransition = false) {
  if (!validThemes.includes(theme)) {
    theme = 'theme-default'
  }

  const resolvedTheme = theme === 'theme-auto' ? getPreferredSystemTheme() : theme

  if (withTransition) {
    document.documentElement.classList.add(TRANSITION_CLASS)
    setTimeout(() => {
      document.documentElement.classList.remove(TRANSITION_CLASS)
    }, 350)
  }

  // 先移除所有主题类
  validThemes.forEach(t => {
    if (t !== 'theme-auto') {
      document.documentElement.classList.remove(t)
    }
  })
  
  // 然后添加解析后的主题类
  document.documentElement.classList.add(resolvedTheme)

  // 保存用户选择（包括 theme-auto）
  localStorage.setItem(THEME_KEY, theme)
}

export function initTheme() {
  const stored = getStoredTheme()
  applyTheme(stored, false)

  if (stored === 'theme-auto') {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => applyTheme('theme-auto', true)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }

  return () => {}
}

export function cycleTheme() {
  const current = getStoredTheme()
  const order = ['theme-light', 'theme-default', 'theme-dark', 'theme-auto']
  const idx = order.indexOf(current)
  const next = order[(idx + 1) % order.length]
  applyTheme(next, true)
  return next
}
