import { writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'

test.setTimeout(60_000)
const slides = [1, 2].map((n) => ({ id: `slide-${n}`, position: n - 1, displayName: `Synthetic slide ${n}`, assetVersion: 'v1', tileSource: `/qa/slide-${n}.dzi`, width: 256, height: 256, tileSize: 256, format: 'png', folderPath: [] }))
async function emit(page: Page, type: string, payload: Record<string, unknown>) {
  await page.evaluate(({ type, payload }) => (window as unknown as { qaEmit: (type: string, payload: unknown) => void }).qaEmit(type, payload), { type, payload })
}
async function publicationAttempts(page: Page) {
  return page.evaluate(() => (window as unknown as { qaPresenterAttempts: unknown[] }).qaPresenterAttempts)
}
async function sample(page: Page) {
  return page.evaluate(async () => {
    const url = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))!.name
    const OSD = (await import(/* @vite-ignore */ url)).default
    let element: Element | null = document.querySelector('.openseadragon-canvas')
    let viewer = element ? OSD.getViewer(element) : null
    while (!viewer && element) { element = element.parentElement; viewer = element ? OSD.getViewer(element) : null }
    const item = viewer.world.getItemAt(0)
    const center = item.viewportToImageCoordinates(viewer.viewport.getCenter(true))
    const node = document.querySelector('[data-teacher-pointer]') as HTMLElement | null
    const matrix = node ? new DOMMatrixReadOnly(getComputedStyle(node).transform) : null
    const pointer = matrix ? item.viewportToImageCoordinates(viewer.viewport.pointFromPixel(new OSD.Point(matrix.e, matrix.f), true)) : null
    return { source: item.source.width, tileUrl: item.source.getTileUrl(0, 0, 0), x: center.x / 256, y: center.y / 256, zoom: item.viewportToImageZoom(viewer.viewport.getZoom(true)), pointer: pointer ? { hidden: node!.hidden, x: pointer.x / 256, y: pointer.y / 256 } : null }
  })
}

test('real OSD teacher slide opening reaches guided student and remote control does not echo', async ({ context, page }, info) => {
  await context.addInitScript(() => {
    const sources: Array<{ closed: boolean; listeners: Map<string, Array<(event: Event) => void>> }> = []
    window.EventSource = class {
      closed = false
      listeners = new Map<string, Array<(event: Event) => void>>()
      constructor() { sources.push(this) }
      addEventListener(type: string, callback: (event: Event) => void) { this.listeners.set(type, [...(this.listeners.get(type) ?? []), callback]) }
      close() { this.closed = true }
    } as unknown as typeof EventSource
    ;(window as unknown as { qaEmit: unknown }).qaEmit = (type: string, payload: unknown) => {
      for (const source of sources) if (!source.closed) for (const listener of source.listeners.get(type) ?? []) listener(new MessageEvent(type, { data: JSON.stringify(payload) }))
    }
    const attempts: Array<{ at: number; body: string | null }> = []
    ;(window as unknown as { qaPresenterAttempts: unknown }).qaPresenterAttempts = attempts
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      const url = input instanceof Request ? input.url : String(input)
      const method = init?.method ?? (input instanceof Request ? input.method : 'GET')
      if (method === 'POST' && /\/admin\/classroom\/sessions\/[^/]+\/presenter$/.test(new URL(url, location.href).pathname)) {
        attempts.push({ at: performance.now(), body: typeof init?.body === 'string' ? init.body : null })
      }
      return originalFetch(input, init)
    }
    sessionStorage.setItem('pathlab-csrf', 'synthetic-csrf')
  })
  const png = await page.evaluate(() => { const c = document.createElement('canvas'); c.width = 256; c.height = 256; const x = c.getContext('2d')!; x.fillStyle = '#eecfc3'; x.fillRect(0, 0, 256, 256); return c.toDataURL().split(',')[1] })
  await context.route('**/qa/*.dzi*', (route) => route.fulfill({ contentType: 'application/xml', body: '<Image TileSize="256" Overlap="0" Format="png" xmlns="http://schemas.microsoft.com/deepzoom/2008"><Size Width="256" Height="256"/></Image>' }))
  await context.route('**/qa/*_files/**', (route) => route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') }))
  let sequence = 0
  let version = 1
  let presenter: { sequence: number; slideId: string; viewport: Record<string, unknown> | null } = { sequence: 0, slideId: 'slide-1', viewport: null }
  let controller: string | null = null
  const receipts: Array<Record<string, unknown>> = []
  const student = await context.newPage()
  let snapshotGate: Promise<void> | null = null
  let releaseSnapshot: (() => void) | null = null
  let heldSnapshots = 0
  const teacherState = () => ({ session: { id: 'qa', status: 'active', phase: 'live', publicId: 'public', joinCode: 'ABC234DEFG', reviewExpiresAt: '2027-01-01T00:00:00Z' }, slides, stateVersion: version, presenter, participantCount: 1, rosterVersion: 1, participants: [], pendingQuestions: [], activePins: [], teacherPointer: null, teachingAnnotations: [], controller: { participantId: controller, leaseId: controller ? 'lease' : null, controlEpoch: version, expiresAt: null } })
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/session')) return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
    if (path.endsWith('/setup/folders')) return route.fulfill({ json: { items: [], nextCursor: null } })
    if (path === '/api/v1/admin/classroom/sessions') return route.fulfill({ json: { sessions: [{ id: 'qa', publicId: 'public', phase: 'live', joinCode: 'ABC234DEFG', reviewExpiresAt: '2027-01-01T00:00:00Z' }] } })
    if (path.endsWith('/participants')) return route.fulfill({ json: { items: [], total: 0, nextCursor: null, rosterVersion: 1 } })
    if (path === '/api/v1/admin/classroom/sessions/qa') {
      const snapshot = teacherState()
      if (snapshotGate) { heldSnapshots += 1; await snapshotGate }
      return route.fulfill({ json: snapshot })
    }
    if (path === '/api/v1/classroom/sessions/qa') {
      const snapshot = { ...teacherState(), csrfToken: 'student-csrf', participant: { id: 'learner', alias: 'SYNTHETIC' }, pendingQuestionIds: [], activePin: null, control: { isController: false, requested: false, leaseId: null, controlEpoch: version, expiresAt: null } }
      if (snapshotGate) { heldSnapshots += 1; await snapshotGate }
      return route.fulfill({ json: snapshot })
    }
    if (path.endsWith('/presenter') && route.request().method() === 'POST') {
      const viewport = route.request().postDataJSON()
      receipts.push({ ...viewport, controller, at: Date.now() })
      // The real owner presenter endpoint takes control back when publishing.
      const tookControl = controller !== null
      if (tookControl) { controller = null; version += 1 }
      presenter = { sequence: presenter.sequence + 1, slideId: viewport.slideId, viewport }
      await route.fulfill({ status: 200, json: { presenterSequence: presenter.sequence } })
      if (tookControl) {
        const control = { hubEpoch: 'epoch', eventSequence: ++sequence, stateVersion: version, participantId: null, leaseId: null, controlEpoch: version, expiresAt: null }
        await emit(page, 'control', control)
        await emit(student, 'control', control)
      }
      const event = { hubEpoch: 'epoch', eventSequence: ++sequence, presenterSequence: presenter.sequence, slideId: viewport.slideId, viewport }
      await emit(page, 'presenter', event)
      await emit(student, 'presenter', event)
      return
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/admin/classroom')
  await page.getByRole('button', { name: 'Resume classroom ABC234DEFG' }).click()
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await student.goto('/classroom/qa')
  await expect(student.getByText('SYNTHETIC', { exact: true })).toBeVisible()
  await expect(student.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  await emit(page, 'stream-ready', { hubEpoch: 'epoch', eventSequence: sequence, stateVersion: version })
  await emit(student, 'stream-ready', { hubEpoch: 'epoch', eventSequence: sequence, stateVersion: version })
  await page.locator('.classroom-activity-tray > summary').click()
  await page.getByRole('button', { name: 'Guide students', exact: true }).click()
  await expect.poll(() => receipts.length).toBeGreaterThan(0)
  expect((await publicationAttempts(page)).length).toBeGreaterThan(0)
  await page.getByRole('button', { name: '1. Synthetic slide 1', exact: true }).click()
  await page.getByRole('button', { name: 'Slide 2 Synthetic slide 2' }).click()
  await expect(page.getByRole('button', { name: '2. Synthetic slide 2', exact: true })).toBeVisible()
  await expect.poll(() => receipts.some((receipt) => receipt.slideId === 'slide-2'), { timeout: 5000 }).toBe(true)
  await expect(student.getByRole('button', { name: '2. Synthetic slide 2', exact: true })).toBeVisible({ timeout: 5000 })
  await expect.poll(async () => (await sample(page)).tileUrl).toContain('slide-2_files')
  await expect.poll(async () => (await sample(student)).tileUrl).toContain('slide-2_files')
  // Resolve the native viewer before the handoff. Dynamic import may yield to
  // legitimate local timers, so it must not sit inside the causal boundary.
  await page.evaluate(async () => {
    const url = performance.getEntriesByType('resource').find((entry) => /openseadragon\.js/.test(entry.name))!.name
    const OSD = (await import(/* @vite-ignore */ url)).default
    let element: Element | null = document.querySelector('.openseadragon-canvas')
    let viewer = element ? OSD.getViewer(element) : null
    while (!viewer && element) { element = element.parentElement; viewer = element ? OSD.getViewer(element) : null }
    ;(window as unknown as { qaQueueField: () => void }).qaQueueField = () => viewer.raiseEvent('animation-finish', {})
  })
  controller = 'learner'; version += 1
  snapshotGate = new Promise<void>((resolve) => { releaseSnapshot = resolve })
  // Count browser dispatches synchronously, not later Node route arrivals.
  // Enqueue and control run without an await in the same browser task.
  const boundary = await page.evaluate((payload) => {
    const qa = window as unknown as { qaPresenterAttempts: unknown[]; qaQueueField: () => void; qaEmit: (type: string, payload: unknown) => void }
    const count = qa.qaPresenterAttempts.length
    const at = performance.now()
    qa.qaQueueField()
    qa.qaEmit('control', payload)
    return { count, at }
  }, { hubEpoch: 'epoch', eventSequence: ++sequence, stateVersion: version })
  const baseline = boundary.count
  await expect.poll(() => heldSnapshots).toBe(1)
  await page.locator('.openseadragon-canvas').first().hover()
  await page.mouse.wheel(0, -200)
  await page.waitForTimeout(700)
  await info.attach('handoff-publication-receipts', { body: JSON.stringify({ receipts, attempts: await publicationAttempts(page), boundary }, null, 2), contentType: 'application/json' })
  expect((await publicationAttempts(page)).length).toBe(baseline)
  snapshotGate = null
  releaseSnapshot!()
  heldSnapshots = 0
  presenter = { sequence: presenter.sequence + 1, slideId: 'slide-2', viewport: { x: .7, y: .3, zoom: 2, zoomSpace: 'image' } }
  await emit(page, 'presenter', { hubEpoch: 'epoch', eventSequence: ++sequence, presenterSequence: presenter.sequence, slideId: 'slide-2', viewport: presenter.viewport })
  await expect.poll(async () => (await sample(page)).x).toBeCloseTo(.7, 2)
  await page.waitForTimeout(700)
  expect((await publicationAttempts(page)).length).toBe(baseline)
  controller = null; version += 1
  await emit(page, 'control', { hubEpoch: 'epoch', eventSequence: ++sequence, stateVersion: version })
  await page.waitForTimeout(1000)
  const afterReclaim = (await publicationAttempts(page)).length
  await page.waitForTimeout(700)
  expect((await publicationAttempts(page)).length).toBe(afterReclaim)
  // Reconnect to a new stream epoch while the authoritative snapshot is held.
  // Later ephemeral traffic must stay bounded and replay after that snapshot.
  controller = 'learner'; version += 1
  snapshotGate = new Promise<void>((resolve) => { releaseSnapshot = resolve })
  const beforeRecovery = { teacher: await sample(page), student: await sample(student) }
  await emit(page, 'stream-ready', { hubEpoch: 'epoch-reconnected', eventSequence: sequence, stateVersion: version })
  await emit(student, 'stream-ready', { hubEpoch: 'epoch-reconnected', eventSequence: sequence, stateVersion: version })
  await expect.poll(() => heldSnapshots).toBe(2)
  const field = { hubEpoch: 'epoch-reconnected', eventSequence: ++sequence, presenterSequence: presenter.sequence + 1, slideId: 'slide-2', viewport: { x: .2, y: .8, zoom: 2, zoomSpace: 'image' } }
  await emit(page, 'presenter', field)
  await emit(student, 'presenter', field)
  const pointerStart = sequence
  sequence += 1000
  for (const target of [page, student]) {
    await target.evaluate(({ pointerStart }) => {
      const emit = (window as unknown as { qaEmit: (type: string, payload: unknown) => void }).qaEmit
      for (let sample = 1; sample <= 1000; sample += 1) emit('pointer', {
        hubEpoch: 'epoch-reconnected', eventSequence: pointerStart + sample,
        slideId: 'slide-2', style: 'green-arrow', x: sample / 4000, y: .75,
      })
    }, { pointerStart })
  }
  expect((await sample(page)).x).toBeCloseTo(beforeRecovery.teacher.x, 2)
  expect((await sample(student)).x).toBeCloseTo(beforeRecovery.student.x, 2)
  snapshotGate = null
  releaseSnapshot!()
  await expect.poll(async () => (await sample(page)).x).toBeCloseTo(.2, 2)
  await expect.poll(async () => (await sample(student)).x).toBeCloseTo(.2, 2)
  for (const target of [page, student]) {
    await expect.poll(async () => (await sample(target)).pointer?.hidden).toBe(false)
    await expect.poll(async () => (await sample(target)).pointer?.x).toBeCloseTo(.25, 2)
    await expect.poll(async () => (await sample(target)).pointer?.y).toBeCloseTo(.75, 2)
  }
  expect(heldSnapshots).toBe(2)
  expect((await publicationAttempts(page)).length).toBe(afterReclaim)
  const receipt = JSON.stringify({ receipts, teacher: await sample(page), student: await sample(student), baseline, afterReclaim, heldSnapshots })
  await writeFile(info.outputPath('actual-osd-receipts.json'), receipt)
  await info.attach('actual-osd-receipts', { body: receipt, contentType: 'application/json' })
  await page.screenshot({ path: info.outputPath('teacher-osd.png') })
  await student.screenshot({ path: info.outputPath('student-osd.png') })
})
