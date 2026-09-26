import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

test('real worker positions growing and repeated 2/4/8/12 slide stacks', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Object.assign(window, { alignmentApplications: [] })
    window.addEventListener('pathlab:alignment-applied', event => {
      const records = (window as unknown as { alignmentApplications: unknown[] }).alignmentApplications
      records.push((event as CustomEvent).detail)
    })
  })
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const { slideIds } = JSON.parse(execFileSync(process.env.PATHLAB_E2E_PYTHON!,
    [path.resolve('../../scripts/seed_frontend_qa.py'), 'alignment'], { encoding: 'utf8' })) as { slideIds: string[] }
  const receipts: unknown[] = []
  const auth = await (await page.request.get('/api/v1/auth/session')).json() as { csrfToken: string }
  for (const count of [2, 4, 8, 12]) for (const mode of ['growing', 'repeated']) {
    const started = performance.now()
    const response = await page.request.post('/api/v1/admin/comparison-sets', {
      headers: { 'X-CSRF-Token': auth.csrfToken },
      data: { name: `Alignment QA ${count} ${mode}`, slideIds: slideIds.slice(0, count), referenceSlideId: slideIds[0] },
    })
    expect(response.ok()).toBe(true)
    const created = await response.json() as { id: string }
    await page.goto(`/admin/comparisons/${created.id}`)
    let members: Array<{ slideId: string; registration?: { status: string; overviewTriangles?: unknown[]; evidence?: unknown } }> = []
    await expect.poll(async () => {
      const response = await page.request.get(`/api/v1/admin/comparison-sets/${created.id}`)
      expect(response.ok()).toBe(true)
      members = (await response.json()).members
      return members.filter(member => member.slideId !== slideIds[0]
        && ['ready', 'approximate'].includes(member.registration?.status ?? '')
        && (member.registration?.overviewTriangles?.length ?? 0) > 0).length
    }, { timeout: 20_000, intervals: [100, 200, 300] }).toBe(count - 1)
    const mapsAvailableMilliseconds = performance.now() - started
    await expect(page.getByText('Approximate sync', { exact: true })).toBeVisible()
    await expect.poll(() => page.evaluate(() => (window as unknown as {
      alignmentApplications: unknown[]
    }).alignmentApplications.length)).toBeGreaterThan(0)
    const applications = await page.evaluate(() => (window as unknown as {
      alignmentApplications: Array<{ slideId: string; sourceViewport: { centerX: number; centerY: number }; viewport: { centerX: number; centerY: number } }>
    }).alignmentApplications)
    const applied = applications.find(application => application.slideId === slideIds[1])!
    expect(applied).toBeTruthy()
    expect(Math.abs(applied.viewport.centerX - applied.sourceViewport.centerX - 2)).toBeLessThan(3)
    expect(Math.abs(applied.viewport.centerY - applied.sourceViewport.centerY - 1)).toBeLessThan(3)
    const browserObservedMilliseconds = performance.now() - started
    expect(browserObservedMilliseconds).toBeLessThanOrEqual(10_000)
    receipts.push({ count, mode, mapsAvailableMilliseconds, browserObservedMilliseconds,
      coverage: count - 1, members: members.map(member => ({ slideId: member.slideId, evidence: member.registration?.evidence })),
      scope: 'Synthetic derivative fixtures, existing worker; includes API, queue and initial visible-pane application. Not production qualification.' })
  }
  await testInfo.attach('stack-timing', { body: JSON.stringify(receipts, null, 2), contentType: 'application/json' })
})
