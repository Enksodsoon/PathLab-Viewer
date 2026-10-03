/** Offline, bounded viewport measurement. Run only after the engine campaign pauses. */
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import { chromium, firefox, webkit, devices } from '@playwright/test'
import ts from 'typescript'
import { acceptedCells, selectComplexitySamples, sha256, sourceSnapshot } from './alignment-browser-latency-inputs.mjs'

const require = createRequire(import.meta.url)
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(webRoot, '../..')
const args = process.argv.slice(2)
const option = name => args[args.indexOf(name) + 1]
for (const required of ['--manifest', '--campaign-dir', '--output', '--expected-host']) {
  if (!args.includes(required) || !option(required) || option(required).startsWith('--')) throw new Error(`Required: ${required}`)
}
if (option('--expected-host') !== os.hostname()) throw new Error('Browser measurement must run on the declared campaign host')
const output = path.resolve(option('--output'))
if (output === repoRoot || output.startsWith(repoRoot + path.sep)) throw new Error('Write private browser evidence outside the repository')
const browserName = args.includes('--browser') ? option('--browser') : 'chromium'
if (!['chromium', 'firefox', 'webkit', 'mobile-chromium'].includes(browserName)) throw new Error('Unsupported measurement browser')
const samples = args.includes('--samples') ? Number(option('--samples')) : 12
if (!Number.isInteger(samples) || samples < 8 || samples > 32) throw new Error('Samples must be between 8 and 32')
const manifestBytes = await fs.readFile(path.resolve(option('--manifest')))
const manifest = JSON.parse(manifestBytes)
const campaignDir = path.resolve(option('--campaign-dir'))
const reportBytes = await fs.readFile(path.join(campaignDir, 'report.json'))
const campaign = JSON.parse(reportBytes)
if (!Array.isArray(manifest.pairs) || !Array.isArray(campaign.rows) || campaign.rows.length > 512) throw new Error('Expected a completed bounded campaign report')
const rows = []
for (const row of campaign.rows) {
  if (!/^[a-f0-9]{64}$/.test(row.digest)) throw new Error('Invalid receipt digest')
  const receiptPath = path.join(campaignDir, 'cache', `${row.digest}.json`)
  if ((await fs.stat(receiptPath)).size > 20 * 1024 ** 2) throw new Error('Receipt exceeds bounded map size')
  const bytes = await fs.readFile(receiptPath)
  const receipt = JSON.parse(bytes)
  if (receipt.digest !== row.digest || receipt.recipe !== row.recipe || receipt.settingsDigest !== row.settingsDigest) throw new Error('Campaign row and coordinate-map receipt differ')
  if (!/^[a-f0-9]{64}$/.test(receipt.settingsDigest) || !Array.isArray(receipt.inputDigests)
    || receipt.inputDigests.length !== 2 || receipt.inputDigests.some(digest => !/^[a-f0-9]{64}$/.test(digest))) throw new Error('Unbound registration source/settings identity')
  if (!Number.isInteger(row.pairIndex) || !manifest.pairs[row.pairIndex]) throw new Error('Campaign pair missing from frozen manifest')
  rows.push({ row, receipt, receiptSha256: sha256(bytes) })
}
const selected = selectComplexitySamples(rows)
if (selected.size > 32) throw new Error('More than 32 selected maps exceeds the bounded browser campaign')
const alignmentBytes = await fs.readFile(path.join(webRoot, 'src/alignment.ts'))
const viewerBytes = await fs.readFile(path.join(webRoot, 'src/components/OpenSeadragonViewer.tsx'))
const osdBytes = await fs.readFile(require.resolve('openseadragon'))
const osdVersion = JSON.parse(await fs.readFile(require.resolve('openseadragon/package.json'))).version
const mappingModule = ts.transpileModule(alignmentBytes.toString(), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const host = { hostname: os.hostname(), expectedCampaignHost: option('--expected-host'), sameHostVerified: true,
  platform: os.platform(), release: os.release(), architecture: os.arch(), cpuModel: os.cpus()[0]?.model,
  logicalCpus: os.cpus().length, memoryBytes: os.totalmem(), nodeVersion: process.version }
const evidence = { schema: 'pathlab.alignment-browser-latency/1', createdAt: new Date().toISOString(), host,
  browser: { name: browserName, version: null }, manifestSha256: sha256(manifestBytes), campaignReportSha256: sha256(reportBytes),
  sourceCode: { alignmentSha256: sha256(alignmentBytes), viewerSetterSourceSha256: sha256(viewerBytes), openSeadragonSha256: sha256(osdBytes), openSeadragonVersion: osdVersion },
  samplingPolicy: 'two accepted map-complexity extremes per recipe; digest tie-break; supported cell centroids; first frame retained; no quality/winner selection',
  acceptanceScope: 'generated ready/approximate supported coordinate maps; approximate acceptance is research preview, not anatomical qualification',
  cacheScope: 'new browser page per map; original pixels loaded before sampling; repeat viewport applications; no filesystem-cache or worker-cache assertion',
  timingScope: 'production mapStackPoint lookup + standalone real OpenSeadragon pan/zoom/rotation through update-viewport after world.draw',
  excluded: ['API queue', 'preparation', 'engine computation', 'map transfer', 'initial source loading', 'React rendering', 'user-input dispatch', 'anatomical accuracy', 'warm worker'],
  warmWorkerRuntimeSeconds: null, productionTouched: false, measurements: [], cleanup: { browserClosed: false } }
const runtime = { chromium, firefox, webkit, 'mobile-chromium': chromium }[browserName]
const browser = selected.size ? await runtime.launch({ headless: true }) : null
evidence.browser.version = browser?.version() ?? null
const percentile = (values, fraction) => [...values].sort((left, right) => left - right)[Math.max(0, Math.ceil(values.length * fraction) - 1)]
try {
  for (const { row, receipt, receiptSha256 } of rows) {
    const cells = acceptedCells(receipt)
    const entry = { recipe: receipt.recipe, pairIndex: row.pairIndex, pairKind: row.kind, registrationDigest: receipt.digest, receiptSha256,
      settingsDigest: receipt.settingsDigest, engineBuild: receipt.engineBuild, inputDigests: receipt.inputDigests,
      status: receipt.registration?.status ?? null, cellCount: cells?.length ?? 0,
      preparationVersion: receipt.registration?.evidence?.preparationVersion ?? null,
      coldRuntimeSeconds: receipt.coldRuntimeSeconds ?? null, preparationSeconds: receipt.registration?.evidence?.preparationSeconds ?? null,
      campaignLandmarkMetrics: row.landmarkMetrics ?? null, browserAnatomicalErrorUm: null,
      queueSeconds: null, warmWorkerRuntimeSeconds: null, fullForegroundLatencySeconds: null,
      browserLatencySeconds: null, outcome: 'not-measured', reason: null }
    evidence.measurements.push(entry)
    if (!cells) { entry.reason = 'no-accepted-supported-coordinate-map'; continue }
    if (!selected.has(receipt.digest)) { entry.reason = 'outside-frozen-complexity-sample'; continue }
    let page = null
    try {
      const pair = manifest.pairs[row.pairIndex]
      const sources = await Promise.all([sourceSnapshot(pair.reference), sourceSnapshot(pair.moving)])
      if (sources.some((source, index) => source.digest !== receipt.inputDigests?.[index])) throw new Error('Registered source digest changed')
      entry.browserSourceDigests = sources.map(source => source.image.digest)
      entry.sourceSizes = sources.map(source => source.size)
      page = await browser.newPage(browserName === 'mobile-chromium'
        ? { ...devices['Pixel 5'] } : { viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 })
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      // Every resource is intercepted; the harness neither contacts production nor starts a worker.
      await page.route('**/*', async route => {
        const url = new URL(route.request().url())
        if (url.origin !== 'http://127.0.0.1') return route.abort()
        if (url.pathname === '/osd.js') return route.fulfill({ contentType: 'text/javascript', body: osdBytes })
        if (url.pathname === '/mapping.js') return route.fulfill({ contentType: 'text/javascript', body: mappingModule })
        if (url.pathname === '/reference.jpg') return route.fulfill({ contentType: sources[0].image.type, body: sources[0].image.bytes })
        if (url.pathname === '/moving.jpg') return route.fulfill({ contentType: sources[1].image.type, body: sources[1].image.bytes })
        if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Private alignment viewport latency</title><style>html,body{margin:0}#panes{display:flex}#reference,#moving{width:50vw;height:100vh}@media(max-width:600px){#panes{display:block}#reference,#moving{width:100vw;height:50vh}}</style><div id="panes"><div id="reference"></div><div id="moving"></div></div><script src="/osd.js"></script>' })
        return route.abort()
      })
      await page.goto('http://127.0.0.1/')
      const measured = await page.evaluate(async ({ registration, sampleCount, sizes }) => {
        const mapping = await import('/mapping.js')
        const OSD = window.OpenSeadragon
        const viewers = ['reference', 'moving'].map(id => OSD({ id, drawer: 'canvas', showNavigationControl: false,
          showNavigator: false, imageLoaderLimit: 2, animationTime: 0, tileSources: { type: 'image', url: `/${id}.jpg`, buildPyramid: false } }))
        window.__alignmentLatencyViewers = viewers
        try {
          await Promise.all(viewers.map(viewer => new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Original browser source did not load')), 10_000)
            viewer.addOnceHandler('tile-loaded', () => { clearTimeout(timer); resolve() })
            viewer.addOnceHandler('open-failed', () => { clearTimeout(timer); reject(new Error('Original browser source open failed')) })
          })))
          for (let index = 0; index < viewers.length; index++) {
            const item = viewers[index].world.getItemAt(0)
            const actual = item.getContentSize()
            if (actual.x !== sizes[index][0] || actual.y !== sizes[index][1]) throw new Error('Browser original size differs from registration frame')
          }
          const cells = registration.status === 'ready' ? registration.triangles : registration.overviewTriangles
          const results = []
          for (let sample = 0; sample < sampleCount; sample++) {
            const cellIndex = Math.floor(sample * cells.length / sampleCount)
            const cell = cells[cellIndex]
            const point = [0, 1].map(axis => cell.moving.reduce((total, vertex) => total + vertex[axis], 0) / 3)
            const source = viewers[1]
            const imageZoom = 0.8 + sample % 3 * 0.05
            const sourceCenter = source.viewport.imageToViewportCoordinates(point[0], point[1])
            source.viewport.panTo(sourceCenter, true)
            source.viewport.zoomTo(source.viewport.imageToViewportZoom(imageZoom), sourceCenter, true)
            const started = performance.now()
            const mapped = mapping.mapStackPoint(point, 'moving', 'reference', 'reference', [
              { slideId: 'moving', registration }, { slideId: 'reference', registration: null },
            ], registration.status === 'ready' ? 'strict' : 'overview')
            const lookupDone = performance.now()
            if (!mapped || !mapped.point.every(Number.isFinite)) throw new Error('Accepted cell centroid has no browser correspondence')
            const target = viewers[0]
            const frame = new Promise((resolve, reject) => {
              const timer = setTimeout(() => { target.removeHandler('update-viewport', drawn); reject(new Error('OSD frame was not drawn')) }, 3000)
              function drawn() { clearTimeout(timer); target.removeHandler('update-viewport', drawn); resolve(performance.now()) }
              target.addHandler('update-viewport', drawn)
            })
            const setterStart = performance.now()
            // Same image-coordinate setter calls as OpenSeadragonViewer.setImageViewport.
            const center = target.viewport.imageToViewportCoordinates(mapped.point[0], mapped.point[1])
            target.viewport.panTo(center, true)
            target.viewport.zoomTo(target.viewport.imageToViewportZoom(imageZoom * mapped.zoomScale), center, true)
            const rotation = ((mapped.rotation % 360) + 360) % 360
            target.viewport.setRotation(rotation)
            const setterDone = performance.now()
            target.forceRedraw()
            const frameAt = await frame
            const actual = target.viewport.viewportToImageCoordinates(target.viewport.getCenter(true))
            const actualZoom = target.viewport.viewportToImageZoom(target.viewport.getZoom(true))
            if (Math.hypot(actual.x - mapped.point[0], actual.y - mapped.point[1]) > 0.01
              || Math.abs(actualZoom - imageZoom * mapped.zoomScale) > 0.0001
              || Math.abs(target.viewport.getRotation() - rotation) > 0.001) throw new Error('Drawn OSD viewport differs from generated map')
            const canvas = target.drawer.canvas
            if (!canvas.width || !canvas.height) throw new Error('No drawn canvas')
            const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data
            let renderedPixelSamples = 0
            let nonBackgroundPixelSamples = 0
            const colors = new Set()
            for (let pixel = 0; pixel < pixels.length; pixel += 400) {
              if (pixels[pixel + 3] === 0) continue
              renderedPixelSamples++
              colors.add(`${pixels[pixel]},${pixels[pixel + 1]},${pixels[pixel + 2]}`)
              if (pixels[pixel] < 245 || pixels[pixel + 1] < 245 || pixels[pixel + 2] < 245) nonBackgroundPixelSamples++
            }
            if (nonBackgroundPixelSamples < 10 || colors.size < 2) throw new Error('Drawn original canvas is blank or uniform')
            results.push({ sample, cellIndex, mapLookupMs: lookupDone - started, viewportSetterMs: setterDone - setterStart,
              viewportToDrawnFrameMs: frameAt - setterStart, mapToDrawnFrameMs: frameAt - started,
              sourcePoint: point, mappedPoint: mapped.point, actualPoint: [actual.x, actual.y], imageZoom: actualZoom, rotation,
              renderedPixelSamples, nonBackgroundPixelSamples, sampledColors: colors.size })
          }
          return results
        } catch (error) {
          viewers.forEach(viewer => viewer.destroy())
          window.__alignmentLatencyViewers = []
          throw error
        }
      }, { registration: receipt.registration, sampleCount: samples, sizes: sources.map(source => source.size) })
      if (errors.length) throw new Error(`Browser exception: ${errors.join('; ')}`)
      entry.outcome = 'measured'
      entry.samples = measured
      entry.browserLatencySeconds = percentile(measured.map(sample => sample.mapToDrawnFrameMs), 0.95) / 1000
      entry.summaryMs = Object.fromEntries(['mapLookupMs', 'viewportSetterMs', 'viewportToDrawnFrameMs', 'mapToDrawnFrameMs'].map(key => [key, {
        median: percentile(measured.map(sample => sample[key]), 0.5), p95: percentile(measured.map(sample => sample[key]), 0.95),
      }]))
      const image = await page.screenshot()
      const imagePath = path.join(path.dirname(output), `alignment-latency-${browserName}-${receipt.digest}.png`)
      await fs.mkdir(path.dirname(output), { recursive: true })
      await fs.writeFile(imagePath, image)
      entry.renderedScreenshot = { path: imagePath, sha256: sha256(image) }
    } catch (error) {
      entry.outcome = 'not-measured'
      entry.reason = error instanceof Error ? error.message : 'Browser measurement failed'
      entry.browserLatencySeconds = null
      delete entry.samples
      delete entry.summaryMs
      delete entry.renderedScreenshot
    } finally {
      if (page) {
        // Successful viewers remain alive until the rendered screenshot is captured.
        // Closing the page/browser still guarantees cleanup if explicit destruction fails.
        try { await page.evaluate(() => window.__alignmentLatencyViewers?.forEach(viewer => viewer.destroy())) } catch { /* Page closure frees the document and viewers. */ }
        await page.close()
      }
    }
  }
} finally {
  await browser?.close()
  evidence.cleanup.browserClosed = true
  await fs.mkdir(path.dirname(output), { recursive: true })
  await fs.writeFile(output, JSON.stringify(evidence, null, 2) + '\n')
}
const measuredCount = evidence.measurements.filter(row => row.outcome === 'measured').length
console.log(JSON.stringify({ output, measuredCount, unmeasuredCount: rows.length - measuredCount, productionTouched: false }))
if (selected.size && measuredCount !== selected.size) process.exitCode = 1
