import { expect, test } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const publicId = process.env.ASSESSMENT_CANARY_PUBLIC_ID
const accessCode = process.env.ASSESSMENT_CANARY_ACCESS_CODE
const identifier = process.env.ASSESSMENT_CANARY_IDENTIFIER
if (!publicId || !accessCode || !identifier) throw new Error('canary fixture inputs required')

test('restores an offline queued answer after a simulated response-service outage', async ({ page, context }) => {
  await page.goto(`/assessment/${publicId}`)
  await page.getByLabel('Student identifier').fill(identifier)
  await page.getByLabel('Access code').fill(accessCode)
  await page.getByRole('button', { name: 'Begin assessment' }).click()
  const answer = page.locator('input[type="radio"]').first()
  await expect(answer).toBeVisible()

  await context.setOffline(true)
  await answer.check()
  await expect(page.getByText(/Offline — queued|Saved locally/)).toBeVisible()
  await context.setOffline(false)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByText(/Saved/)).toBeVisible({ timeout: 30_000 })

  let failedOnce = false
  await page.route('**/responses', async (route) => {
    if (!failedOnce) {
      failedOnce = true
      await route.abort('connectionfailed')
    } else {
      await route.continue()
    }
  })
  const outageAnswer = page.locator('input[type="radio"]').nth(1)
  await outageAnswer.check()
  await expect.poll(() => failedOnce).toBe(true)
  await page.unroute('**/responses')
  await page.reload()
  await expect(outageAnswer).toBeChecked({ timeout: 30_000 })
  await expect(page.getByText(/Saved/)).toBeVisible()
  await page.getByRole('button', { name: 'Save & next' }).click()
  await page.getByRole('button', { name: 'Submit assessment' }).click()
  await page.getByRole('button', { name: 'Submit assessment' }).click()
  await expect(page.getByRole('heading', { name: 'Assessment submitted' })).toBeVisible()

  const output = path.resolve(process.cwd(), '../../artifacts/assessment-capacity/canaries-browser.json')
  await mkdir(path.dirname(output), { recursive: true })
  await writeFile(output, JSON.stringify({ offlineResume: true, browserOutageRecovery: true }, null, 2))
})
