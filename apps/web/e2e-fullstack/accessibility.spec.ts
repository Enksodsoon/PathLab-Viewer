import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'
import { sweepVisibleTabStops } from './tab-traversal'

test('library, dialogs and Teaching Studio pass automated accessibility checks in both themes', async ({ page, isMobile }, testInfo) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const audit = async (surface: string) => {
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze()
    await testInfo.attach(`${surface}.json`, { body: JSON.stringify({ violations: results.violations, incomplete: results.incomplete }), contentType: 'application/json' })
    expect(results.violations.map(({ id, impact, nodes }) => ({ id, impact, targets: nodes.map((node) => node.target) }))).toEqual([])
  }
  for (const theme of ['Light', 'Dark']) {
    await page.getByRole('radio', { name: theme, exact: true }).check()
    await audit(`library-${theme}`)
    await page.getByRole('button', { name: 'Create', exact: true }).click()
    await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
    await audit(`folder-${theme}`)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await page.getByRole('button', { name: 'Upload', exact: true }).first().click()
    await audit(`upload-${theme}`)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: 'Teaching Studio', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'My Assessments', exact: true })).toBeVisible()
    await expect(page.getByRole('status').filter({ hasText: 'Loading assessments' })).not.toBeVisible()
    await audit(`studio-${theme}`)
    await page.goto('/admin')
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  // CSS zoom exercises doubled text/layout; native browser chrome zoom is separate evidence.
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  await expect(page.getByRole('searchbox', { name: 'Search slides', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('css-zoom-200.png') })
  await page.evaluate(() => { document.documentElement.style.zoom = '' })
  if (isMobile) return // Hardware-keyboard evidence is recorded by desktop projects.
  await page.getByRole('button', { name: 'Create', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('menuitem', { name: 'New folder', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Create', exact: true })).toBeFocused()
})

test('keyboard traversal reaches visible enabled controls on library and Teaching Studio', async ({ page, isMobile }) => {
  test.skip(isMobile, 'Hardware keyboard traversal is covered by desktop browser projects')
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  await sweepVisibleTabStops(page, 12)
  await page.getByRole('button', { name: 'Teaching Studio', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'My Assessments', exact: true })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Loading assessments' })).not.toBeVisible()
  await sweepVisibleTabStops(page, 8)
})
