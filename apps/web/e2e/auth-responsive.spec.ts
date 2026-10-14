import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })
test.setTimeout(90_000)

async function waitForAuthEntry(page: Page) {
  await expect(page.locator('.auth-form-panel')).toHaveCSS('opacity', '1')
  await expect(page.locator('.auth-form-content')).toHaveCSS('opacity', '1')
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ detail: { code: 'AUTHENTICATION_REQUIRED' } }),
  }))
})

test('persists theme choice and remains usable at every layout boundary', async ({ page }, testInfo) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await expect(page.getByRole('radio', { name: 'System' })).toBeChecked()
  await expect(page.locator('.auth-visual-image')).toHaveAttribute('data-auth-artwork-theme', 'dark')

  const initialArtwork = page.locator('.auth-visual-image')
  await expect.poll(() => initialArtwork.evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0)
  const initialVariant = (page.viewportSize()?.width ?? 1584) <= 767 ? 'mobile' : 'desktop'
  await expect.poll(() => initialArtwork.evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain(`auth-login-dark-${initialVariant}-v2.png`)

  await page.getByRole('radio', { name: 'Light' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.locator('.auth-visual-image')).toHaveAttribute('data-auth-artwork-theme', 'light')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await expect(page.getByRole('radio', { name: 'Light' })).toBeChecked()

  await page.getByRole('radio', { name: 'System' }).click()
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('.auth-visual-image')).toHaveAttribute('data-auth-artwork-theme', 'dark')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('.auth-visual-image')).toHaveAttribute('data-auth-artwork-theme', 'light')

  const viewports = [
    { width: 320, height: 844 },
    { width: 390, height: 844 },
    { width: 667, height: 375 },
    { width: 767, height: 1024 },
    { width: 768, height: 1024 },
    { width: 820, height: 1180 },
    { width: 940, height: 844 },
    { width: 941, height: 900 },
    { width: 1024, height: 768 },
    { width: 1280, height: 720 },
    { width: 1366, height: 768 },
    { width: 1439, height: 900 },
    { width: 1440, height: 900 },
    { width: 1584, height: 900 },
    { width: 1920, height: 1080 },
    { width: 2560, height: 1440 },
    { width: 3440, height: 1440 },
    { width: 3840, height: 2160 },
  ]
  for (const { width, height } of viewports) {
    await page.setViewportSize({ width, height })
    await expect(page.getByRole('heading', { name: 'A closer perspective.' })).toBeVisible()
    const titleLines = await page.locator('#auth-visual-title').evaluate((element) => {
      const range = document.createRange()
      range.selectNodeContents(element)
      return range.getClientRects().length
    })
    expect(titleLines, `title lines at ${width}px`).toBe(1)
    const artworkVariant = width <= 767 && width <= height
      ? 'mobile-v2'
      : width <= 1439 && width <= height
        ? 'tablet-portrait-v2'
        : width <= 1439
          ? 'tablet-landscape-v2'
      : 'desktop-v2'
    await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
      .toContain(`auth-login-light-${artworkVariant}.png`)
    const layout = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      formWidth: document.querySelector('.auth-form-panel')?.getBoundingClientRect().width ?? 0,
      visualWidth: document.querySelector('.auth-visual')?.getBoundingClientRect().width ?? 0,
    }))
    expect(layout.scrollWidth, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(layout.clientWidth)
    expect(layout.formWidth).toBeGreaterThan(0)
    expect(layout.visualWidth).toBeGreaterThan(0)
    if (testInfo.project.name === 'chromium' && (width === 320 || width === 1584 || width === 2560)) {
      await page.screenshot({ path: testInfo.outputPath(`login-light-${width}.png`), fullPage: true })
    }
  }
})

test('uses aligned v2 artwork for portrait and landscape themes', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })

  for (const theme of ['Light', 'Dark']) {
    await page.getByRole('radio', { name: theme }).click()
    await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
      .toContain(`auth-login-${theme.toLowerCase()}-mobile-v2.png`)
    await expect(page.locator('.auth-visual-image')).toHaveCSS('transform', 'none')
    const dimensions = await page.locator('.auth-visual-image').evaluate((image) => {
      const { naturalWidth, naturalHeight } = image as HTMLImageElement
      return { naturalWidth, naturalHeight }
    })
    expect(dimensions.naturalWidth).toBeGreaterThan(0)
    expect(dimensions.naturalHeight).toBeGreaterThan(dimensions.naturalWidth)
  }

  await page.setViewportSize({ width: 667, height: 375 })
  await page.getByRole('radio', { name: 'Dark' }).click()
  await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('dark-tablet-landscape-v2.png')
  await page.getByRole('radio', { name: 'Light' }).click()
  await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('light-tablet-landscape-v2.png')

  await page.setViewportSize({ width: 793, height: 794 })
  await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('light-tablet-portrait-v2.png')
  await expect(page.locator('.auth-visual-image')).toHaveCSS('transform', 'none')
  await page.getByRole('radio', { name: 'Dark' }).click()
  await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('dark-tablet-portrait-v2.png')
  await expect(page.locator('.auth-visual-image')).toHaveCSS('transform', 'none')
})

test('uses aligned v2 artwork at wide desktop sizes in both themes', async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1440 })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })

  const transforms: string[] = []
  for (const theme of ['Light', 'Dark']) {
    await page.getByRole('radio', { name: theme }).check()
    const image = page.locator('.auth-visual-image')
    await expect.poll(() => image.evaluate((element) => (element as HTMLImageElement).currentSrc))
      .toContain(`auth-login-${theme.toLowerCase()}-desktop-v2.png`)
    await expect.poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0)
    const transform = await image.evaluate((element) => getComputedStyle(element).transform)
    expect(transform).toBe('none')
    transforms.push(transform)
  }
  expect(transforms[1]).toBe(transforms[0])
})

test('matches the approved login copy, geometry, and focus behavior', async ({ page }) => {
  await page.setViewportSize({ width: 991, height: 794 })
  await page.goto('/admin')
  await waitForAuthEntry(page)

  const metrics = await page.evaluate(() => {
    const title = document.querySelector('#auth-visual-title')!
    const titleRange = document.createRange()
    titleRange.selectNodeContents(title)
    const button = document.querySelector('.auth-submit')!
    const icon = button.querySelector('svg')!
    const buttonBox = button.getBoundingClientRect()
    const iconBox = icon.getBoundingClientRect()
    return {
      title: title.textContent?.trim(),
      titleLines: titleRange.getClientRects().length,
      heading: document.querySelector('#auth-form-title')?.textContent?.trim(),
      description: document.querySelector('.auth-form-heading p')?.textContent?.trim(),
      labelSizes: [...document.querySelectorAll('.auth-field > label')].slice(0, 2)
        .map((label) => getComputedStyle(label).fontSize),
      arrowCenterError: Math.abs(
        (buttonBox.left + buttonBox.width / 2) - (iconBox.left + iconBox.width / 2),
      ),
    }
  })
  expect(metrics).toEqual({
    title: 'A closer perspective.',
    titleLines: 1,
    heading: 'Welcome back',
    description: 'Sign in to continue to your slides',
    labelSizes: ['15px', '15px'],
    arrowCenterError: 0,
  })

  const username = page.getByLabel('Username')
  const usernameField = page.locator('.auth-field').filter({ has: username }).locator('.auth-input')
  await username.click()
  await expect(usernameField).toHaveCSS('outline-style', 'none')
  await page.keyboard.press('Tab')
  const password = page.getByRole('textbox', { name: 'Password' })
  await expect(password).toBeFocused()
  const passwordField = page.locator('.auth-field').filter({ has: password }).locator('.auth-input')
  await expect(passwordField).toHaveCSS('outline-style', 'solid')

  await page.getByRole('radio', { name: 'Light' }).check()
  const lightOffset = await page.locator('.auth-visual-image').evaluate((image) => {
    const transform = getComputedStyle(image).transform
    const matrix = transform === 'none' ? new DOMMatrixReadOnly() : new DOMMatrixReadOnly(transform)
    return { horizontal: matrix.m41, vertical: matrix.m42 }
  })
  expect(await page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('light-tablet-landscape-v2.png')
  await page.getByRole('radio', { name: 'Dark' }).check()
  const darkOffset = await page.locator('.auth-visual-image').evaluate((image) => {
    const transform = getComputedStyle(image).transform
    const matrix = transform === 'none' ? new DOMMatrixReadOnly() : new DOMMatrixReadOnly(transform)
    return { horizontal: matrix.m41, vertical: matrix.m42 }
  })
  expect(await page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).currentSrc))
    .toContain('dark-tablet-landscape-v2.png')
  expect(darkOffset).toEqual(lightOffset)
  expect(darkOffset.horizontal).toBeGreaterThan(100)
  expect(darkOffset.vertical).toBe(0)
})

test('keeps recovery immediate, focused, and motion-safe', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })
  const animationName = await page.locator('.auth-visual-image').evaluate((element) => getComputedStyle(element).animationName)
  expect(animationName).toBe('none')

  await page.getByRole('button', { name: 'Forgot password?' }).click()
  await expect(page.getByRole('heading', { name: 'Recover administrator access' })).toBeFocused()
  await expect(page.getByLabel('Recovery code')).toBeVisible()
  await expect(page.getByLabel('New password', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Confirm new password', { exact: true })).toBeVisible()
  await expect(page.getByText('Ask your PathLab administrator for a 15-minute recovery code, then enter it below.')).toBeVisible()
  const operatorInstructions = page.getByText('PathLab administrator instructions', { exact: true })
  await expect(operatorInstructions).toBeVisible()
  await expect(page.getByText('docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin', { exact: true })).toBeHidden()
  await operatorInstructions.click()
  await expect(page.getByText('docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin', { exact: true })).toBeVisible()

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth)
})

test('keeps login and recovery accessible in both themes', async ({ page }, testInfo) => {
  await page.goto('/admin')
  for (const theme of ['Light', 'Dark']) {
    await page.setViewportSize({ width: 1584, height: 992 })
    await page.getByRole('radio', { name: theme }).check()
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme.toLowerCase())
    await expect(page.locator('.auth-visual-image')).toBeVisible()
    await expect.poll(() => page.locator('.auth-visual-image').evaluate((image) => (image as HTMLImageElement).naturalWidth))
      .toBeGreaterThan(0)
    await waitForAuthEntry(page)
    for (const [label, placeholder] of [['Username', 'admin'], ['Password', '••••••••']] as const) {
      const input = page.getByLabel(label, { exact: true })
      await expect(input).toHaveValue('')
      await expect(input).toHaveAttribute('placeholder', placeholder)
      expect(await input.evaluate((element) => getComputedStyle(element, '::placeholder').color))
        .toBe(theme === 'Light' ? 'rgb(109, 101, 94)' : 'rgb(170, 161, 154)')
    }
    if (testInfo.project.name === 'chromium') {
      await page.screenshot({ path: testInfo.outputPath(`login-${theme.toLowerCase()}-desktop.png`), fullPage: true })
    }
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])

    await page.setViewportSize({ width: 390, height: 844 })
    await waitForAuthEntry(page)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Forgot password?' }).click()
    await expect(page.getByRole('heading', { name: 'Recover administrator access' })).toBeFocused()
    await waitForAuthEntry(page)
    if (testInfo.project.name === 'chromium') {
      await page.screenshot({ path: testInfo.outputPath(`recovery-${theme.toLowerCase()}-mobile.png`), fullPage: true })
    }
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
    await page.getByRole('button', { name: 'Back to sign in' }).click()
  }
})

test('keeps sign-in usable when decorative artwork fails and in forced colors', async ({ page }) => {
  await page.route('**/auth-login-*.png', (route) => route.fulfill({ status: 404 }))
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByLabel('Username')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Password' })).toBeVisible()
  await expect(page.locator('.auth-visual-image')).toHaveCSS('visibility', 'hidden')

  await page.emulateMedia({ forcedColors: 'active' })
  await expect(page.locator('.auth-visual')).toHaveCSS('display', 'none')
  await expect(page.getByRole('button', { name: 'Enter workspace' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(await page.evaluate(() => document.documentElement.clientWidth))
})

test('keeps continuous motion below the long-task threshold', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'One desktop Chromium performance sample is sufficient.')
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 20_000 })

  const longTasks = await page.evaluate(() => new Promise<number[]>((resolve) => {
    const durations: number[] = []
    const observer = new PerformanceObserver((list) => {
      durations.push(...list.getEntries().map((entry) => entry.duration))
    })
    observer.observe({ type: 'longtask', buffered: false })
    window.setTimeout(() => {
      observer.disconnect()
      resolve(durations)
    }, 10_000)
  }))

  expect(longTasks.filter((duration) => duration > 50)).toEqual([])
})
