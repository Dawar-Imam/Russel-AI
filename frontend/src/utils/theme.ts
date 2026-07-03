export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'russel-ai-theme'
const THEME_EVENT = 'theme-change'

export function getStoredTheme(): Theme {
  return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark'
}

export function applyTheme(theme: Theme) {
  document.body.classList.toggle('light-theme', theme === 'light')
  localStorage.setItem(STORAGE_KEY, theme)
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }))
}

export function initTheme() {
  applyTheme(getStoredTheme())
}

export function toggleTheme() {
  applyTheme(getStoredTheme() === 'light' ? 'dark' : 'light')
}

export function onThemeChange(handler: (theme: Theme) => void) {
  function listener(e: Event) {
    handler((e as CustomEvent<Theme>).detail)
  }
  window.addEventListener(THEME_EVENT, listener)
  return () => window.removeEventListener(THEME_EVENT, listener)
}
