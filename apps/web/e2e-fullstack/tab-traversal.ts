import { expect, type Page } from '@playwright/test'

export async function sweepVisibleTabStops(page: Page, minimum = 1) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  const visited = new Set<string>()
  let finished = false
  for (let index = 0; index < 400; index += 1) {
    await page.keyboard.press('Tab')
    const focus = await page.evaluate(() => {
      const element = document.activeElement
      if (!(element instanceof HTMLElement) || element === document.body) return null
      const path: string[] = []
      for (let current: Element | null = element; current?.parentElement; current = current.parentElement) {
        const peers = [...current.parentElement.children].filter((peer) => peer.tagName === current.tagName)
        path.unshift(`${current.tagName}:${peers.indexOf(current)}`)
      }
      const label = element.getAttribute('aria-label') || element.getAttribute('placeholder')
        || element.textContent?.trim() || element.tagName
      return {
        identity: `${element.tagName}:${element.id}:${label}:${path.join('/')}`,
        visible: element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible',
        enabled: !element.matches(':disabled'),
      }
    })
    if (!focus) {
      finished = true
      break
    }
    expect(focus.visible, `Tab stop ${focus.identity} is visible`).toBe(true)
    expect(focus.enabled, `Tab stop ${focus.identity} is enabled`).toBe(true)
    if (visited.has(focus.identity)) {
      finished = true
      break
    }
    visited.add(focus.identity)
  }
  expect(finished, 'Tab traversal ended instead of exceeding its safety bound').toBe(true)
  expect(visited.size).toBeGreaterThanOrEqual(minimum)
  return [...visited]
}
