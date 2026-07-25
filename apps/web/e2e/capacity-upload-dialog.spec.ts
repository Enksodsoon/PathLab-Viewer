import { expect, test } from '@playwright/test'

import { capacityUploadDialog } from '../e2e-live/capacity-helpers'

test('capacity upload fields stay scoped when closed dialogs remain mounted', async ({ page }) => {
  await page.setContent(`
    <dialog open aria-labelledby="upload-title">
      <h2 id="upload-title">Upload OME-TIFF</h2>
      <label>Display name<input value=""></label>
    </dialog>
    <dialog aria-labelledby="edit-title">
      <h2 id="edit-title">Edit slide details</h2>
      <label>Display name<input value="Existing slide"></label>
    </dialog>
  `)

  const upload = capacityUploadDialog(page)
  await upload.getByLabel('Display name', { exact: true }).fill('Synthetic fixture')

  await expect(upload.getByLabel('Display name', { exact: true })).toHaveValue(
    'Synthetic fixture',
  )
  await expect(page.locator('dialog:not([open]) input')).toHaveValue('Existing slide')
})
