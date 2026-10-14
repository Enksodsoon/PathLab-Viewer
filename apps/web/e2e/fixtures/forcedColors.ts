import { expect, type Locator, type Page } from '@playwright/test'

export async function focusByTabSequence(page: Page, control: Locator, label: string) {
  const previousTabIndex = await page.evaluate(() => document.body.getAttribute('tabindex'))
  await page.evaluate(() => {
    document.body.setAttribute('tabindex', '-1')
    document.body.focus()
  })

  try {
    for (let index = 0; index < 60; index += 1) {
      await page.keyboard.press('Tab')
      if (await control.evaluate((element) => element === document.activeElement)) return index + 1
    }
    const activeElement = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.outerHTML.slice(0, 160))
    throw new Error(`Tab sequence did not reach ${label}; active element: ${activeElement ?? 'none'}`)
  } finally {
    await page.evaluate((tabIndex) => {
      if (tabIndex === null) document.body.removeAttribute('tabindex')
      else document.body.setAttribute('tabindex', tabIndex)
    }, previousTabIndex)
  }
}

export async function expectForcedColorsFocus(
  page: Page,
  control: Locator,
  options: { alreadyFocused?: boolean } = {},
) {
  await page.emulateMedia({ forcedColors: 'active' })
  if (!options.alreadyFocused) await focusByTabSequence(page, control, 'forced-colors target')
  await expect(control).toBeFocused()

  const style = await control.evaluate((element) => {
    const computed = getComputedStyle(element)
    return {
      forcedColors: matchMedia('(forced-colors: active)').matches,
      focusVisible: element.matches(':focus-visible'),
      outlineColor: computed.outlineColor,
      outlineStyle: computed.outlineStyle,
      outlineWidth: Number.parseFloat(computed.outlineWidth),
    }
  })

  expect(style.forcedColors).toBe(true)
  expect(style.focusVisible).toBe(true)
  expect(style.outlineStyle).not.toBe('none')
  expect(style.outlineWidth).toBeGreaterThanOrEqual(2)
  expect(style.outlineColor).not.toBe('rgba(0, 0, 0, 0)')
  return style
}
