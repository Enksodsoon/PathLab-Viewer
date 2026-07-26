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

it('renders an accessible three-choice theme control', () => {
  installColorScheme(false)

  renderTheme()

  expect(screen.getByRole('group', { name: 'Theme preference' })).toBeInTheDocument()
  expect(screen.getAllByRole('radio')).toHaveLength(3)
  expect(screen.getByRole('radio', { name: 'Light' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'System' })).toBeInTheDocument()
})
