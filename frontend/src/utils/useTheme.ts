import { useEffect, useState } from 'react'
import { getStoredTheme, onThemeChange, type Theme } from './theme'

export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(getStoredTheme)

  useEffect(() => onThemeChange(setTheme), [])

  return theme
}
