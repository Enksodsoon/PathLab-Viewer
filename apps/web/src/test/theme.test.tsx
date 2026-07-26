import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  THEME_STORAGE_KEY,
  type ThemePreference,
  useTheme,
} from '../theme'
import { ThemeProvider } from '../ThemeProvider'

function installMatchMedia(initialDark = false) {
  let dark = initialDark
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const matchMedia = vi.fn((query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' ? dark : false,
    media: query,
    onchange: null,
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    },
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: matchMedia })
  return {
    setDark(nextDark: boolean) {
      dark = nextDark
      const event = { matches: dark, media: '(prefers-color-scheme: dark)' } as MediaQueryListEvent
      listeners.forEach((listener) => listener(event))
    },
  }
}

function ThemeHarness() {
  const { preference, resolvedTheme, setPreference } = useTheme()
  return (
    <>
      <output>{`${preference}:${resolvedTheme}`}</output>
      {(['light', 'dark', 'system'] satisfies ThemePreference[]).map((theme) => (
        <button key={theme} onClick={() => setPreference(theme)}>{theme}</button>
      ))}
    </>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-theme-preference')
  installMatchMedia(false)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('theme foundation', () => {
  it('defaults to system and follows operating-system changes', async () => {
    const media = installMatchMedia(false)
    render(<ThemeProvider><ThemeHarness /></ThemeProvider>)

    expect(screen.getByText('system:light')).toBeVisible()
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(document.documentElement).toHaveAttribute('data-theme-preference', 'system')

    media.setDark(true)
    await waitFor(() => expect(screen.getByText('system:dark')).toBeVisible())
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })

  it('persists an explicit choice and ignores later system changes', async () => {
    const media = installMatchMedia(false)
    render(<ThemeProvider><ThemeHarness /></ThemeProvider>)

    await userEvent.click(screen.getByRole('button', { name: 'dark' }))
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')

    media.setDark(false)
    expect(screen.getByText('dark:dark')).toBeVisible()
  })

  it('restores a valid choice and replaces invalid stored values with system', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    const { unmount } = render(<ThemeProvider><ThemeHarness /></ThemeProvider>)
    expect(screen.getByText('light:light')).toBeVisible()
    unmount()

    localStorage.setItem(THEME_STORAGE_KEY, 'sepia')
    render(<ThemeProvider><ThemeHarness /></ThemeProvider>)
    expect(screen.getByText('system:light')).toBeVisible()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull()
  })

  it('survives unavailable browser storage', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError')
    })

    render(<ThemeProvider><ThemeHarness /></ThemeProvider>)
    expect(screen.getByText('system:light')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'dark' }))
    expect(screen.getByText('dark:dark')).toBeVisible()
    expect(getItem).toHaveBeenCalled()
    expect(setItem).toHaveBeenCalled()
  })
})
