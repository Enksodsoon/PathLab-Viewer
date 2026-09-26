import { describe, expect, it } from 'vitest'
import { ignoresShortcut, isNestedControl, readLibraryContext } from '../components/library/viewerNavigation'

describe('library viewer navigation boundaries', () => {
  it('ignores editable elements including editable ancestors', () => {
    const editor = document.createElement('div'); editor.setAttribute('contenteditable', 'true')
    const child = document.createElement('span'); editor.append(child)
    expect(ignoresShortcut(child)).toBe(true)
    expect(ignoresShortcut(document.createElement('input'))).toBe(true)
    expect(ignoresShortcut(document.createElement('button'))).toBe(false)
  })
  it('does not treat nested checkbox or action controls as card activation', () => {
    const card = document.createElement('article'); const button = document.createElement('button'); const icon = document.createElement('span'); button.append(icon); card.append(button)
    expect(isNestedControl(icon, card)).toBe(true)
    expect(isNestedControl(card, card)).toBe(false)
  })
  it('accepts supplied library context but refuses external return routes', () => {
    expect(readLibraryContext({ library: { returnTo: '//evil.test', slides: [] } })).toBeNull()
    expect(readLibraryContext({ library: { returnTo: '/admin/preview/private', slides: [] } })).toBeNull()
    expect(readLibraryContext({ library: { returnTo: '/admin?folder=one&q=kidney', slides: [{ id: 'a', displayName: 'A' }, {}] } })).toEqual({ returnTo: '/admin?folder=one&q=kidney', slides: [{ id: 'a', displayName: 'A' }] })
  })
})
