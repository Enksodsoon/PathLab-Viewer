import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
} from 'react'

import {
  applyResolvedTheme,
  getStoredThemePreference,
  persistThemePreference,
  resolveTheme,
  type ResolvedTheme,
  type ThemePreference,
} from './theme'

export type ThemeContextValue = {
  preference: ThemePreference
  resolvedTheme: ResolvedTheme
  setPreference: (preference: ThemePreference) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(getStoredThemePreference)
  const [systemPrefersDark, setSystemPrefersDark] = useState(() => (
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  ))
  const resolvedTheme = resolveTheme(preference, systemPrefersDark)

  useEffect(() => {
    const colorScheme = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!colorScheme) {
      if (preference === 'system') applyResolvedTheme('light')
      return undefined
    }
    const updateSystemPreference = () => {
      const nextSystemPrefersDark = colorScheme.matches
      setSystemPrefersDark(nextSystemPrefersDark)
      if (preference === 'system') {
        applyResolvedTheme(resolveTheme('system', nextSystemPrefersDark))
      }
    }

    updateSystemPreference()
    if (preference !== 'system') return undefined

    colorScheme.addEventListener('change', updateSystemPreference)
    return () => colorScheme.removeEventListener('change', updateSystemPreference)
  }, [preference])

  useLayoutEffect(() => {
    applyResolvedTheme(resolvedTheme)
  }, [resolvedTheme])

  const value = useMemo<ThemeContextValue>(() => ({
    preference,
    resolvedTheme,
    setPreference(nextPreference) {
      const nextSystemPrefersDark = (
        window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
      )
      const nextResolvedTheme = resolveTheme(
        nextPreference,
        nextSystemPrefersDark,
      )
      applyResolvedTheme(nextResolvedTheme)
      persistThemePreference(nextPreference)
      setSystemPrefersDark(nextSystemPrefersDark)
      setPreferenceState(nextPreference)
    },
  }), [preference, resolvedTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within ThemeProvider')
  return context
}
