export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = Exclude<ThemePreference, 'system'>

export const THEME_STORAGE_KEY = 'pathlab-theme:v1'

export function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system'
}

export function getStoredThemePreference(): ThemePreference {
  try {
    const storedPreference = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isThemePreference(storedPreference) ? storedPreference : 'system'
  } catch {
    return 'system'
  }
}

export function resolveTheme(
  preference: ThemePreference,
  systemPrefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false,
): ResolvedTheme {
  if (preference === 'system') return systemPrefersDark ? 'dark' : 'light'
  return preference
}

export function applyResolvedTheme(theme: ResolvedTheme) {
  document.documentElement.setAttribute('data-theme', theme)
}

export function persistThemePreference(preference: ThemePreference) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // A blocked local store must not prevent changing the active theme.
  }
}
