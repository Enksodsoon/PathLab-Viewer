import { readFileSync } from 'node:fs'

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ThemeControl } from '../theme/ThemeControl'
import { ThemeProvider, useTheme } from '../theme/ThemeProvider'
import { THEME_STORAGE_KEY } from '../theme/theme'

type MediaListener = (event: MediaQueryListEvent) => void

function installColorScheme(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<MediaListener>()
  const mediaQuery = {
    get matches() { return matches },
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_: 'change', listener: MediaListener) => listeners.add(listener),
    removeEventListener: (_: 'change', listener: MediaListener) => listeners.delete(listener),
    addListener: (listener: MediaListener) => listeners.add(listener),
    removeListener: (listener: MediaListener) => listeners.delete(listener),
    dispatchEvent: () => true,
  } as MediaQueryList

  vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery))

  return {
    setMatches(nextMatches: boolean) {
      matches = nextMatches
      const event = { matches, media: mediaQuery.media } as MediaQueryListEvent
      listeners.forEach((listener) => listener(event))
    },
  }
}

function ThemeProbe() {
  const { preference, resolvedTheme } = useTheme()
  return <output>{`${preference}/${resolvedTheme}`}</output>
}

function renderTheme() {
  return render(
    <ThemeProvider>
      <ThemeProbe />
      <ThemeControl />
    </ThemeProvider>,
  )
}

function relativeLuminance(hex: string) {
  const channels = hex.match(/[a-f\d]{2}/gi)?.map((channel) => Number.parseInt(channel, 16) / 255)
  if (!channels || channels.length !== 3) throw new Error(`Expected a six-digit hex colour, received ${hex}`)

  const [red, green, blue] = channels.map((channel) => (
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  ))
  return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
}

function contrastRatio(foreground: string, background: string) {
  const [lighter, darker] = [relativeLuminance(foreground), relativeLuminance(background)].sort((a, b) => b - a)
  return (lighter + 0.05) / (darker + 0.05)
}

afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  vi.unstubAllGlobals()
})

it('defaults to the system preference and resolves the current OS theme', () => {
  installColorScheme(true)

  renderTheme()

  expect(screen.getByText('system/dark')).toBeInTheDocument()
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  expect(screen.getByRole('radio', { name: 'System' })).toBeChecked()
})

it.each([
  ['light', 'light'],
  ['dark', 'dark'],
] as const)('uses a stored %s preference without consulting the OS', (preference, resolvedTheme) => {
  installColorScheme(preference === 'light')
  localStorage.setItem(THEME_STORAGE_KEY, preference)

  renderTheme()

  expect(screen.getByText(`${preference}/${resolvedTheme}`)).toBeInTheDocument()
  expect(document.documentElement).toHaveAttribute('data-theme', resolvedTheme)
})

it('falls back to system when local storage contains an invalid preference', () => {
  installColorScheme(false)
  localStorage.setItem(THEME_STORAGE_KEY, 'midnight')

  renderTheme()

  expect(screen.getByText('system/light')).toBeInTheDocument()
  expect(document.documentElement).toHaveAttribute('data-theme', 'light')
})

it('tracks OS preference changes while using the system preference', () => {
  const colorScheme = installColorScheme(false)

  renderTheme()
  act(() => colorScheme.setMatches(true))

  expect(screen.getByText('system/dark')).toBeInTheDocument()
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
})

it('persists an explicit choice and applies it to the document root', () => {
  installColorScheme(true)

  renderTheme()
  fireEvent.click(screen.getByRole('radio', { name: 'Light' }))

  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  expect(screen.getByText('light/light')).toBeInTheDocument()
  expect(document.documentElement).toHaveAttribute('data-theme', 'light')
})

it('never renders an explicit preference with a stale resolved or root theme', () => {
  installColorScheme(true)
  const snapshots: Array<{ resolvedTheme: string; rootTheme: string | null }> = []

  function AtomicThemeProbe() {
    const { preference, resolvedTheme, setPreference } = useTheme()
    if (preference === 'light') {
      snapshots.push({
        resolvedTheme,
        rootTheme: document.documentElement.getAttribute('data-theme'),
      })
    }
    return <button onClick={() => setPreference('light')} type="button">Use light theme</button>
  }

  render(<ThemeProvider><AtomicThemeProbe /></ThemeProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Use light theme' }))

  expect(snapshots).toEqual([{ resolvedTheme: 'light', rootTheme: 'light' }])
})

it('switches to system with a fresh OS value after an explicit preference', () => {
  const colorScheme = installColorScheme(false)
  localStorage.setItem(THEME_STORAGE_KEY, 'dark')
  const snapshots: Array<{ resolvedTheme: string; rootTheme: string | null }> = []

  function SystemThemeProbe() {
    const { preference, resolvedTheme, setPreference } = useTheme()
    if (preference === 'system') {
      snapshots.push({
        resolvedTheme,
        rootTheme: document.documentElement.getAttribute('data-theme'),
      })
    }
    return <button onClick={() => setPreference('system')} type="button">Use system theme</button>
  }

  render(<ThemeProvider><SystemThemeProbe /></ThemeProvider>)
  act(() => colorScheme.setMatches(true))
  fireEvent.click(screen.getByRole('button', { name: 'Use system theme' }))

  expect(snapshots).toEqual([{ resolvedTheme: 'dark', rootTheme: 'dark' }])
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
})

it('keeps primary action text at WCAG AA normal-text contrast in both themes', () => {
  const css = readFileSync('src/theme/theme.css', 'utf8')
  const lightBlock = css.match(/:root,\s*\[data-theme='light'\]\s*\{([\s\S]*?)\}/)?.[1]
  const darkBlock = css.match(/\[data-theme='dark'\]\s*\{([\s\S]*?)\}/)?.[1]

  for (const block of [lightBlock, darkBlock]) {
    expect(block).toBeDefined()
    const primary = block?.match(/--primary:\s*(#[\da-f]{6})/i)?.[1]
    const onPrimary = block?.match(/--on-primary:\s*(#[\da-f]{6})/i)?.[1]

    expect(primary).toBeDefined()
    expect(onPrimary).toBeDefined()
    expect(contrastRatio(onPrimary!, primary!)).toBeGreaterThanOrEqual(4.5)
  }
})

it('uses a dedicated near-black navigator surface in dark mode', () => {
  const themeCss = readFileSync('src/theme/theme.css', 'utf8')
  const libraryCss = readFileSync('src/library.css', 'utf8')
  const darkBlock = themeCss.match(/\[data-theme='dark'\]\s*\{([\s\S]*?)\}/)?.[1]

  expect(darkBlock).toContain('--navigator-surface: #06141d')
  expect(libraryCss).toContain('background: var(--navigator-surface)')
})

it('renders an accessible three-choice theme control', () => {
  installColorScheme(false)

  renderTheme()

  expect(screen.getByRole('group', { name: 'Theme preference' })).toBeInTheDocument()
  expect(screen.getAllByRole('radio')).toHaveLength(3)
  expect(screen.getByRole('radio', { name: 'Light' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'System' })).toBeInTheDocument()
})
