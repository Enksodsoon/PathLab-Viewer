import { expect, test } from '@playwright/test'
import { readFileSync, writeFileSync } from 'node:fs'

import { signIn } from './capacity-helpers'

const resultPath = required('CAPACITY_SENTINEL_RESULT')
const joinCode = required('CAPACITY_CLASSROOM_JOIN_CODE')
const sessionId = required('CAPACITY_CLASSROOM_SESSION_ID')
const browserCiRunId = Number(required('CAPACITY_BROWSER_CI_RUN_ID'))
const adminUsername = required('LOAD_TEST_ADMIN_USERNAME')
const adminPassword = required('LOAD_TEST_ADMIN_PASSWORD')

function required(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

test('records run-bound live frontend SLO evidence', async ({ page }, testInfo) => {
  const consoleErrors: string[] = []
  const networkErrors: string[] = []
  let successfulImageResponses = 0
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  page.on('requestfailed', (request) => networkErrors.push(request.url()))
  page.on('response', (response) => {
    if (response.status() >= 400) networkErrors.push(response.url())
    if (response.ok() && response.headers()['content-type']?.startsWith('image/')) {
      successfulImageResponses += 1
    }
  })
  await page.addInitScript(() => {
    const state = { cls: 0, lcp: 0 }
    Object.defineProperty(window, '__capacityVitals', { value: state })
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { value?: number, hadRecentInput?: boolean }>) {
        if (!entry.hadRecentInput) state.cls += entry.value ?? 0
      }
    }).observe({ type: 'layout-shift', buffered: true })
    new PerformanceObserver((list) => {
      const entries = list.getEntries()
      state.lcp = entries.at(-1)?.startTime ?? state.lcp
    }).observe({ type: 'largest-contentful-paint', buffered: true })
  })
  await page.goto('/classroom', { waitUntil: 'networkidle' })
  await page.getByLabel('Join code').fill(joinCode)
  await page.getByLabel(/Name/).fill(`Synthetic ${testInfo.project.name}`)
  await page.getByRole('button', { name: 'Join classroom' }).click()
  await expect(page.locator('.classroom-control-status')).toContainText(/Teacher controls|View frozen|You control/)
  const canvases = page.locator('.osd-surface canvas')
  await expect(canvases.first()).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Ask for control' }).click()
  await expect(page.getByRole('button', { name: 'Cancel request' })).toBeVisible()
  await page.getByRole('button', { name: 'Cancel request' }).click()
  await expect(page.getByRole('button', { name: 'Ask for control' })).toBeVisible()
  await page.getByRole('button', { name: 'Draw on slide' }).click()
  await expect(page.getByRole('button', { name: 'Finish drawing' })).toBeVisible()
  await page.getByRole('button', { name: 'Finish drawing' }).click()
  const note = page.getByPlaceholder('Write a private note…')
  await note.fill(`Synthetic capacity notebook ${testInfo.project.name}`)
  await expect(note).toHaveValue(`Synthetic capacity notebook ${testInfo.project.name}`)

  const studentState = await page.evaluate(async (approvedSessionId) => {
    const response = await fetch(`/api/v1/classroom/sessions/${encodeURIComponent(approvedSessionId)}`, {
      credentials: 'same-origin', cache: 'no-store',
    })
    if (!response.ok) throw new Error(`student state unavailable: ${response.status}`)
    return response.json() as Promise<{
      session: { publicId: string | null, phase: 'live' }
      slides: unknown[]
      stateVersion: number
    }>
  }, sessionId)

  await signIn(page, adminUsername, adminPassword)
  await page.evaluate(({ approvedJoinCode, approvedSessionId, state }) => {
    sessionStorage.setItem('pathlab-active-classroom:v1', JSON.stringify({
      id: approvedSessionId,
      joinCode: approvedJoinCode,
      publicId: state.session.publicId,
      phase: state.session.phase,
      reviewExpiresAt: null,
      stateVersion: state.stateVersion,
      slides: state.slides,
    }))
  }, { approvedJoinCode: joinCode, approvedSessionId: sessionId, state: studentState })
  await page.goto('/admin/classroom', { waitUntil: 'networkidle' })
  await expect(page.locator('.classroom-shell--teacher')).toBeVisible({ timeout: 60_000 })
  await expect(page.locator('.classroom-shell--teacher .osd-surface canvas').first()).toBeVisible({ timeout: 60_000 })
  const rosterSearch = page.getByRole('searchbox', { name: 'Search students' })
  await rosterSearch.fill(`Synthetic ${testInfo.project.name}`)
  await rosterSearch.clear()
  await page.getByRole('button', { name: 'Guide students' }).click()
  await expect(page.getByRole('button', { name: 'Stop guiding students' })).toBeVisible()
  await page.getByRole('button', { name: 'Stop guiding students' }).click()
  await page.getByRole('button', { name: 'Join code' }).click()
  await expect(page.getByRole('dialog', { name: 'Review slides and join class' })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await page.waitForTimeout(1_000)
  let blankCanvases = await canvases.evaluateAll((items) => items.filter((item) => {
    const canvas = item as HTMLCanvasElement
    return canvas.width === 0 || canvas.height === 0
  }).length)
  if (successfulImageResponses < 1) blankCanvases += 1
  const vitals = await page.evaluate(() => (window as unknown as { __capacityVitals: { cls: number, lcp: number } }).__capacityVitals)
  const current = JSON.parse(readFileSync(resultPath, 'utf8')) as Record<string, unknown>
  const prior = (current.frontend ?? {}) as Record<string, unknown>
  const priorProjects = (prior.projects ?? {}) as Record<string, unknown>
  const projects = Array.from(new Set([
    ...((current.crossBrowser as { projects?: string[] } | undefined)?.projects ?? []),
    testInfo.project.name,
  ])).sort()
  const frontend = {
    clsMax: Math.max(Number(prior.clsMax ?? 0), vitals.cls),
    lcpMsMax: Math.max(Number(prior.lcpMsMax ?? 0), vitals.lcp),
    consoleErrors: Number(prior.consoleErrors ?? 0) + consoleErrors.length,
    networkErrors: Number(prior.networkErrors ?? 0) + networkErrors.length,
    blankCanvases: Number(prior.blankCanvases ?? 0) + blankCanvases,
    mobilePassed: prior.mobilePassed === true || testInfo.project.name === 'mobile-chromium',
    projects: {
      ...priorProjects,
      [testInfo.project.name]: {
        cls: vitals.cls,
        lcpMs: vitals.lcp,
        consoleErrors: consoleErrors.length,
        networkErrors: networkErrors.length,
        blankCanvases,
        studentInteractionsPassed: true,
        teacherInteractionsPassed: true,
      },
    },
  }
  const requiredProjects = ['chromium', 'firefox', 'mobile-chromium', 'webkit']
  const crossBrowser = {
    approved: projects.length === requiredProjects.length
      && projects.every((project, index) => project === requiredProjects[index]),
    projects: ['chromium', 'firefox', 'webkit', 'mobile-chromium'],
    ciRunId: browserCiRunId,
  }
  writeFileSync(resultPath, `${JSON.stringify({ ...current, frontend, crossBrowser }, null, 2)}\n`)
  expect(frontend.clsMax).toBeLessThanOrEqual(0.1)
  expect(frontend.lcpMsMax).toBeLessThanOrEqual(2500)
  expect(frontend.consoleErrors).toBe(0)
  expect(frontend.networkErrors).toBe(0)
  expect(frontend.blankCanvases).toBe(0)
})
