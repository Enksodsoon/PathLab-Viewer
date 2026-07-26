(() => {
  const storageKey = 'pathlab-theme:v1'
  let preference = 'system'

  try {
    const storedPreference = window.localStorage.getItem(storageKey)
    if (storedPreference === 'light' || storedPreference === 'dark' || storedPreference === 'system') {
      preference = storedPreference
    }
  } catch {
    // Storage can be unavailable in hardened browsing contexts. System remains safe.
  }

  const systemPrefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  const resolvedTheme = preference === 'system'
    ? (systemPrefersDark ? 'dark' : 'light')
    : preference

  document.documentElement.setAttribute('data-theme', resolvedTheme)
})()
