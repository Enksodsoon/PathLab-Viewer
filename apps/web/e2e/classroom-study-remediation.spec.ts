import { expect, test, type Page } from '@playwright/test'

test.setTimeout(60_000)
const sizes = [{ width: 320, height: 740 }, { width: 768, height: 1024 }, { width: 740, height: 360 }]
const slide = { id: 'slide', position: 0, displayName: 'Synthetic geometry slide', assetVersion: 'v1', tileSource: '/qa/slide.dzi', width: 256, height: 256, tileSize: 256, format: 'png', folderPath: ['Synthetic'] }
const study = { csrfToken: 'synthetic-study-csrf', pseudonym: 'SYNTHETIC', course: { id: 'qa-course', title: 'Synthetic course', status: 'active', endsAt: null }, pack: { schema: 'pathlab.study-pack/1', title: 'Synthetic pack', slides: [{ viewerSlideId: 'slide', displayName: slide.displayName, tileSource: slide.tileSource }], tasks: [{ id: 'spatial', type: 'spatial', slideId: 'slide', prompt: 'Select a synthetic region', hints: ['Faculty hint'] }, { id: 'choice', type: 'multiple-choice', slideId: 'slide', prompt: 'Choose synthetic answer', options: ['Synthetic A', 'Synthetic B'], hints: [] }] }, progress: [], ai: { eligible: false } }
const classroom = { session: { id: 'qa-session', status: 'active', phase: 'live', publicId: 'qa-public' }, participant: { id: 'qa-participant', alias: 'SYNTHETIC-1' }, csrfToken: 'synthetic-classroom-csrf', stateVersion: 1, presenter: { sequence: 0, slideId: 'slide', viewport: null }, control: { isController: false, requested: false, leaseId: null, controlEpoch: 0, expiresAt: null }, slides: [slide], pendingQuestionIds: [], activePin: null, teacherPointer: null, teachingAnnotations: [] }
async function tiles(page: Page) {
  const tile = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 256; canvas.height = 256; const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#eecfc3'; ctx.fillRect(0, 0, 256, 256); ctx.fillStyle = '#995d75'; for (let x = 20; x < 256; x += 40) for (let y = 20; y < 256; y += 40) { ctx.beginPath(); ctx.arc(x, y, 8, 0, 7); ctx.fill() } return canvas.toDataURL('image/png').split(',')[1] })
  await page.route('**/qa/slide.dzi*', (route) => route.fulfill({ contentType: 'application/xml', body: '<Image TileSize="256" Overlap="0" Format="png" xmlns="http://schemas.microsoft.com/deepzoom/2008"><Size Width="256" Height="256"/></Image>' }))
  await page.route('**/qa/slide_files/**', (route) => route.fulfill({ contentType: 'image/png', body: Buffer.from(tile, 'base64') }))
}
async function noOverflow(page: Page) { const result = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, offenders: [...document.querySelectorAll('*')].filter((el) => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 8).map((el) => ({ tag: el.tagName, class: el.className, right: el.getBoundingClientRect().right })) })); expect(result.scroll, JSON.stringify(result)).toBeLessThanOrEqual(result.width + 1) }
async function contrast(page: Page, selector: string) {
  const colors = await page.locator(selector).first().evaluate((el) => {
    const luminance = (color: string) => { const values = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map((n) => { const x = n / 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4 }); return values[0] * .2126 + values[1] * .7152 + values[2] * .0722 }
    let surface: Element | null = el
    while (surface && getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)') surface = surface.parentElement
    const a = luminance(getComputedStyle(el).color)
    const b = luminance(getComputedStyle(surface ?? document.documentElement).backgroundColor)
    return { foreground: getComputedStyle(el).color, background: getComputedStyle(surface ?? document.documentElement).backgroundColor, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) }
  })
  expect(colors.ratio).toBeGreaterThanOrEqual(4.5)
  return colors
}
async function denyStorage(page: Page) { await page.addInitScript(() => { for (const method of ['getItem', 'setItem', 'removeItem']) Object.defineProperty(Storage.prototype, method, { configurable: true, value: () => { throw new DOMException('Synthetic storage denial', 'SecurityError') } }) }) }

test('Study actual invitation, denied storage, spatial target, keyboard confidence and released feedback', async ({ page }, info) => {
  await denyStorage(page)
  await tiles(page)
  let entered = false
  let failures = 1
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname
    if (url.endsWith('/study/session')) return route.fulfill({ status: 401, json: { detail: { code: 'STUDY_SESSION_REQUIRED' } } })
    if (url.endsWith('/study/redeem')) {
      if (route.request().postDataJSON().code !== 'issued_Ab-cd0123456789CODE') return route.fulfill({ status: 403, json: { detail: { code: 'STUDY_INVITATION_INVALID' } } })
      entered = true; return route.fulfill({ json: study })
    }
    if (url.endsWith('/submit')) {
      expect(entered).toBe(true)
      expect(route.request().headers()['x-study-csrf']).toBe('synthetic-study-csrf')
      if (failures-- > 0) return route.fulfill({ status: 503, json: { detail: { code: 'SYNTHETIC_SAVE_FAILURE' } } })
      return route.fulfill({ json: { taskId: 'spatial', status: 'completed', correct: true, attemptCount: 1, explanation: 'Released faculty feedback', sources: [], hints: [] } })
    }
    return route.fulfill({ json: {} })
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/study')
  await page.getByLabel('One-time invitation code').fill('wrong-issued-code-0123456')
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Enter Study Mode' }).click()
  await expect(page.getByRole('alert')).toContainText('STUDY_INVITATION_INVALID')
  await page.getByLabel('One-time invitation code').fill('issued_Ab-cd0123456789CODE')
  await page.getByRole('button', { name: 'Enter Study Mode' }).click()
  await expect(page.getByRole('heading', { name: 'Select a synthetic region' })).toBeVisible()
  await expect(page.locator('.openseadragon-canvas canvas').first()).toBeVisible()
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    if (info.project.name === 'mobile-chromium') await page.getByRole('button', { name: 'Select centre of visible field' }).tap()
    else await page.getByRole('button', { name: 'Select centre of visible field' }).click()
    await expect(page.getByLabel('Your selected region pinned this point')).toBeVisible()
    expect(await page.getByLabel('Your selected region pinned this point').locator('span').evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThanOrEqual(28)
    await page.getByLabel('4: Confident').focus()
    await page.keyboard.press('Space')
    await expect(page.getByLabel('4: Confident')).toBeChecked()
    await noOverflow(page)
    await info.attach(`study-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.study-task')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`study-${size.width}x${size.height}-${theme}.png`), fullPage: true })
  }
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.getByRole('alert')).toContainText('SYNTHETIC_SAVE_FAILURE')
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.getByText('Released faculty feedback')).toBeVisible()
  await page.getByRole('button', { name: /Task 2.*Pending/ }).click()
  await expect(page.getByText('Released faculty feedback')).toHaveCount(0)
  await expect(page.getByLabel('Your selected region pinned this point')).toHaveCount(0)
  await page.getByRole('radio', { name: 'Synthetic A', exact: true }).check()
  await expect(page.getByLabel('3: Probable')).toBeChecked()
})

test('Classroom full stage, native tray, P and Alt-click anchored questions with retry', async ({ page }, info) => {
  await tiles(page)
  await page.addInitScript(() => { window.EventSource = class { addEventListener() {} close() {} } as unknown as typeof EventSource })
  let questions = 0
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url()).pathname
    if (url.endsWith('/sessions/qa-session')) return route.fulfill({ json: classroom })
    if (url.endsWith('/questions')) {
      const body = route.request().postDataJSON()
      expect(body.csrfToken).toBe('synthetic-classroom-csrf')
      expect(body.x).toBeGreaterThanOrEqual(0); expect(body.x).toBeLessThanOrEqual(1)
      questions += 1
      return route.fulfill({ status: questions === 1 ? 503 : 200, json: questions === 1 ? { detail: { code: 'SYNTHETIC_QUESTION_FAILURE' } } : {} })
    }
    return route.fulfill({ json: {} })
  })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/classroom/qa-session')
  const canvas = page.locator('.openseadragon-canvas canvas').first()
  await expect(canvas).toBeVisible()
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    const tray = page.locator('.classroom-activity-tray')
    const summary = tray.locator('summary')
    await summary.click()
    await expect(tray).not.toHaveAttribute('open')
    const width = await page.locator('.classroom-viewer').evaluate((el) => el.getBoundingClientRect().width)
    expect(width).toBeGreaterThan(size.width - 2)
    await page.keyboard.press('p')
    await expect(page.getByLabel('Question at this point')).toBeFocused()
    await page.getByLabel('Question at this point').fill('Synthetic pinned question')
    await expect.poll(async () => page.locator('.classroom-question-composer').evaluate((el) => { const r = el.getBoundingClientRect(); return r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight })).toBe(true)
    await info.attach(`classroom-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.classroom-question-composer')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`classroom-${size.width}x${size.height}-${theme}.png`), fullPage: true })
    await noOverflow(page)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await summary.click()
    if (info.project.name === 'mobile-chromium') await page.getByRole('button', { name: 'Ask at visible centre (P)' }).tap()
    else await page.getByRole('button', { name: 'Ask at visible centre (P)' }).click()
    await expect(page.getByLabel('Question at this point')).toBeVisible()
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  }
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.locator('.classroom-activity-tray summary').click()
  await page.locator('.openseadragon-canvas').first().click({ position: { x: 250, y: 200 }, modifiers: ['Alt'] })
  await page.getByLabel('Question at this point').fill('Retain this failed question')
  await page.keyboard.press('Control+Enter')
  await page.locator('.classroom-activity-tray summary').click()
  await expect(page.locator('.classroom-message')).toContainText('Question could not be sent')
  await expect(page.getByLabel('Question at this point')).toHaveValue('Retain this failed question')
  await page.getByLabel('Question at this point').focus()
  await page.keyboard.press('Meta+Enter')
  await expect(page.getByLabel('Question at this point')).toHaveCount(0)
  await expect(page.locator('.classroom-message')).toContainText('Question sent to the teacher')
})

test('Assessment practice survives denied reads and writes without promising persistence', async ({ page }, info) => {
  await denyStorage(page)
  const definition = { title: 'Synthetic practice', settings: {}, items: [{ id: 'one', type: 'multiple-choice', prompt: 'Synthetic practice question', points: '1', required: true, options: [{ id: 'a', label: 'Synthetic answer' }], answerKey: { optionIds: ['a'] } }] }
  await page.route('**/api/**', (route) => route.fulfill({ json: route.request().url().includes('/practice/') ? { publicId: 'qa-practice', storage: 'browser-local', definition, assets: {} } : { publicId: 'qa-practice', mode: 'practice', status: 'open', durationSeconds: 0, closesAt: null, assets: {}, manifest: definition } }))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  for (const size of sizes) for (const theme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize(size)
    await page.goto('/assessment/qa-practice')
    await page.getByLabel('Synthetic answer').check()
    await expect(page.getByLabel('Synthetic answer')).toBeChecked()
    await expect(page.getByRole('alert')).toContainText('only in memory for this tab and will be lost on reload')
    await expect(page.getByText('Stored only in this browser')).toHaveCount(0)
    await noOverflow(page)
    await info.attach(`practice-contrast-${size.width}-${theme}`, { body: JSON.stringify(await contrast(page, '.assessment-student-main')), contentType: 'application/json' })
    await page.screenshot({ path: info.outputPath(`practice-${size.width}x${size.height}-${theme}.png`), fullPage: true })
  }
})
