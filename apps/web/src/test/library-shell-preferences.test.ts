import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getStoredRailExpanded,
  persistRailExpanded,
  RAIL_STORAGE_KEY,
} from '../components/library/libraryShellPreferences'

describe('library shell preferences', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('defaults to collapsed and restores an expanded rail', () => {
    expect(getStoredRailExpanded()).toBe(false)
    localStorage.setItem(RAIL_STORAGE_KEY, 'expanded')
    expect(getStoredRailExpanded()).toBe(true)
  })

  it('persists state without failing when storage is blocked', () => {
    persistRailExpanded(true)
    expect(localStorage.getItem(RAIL_STORAGE_KEY)).toBe('expanded')

    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked')
    })
    expect(() => persistRailExpanded(false)).not.toThrow()
  })
})
