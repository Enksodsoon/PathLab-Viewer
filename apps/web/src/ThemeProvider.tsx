import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import {
  DARK_THEME_QUERY,
  THEME_STORAGE_KEY,
  ThemeContext,
  type ThemeContextValue,
  type ThemePreference,
  type ResolvedTheme,
} from './theme'

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (isThemePreference(stored)) return stored
    if (stored !== null) window.localStorage.removeItem(THEME_STORAGE_KEY)
  } catch {
    // Storage can be unavailable in private or policy-restricted contexts.
  }
  return 'system'
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia?.(DARK_THEME_QUERY).matches ? 'dark' : 'light'
}

function applyResolvedTheme(preference: ThemePreference, resolvedTheme: ResolvedTheme) {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme
  root.dataset.themePreference = preference
  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  themeColor?.setAttribute('content', resolvedTheme === 'dark' ? '#181715' : '#faf9f5')
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readStoredPreference)
  const [preferredSystemTheme, setPreferredSystemTheme] = useState<ResolvedTheme>(systemTheme)
  const resolvedTheme = preference === 'system' ? preferredSystemTheme : preference

  useEffect(() => {
    const media = window.matchMedia?.(DARK_THEME_QUERY)
    if (!media) return undefined
    const update = (event: MediaQueryListEvent) => setPreferredSystemTheme(event.matches ? 'dark' : 'light')
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useLayoutEffect(() => {
    applyResolvedTheme(preference, resolvedTheme)
  }, [preference, resolvedTheme])

  const value = useMemo<ThemeContextValue>(() => ({
    preference,
    resolvedTheme,
    setPreference(nextPreference) {
      setPreferenceState(nextPreference)
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, nextPreference)
      } catch {
        // The active page can still switch theme when persistence is unavailable.
      }
    },
  }), [preference, resolvedTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
