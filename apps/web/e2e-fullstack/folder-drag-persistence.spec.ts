import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'

test.use({ trace: 'retain-on-failure' })

test('folder drag and accessible Move persist without a descendant cycle', async ({ page, isMobile }, info) => {
  await signIn(page, process.env.PATHLAB_E2E_USERNAME!, process.env.PATHLAB_E2E_PASSWORD!)
  for (let index = 0; index < 12; index += 1) {
    await page.getByLabel('Library command bar', { exact: true }).getByRole('button', { name: 'Create', exact: true }).click()
    await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
    const prior = page.getByRole('dialog', { name: 'New folder', exact: true })
    await prior.getByRole('textbox', { name: 'Name', exact: true }).fill(`A prior folder ${index}`)
    await prior.getByRole('button', { name: 'Create', exact: true }).click()
    await expect(prior).toBeHidden()
  }
  const names = [`QA drag source ${info.project.name}`, `QA drag parent ${info.project.name}`]
  const ids: string[] = []
  for (const name of names) {
    await page.getByLabel('Library command bar', { exact: true })
      .getByRole('button', { name: 'Create', exact: true }).click()
    await page.getByRole('menuitem', { name: 'New folder', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'New folder', exact: true })
    await dialog.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
    const created = page.waitForResponse((response) => response.request().method() === 'POST'
      && new URL(response.url()).pathname === '/api/v2/admin/folders')
    await dialog.getByRole('button', { name: 'Create', exact: true }).click()
    const response = await created
    expect(response.status()).toBe(201)
    const folder = await response.json()
    expect(folder.parentId).toBeNull()
    ids.push(folder.id)
    await expect(dialog).toBeHidden()
  }
  const tree = page.getByRole('tree', { name: 'Folders', exact: true })
  const source = tree.getByRole('treeitem', { name: names[0], exact: true })
  const parent = tree.getByRole('treeitem', { name: names[1], exact: true })
  async function openTree() {
    if (!await tree.isVisible()) await page.getByRole('button', { name: 'Slide library', exact: true }).click()
    await expect(parent).toBeVisible()
  }
  async function moveWithDialog(destination: string) {
    await source.getByRole('button', { name: `More actions for ${names[0]}`, exact: true }).click()
    await page.getByRole('menuitem', { name: 'Move', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Move folder', exact: true })
    await dialog.getByRole('combobox', { name: 'Parent folder', exact: true }).selectOption(destination)
    await dialog.getByRole('button', { name: 'Move folder', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  async function dragFolders(fromName: string, toName: string) {
    const from = tree.getByRole('treeitem', { name: fromName, exact: true }).locator('.folder-name')
    const to = tree.getByRole('treeitem', { name: toName, exact: true }).locator('.folder-name')
    await from.hover()
    const start = await from.boundingBox()
    if (!start) throw new Error('Folder has no native drag target')
    await page.mouse.down()
    // Start the native gesture before target actionability can scroll the drawer.
    // Otherwise the source can disappear underneath a stationary held pointer.
    await page.mouse.move(start.x + start.width / 2 + 12, start.y + start.height / 2, { steps: 4 })
    // Some engines emit dragover only after a second move onto the target.
    await to.hover()
    await to.hover()
    await page.mouse.up()
  }
  await openTree()
  await page.evaluate(() => {
    const events: unknown[] = []
    Object.assign(window, { __folderDragEvidence: events })
    for (const type of ['dragstart', 'dragenter', 'dragover', 'drop', 'dragend']) document.addEventListener(type, (event) => {
      const drag = event as DragEvent
      const row = (event.target as Element).closest('.folder-tree-row')
      if (!row || events.length >= 64) return
      events.push({ type, target: row.getAttribute('aria-label') || row.textContent,
        x: drag.clientX, y: drag.clientY, types: [...(drag.dataTransfer?.types ?? [])] })
    }, true)
  })
  const moved = page.waitForResponse((response) => response.request().method() === 'PATCH'
    && new URL(response.url()).pathname === `/api/v2/admin/folders/${ids[0]}`).catch(() => null)
  try {
    if (isMobile) await moveWithDialog(ids[1])
    else await dragFolders(names[0], names[1])
  } finally {
    const dragEvents = await page.evaluate(() => (window as unknown as { __folderDragEvidence: unknown[] }).__folderDragEvidence)
    await info.attach('native-drag-events.json', { body: JSON.stringify(dragEvents), contentType: 'application/json' })
    // Also retain the bounded synthetic gesture evidence in CI's diagnostic tail.
    console.info('Native folder drag events:', JSON.stringify(dragEvents))
  }
  const response = await moved
  if (!response) throw new Error('Folder gesture did not receive a server move acknowledgment')
  expect(response.status()).toBe(200)
  expect((await response.json()).parentId).toBe(ids[1])

  await page.reload()
  await openTree()
  await parent.getByRole('button', { name: `Expand ${names[1]}`, exact: true }).click()
  await expect(source).toHaveAttribute('aria-level', '2')
  await expect(parent).toHaveAttribute('aria-level', '1')
  const patchRequests: string[] = []
  page.on('request', (request) => {
    if (request.method() === 'PATCH' && new URL(request.url()).pathname.startsWith('/api/v2/admin/folders/')) {
      patchRequests.push(new URL(request.url()).pathname)
    }
  })
  if (!isMobile) await dragFolders(names[1], names[0])
  await parent.getByRole('button', { name: `More actions for ${names[1]}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Move', exact: true }).click()
  const parentMove = page.getByRole('dialog', { name: 'Move folder', exact: true })
  await expect(parentMove.getByRole('combobox', { name: 'Parent folder', exact: true })
    .getByRole('option', { name: names[0], exact: true })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(parentMove).toBeHidden()
  await expect(tree).toBeVisible()
  expect(patchRequests).toEqual([])
  await info.attach('folder-nested.png', { body: await page.screenshot(), contentType: 'image/png' })

  if (!isMobile) {
    const returned = page.waitForResponse((result) => result.request().method() === 'PATCH'
      && new URL(result.url()).pathname === `/api/v2/admin/folders/${ids[0]}`)
    await source.locator('.folder-name').hover()
    const from = await source.locator('.folder-name').boundingBox()
    if (!from) throw new Error('Nested folder has no native drag target')
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
    await page.mouse.down()
    await page.mouse.move(from.x + from.width / 2 + 12, from.y + from.height / 2, { steps: 4 })
    const topLevel = tree.getByText('Move to top level', { exact: true })
    await expect(topLevel).toBeVisible()
    // Scroll the native target into view while holding the actual drag.
    await topLevel.hover()
    await topLevel.hover()
    const to = await topLevel.boundingBox()
    const viewport = page.viewportSize()
    if (!to || !viewport || to.y < 0 || to.y + to.height > viewport.height) {
      throw new Error('Top-level native target is outside the viewport')
    }
    await page.mouse.up()
    const acknowledgment = await returned
    expect(acknowledgment.status()).toBe(200)
    expect((await acknowledgment.json()).parentId).toBeNull()
    await page.reload()
    await openTree()
    await expect(source).toHaveAttribute('aria-level', '1')
    await moveWithDialog(ids[1])
    await openTree()
    const expand = parent.getByRole('button', { name: `Expand ${names[1]}`, exact: true })
    if (await expand.isVisible()) await expand.click()
    await expect(source).toHaveAttribute('aria-level', '2')
  }
  await moveWithDialog('')
  await page.reload()
  await openTree()
  await expect(source).toHaveAttribute('aria-level', '1')
  await expect(parent).toHaveAttribute('aria-level', '1')
  await info.attach('folder-move-receipt.json', { body: JSON.stringify({
    engine: info.project.name, gesture: isMobile ? 'accessible Move' : 'native HTML5 drag',
    sourceId: ids[0], parentId: ids[1], nestedAfterReload: true,
    descendantDropBlocked: !isMobile, nativeTopLevelDrop: !isMobile,
    descendantMoveOmitted: true, dialogEscapePreservesNavigator: true, topLevelAfterReload: true,
  }), contentType: 'application/json' })
})
