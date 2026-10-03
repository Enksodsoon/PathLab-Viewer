import { expect, test } from './qa-test'
import { signIn, uploadSyntheticSlide, waitForSlideConversion } from '../e2e-live/capacity-helpers'

for (const action of ['reload', 'layer patch']) {
  test(`queued annotation ${action} cancels cleanly on Library return`, async ({ page, isMobile }) => {
    await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
    const id = await uploadSyntheticSlide(page, process.env.PATHLAB_E2E_OME!, `QA queued ${action}`)
    await waitForSlideConversion(page, id)
    await page.goto(`/admin/preview/${id}`)
    await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).toBeVisible({ timeout: 15000 })
    const open = page.getByRole('button', { name: 'Open annotation inspector', exact: true })
    if (await open.isVisible()) await open.click()
    await page.getByRole('button', { name: 'Show advanced annotation details', exact: true }).click()
    await page.getByRole('button', { name: 'Add annotation layer', exact: true }).click()
    await expect(page.getByText('Layer 1 created', { exact: true })).toBeVisible()
    const visible = page.getByRole('checkbox', { name: 'Show Layer 1', exact: true })
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    let started!: () => void
    const held = new Promise<void>((resolve) => { started = resolve })
    let patches = 0
    const path = `**/api/v2/admin/annotations/slides/${id}/layers/*`
    await page.route(path, async (route) => {
      if (route.request().method() !== 'PATCH') return route.continue()
      patches++
      const response = await route.fetch()
      started()
      await gate
      await route.fulfill({ response })
    })
    try {
      await visible.click()
      await held
      if (action === 'reload') {
        await page.getByRole('button', { name: 'Reload annotations', exact: true }).click()
      } else await visible.click()
      if (isMobile) {
        await page.getByRole('dialog', { name: 'Annotation inspector', exact: true })
          .getByRole('button', { name: 'Close annotation inspector', exact: true }).click()
      }
      await page.getByRole('link', { name: 'Library', exact: true }).click()
      await expect(page).toHaveURL(/\/admin$/)
    } finally { release() }
    // Let the released response and its queued continuation settle. qa-test
    // rejects any unhandled page errors, including after workspace unmount.
    await page.waitForTimeout(250)
    expect(patches).toBe(1)
    await expect(page.getByRole('toolbar', { name: 'Annotation tools' })).not.toBeVisible()
    await page.unroute(path)
  })
}
