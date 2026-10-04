import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

test('real committed assessment save recovers a dropped response and persists newer edits', async ({ page }) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  await page.goto('/admin/assessments')
  await page.getByRole('button', { name: 'New assessment', exact: true }).click()
  await page.getByRole('button', { name: 'Create assessment', exact: true }).click()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  const id = new URL(page.url()).pathname.split('/').at(-1)!
  const revisions: string[] = []
  let loseResponse!: () => void
  const pending = new Promise<void>(resolve => { loseResponse = resolve })
  await page.route(`**/api/v2/admin/assessment/drafts/${id}`, async route => {
    if (route.request().method() !== 'PATCH') return route.continue()
    revisions.push(route.request().headers()['if-match'])
    const response = await route.fetch()
    expect(response.status(), await response.text()).toBe(200)
    if (revisions.length === 1) {
      // The real handler has committed before its response is withheld.
      expect((await response.json()).revision).toBe(2)
      await pending
      return route.abort('connectionreset')
    }
    return route.fulfill({ response })
  })
  const name = page.getByRole('textbox', { name: 'Assessment name', exact: true })
  await name.fill('Synthetic committed first edit')
  await expect.poll(() => revisions).toEqual(['1'])
  await name.fill('Synthetic newer retained edit')
  await expect(page.getByText('All changes saved', { exact: true })).toHaveCount(0)
  loseResponse()
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(revisions).toEqual(['1', '2'])
  const persisted = await page.request.get(`/api/v2/admin/assessment/drafts/${id}`)
  expect(persisted.ok(), await persisted.text()).toBe(true)
  const saved = await persisted.json()
  expect(saved.revision).toBe(3)
  expect(saved.document.title).toBe('Synthetic newer retained edit')
  await page.reload()
  await expect(name).toHaveValue('Synthetic newer retained edit')
  await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
  expect(revisions).toEqual(['1', '2'])
})
