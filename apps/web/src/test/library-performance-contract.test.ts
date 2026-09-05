import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const normalizeNewlines = (source: string) => source.replace(/\r\n/g, '\n')
const libraryCss = normalizeNewlines(readFileSync('src/library.css', 'utf8'))
const globalCss = normalizeNewlines(readFileSync('src/styles.css', 'utf8'))

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
      '.library-breadcrumb-row nav button { min-width: 44px; min-height: 44px; }',
    )
    expect(mobileCss).toContain(
      '.filter-panel-heading button, .filter-clear, .state-page-actions button, .load-more, .library-menu button, .library-menu a, .selection-action-bar button { min-width: 44px; min-height: 44px; }',
    )
  })

  it('uses neutral black elevation shadows in every theme', () => {
    expect(libraryCss).not.toMatch(/box-shadow:[^;]*var\(--ink\)/)
    expect(libraryCss).toContain('var(--shadow-color)')
  })

  it('keeps the selection toolbar on the active theme surface', () => {
    const selectionCss = libraryCss.slice(
      libraryCss.indexOf('.selection-action-bar {'),
      libraryCss.indexOf('/* Right overlay inspector */'),
    )

    expect(selectionCss).toContain(
      'background: color-mix(in srgb, var(--surface-elevated) 94%, var(--primary));',
    )
    expect(selectionCss).toContain('border: 1px solid var(--border);')
    expect(selectionCss).toContain('color: var(--ink);')
    expect(selectionCss).toContain('color: var(--body);')
    expect(selectionCss).not.toContain('background: var(--ink);')
    expect(selectionCss).not.toContain('color: var(--canvas);')
  })

  it('dims the open navigator with a dark neutral backdrop', () => {
    expect(libraryCss).toContain(
      'background: color-mix(in srgb, var(--shadow-color) 58%, transparent);',
    )
    expect(libraryCss).not.toContain(
      'background: color-mix(in srgb, var(--ink) 38%, transparent);',
    )
  })

  it('uses dark neutral backdrops and shadows for dialogs in every theme', () => {
    expect(libraryCss).toContain(
      '.library-dialog::backdrop {\n  background: color-mix(in srgb, var(--shadow-color) 58%, transparent);',
    )
    expect(globalCss).toContain(
      'background:color-mix(in srgb,var(--shadow-color) 58%,transparent);',
    )
    expect(globalCss).toContain(
      'box-shadow:0 24px 70px color-mix(in srgb,var(--shadow-color) 48%,transparent);',
    )
    expect(globalCss).not.toContain(
      'background:color-mix(in srgb,var(--ink) 52%,transparent);',
    )
  })

  it('uses the theme primary color for the shared motion-safe loader', () => {
    expect(globalCss).toContain(
      '.pathlab-loader { --pathlab-loader-size:32px;',
    )
    expect(globalCss).toContain('color:var(--primary);')
    expect(globalCss).toContain('stroke:currentColor;')
    expect(globalCss).toContain('@keyframes pathlab-loader-boxes')
    expect(globalCss).toContain(
      '.pathlab-loader__boxes {\n    animation:none;',
    )
  })

  it('keeps the navigator close control compact on desktop and touch-safe on mobile', () => {
    const closeControl = libraryCss
      .slice(
        libraryCss.indexOf('.mobile-navigator-close {'),
        libraryCss.indexOf('.library-navigator {'),
      )
      .replace(/\s+/g, ' ')
    const mobileCss = libraryCss
      .slice(libraryCss.indexOf('@media (max-width: 600px)'))
      .replace(/\s+/g, ' ')

    expect(closeControl).toContain('width: 32px; height: 32px;')
    expect(closeControl).toContain('right: 20px;')
    expect(libraryCss).toContain('scrollbar-gutter: stable;')
    expect(mobileCss).toContain('.mobile-navigator-close { width: 44px; height: 44px; }')
  })
})
