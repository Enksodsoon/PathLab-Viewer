import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ShareDialog } from '../components/library/ShareDialog'

const api = vi.hoisted(() => ({
  previewLibraryShare: vi.fn(),
  listLibraryShares: vi.fn(),
  createLibraryShare: vi.fn(),
  rotateLibraryShare: vi.fn(),
  revokeLibraryShare: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api')>(),
  ...api,
}))

beforeEach(() => {
  api.previewLibraryShare.mockResolvedValue({
    targetType: 'folder',
    targetId: 'folder-1',
    name: 'GI teaching set',
    description: '',
    included: [{ id: 'slide-1', displayName: 'Colon adenocarcinoma' }],
    excluded: [{ id: 'slide-2', displayName: 'Pending slide', reason: 'privacy_pending' }],
  })
  api.listLibraryShares.mockResolvedValue([])
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('share activation dialog', () => {
  it('previews safe membership and requires de-identification confirmation', async () => {
    api.createLibraryShare.mockResolvedValue({
      id: 'share-1',
      publicId: 'share-public',
      targetType: 'folder',
      targetId: 'folder-1',
      state: 'active',
      includeDescendants: false,
      autoIncludeNew: false,
      expiresAt: null,
      includedCount: 1,
      updatedAt: '2026-07-23T00:00:00Z',
    })
    render(<ShareDialog open targetType="folder" targetId="folder-1" targetName="GI teaching set" onClose={vi.fn()} />)

    expect(await screen.findByText('Colon adenocarcinoma')).toBeVisible()
    const create = screen.getByRole('button', { name: 'Create shared link' })
    expect(create).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /I confirm public names/i }))
    expect(create).toBeEnabled()
    await userEvent.click(create)

    expect(api.createLibraryShare).toHaveBeenCalledWith(expect.objectContaining({
      targetType: 'folder',
      targetId: 'folder-1',
      autoIncludeNew: false,
      slideIds: ['slide-1'],
      deidentifiedConfirmed: true,
    }))
    expect(await screen.findByDisplayValue(/\/f\/share-public$/)).toBeVisible()
  })

  it('reports link-management failures and confirms revocation', async () => {
    api.listLibraryShares.mockResolvedValue([{
      id: 'share-1',
      publicId: 'share-public',
      targetType: 'folder',
      targetId: 'folder-1',
      state: 'active',
      includeDescendants: false,
      autoIncludeNew: false,
      expiresAt: null,
      includedCount: 1,
      updatedAt: '2026-07-23T00:00:00Z',
    }])
    api.rotateLibraryShare.mockRejectedValue(new Error('offline'))
    render(<ShareDialog open targetType="folder" targetId="folder-1" targetName="GI teaching set" onClose={vi.fn()} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Rotate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/rotate.*failed/i)

    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    expect(screen.getByRole('button', { name: /confirm revoke/i })).toBeVisible()
    expect(api.revokeLibraryShare).not.toHaveBeenCalled()
  })
})
