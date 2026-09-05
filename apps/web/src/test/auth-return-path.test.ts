import { describe, expect, it } from 'vitest'

import { adminSignInPath, safeAdminReturnPath } from '../authReturnPath'

describe('administrator return paths', () => {
  it('preserves a private same-origin admin route', () => {
    expect(adminSignInPath('/admin/preview/private-1?mode=review#mark')).toBe(
      '/admin?returnTo=%2Fadmin%2Fpreview%2Fprivate-1%3Fmode%3Dreview%23mark',
    )
    expect(safeAdminReturnPath('/admin/classroom')).toBe('/admin/classroom')
  })

  it.each([
    'https://example.test/admin/preview/private-1',
    '//example.test/admin/preview/private-1',
    '/\\example.test/admin/preview/private-1',
    '/study',
  ])('rejects unsafe or non-admin return path %s', (value) => {
    expect(safeAdminReturnPath(value)).toBeNull()
    expect(adminSignInPath(value)).toBe('/admin')
  })
})
