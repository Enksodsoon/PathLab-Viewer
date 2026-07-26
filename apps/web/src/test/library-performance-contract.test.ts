import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const libraryCss = readFileSync('src/library.css', 'utf8')

describe('library rendering performance contract', () => {
  it('avoids persistent blur layers and isolates off-screen slide cards', () => {
    expect(libraryCss).not.toContain('backdrop-filter:blur(14px)')
    expect(libraryCss).not.toContain('backdrop-filter:blur(8px)')
    expect(libraryCss).toContain('content-visibility:auto')
    expect(libraryCss).toContain('contain:layout paint style')
    expect(libraryCss).toContain('contain-intrinsic-size:')
  })

  it('keeps every representative mobile action at least 44 pixels tall', () => {
    const mobileStart = libraryCss.indexOf('@media (max-width: 600px)')
    const mobileEnd = libraryCss.indexOf('@media (max-width: 390px)')
    const mobileCss = libraryCss
      .slice(mobileStart, mobileEnd)
      .replace(/\s+/g, ' ')

    expect(mobileCss).toContain(
      '.library-breadcrumb-row > button { min-width: 44px; min-height: 44px; }',
    )
    expect(mobileCss).toContain(
      '.filter-panel-heading button, .filter-clear, .state-page-actions button, .load-more, .library-menu button, .library-menu a, .selection-action-bar button { min-width: 44px; min-height: 44px; }',
    )
  })
})
