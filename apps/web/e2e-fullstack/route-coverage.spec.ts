import { readFileSync } from 'node:fs'
import { expect, test } from './qa-test'
import { signIn, uploadSyntheticSlide, waitForSlideConversion } from '../e2e-live/capacity-helpers'
import { sweepVisibleTabStops } from './tab-traversal'

const declaredRoutePatterns = [
  '/admin', '/admin/preview/:slideId', '/admin/comparisons/:comparisonId', '/admin/connect', '/admin/classroom', '/classroom',
  '/classroom/invite/:publicId', '/classroom/:sessionId', '/admin/study', '/admin/study/packs/new',
  '/admin/assessments', '/admin/assessments/classes', '/admin/assessments/courses/new',
  '/admin/assessments/courses/:courseId', '/admin/assessments/courses/:courseId/edit',
  '/admin/assessments/courses/:courseId/roster', '/admin/assessments/courses/:courseId/classes/new',
  '/admin/assessments/courses/:courseId/classes/:classId', '/admin/assessments/courses/:courseId/classes/:classId/edit',
  '/admin/assessments/:draftId/report', '/admin/assessments/:draftId', '/assessment/:publicId',
  '/admin/study/evidence', '/study', '/s/:publicId', '/f/:publicId', '/c/:publicId', '/c/:publicId/compare/:comparisonId', '*',
]

async function createCourseAndClass(page: Parameters<typeof signIn>[0], label: string, withSlideSet = false) {
  const suffix = `${Date.now().toString(36).toUpperCase().slice(-6)}`
  const courseName = `QA ${label} course ${suffix}`
  const courseCode = `QA-${suffix}`
  const className = `QA ${label} class ${suffix}`
  const sectionCode = `S-${suffix}`
  const folderName = `QA ${label} slide folder ${suffix}`

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
  const folderDialog = page.getByRole('dialog', { name: 'New folder', exact: true })
  await folderDialog.getByRole('textbox', { name: 'Name', exact: true }).fill(folderName)
  await folderDialog.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(folderDialog).not.toBeVisible()

  if (withSlideSet) {
    const slideName = `QA ${label} slide ${suffix}`
    const slideId = await uploadSyntheticSlide(page, process.env.PATHLAB_E2E_OME!, slideName)
    await waitForSlideConversion(page, slideId)
    await page.reload()
    await page.getByRole('button', { name: `More actions for ${slideName}`, exact: true }).click()
    await page.getByRole('menuitem', { name: 'Move', exact: true }).click()
    const move = page.getByRole('dialog', { name: 'Move slides', exact: true })
    await move.getByRole('combobox', { name: 'Destination', exact: true }).selectOption({ label: folderName })
    await move.getByRole('button', { name: 'Move', exact: true }).click()
    await expect(move).not.toBeVisible()
  }

  await page.getByRole('button', { name: 'Teaching Studio', exact: true }).click()
  await page.getByRole('link', { name: 'Courses', exact: true }).click()
  await page.getByRole('link', { name: 'Create course', exact: true }).click()
  for (const [name, value] of [
    [/Course name/, courseName],
    [/Course ID/, courseCode],
    [/Semester/, 'Route coverage'],
    [/Academic year/, '2026'],
  ] as const) {
    await page.getByRole('textbox', { name }).fill(value)
  }
  await page.getByRole('button', { name: 'Save course', exact: true }).click()
  await expect(page.getByRole('heading', { name: courseName, exact: true })).toBeVisible()
  const coursePath = new URL(page.url()).pathname

  await page.getByRole('link', { name: 'New class', exact: true }).first().click()
  await page.getByRole('textbox', { name: 'Class name', exact: true }).fill(className)
  await page.getByRole('textbox', { name: 'Section code', exact: true }).fill(sectionCode)
  await page.getByRole('button', { name: 'Save class', exact: true }).click()
  await expect(page.getByRole('heading', { name: className, exact: true })).toBeVisible()
  return {
    courseName,
    courseCode,
    className,
    sectionCode,
    courseId: coursePath.split('/').at(-1)!,
    coursePath,
    classId: new URL(page.url()).pathname.split('/').at(-1)!,
    folderName,
  }
}

async function createDraft(page: Parameters<typeof signIn>[0], courseName: string, courseCode: string, className: string, sectionCode: string) {
  await page.goto('/admin/assessments')
  await page.getByRole('button', { name: 'New assessment', exact: true }).click()
  await page.getByRole('combobox', { name: 'Course', exact: true }).selectOption({ label: `${courseName} · ${courseCode}` })
  await page.getByRole('combobox', { name: 'Class', exact: true }).selectOption({ label: `${className} · ${sectionCode}` })
  await page.getByRole('button', { name: 'Create assessment', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Assessment name', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Untitled assessment', exact: true })).toBeVisible()
  return { title: 'Untitled assessment', id: new URL(page.url()).pathname.split('/').at(-1)! }
}

test('every declared route renders; buttons and menus are inventoried and explored', async ({ page }, testInfo) => {
  test.setTimeout(1_800_000)
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const sourceRoutes = [...appSource.matchAll(/<Route\s+path="([^"]+)"/g)].map((match) => match[1])
  expect(sourceRoutes, 'Route inventory must match App.tsx declarations').toEqual(declaredRoutePatterns)
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const fixture = await createCourseAndClass(page, 'route')
  const draft = await createDraft(page, fixture.courseName, fixture.courseCode, fixture.className, fixture.sectionCode)
  const routeSlideName = `QA route explorer slide ${Date.now().toString(36).toUpperCase().slice(-6)}`
  await page.goto('/admin')
  const routeSlideId = await uploadSyntheticSlide(page, process.env.PATHLAB_E2E_OME!, routeSlideName)
  await waitForSlideConversion(page, routeSlideId)
  await page.reload()
  await expect(page.getByRole('article', { name: routeSlideName, exact: true })).toBeVisible()
  await page.getByRole('button', { name: `More actions for ${routeSlideName}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Publish', exact: true }).click()
  const publication = page.getByRole('dialog', { name: 'Confirm deidentification', exact: true })
  await publication.getByRole('checkbox').check()
  await publication.getByRole('button', { name: 'Publish 1 slide', exact: true }).click()
  await expect(publication).toBeHidden()

  const routes = [
    { route: '/admin', marker: 'All slides' },
    { route: '/admin?location=storage', marker: 'Storage' },
    { route: '/admin?location=trash', marker: 'Trash' },
    { route: '/admin/preview/qa-missing-slide', marker: 'This slide is unavailable' },
    { route: '/admin/comparisons/qa-missing-comparison', marker: 'Comparison set is unavailable.' },
    { route: '/admin/connect?code=QA-INVALID-CODE', marker: 'Connect PathLab Forge' },
    { route: '/admin/classroom', marker: 'Choose a class folder' },
    { route: '/classroom', marker: 'Join a slide session' },
    { route: '/classroom/invite/qa-missing-invite', marker: 'Open teaching slides' },
    { route: '/classroom/qa-missing-session', marker: 'Join a slide session' },
    { route: '/admin/study', marker: 'Study Coach' },
    { route: '/admin/study/packs/new', marker: 'Author a Study Pack' },
    { route: '/admin/assessments', marker: 'My Assessments' },
    { route: '/admin/assessments/classes', marker: 'Courses' },
    { route: '/admin/assessments/courses/new', marker: 'Create a course' },
    { route: fixture.coursePath, marker: fixture.courseName },
    { route: `${fixture.coursePath}/edit`, marker: 'Edit course' },
    { route: `${fixture.coursePath}/roster`, marker: 'Course roster' },
    { route: `${fixture.coursePath}/classes/new`, marker: 'Create a class' },
    { route: `${fixture.coursePath}/classes/${fixture.classId}`, marker: fixture.className },
    { route: `${fixture.coursePath}/classes/${fixture.classId}/edit`, marker: 'Edit class' },
    { route: `/admin/assessments/${draft.id}/report?source=route-coverage`, marker: 'Responses', redirect: true },
    { route: `/admin/assessments/${draft.id}`, marker: draft.title },
    { route: '/assessment/qa-missing-public-assessment', marker: 'Assessment unavailable', heading: false },
    { route: '/admin/study/evidence', marker: 'Review signed pathology evidence' },
    { route: '/study', marker: 'Learn from faculty-selected slides' },
    { route: '/s/qa-missing-public-slide', marker: 'This slide is unavailable' },
    { route: '/f/qa-missing-folder-share', marker: 'This shared library is unavailable' },
    { route: '/c/qa-missing-collection-share', marker: 'This shared library is unavailable' },
    { route: '/c/qa-missing-collection-share/compare/qa-missing-comparison', marker: 'Comparison set is unavailable.' },
  ]
  const routeEvidence: Array<{
    route: string
    finalPath: string
    marker: string
    menuTriggers: number
    disabledMenuTriggers: number
    menuItems: string[]
    keyboardStops: number
    buttons: Array<{ domIndex: number; name: string; disabled: boolean; expanded: string | null; popup: string | null }>
  }> = []

  for (const item of routes) {
    await page.goto(item.route, { waitUntil: 'domcontentloaded' })
    if (item.redirect) {
      await expect(page).toHaveURL(new RegExp(`/admin/assessments/${draft.id}\\?source=route-coverage&tab=responses$`))
      await expect(page.getByRole('tab', { name: 'Responses', exact: true })).toBeVisible()
    } else {
      expect(new URL(page.url()).pathname, `Route did not resolve: ${item.route}`).toBe(new URL(item.route, page.url()).pathname)
    }
    await expect(page.getByRole('heading', { name: 'Administrator sign in' })).toHaveCount(0)
    const marker = item.redirect
      ? page.getByRole('tab', { name: item.marker, exact: true })
      : item.heading === false
      ? page.getByText(item.marker, { exact: true }).first()
      : page.getByRole('heading', { name: item.marker, exact: true }).first()
    await expect(marker, `Screen not ready for ${item.route}`).toBeVisible()
    if (item.redirect) {
      await expect(page.getByRole('navigation', { name: 'Response views', exact: true })).toBeVisible()
    }

    const triggers = page.locator('button[aria-haspopup="menu"]')
    const triggerCount = await triggers.count()
    if (item.route === '/admin') expect(triggerCount, 'Library context menu trigger inventory').toBeGreaterThan(0)
    let visibleMenuTriggers = 0
    let disabledMenuTriggers = 0
    const itemNames = new Set<string>()
    for (let index = 0; index < triggerCount; index += 1) {
      const trigger = triggers.nth(index)
      if (!(await trigger.isVisible())) continue
      visibleMenuTriggers += 1
      if (!(await trigger.isEnabled())) {
        disabledMenuTriggers += 1
        continue
      }
      await trigger.scrollIntoViewIfNeeded()
      await trigger.click()
      const menu = page.getByRole('menu').last()
      await expect(menu, `Menu did not open at ${item.route}`).toBeVisible()
      for (const name of await menu.getByRole('menuitem').allTextContents()) {
        if (name.trim()) itemNames.add(name.trim().replace(/\s+/g, ' '))
      }
      await page.keyboard.press('Escape')
      await expect(menu, `Escape did not close menu at ${item.route}`).toBeHidden()
      await expect(trigger, `Focus was not restored at ${item.route}`).toBeFocused()
    }
    const keyboardStops = await sweepVisibleTabStops(page, 0)
    const buttons = await page.locator('button,[role="button"]').evaluateAll((elements) => elements
      .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible')
      .map((element) => ({
        domIndex: [...document.querySelectorAll('button,[role="button"]')].indexOf(element),
        name: element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)',
        disabled: element.matches(':disabled,[aria-disabled="true"]'),
        expanded: element.getAttribute('aria-expanded'),
        popup: element.getAttribute('aria-haspopup'),
      })))
    routeEvidence.push({ route: item.route, finalPath: new URL(page.url()).pathname, marker: item.marker,
      menuTriggers: visibleMenuTriggers, disabledMenuTriggers, menuItems: [...itemNames].sort(),
      keyboardStops: keyboardStops.length, buttons })
  }

  await page.goto('/pathlab-qa-unmatched-route')
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.getByRole('heading', { name: 'All slides', exact: true })).toBeVisible()
  const keyboardStops = await sweepVisibleTabStops(page, 0)
  const buttons = await page.locator('button,[role="button"]').evaluateAll((elements) => elements
    .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible')
    .map((element) => ({
      domIndex: [...document.querySelectorAll('button,[role="button"]')].indexOf(element),
      name: element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)',
      disabled: element.matches(':disabled,[aria-disabled="true"]'),
      expanded: element.getAttribute('aria-expanded'),
      popup: element.getAttribute('aria-haspopup'),
    })))
  routeEvidence.push({ route: '*', finalPath: new URL(page.url()).pathname, marker: 'All slides', menuTriggers: 0,
    disabledMenuTriggers: 0, menuItems: [], keyboardStops: keyboardStops.length, buttons })

  const activationEvidence: Array<Record<string, unknown>> = []
  const loadRoute = async (routeIndex: number) => {
    const item = routes[routeIndex]
    const target = item?.route ?? '/pathlab-qa-unmatched-route'
    await page.goto(target, { waitUntil: 'domcontentloaded' })
    if (await page.getByRole('heading', { name: 'Administrator sign in', exact: true }).count()) {
      await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
      await page.goto(target, { waitUntil: 'domcontentloaded' })
    }
    if (item?.redirect) {
      await expect(page).toHaveURL(new RegExp(`/admin/assessments/${draft.id}\\?source=route-coverage&tab=responses$`))
    }
    const marker = item?.redirect
      ? page.getByRole('tab', { name: item.marker, exact: true })
      : item?.heading === false
      ? page.getByText(item.marker, { exact: true }).first()
      : page.getByRole('heading', { name: item?.marker ?? 'All slides', exact: true }).first()
    await expect(marker, `Could not restore route ${target}`).toBeVisible()
    // The unmatched route redirects to Library before its data has settled.
    if (target === '/admin' || !item) {
      await expect(page.getByRole('article', { name: routeSlideName, exact: true })).toBeVisible()
    }
    if (item?.redirect) {
      await expect(page.getByRole('navigation', { name: 'Response views', exact: true })).toBeVisible()
    }
  }
  const describeSurface = async () => page.evaluate(() => {
    const text = (element: Element) => (element.getAttribute('aria-label')
      || element.getAttribute('title') || element.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 180)
    const visible = (element: Element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible'
    const nodes = (selector: string) => [...document.querySelectorAll(selector)].filter(visible)
    return {
      path: location.pathname + location.search,
      headings: nodes('h1,h2,[role="heading"]').map(text),
      dialogs: [...document.querySelectorAll('[role="dialog"],[role="alertdialog"],dialog[open]')]
        .filter(visible)
        .map((element) => ({
        name: element.getAttribute('aria-label') || element.querySelector('h1,h2,[role="heading"]')?.textContent?.trim() || '',
        buttons: [...element.querySelectorAll('button,[role="button"],[role="menuitem"]')].filter(visible).map(text),
        })),
      menus: nodes('[role="menu"]').map((element) => [...element.querySelectorAll('[role="menuitem"]')].filter(visible).map(text)),
      alerts: nodes('[role="alert"],[role="status"]').map(text),
      buttons: nodes('button,[role="button"],[role="menuitem"]').map(text),
    }
  })
  const explorationOrder = routeEvidence.map((entry, index) => ({ entry, index }))
    .sort((left, right) => Number(left.entry.route === '/admin/assessments') - Number(right.entry.route === '/admin/assessments'))
  const normalizeButtonName = (name: string) => name
    .replace(/^Open storage,.* available$/, 'Open storage')
    .replace(/^(Expand|Collapse) navigation rail$/, 'Navigation rail toggle')
    .replace(/^(Archive|Restore) Untitled assessment.*$/, 'Assessment archive toggle')
    .replace(/Untitled assessment( copy)?/g, 'Untitled assessment')
  const findButton = async (expectedName: string) => (await page.evaluateHandle((name) => {
    const normalize = (value: string) => value
      .replace(/^Open storage,.* available$/, 'Open storage')
      .replace(/^(Expand|Collapse) navigation rail$/, 'Navigation rail toggle')
      .replace(/^(Archive|Restore) Untitled assessment.*$/, 'Assessment archive toggle')
      .replace(/Untitled assessment( copy)?/g, 'Untitled assessment')
      .replace(/\s+/g, ' ').trim()
    return [...document.querySelectorAll('button,[role="button"]')].find((element) => {
      if (!(element instanceof HTMLElement) || !element.getClientRects().length
        || getComputedStyle(element).visibility !== 'visible') return false
      const currentName = element.getAttribute('aria-label') || element.getAttribute('title')
        || element.textContent?.trim() || '(unnamed)'
      return normalize(currentName) === normalize(name)
    }) ?? null
  }, expectedName)).asElement()
  const routeButtonsInOrder = explorationOrder.flatMap(({ entry, index }) =>
    entry.buttons.map((button) => ({ entry, index, button })))
  const exploredButtons = new Set<string>()
  const exploredMenuActions = new Set<string>()
  for (const { entry, index, button } of [
    ...routeButtonsInOrder.filter(({ button: item }) => item.popup !== 'menu'),
    ...routeButtonsInOrder.filter(({ button: item }) => item.popup === 'menu'),
  ]) {
      const name = button.name
      const buttonKey = JSON.stringify([entry.route, name.trim().replace(/\s+/g, ' '), button.popup, button.disabled])
      if (exploredButtons.has(buttonKey)) {
        activationEvidence.push({ route: entry.route, name, result: 'covered-by-equivalent-control' })
        continue
      }
      if (/^(Move to Trash|Delete permanently|Restore):/i.test(name)) {
        activationEvidence.push({ route: entry.route, name, result: 'covered-by-library-lifecycle.spec.ts' })
        continue
      }
      if (/^Archive .+, revision \d+$/i.test(name)) {
        activationEvidence.push({ route: entry.route, name, result: 'covered-by-assessment-types.spec.ts' })
        continue
      }
      if (button.disabled) {
        activationEvidence.push({ route: entry.route, name, result: 'disabled', popup: button.popup })
        continue
      }
      if (name === 'Sign out') {
        activationEvidence.push({ route: entry.route, name, result: 'covered-by-account-workflow.spec.ts' })
        continue
      }
      await loadRoute(index)
      const buttonLocator = page.locator('button,[role="button"]')
      const target = await findButton(name)
      if (!target) {
        const currentButtons = await buttonLocator.evaluateAll((elements) => elements
          .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible')
          .map((element) => element.getAttribute('aria-label') || element.getAttribute('title')
            || element.textContent?.trim() || '(unnamed)'))
        activationEvidence.push({ route: entry.route, name, result: 'not-reachable-after-prior-action', currentButtons })
        continue
      }
      if (!(await target.isEnabled())) {
        activationEvidence.push({ route: entry.route, name, result: 'disabled-after-state-change' })
        continue
      }
      const currentName = await target.evaluate((element) => element.getAttribute('aria-label')
        || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)')
      if (normalizeButtonName(currentName) !== normalizeButtonName(name)) {
        activationEvidence.push({ route: entry.route, name, result: 'control-label-changed', observed: currentName })
        continue
      }
      try {
        await target.click({ timeout: 5000, noWaitAfter: true })
        await page.waitForTimeout(100)
        exploredButtons.add(buttonKey)
        const state = await describeSurface()
        activationEvidence.push({ route: entry.route, routeIndex: index, name, observed: currentName, result: 'clicked', popup: button.popup, state })
        if (button.popup === 'menu') {
          const items = await page.getByRole('menu').last().getByRole('menuitem').allTextContents()
          for (let menuIndex = 0; menuIndex < items.length; menuIndex += 1) {
            const menuItemName = items[menuIndex].trim().replace(/\s+/g, ' ')
            await loadRoute(index)
            const trigger = await findButton(name)
            if (!trigger) {
              activationEvidence.push({ route: entry.route, name,
                result: 'not-reachable-after-prior-action', currentButtons: await buttonLocator.allTextContents() })
              continue
            }
            await trigger.click({ timeout: 5000 })
            const menu = page.getByRole('menu').last()
            const currentItems = await menu.getByRole('menuitem').allTextContents()
            const currentIndex = currentItems.findIndex((item) => item.trim().replace(/\s+/g, ' ') === menuItemName)
            if (currentIndex < 0) {
              activationEvidence.push({ route: entry.route, name: menuItemName,
                result: 'not-reachable-after-prior-action', currentButtons: currentItems })
              continue
            }
            const menuItem = menu.getByRole('menuitem').nth(currentIndex)
            const menuActionKey = JSON.stringify([entry.route, menuItemName,
              currentItems.map((item) => item.trim().replace(/\s+/g, ' ')).sort()])
            if (exploredMenuActions.has(menuActionKey)) {
              activationEvidence.push({ route: entry.route, name: menuItemName, parentMenu: name,
                result: 'covered-by-equivalent-menu-state' })
              continue
            }
            if (/^(Move to Trash|Delete permanently|Restore)$/i.test(menuItemName)) {
              activationEvidence.push({ route: entry.route, name: menuItemName, parentMenu: name,
                result: 'covered-by-library-lifecycle.spec.ts' })
              continue
            }
            if (/^Archive assessment$/i.test(menuItemName)) {
              activationEvidence.push({ route: entry.route, name: menuItemName, parentMenu: name,
                result: 'covered-by-assessment-types.spec.ts' })
              continue
            }
            if (entry.route === '/admin' && /^More actions for /.test(name) && /^Unpublish$/i.test(menuItemName)) {
              activationEvidence.push({ route: entry.route, name: menuItemName, parentMenu: name,
                result: 'covered-by-imaging-journey.spec.ts' })
              continue
            }
            if (!(await menuItem.isEnabled())) {
              activationEvidence.push({ route: entry.route, name: menuItemName, result: 'disabled-menu-item' })
              continue
            }
            await menuItem.click({ timeout: 5000, noWaitAfter: true })
            exploredMenuActions.add(menuActionKey)
            await page.waitForTimeout(100)
            activationEvidence.push({ route: entry.route, routeIndex: index, name: menuItemName, parentMenu: name,
              result: 'clicked', state: await describeSurface() })
          }
        }
      } catch (error) {
        activationEvidence.push({ route: entry.route, name, result: 'click-error', error: String(error) })
      }
  }

  type DialogStep = { dialogName: string; buttonName: string; occurrence: number }
  type DialogSeed = {
    routeIndex: number
    triggerName: string
    menuItem?: string
    dialogName: string
    buttons: string[]
    path: DialogStep[]
    selectSlide?: string
  }
  const dialogSeeds: DialogSeed[] = []
  const dialogSeedKeys = new Set<string>()
  const addDialogSeed = (seed: DialogSeed) => {
    const key = JSON.stringify([seed.routeIndex, seed.triggerName, seed.menuItem, seed.path, seed.dialogName,
      seed.buttons.map((name) => name.replace(/\s+/g, ' ').trim())])
    if (dialogSeedKeys.has(key)) return
    dialogSeedKeys.add(key)
    dialogSeeds.push(seed)
  }
  for (const action of activationEvidence) {
    if (action.result !== 'clicked' || typeof action.routeIndex !== 'number') continue
    const state = action.state as { path?: string; dialogs?: Array<{ name: string; buttons: string[] }> } | undefined
    const stateRouteIndex = state?.path
      ? routeEvidence.findIndex((entry) => entry.route === state.path)
      : -1
    const routeIndex = stateRouteIndex >= 0 ? stateRouteIndex : action.routeIndex
    for (const dialog of state?.dialogs ?? []) {
      if (!dialog.name) continue
      const fromMenu = typeof action.parentMenu === 'string'
      addDialogSeed({
        routeIndex,
        triggerName: fromMenu ? String(action.parentMenu) : String(action.name),
        ...(fromMenu ? { menuItem: String(action.name) } : {}),
        dialogName: dialog.name,
        buttons: dialog.buttons,
        path: [],
        ...(dialog.name.startsWith('Quick look: ')
          ? { selectSlide: dialog.name.slice('Quick look: '.length) } : {}),
      })
    }
  }

  const dialogButtonEvidence: Array<Record<string, unknown>> = []
  const normalizeActionName = (value: string) => value.replace(/\s+/g, ' ').trim()
  const dialogActions = (dialog: ReturnType<typeof page.getByRole>) => dialog.locator('button,[role="button"],[role="menuitem"]')
  const readDialogButtons = async (dialog: ReturnType<typeof page.getByRole>) => dialogActions(dialog).evaluateAll((elements) =>
    elements.filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible')
      .map((element) => element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)'))
  const findDialogAction = async (dialog: ReturnType<typeof page.getByRole>, name: string, occurrence = 0) => {
    const buttons = dialog.getByRole('button', { name, exact: true })
    if (await buttons.count() > occurrence) return buttons.nth(occurrence)
    const options = dialog.locator('button[role="option"]')
    const matchingOptions = await options.evaluateAll((elements, expectedName) => {
      const normalize = (value: string) => value.replace(/\s+/g, ' ').trim()
      return elements.flatMap((element, index) => {
        const currentName = element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)'
        return normalize(currentName) === normalize(expectedName) ? [index] : []
      })
    }, name)
    if (matchingOptions.length > occurrence) return options.nth(matchingOptions[occurrence])
    const menuItems = dialog.getByRole('menuitem', { name, exact: true })
    return await menuItems.count() > occurrence ? menuItems.nth(occurrence) : undefined
  }
  const readRouteButtons = async () => page.locator('button,[role="button"]').evaluateAll((elements) =>
    elements.filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility === 'visible')
      .map((element) => element.getAttribute('aria-label') || element.getAttribute('title') || element.textContent?.trim() || '(unnamed)'))
  const reopenDialog = async (seed: DialogSeed) => {
    await loadRoute(seed.routeIndex)
    let trigger
    if (seed.selectSlide) {
      const slide = page.getByRole('article', { name: seed.selectSlide, exact: true })
      if (seed.triggerName === 'Quick look') trigger = slide.getByRole('button', { name: 'Quick look', exact: true })
      else {
        const selection = slide.getByRole('checkbox', { name: `Select ${seed.selectSlide}`, exact: true })
        if (await selection.isVisible()) await selection.check()
      }
    }
    trigger ??= await findButton(seed.triggerName) ?? undefined
    if (!trigger) {
      return { unavailable: { reason: 'trigger-not-present-after-state-change', dialogName: seed.dialogName,
        triggerName: seed.triggerName, buttons: await readRouteButtons(), dialogs: (await describeSurface()).dialogs,
        path: seed.path } }
    }
    if (!(await trigger.isEnabled())) {
      return { unavailable: { reason: 'trigger-disabled-after-state-change', dialogName: seed.dialogName,
        triggerName: seed.triggerName, buttons: await readRouteButtons(), dialogs: (await describeSurface()).dialogs,
        path: seed.path } }
    }
    await trigger.click({ timeout: 5000 })
    if (seed.menuItem) {
      const menuItem = page.getByRole('menuitem', { name: seed.menuItem, exact: true })
      if (!(await menuItem.isVisible())) {
        return { unavailable: { reason: 'menu-item-not-present-after-state-change', dialogName: seed.dialogName,
          triggerName: seed.triggerName, buttons: await page.getByRole('menuitem').allTextContents(),
          dialogs: (await describeSurface()).dialogs, path: seed.path } }
      }
      await menuItem.click({ timeout: 5000 })
    }
    for (const [stepIndex, step] of seed.path.entries()) {
      const owner = page.getByRole('dialog', { name: step.dialogName, exact: true })
      await owner.waitFor({ state: 'visible', timeout: 1500 }).catch(() => undefined)
      if (!(await owner.isVisible())) {
        const surface = await describeSurface()
        return { unavailable: { reason: 'path-dialog-not-present-after-state-change', dialogName: step.dialogName,
          triggerName: seed.triggerName, buttons: await readRouteButtons(), dialogs: surface.dialogs,
          path: seed.path.slice(0, stepIndex) } }
      }
      const action = await findDialogAction(owner, step.buttonName, step.occurrence)
      if (!action) {
        return { unavailable: { reason: 'path-action-not-present-after-state-change', dialogName: step.dialogName,
          triggerName: seed.triggerName, buttons: await readDialogButtons(owner), dialogs: (await describeSurface()).dialogs,
          path: seed.path.slice(0, stepIndex) } }
      }
      await action.click({ timeout: 5000, noWaitAfter: true })
    }
    const dialog = page.getByRole('dialog', { name: seed.dialogName, exact: true })
    await dialog.waitFor({ state: 'visible', timeout: 1500 }).catch(() => undefined)
    if (!(await dialog.isVisible())) {
      const surface = await describeSurface()
      return { unavailable: { reason: 'dialog-not-present-after-state-change', dialogName: seed.dialogName,
        triggerName: seed.triggerName, buttons: await readRouteButtons(), dialogs: surface.dialogs, path: seed.path } }
    }
    return { dialog }
  }

  for (let seedIndex = 0; seedIndex < dialogSeeds.length; seedIndex += 1) {
    const seed = dialogSeeds[seedIndex]
    const coveredBy = seed.dialogName === 'Search library commands'
      || seed.dialogName.startsWith('Quick look: ')
      ? 'library-lifecycle.spec.ts'
      : seed.dialogName === 'Slide rotation' && seed.triggerName === 'Quick look'
      ? 'library-lifecycle.spec.ts'
      : seed.dialogName === 'Edit slide details'
      ? 'library-lifecycle.spec.ts'
      : seed.dialogName === 'Learner preview'
      ? 'assessment-types.spec.ts'
      : undefined
    if (coveredBy) {
      for (const button of seed.buttons) dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*',
        dialog: seed.dialogName, button, result: `covered-by-${coveredBy}` })
      continue
    }
    const initial = await reopenDialog(seed)
    if (!initial.dialog) {
      const unavailable = initial.unavailable!
      if (unavailable.reason === 'path-action-not-present-after-state-change') {
        dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: unavailable.dialogName,
          path: unavailable.path, result: unavailable.reason, currentButtons: unavailable.buttons })
        addDialogSeed({ ...seed, dialogName: unavailable.dialogName, buttons: unavailable.buttons, path: unavailable.path })
      } else {
        for (const button of seed.buttons) dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*',
          dialog: seed.dialogName, button, trigger: unavailable.triggerName, path: seed.path,
          result: unavailable.reason, currentButtons: unavailable.buttons, currentDialogs: unavailable.dialogs })
      }
      continue
    }
    const currentButtons = await readDialogButtons(initial.dialog)
    if (JSON.stringify(currentButtons.map(normalizeActionName)) !== JSON.stringify(seed.buttons.map(normalizeActionName))) {
      addDialogSeed({ ...seed, buttons: currentButtons })
    }
    for (let buttonIndex = 0; buttonIndex < seed.buttons.length; buttonIndex += 1) {
      const buttonName = seed.buttons[buttonIndex]
      const occurrence = seed.buttons.slice(0, buttonIndex).filter((name) => normalizeActionName(name)
        === normalizeActionName(buttonName)).length
      const opened = await reopenDialog(seed)
      if (!opened.dialog) {
        const unavailable = opened.unavailable!
        if (unavailable.reason === 'path-action-not-present-after-state-change') {
          dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: unavailable.dialogName,
            path: unavailable.path, result: unavailable.reason, currentButtons: unavailable.buttons })
          addDialogSeed({ ...seed, dialogName: unavailable.dialogName, buttons: unavailable.buttons, path: unavailable.path })
        } else {
          for (const button of seed.buttons.slice(buttonIndex)) dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*',
            dialog: seed.dialogName, button, trigger: unavailable.triggerName, path: seed.path,
            result: unavailable.reason, currentButtons: unavailable.buttons, currentDialogs: unavailable.dialogs })
        }
        break
      }
      const dialog = opened.dialog
      const action = await findDialogAction(dialog, buttonName, occurrence)
      if (!action) {
        dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: seed.dialogName,
          button: buttonName, path: seed.path, result: 'not-present-after-state-change', currentButtons: await readDialogButtons(dialog) })
        addDialogSeed({ ...seed, buttons: await readDialogButtons(dialog) })
        continue
      }
      if (seed.dialogName === 'Move slides' && buttonName === 'Move') {
        dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: seed.dialogName,
          button: buttonName, path: seed.path, result: 'covered-by-library-lifecycle.spec.ts' })
        continue
      }
      if (!(await action.isEnabled())) {
        dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: seed.dialogName,
          button: buttonName, path: seed.path, result: 'disabled' })
        continue
      }
      if (/choose files/i.test(buttonName)) {
        const [chooser] = await Promise.all([
          page.waitForEvent('filechooser', { timeout: 5000 }),
          action.click({ timeout: 5000 }),
        ])
        dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: seed.dialogName,
          button: buttonName, path: seed.path, result: 'file-chooser-opened', multiple: chooser.isMultiple(),
          accept: await chooser.element().getAttribute('accept') })
        continue
      }
      await action.click({ timeout: 5000, noWaitAfter: true })
      await page.waitForTimeout(100)
      const state = await describeSurface()
      const closesDialog = /^(close\b|cancel$)/i.test(buttonName)
      if (closesDialog) await expect(dialog, `${buttonName} did not close ${seed.dialogName}`).toBeHidden()
      dialogButtonEvidence.push({ route: routes[seed.routeIndex]?.route ?? '*', dialog: seed.dialogName,
        button: buttonName, path: seed.path, result: 'clicked', state })

      const ancestorDialogs = new Set([seed.dialogName, ...seed.path.map((step) => step.dialogName)])
      for (const child of state.dialogs as Array<{ name: string; buttons: string[] }> ?? []) {
        if (!child.name || ancestorDialogs.has(child.name)) continue
        addDialogSeed({
          ...seed,
          dialogName: child.name,
          buttons: child.buttons,
          path: [...seed.path, { dialogName: seed.dialogName, buttonName, occurrence }],
        })
      }
    }
  }
  await testInfo.attach('dialog-button-exploration.json', {
    body: JSON.stringify({ discoveredDialogs: dialogSeeds.length, actions: dialogButtonEvidence }, null, 2),
    contentType: 'application/json',
  })
  expect(dialogButtonEvidence.filter((item) => item.result === 'clicked' || item.result === 'file-chooser-opened'
    || item.result === 'disabled').length, 'Dialog button exploration records').toBeGreaterThan(0)

  await testInfo.attach('route-menu-exploration.json', {
    body: JSON.stringify({ source: 'apps/web/src/App.tsx', visitedPatterns: routeEvidence.length, routes: routeEvidence,
      activationEvidence }, null, 2),
    contentType: 'application/json',
  })
  expect(routeEvidence, 'Route and library substate inventory').toHaveLength(31)
  expect(activationEvidence.filter((item) => item.result === 'click-error'), 'Button activation errors').toEqual([])
  expect(activationEvidence.filter((item) => item.result === 'control-label-changed'), 'Unexpected control label changes').toEqual([])
  expect(activationEvidence.filter((item) => item.result === 'not-reachable-after-prior-action')
    .every((item) => Array.isArray(item.currentButtons)), 'State-changed controls include the observed route state').toBe(true)
  expect(activationEvidence.filter((item) => !['clicked', 'disabled', 'disabled-menu-item', 'not-reachable-after-prior-action']
    .includes(String(item.result)) && !String(item.result).startsWith('covered-by-')),
  'Every route button and menu item has an exploration outcome').toEqual([])
  const changedDialogActions = dialogButtonEvidence.filter((item) => String(item.result).endsWith('after-state-change'))
  expect(changedDialogActions.every((item) => Array.isArray(item.currentButtons)),
    'State-changed dialog actions include their observed controls').toBe(true)
  expect(dialogButtonEvidence.filter((item) => !['clicked', 'disabled', 'file-chooser-opened']
    .includes(String(item.result)) && !String(item.result).endsWith('after-state-change')
    && !String(item.result).startsWith('covered-by-')),
  'Every discovered dialog action has an exploration outcome').toEqual([])
})

test('library navigator menus expose and exercise every folder, collection, and saved-view action', async ({ page }, testInfo) => {
  test.setTimeout(180_000)
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const suffix = Date.now().toString(36).toUpperCase().slice(-6)
  const parentName = `QA menu parent ${suffix}`
  const folderName = `QA menu folder ${suffix}`
  const renamedFolder = `${folderName} renamed`
  const collectionName = `QA menu collection ${suffix}`
  const renamedCollection = `${collectionName} renamed`
  const savedViewName = `QA menu view ${suffix}`
  const renamedSavedView = `${savedViewName} renamed`
  const evidence: Array<{ kind: string; trigger: string; items: string[]; exercised: string[] }> = []

  const createWithMenu = async (kind: 'folder' | 'collection' | 'saved view', name: string) => {
    await page.getByRole('button', { name: 'Create', exact: true }).click()
    await page.getByRole('menuitem', { name: `New ${kind}`, exact: true }).click()
    const dialog = page.getByRole('dialog', { name: `New ${kind}`, exact: true })
    await dialog.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
    await dialog.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(dialog).not.toBeVisible()
  }
  await createWithMenu('folder', parentName)
  await createWithMenu('folder', folderName)
  await createWithMenu('collection', collectionName)
  await createWithMenu('saved view', savedViewName)

  const openNavigator = async () => {
    const navigator = page.getByRole('complementary', { name: 'Library navigator', exact: true })
    if (!(await navigator.isVisible())) await page.getByRole('button', { name: 'Slide library', exact: true }).click()
    await expect(navigator).toBeVisible()
    return navigator
  }
  const navigator = await openNavigator()
  const inspectMenu = async (kind: string, trigger: ReturnType<typeof navigator.getByRole>, expected: string[]) => {
    await trigger.click()
    const menu = page.getByRole('menu').last()
    await expect(menu).toBeVisible()
    const items = (await menu.getByRole('menuitem').allTextContents())
      .map((item) => item.trim().replace(/\s+/g, ' ')).sort()
    expect(items, `${kind} menu items`).toEqual([...expected].sort())
    await page.keyboard.press('Escape')
    await expect(menu).toBeHidden()
    await expect(page.getByRole('complementary', { name: 'Library navigator', exact: true })).toBeVisible()
    await expect(trigger).toBeFocused()
    return items
  }
  const folderTrigger = (name: string) => navigator.getByRole('button', { name: `More actions for ${name}`, exact: true })
  const folderItems = await inspectMenu('Folder', folderTrigger(folderName), ['Move', 'Move to Trash', 'Rename'])
  evidence.push({ kind: 'folder', trigger: folderName, items: folderItems, exercised: [] })

  await folderTrigger(folderName).click()
  await page.getByRole('menuitem', { name: 'Rename', exact: true }).click()
  const folderRename = page.getByRole('dialog', { name: 'Rename folder', exact: true })
  await folderRename.getByRole('textbox', { name: 'Name', exact: true }).fill(renamedFolder)
  await folderRename.getByRole('button', { name: 'Save folder', exact: true }).click()
  await expect(folderRename).not.toBeVisible()
  await expect(navigator.getByRole('treeitem', { name: renamedFolder, exact: true })).toBeVisible()
  evidence[0].exercised.push('Rename: saved and visible in navigator')

  await folderTrigger(renamedFolder).click()
  await page.getByRole('menuitem', { name: 'Move', exact: true }).click()
  const moveFolder = page.getByRole('dialog', { name: 'Move folder', exact: true })
  await moveFolder.getByRole('combobox', { name: 'Parent folder', exact: true }).selectOption({ label: parentName })
  await moveFolder.getByRole('button', { name: 'Move folder', exact: true }).click()
  await expect(moveFolder).not.toBeVisible()
  const parent = navigator.getByRole('treeitem', { name: parentName, exact: true })
  const expandParent = parent.getByRole('button', { name: `Expand ${parentName}`, exact: true })
  if (await expandParent.isVisible()) await expandParent.click()
  const nestedFolder = navigator.getByRole('treeitem', { name: renamedFolder, exact: true })
  await expect(nestedFolder).toBeVisible()
  await expect(nestedFolder).toHaveAttribute('aria-level', '2')
  evidence[0].exercised.push('Move: nested under the selected parent')

  await folderTrigger(renamedFolder).click()
  await page.getByRole('menuitem', { name: 'Move to Trash', exact: true }).click()
  const trashFolder = page.getByRole('dialog', { name: 'Move folder to Trash', exact: true })
  await expect(trashFolder).toBeVisible()
  await trashFolder.getByRole('button', { name: 'Move folder to Trash', exact: true }).click()
  await expect(trashFolder).not.toBeVisible()
  await expect(navigator.getByRole('treeitem', { name: renamedFolder, exact: true })).toHaveCount(0)
  await page.reload()
  const refreshedNavigator = await openNavigator()
  await expect(refreshedNavigator.getByRole('treeitem', { name: renamedFolder, exact: true })).toHaveCount(0)
  evidence[0].exercised.push('Move to Trash: removed from the refreshed navigator')

  const collectionTrigger = () => refreshedNavigator.getByRole('button', { name: `More actions for ${collectionName}`, exact: true })
  const collectionItems = await inspectMenu('Collection', collectionTrigger(), ['Delete collection', 'Rename'])
  evidence.push({ kind: 'collection', trigger: collectionName, items: collectionItems, exercised: [] })
  await collectionTrigger().click()
  await page.getByRole('menuitem', { name: 'Rename', exact: true }).click()
  const collectionRename = page.getByRole('dialog', { name: 'Rename collection', exact: true })
  await collectionRename.getByRole('textbox', { name: 'Name', exact: true }).fill(renamedCollection)
  await collectionRename.getByRole('button', { name: 'Save name', exact: true }).click()
  await expect(collectionRename).not.toBeVisible()
  const renamedCollectionRow = () => refreshedNavigator.locator('.navigator-list-row').filter({ hasText: renamedCollection })
  await expect(renamedCollectionRow()).toBeVisible()
  evidence[1].exercised.push('Rename: saved and visible in navigator')
  await refreshedNavigator.getByRole('button', { name: `More actions for ${renamedCollection}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Delete collection', exact: true }).click()
  const deleteCollection = page.getByRole('dialog', { name: 'Delete collection', exact: true })
  await deleteCollection.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(deleteCollection).not.toBeVisible()
  await expect(renamedCollectionRow()).toHaveCount(0)
  evidence[1].exercised.push('Delete collection: removed from navigator')

  const savedViewTrigger = () => refreshedNavigator.getByRole('button', { name: `More actions for ${savedViewName}`, exact: true })
  const savedViewItems = await inspectMenu('Saved view', savedViewTrigger(), ['Delete saved view', 'Rename'])
  evidence.push({ kind: 'saved view', trigger: savedViewName, items: savedViewItems, exercised: [] })
  await savedViewTrigger().click()
  await page.getByRole('menuitem', { name: 'Rename', exact: true }).click()
  const savedViewRename = page.getByRole('dialog', { name: 'Rename saved view', exact: true })
  await savedViewRename.getByRole('textbox', { name: 'Name', exact: true }).fill(renamedSavedView)
  await savedViewRename.getByRole('button', { name: 'Save name', exact: true }).click()
  await expect(savedViewRename).not.toBeVisible()
  const renamedSavedViewRow = () => refreshedNavigator.locator('.navigator-list-row').filter({ hasText: renamedSavedView })
  await expect(renamedSavedViewRow()).toBeVisible()
  evidence[2].exercised.push('Rename: saved and visible in navigator')
  await refreshedNavigator.getByRole('button', { name: `More actions for ${renamedSavedView}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Delete saved view', exact: true }).click()
  const deleteSavedView = page.getByRole('dialog', { name: 'Delete saved view', exact: true })
  await deleteSavedView.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(deleteSavedView).not.toBeVisible()
  await expect(renamedSavedViewRow()).toHaveCount(0)
  evidence[2].exercised.push('Delete saved view: removed from navigator')

  await page.reload()
  const finalNavigator = await openNavigator()
  await expect(finalNavigator.getByRole('treeitem', { name: parentName, exact: true })).toBeVisible()
  await expect(finalNavigator.locator('.navigator-list-row').filter({ hasText: renamedCollection })).toHaveCount(0)
  await expect(finalNavigator.locator('.navigator-list-row').filter({ hasText: renamedSavedView })).toHaveCount(0)
  expect(evidence.every((item) => item.items.length === item.exercised.length)).toBe(true)
  await testInfo.attach('library-navigator-menu-exploration.json', {
    body: JSON.stringify(evidence, null, 2),
    contentType: 'application/json',
  })
})

test('course and class edit deep links save and reload synthetic changes', async ({ page }) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  const fixture = await createCourseAndClass(page, 'edit', true)
  await page.goto(fixture.coursePath)
  await page.getByRole('link', { name: 'Edit course', exact: true }).click()
  await expect(page.getByRole('textbox', { name: /Course name/ })).toHaveValue(fixture.courseName)
  await page.getByRole('textbox', { name: 'Description' }).fill('Updated on the synthetic route audit.')
  await page.getByRole('button', { name: 'Save course', exact: true }).click()
  await expect(page.locator('.assessment-course-detail-header')).toContainText('Updated on the synthetic route audit.')
  await page.reload()
  await expect(page.locator('.assessment-course-detail-header')).toContainText('Updated on the synthetic route audit.')

  await page.goto(`${fixture.coursePath}/classes/${fixture.classId}`)
  await page.getByRole('link', { name: 'Edit class', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Class name', exact: true })).toHaveValue(fixture.className)
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('Edited through the class deep link.')
  await page.getByRole('button', { name: 'Save class', exact: true }).click()
  await expect(page.getByRole('heading', { name: fixture.className, exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'Edit class', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Description', exact: true })).toHaveValue('Edited through the class deep link.')
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Description', exact: true })).toHaveValue('Edited through the class deep link.')
  await page.goto(fixture.coursePath)
  await expect(page.getByRole('heading', { name: fixture.courseName, exact: true })).toBeVisible()

  await page.goto(`${fixture.coursePath}/classes/${fixture.classId}`)
  await page.getByRole('button', { name: /Choose a slide folder/ }).click()
  const folderPicker = page.getByRole('dialog', { name: 'Choose a folder', exact: true })
  await folderPicker.getByRole('option', { name: new RegExp(fixture.folderName) }).click()
  await expect(folderPicker.getByRole('button', { name: 'Use this folder', exact: true })).toBeEnabled()
  await folderPicker.getByRole('button', { name: 'Use this folder', exact: true }).click()
  await expect(page.getByText(fixture.folderName, { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText(fixture.folderName, { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /Start classroom/ })).toBeVisible()
})
