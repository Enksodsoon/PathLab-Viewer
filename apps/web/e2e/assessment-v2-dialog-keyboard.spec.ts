import { expect, test } from '@playwright/test'

const draft = {
  id: 'section-dialog-qa', revision: 1, status: 'draft', title: 'Synthetic sectioned assessment',
  document: {
    schema: 'pathlab.assessment/2', title: 'Synthetic sectioned assessment',
    presentation: { preset: 'standard', showProgress: true, showSectionTitles: true },
    settings: { mode: 'formative' },
    sections: [{ id: 'section-1', title: 'Synthetic section', items: [{
      id: 'question-1', type: 'multiple-choice', prompt: 'Synthetic question', required: true, points: '1',
      options: [{ id: 'option-1', label: 'Option one' }, { id: 'option-2', label: 'Option two' }],
      answerKey: { optionIds: ['option-1'] },
    }] }],
  },
}

for (const action of ['preview', 'import'] as const) {
  test(`sectioned ${action} returns to a connected trigger at 320px`, async ({ page }) => {
    let unexpectedWrites = 0
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path.endsWith('/preview')) return route.fulfill({ json: { learnerManifest: draft.document, checksum: 'synthetic' } })
      if (request.method() !== 'GET') { unexpectedWrites++; return route.fulfill({ status: 500, json: { detail: { code: 'UNEXPECTED_QA_WRITE' } } }) }
      if (path === '/api/v1/auth/session') return route.fulfill({ json: { csrfToken: 'synthetic-csrf' } })
      if (path.endsWith('/drafts/section-dialog-qa')) return route.fulfill({ json: draft })
      if (path.endsWith('/drafts')) return route.fulfill({ json: { items: [draft], total: 1 } })
      if (path.endsWith('/templates')) return route.fulfill({ json: { items: [] } })
      if (path === '/api/v2/admin/library/navigation') return route.fulfill({ json: {
        capabilities: { classroom: false, study: false, assessment: true },
        counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
        folders: [], collections: [], savedViews: [],
        storage: { usedBytes: 0, usableBytes: 1000, effectiveCapacityBytes: 1000 },
      } })
      return route.fulfill({ status: 404, json: { detail: { code: 'QA_ROUTE_NOT_FOUND' } } })
    })
    await page.setViewportSize({ width: 320, height: 568 })
    await page.goto('/admin/assessments/section-dialog-qa')
    await expect(page.getByText('All changes saved', { exact: true })).toBeVisible()
    const opener = page.getByRole('button', { name: action === 'preview' ? 'Assignment preview' : 'Templates & import', exact: true })
    await opener.click()
    if (action === 'import') await page.getByRole('button', { name: 'Choose assessment', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: action === 'preview' ? 'Learner preview' : 'Import assessment', exact: true })
    await expect(dialog).toBeVisible()
    if (action === 'preview') await expect(dialog.getByText('Synthetic question', { exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
    expect(unexpectedWrites).toBe(0)
  })
}
