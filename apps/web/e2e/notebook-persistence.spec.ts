import { expect, test } from '@playwright/test'

test('notebook commits survive reload, enforce concurrent capacity, and allow updates at capacity', async ({ page }) => {
  await page.goto('/admin')
  const counts = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const notebook = await import('/src/classroom/notebook.ts')
    const entry = { sessionId: 'synthetic-notebook', slideId: 'slide', slideName: 'Synthetic slide', note: '', createdAt: '' }
    const outcomes = await Promise.allSettled(Array.from({ length: 105 }, (_, index) => notebook.saveEntry({ ...entry, id: `note-${index}` })))
    const values = await notebook.listEntries(entry.sessionId)
    await notebook.saveEntry({ ...values[0], note: 'Updated at capacity' })
    return { saved: outcomes.filter((item) => item.status === 'fulfilled').length, rejected: outcomes.filter((item) => item.status === 'rejected').length, count: values.length }
  })
  expect(counts).toEqual({ saved: 100, rejected: 5, count: 100 })
  await page.reload()
  const persisted = await page.evaluate(async () => {
    // @ts-expect-error Vite serves this source module for browser storage checks.
    const notebook = await import('/src/classroom/notebook.ts')
    const entries = await notebook.listEntries('synthetic-notebook')
    await notebook.deleteSessionEntries('synthetic-notebook')
    return { count: entries.length, updated: entries.some((entry: { note: string }) => entry.note === 'Updated at capacity'), remaining: (await notebook.listEntries('synthetic-notebook')).length }
  })
  expect(persisted).toEqual({ count: 100, updated: true, remaining: 0 })
})
