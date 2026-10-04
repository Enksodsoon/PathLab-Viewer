/** Real candidate UI application, separate from queue/engine and human scoring. */
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { chromium, firefox, webkit, devices } from '@playwright/test'

const sha = bytes => createHash('sha256').update(bytes).digest('hex')
function transform(cell, point) {
  const [[ax, ay], [bx, by], [cx, cy]] = cell.moving
  const divisor = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
  const a = ((by - cy) * (point[0] - cx) + (cx - bx) * (point[1] - cy)) / divisor
  const b = ((cy - ay) * (point[0] - cx) + (ax - cx) * (point[1] - cy)) / divisor, c = 1 - a - b
  if (!Number.isFinite(divisor) || Math.abs(divisor) < 1e-12 || Math.min(a, b, c) < -1e-7) return null
  return [0, 1].map(axis => a * cell.reference[0][axis] + b * cell.reference[1][axis] + c * cell.reference[2][axis])
}
export function previewCandidateProof({ applications, started, cells, sourceId, anchorId }) {
  if (!Number.isFinite(started)) return null
  for (const application of applications) {
    const reverse = application.sourceSlideId === anchorId && application.slideId === sourceId
    if (!reverse && (application.sourceSlideId !== sourceId || application.slideId !== anchorId)) continue
    if (application.retainedOverview || application.regional
      || !Number.isInteger(application.nonuniformCanvases) || application.nonuniformCanvases < 2
      || !Number.isFinite(application.observedAt) || !Number.isFinite(application.frameObservedAt)
      || application.observedAt < started || application.frameObservedAt < application.observedAt) continue
    const point = [application.sourceViewport?.centerX, application.sourceViewport?.centerY]
    if (!point.every(Number.isFinite)) continue
    const expected = cells.map(cell => transform(reverse ? { moving: cell.reference, reference: cell.moving } : cell, point)).find(value => value !== null)
    if (!expected) continue
    const residual = Math.hypot(application.viewport?.centerX - expected[0], application.viewport?.centerY - expected[1])
    if (!Number.isFinite(residual) || residual > 0.01) continue
    return { application, expected, centerResidualPixels: residual,
      direction: reverse ? 'anchor-to-candidate' : 'candidate-to-anchor',
      seconds: (application.frameObservedAt - started) / 1000,
      clock: 'Actual Preview button click dispatch to own candidate-cell OSD application/readback and subsequent two-animation-frame nonuniform-original-canvas observation; includes React scheduling, excludes queue/preparation/compute and first world.draw.' }
  }
  return null
}

async function main() {
  const args = process.argv.slice(2)
  const option = name => args[args.indexOf(name) + 1]
  for (const name of ['--queue', '--guard', '--auth-file', '--output-dir']) {
    if (!args.includes(name) || !option(name) || option(name).startsWith('--')) throw new Error(`Required ${name}`)
  }
  const queueBytes = await fs.readFile(option('--queue')), guardBytes = await fs.readFile(option('--guard'))
  if (queueBytes.length > 64 * 1024 ** 2 || guardBytes.length > 1024 ** 2) throw new Error('Private receipt exceeds bound')
  const queue = JSON.parse(queueBytes), guard = JSON.parse(guardBytes)
  const origin = new URL(guard.baseUrl)
  if (guard.schema !== 'real-api-nine-serial-operational-jobs/1' || guard.ownedDisposable !== true
    || origin.protocol !== 'http:' || origin.hostname !== '127.0.0.1' || !origin.port
    || ['8001', '5175'].includes(origin.port) || origin.pathname !== '/' || origin.search || origin.hash
    || queue.comparisonSetId !== guard.comparisonSetId || queue.setVersion !== guard.setVersion
    || queue.plannedRecipes !== 9 || queue.completedRecipes !== 9 || queue.rows?.length !== 9
    || new Set(queue.rows.map(row => row.recipe)).size !== 9) throw new Error('Operational UI admission does not match complete nine-job receipt')
  const output = path.resolve(option('--output-dir'))
  const repo = path.resolve(import.meta.dirname, '../../..')
  if (output === repo || output.startsWith(repo + path.sep)) throw new Error('Private output must remain outside repository')
  await fs.mkdir(output, { recursive: true })
  const authBytes = await fs.readFile(option('--auth-file'))
  if (authBytes.length > 64 * 1024) throw new Error('Private authentication exceeds bound')
  const auth = JSON.parse(authBytes)
  const headers = auth.headers ?? auth
  if (typeof headers.Cookie !== 'string' || !headers['X-CSRF-Token']) throw new Error('Private session admission missing')
  const cookies = headers.Cookie.split(';').map(value => {
    const at = value.indexOf('=')
    return { name: value.slice(0, at).trim(), value: value.slice(at + 1), url: origin.origin, httpOnly: true }
  })
  const canonical = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item)
  const center = triangle => [0, 1].map(axis => triangle.reduce((sum, point) => sum + point[axis], 0) / 3)

  if (canonical(queue.admission) !== canonical(guard)) throw new Error('Queue admission differs from the exact private guard')
  const summary = values => {
    const sorted = [...values].sort((a, b) => a - b)
    return { count: sorted.length, median: sorted[Math.ceil(sorted.length * 0.5) - 1] ?? null, p95: sorted[Math.ceil(sorted.length * 0.95) - 1] ?? null }
  }
  const receipt = {
    schema: 'pathlab.real-api-operational-ui/1', createdAt: new Date().toISOString(),
    queueReceiptSha256: sha(queueBytes), guardSha256: sha(guardBytes), harnessSha256: sha(await fs.readFile(import.meta.filename)),
    scope: 'Actual production candidate Preview and ordinary pan, application event OSD readback, two-animation-frame rendered-canvas check. This is an observed UI interval, not the first OSD world.draw event.',
    excluded: ['queue', 'preparation', 'engine compute', 'anatomical qualification', 'human anatomical correction effort'],
    plannedRecipesPerBrowser: 9, humanCorrectionEffort: null, anatomicalAccuracy: null,
    browserApplicationClock: 'Actual Preview click dispatch to own candidate-cell application and subsequent two-animation-frame nonuniform-original-canvas observation, or null with reason. React scheduling included; queue/preparation/compute and first OSD world.draw excluded.',
    setterAndCanvasObservationClock: 'Production target setter duration plus browser event arrival to two-animation-frame original-canvas observation. Map lookup and first OSD draw time are not measured. Ordinary-pan interval includes explicit250ms hold/350ms settle and is separate.',
    applicationSourceSha256: Object.fromEntries(await Promise.all([
      'apps/web/src/pages/ComparisonPage.tsx', 'apps/web/src/candidatePreview.ts',
      'apps/web/src/alignment.ts', 'apps/web/src/components/OpenSeadragonViewer.tsx',
    ].map(async file => [file, sha(await fs.readFile(path.join(repo, file)))]))),
    browsers: [], cleanup: { browsersClosed: false },
  }
  let anyFailure = false
  try {
    for (const profile of ['chromium', 'firefox', 'webkit', 'mobile-chromium']) {
      const startedAt = performance.now()
      let browser, context, timedOut = false
      const batch = { profile, version: null, browserClosed: true, maximumSeconds: 240, rows: queue.rows.map(row => ({
        recipe: row.recipe, jobId: row.jobId ?? null, candidateId: row.candidate?.id ?? null,
        candidateDigest: row.candidateDigest ?? null, outcome: 'no-application', reason: 'Not attempted',
        browserApplicationSeconds: null, setterAndCanvasObservationSeconds: null, setterMs: null, samples: [], automaticCorrection: null, humanCorrectionEffort: null,
        previewClickApplicationSeconds: null, previewClickApplication: null,
        previewClickApplicationReason: 'No admitted candidate Preview attempted',
      })) }
      receipt.browsers.push(batch)
      const timer = setTimeout(() => {
        timedOut = true
        if (browser) void browser.close().catch(() => {})
      }, 240_000)
      try {
        browser = await ({ chromium, firefox, webkit, 'mobile-chromium': chromium }[profile]).launch({ headless: true, timeout: 30_000 })
        batch.browserClosed = false
        if (timedOut) throw new Error('Browser profile deadline exhausted during launch')
        batch.version = browser.version()
        context = await browser.newContext({ baseURL: origin.origin,
          ...(profile === 'mobile-chromium' ? devices['Pixel 5'] : { viewport: { width: 1280, height: 800 } }) })
        await context.addCookies(cookies)
        await context.addInitScript(({ admittedOrigin, token }) => {
          if (location.origin === admittedOrigin) sessionStorage.setItem('pathlab-csrf', token)
        }, { admittedOrigin: origin.origin, token: headers['X-CSRF-Token'] })
        context.setDefaultTimeout(15_000)
        context.setDefaultNavigationTimeout(20_000)
        for (const [rowIndex, row] of queue.rows.entries()) {
          if (timedOut) throw new Error('Browser profile deadline exhausted')
          const entry = batch.rows[rowIndex]
          entry.reason = null
          if (!row.candidate || !['ready', 'approximate'].includes(row.candidate.status)) {
            entry.reason = 'No accepted candidate from this real API job'; continue
          }
          let page
          try {
            page = await context.newPage()
            let loadedTiles = 0
            page.on('response', response => { if (response.ok() && response.url().includes('/preview/slide_files/')) loadedTiles++ })
            await page.addInitScript(() => {
              window.__operationalApplications = []
              window.addEventListener('pathlab:alignment-applied', event => {
                const row = { ...event.detail, observedAt: performance.now() }
                window.__operationalApplications.push(row)
                requestAnimationFrame(() => requestAnimationFrame(() => {
                  row.frameObservedAt = performance.now()
                  row.nonuniformCanvases = [...document.querySelectorAll('.comparison-pane .openseadragon-canvas canvas')].filter(canvas => {
                    const context = canvas.getContext('2d')
                    if (!context || !canvas.width || !canvas.height) return false
                    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data, colors = new Set()
                    for (let i = 0; i < pixels.length; i += 404) if (pixels[i + 3] && (pixels[i] < 240 || pixels[i + 1] < 240 || pixels[i + 2] < 240)) colors.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]}`)
                    return colors.size > 10
                  }).length
                }))
              })
            })
            const endpoint = `/api/v1/admin/comparison-sets/${guard.comparisonSetId}`
            const comparison = await (await page.request.get(endpoint)).json()
            const manifest = await (await page.request.get(`${endpoint}/candidates`)).json()
            const candidate = manifest.candidates?.find(item => item.id === row.candidate.id)
            const source = comparison.members?.find(item => item.slideId === candidate?.slideId)
            const anchor = comparison.members?.find(item => item.slideId === candidate?.anchorSlideId)
            if (comparison.version !== guard.setVersion || candidate?.currentPair !== true || candidate.currentSettings !== true
              || candidate.sourceSnapshotVersion !== source?.alignmentSourceVersion
              || candidate.anchorSnapshotVersion !== anchor?.alignmentSourceVersion
              || canonical(candidate.registration) !== canonical(row.candidate.registration)) throw new Error('Fresh candidate source/map proof differs from queue receipt')
            const cells = candidate.registration.status === 'ready' ? candidate.registration.triangles : candidate.registration.overviewTriangles
            if (!cells?.length) throw new Error('No accepted own support cells')
            await page.goto(`/admin/comparisons/${guard.comparisonSetId}`)
            await page.getByText('Advanced', { exact: true }).click()
            await page.getByText('Registration engine candidates', { exact: true }).click()
            const preview = page.getByRole('button', { name: `Preview ${candidate.engine} for ${source.displayName}` })
            if (!(await preview.isEnabled())) throw new Error('Production candidate Preview refused current admission')
            await preview.evaluate(button => button.addEventListener('click', () => {
              window.__operationalPreviewStarted = performance.now()
            }, { once: true, capture: true }))
            await preview.click()
            await page.getByText('Experimental alignment preview', { exact: true }).waitFor()
            try {
              await page.waitForFunction(({ sourceId, anchorId }) => window.__operationalApplications.some(item =>
                item.observedAt >= window.__operationalPreviewStarted && Number.isFinite(item.frameObservedAt)
                && item.nonuniformCanvases >= 2 && !item.retainedOverview && !item.regional
                && ((item.sourceSlideId === sourceId && item.slideId === anchorId)
                  || (item.sourceSlideId === anchorId && item.slideId === sourceId))),
              { sourceId: source.slideId, anchorId: anchor.slideId }, { timeout: 10_000 })
              const clickProof = await page.evaluate(() => ({
                started: window.__operationalPreviewStarted,
                applications: window.__operationalApplications.filter(item => item.observedAt >= window.__operationalPreviewStarted
                  && Number.isFinite(item.frameObservedAt) && item.nonuniformCanvases >= 2),
              }))
              const ownProof = previewCandidateProof({ ...clickProof, cells, sourceId: source.slideId, anchorId: anchor.slideId })
              if (ownProof) {
                entry.previewClickApplicationSeconds = ownProof.seconds
                entry.browserApplicationSeconds = ownProof.seconds
                entry.previewClickApplication = ownProof
                entry.previewClickApplicationReason = null
              }
              if (entry.previewClickApplicationSeconds === null) entry.previewClickApplicationReason = 'Preview produced no rendered own candidate-cell application with matching original-coordinate oracle'
            } catch (error) {
              entry.previewClickApplicationReason = error instanceof Error ? error.message : 'Own candidate application was not observed after Preview'
            }
            await page.getByText('Advanced', { exact: true }).click()
            const samples = [...new Set([0, Math.floor(cells.length / 2), cells.length - 1])]
            for (const cellIndex of samples) {
              const point = center(cells[cellIndex].moving)
              const previous = await page.evaluate(id => window.__operationalApplications.findLast(item => item.sourceSlideId === id || item.slideId === id), source.slideId)
              if (!previous) throw new Error('No actual OSD starting viewport application')
              const view = previous.sourceSlideId === source.slideId ? previous.sourceViewport : previous.viewport
              const paneIndex = await page.locator('.comparison-pane select').evaluateAll((selects, id) => selects.findIndex(select => select.value === id), source.slideId)
              if (paneIndex < 0) throw new Error('Source slide is not displayed')
              const pane = page.locator('.comparison-pane').nth(paneIndex)
              const canvas = pane.locator('.openseadragon-canvas').first()
              await canvas.scrollIntoViewIfNeeded()
              const box = await canvas.boundingBox()
              if (!box) throw new Error('Source canvas not visible')
              const before = await page.evaluate(() => window.__operationalApplications.length)
              const started = await page.evaluate(() => performance.now())
              const angle = view.rotation * Math.PI / 180, dx = (view.centerX - point[0]) * view.imageZoom, dy = (view.centerY - point[1]) * view.imageZoom
              const x = box.x + box.width / 2, y = box.y + box.height / 2
              await page.mouse.move(x, y); await page.mouse.down()
              await page.mouse.move(x + dx * Math.cos(angle) - dy * Math.sin(angle), y + dx * Math.sin(angle) + dy * Math.cos(angle), { steps: 8 })
              await page.waitForTimeout(250); await page.mouse.up()
              await page.waitForFunction(({ count, id }) => window.__operationalApplications.slice(count).some(item => item.sourceSlideId === id), { count: before, id: source.slideId }, { timeout: 10_000 })
              await page.waitForTimeout(350)
              const drawn = await page.evaluate(async id => {
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
                const application = window.__operationalApplications.findLast(item => item.sourceSlideId === id)
                const canvases = [...document.querySelectorAll('.comparison-pane .openseadragon-canvas canvas')]
                const nonuniform = canvases.filter(canvas => {
                  const context = canvas.getContext('2d')
                  if (!context || !canvas.width || !canvas.height) return false
                  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data, colors = new Set()
                  for (let i = 0; i < pixels.length; i += 404) if (pixels[i + 3] && (pixels[i] < 240 || pixels[i + 1] < 240 || pixels[i + 2] < 240)) colors.add(`${pixels[i]},${pixels[i + 1]},${pixels[i + 2]}`)
                  return colors.size > 10
                }).length
                return { application, nonuniform, checkedAt: performance.now() }
              }, source.slideId)
              const applied = drawn.application
              const expected = cells.map(cell => transform(cell, [applied.sourceViewport.centerX, applied.sourceViewport.centerY])).find(value => value !== null)
              if (!expected || applied.retainedOverview || applied.regional || drawn.nonuniform < 2
                || applied.nonuniformCanvases < 2 || !Number.isFinite(applied.frameObservedAt)
                || !Number.isFinite(applied.applicationMilliseconds) || !loadedTiles) throw new Error('Own map was not actually applied and rendered on both original panes')
              const residual = Math.hypot(applied.viewport.centerX - expected[0], applied.viewport.centerY - expected[1])
              if (!Number.isFinite(residual) || residual > 0.01) throw new Error('Actual OSD center differs from own cell oracle')
              entry.samples.push({ cellIndex, applied, expected, centerResidualPixels: residual, nonuniformCanvases: drawn.nonuniform,
                observedUiMs: drawn.checkedAt - started, setterMs: applied.applicationMilliseconds,
                setterAndObservedRenderMs: applied.applicationMilliseconds + applied.frameObservedAt - applied.observedAt })
            }
            entry.setterAndCanvasObservationSeconds = summary(entry.samples.map(item => item.setterAndObservedRenderMs)).p95 / 1000
            entry.setterMs = summary(entry.samples.map(item => item.setterMs))
            entry.observedUiMs = summary(entry.samples.map(item => item.observedUiMs))
            entry.setterAndObservedRenderMs = summary(entry.samples.map(item => item.setterAndObservedRenderMs))
            const screenshot = await page.screenshot({ fullPage: true })
            const screenshotName = `${profile}-${candidate.id}.png`
            await fs.writeFile(path.join(output, screenshotName), screenshot)
            entry.renderedScreenshot = { filename: screenshotName, sha256: sha(screenshot) }
            entry.loadedTiles = loadedTiles
            entry.outcome = 'applied'
            // This measures scripted crosshair actions, without anatomical scoring or a save.
            entry.automaticCorrection = []
            for (const pairs of [1, 2]) {
              const actionStart = await page.evaluate(() => performance.now())
              await page.getByRole('button', { name: 'Adjust region', exact: true }).click()
              await page.getByRole('button', { name: 'Record point pair', exact: true }).click()
              if (pairs === 2) {
                for (const pane of await page.locator('.comparison-pane').all()) {
                  const canvas = pane.locator('.openseadragon-canvas').first()
                  await canvas.scrollIntoViewIfNeeded()
                  const box = await canvas.boundingBox(), x = box.x + box.width / 2, y = box.y + box.height / 2
                  await page.mouse.move(x, y); await page.mouse.down()
                  await page.mouse.move(x - 12, y - 10, { steps: 5 })
                  await page.waitForTimeout(250); await page.mouse.up()
                }
                await page.getByRole('button', { name: 'Record point pair', exact: true }).click()
              }
              const observed = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/region-corrections'))
              await page.getByRole('button', { name: 'Preview correction', exact: true }).click()
              const response = await observed
              if (response.ok()) await page.getByText(/^Unsaved correction preview/).first().waitFor()
              const actionEnd = await page.evaluate(() => performance.now())
              await page.getByRole('button', { name: 'Cancel correction', exact: true }).click()
              entry.automaticCorrection.push({ scope: 'Scripted crosshair pairs, Preview and Cancel; no correspondence/human quality scoring and no Save',
                recordedPointPairs: response.request().postDataJSON().movingPoints.length,
                controlActionCount: pairs + 3, pointerPans: pairs === 2 ? 2 : 0,
                previewObserved: response.ok(), responseStatus: response.status(),
                observedSeconds: (actionEnd - actionStart) / 1000, humanCorrectionEffort: null, anatomicalAccuracy: null })
            }
            if ((await (await page.request.get(endpoint)).json()).version !== guard.setVersion) throw new Error('Automated correction changed comparison version')
          } catch (error) {
            anyFailure = true
            entry.outcome = entry.outcome === 'applied' ? 'applied-correction-failed'
              : entry.browserApplicationSeconds !== null ? 'preview-applied-pan-failed' : 'no-application'
            entry.reason = error instanceof Error ? error.message : 'UI application failed'
            if (entry.outcome === 'no-application') entry.browserApplicationSeconds = null
          } finally { if (page) await page.close().catch(() => {}) }
          await fs.writeFile(path.join(output, 'operational-ui.json'), JSON.stringify(receipt, null, 2))
        }
      } catch (error) {
        anyFailure = true
        batch.failure = error instanceof Error ? error.message : 'Browser profile failed'
        for (const row of batch.rows) if (row.reason === 'Not attempted') row.reason = batch.failure
      } finally {
        clearTimeout(timer)
        if (context) await context.close().catch(() => {})
        if (browser) {
          try { await browser.close(); batch.browserClosed = true }
          catch (error) {
            anyFailure = true
            batch.cleanupError = error instanceof Error ? error.message : 'Browser cleanup failed'
          }
        }
        batch.actualTotalSeconds = (performance.now() - startedAt) / 1000
        batch.deadlineTriggered = timedOut
        batch.withinDeclaredBound = batch.actualTotalSeconds <= 240
        if (!batch.withinDeclaredBound) anyFailure = true
        await fs.writeFile(path.join(output, 'operational-ui.json'), JSON.stringify(receipt, null, 2))
      }
    }
  } finally {
    receipt.cleanup.browsersClosed = receipt.browsers.every(batch => batch.browserClosed)
    await fs.writeFile(path.join(output, 'operational-ui.json'), JSON.stringify(receipt, null, 2) + '\n')
  }
  if (anyFailure) process.exitCode = 1

}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main()
