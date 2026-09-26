import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

for (const kind of ['invitations', 'progress'] as const) {
  test(`Study ${kind} CSV downloads real contents before object URL cleanup`, async ({ page }) => {
    const csv = 'participant,invitation\r\nSynthetic learner,synthetic-code\r\n'
    await page.route('**/api/v1/admin/study/courses/synthetic/**', (route) => route.fulfill({ contentType: 'text/csv', body: csv }))
    await page.goto('/admin')
    const downloaded = page.waitForEvent('download')
    await page.evaluate(async (exportKind) => {
      // @ts-expect-error Vite serves this actual source module for browser checks.
      const study = await import('/src/study/api.ts')
      if (exportKind === 'invitations') await study.downloadStudyInvitations('synthetic', 1)
      else await study.downloadStudyProgress('synthetic')
    }, kind)
    const download = await downloaded
    expect(await download.failure()).toBeNull()
    expect(download.suggestedFilename()).toBe(`study-${kind}-synthetic.csv`)
    expect(await readFile((await download.path())!, 'utf8')).toBe(csv)
  })
}
