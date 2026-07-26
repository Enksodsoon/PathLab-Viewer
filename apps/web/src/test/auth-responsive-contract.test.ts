import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const themeCss = readFileSync('src/theme/theme.css', 'utf8')
const authCss = readFileSync('src/auth.css', 'utf8')

describe('mobile authentication control contract', () => {
  it('keeps compact theme choices at least 44 by 44 pixels', () => {
    const compactControl = themeCss.match(
      /\.theme-control--compact \.theme-control__option\s*\{([^}]*)\}/,
    )?.[1]

    expect(compactControl).toBeDefined()
    expect(compactControl).toMatch(/min-width:\s*44px/)
    expect(compactControl).toMatch(/min-height:\s*44px/)
    expect(authCss).toMatch(
      /\.auth-panel-header \.theme-control__option\s*\{[^}]*min-width:44px[^}]*min-height:44px/,
    )
  })

  it('collapses the split authentication layout without hiding the theme control', () => {
    expect(authCss).toMatch(
      /@media \(max-width:940px\)\s*\{[\s\S]*?\.auth-layout\s*\{[^}]*grid-template-columns:1fr/,
    )
    expect(authCss).toMatch(
      /@media \(max-width:520px\)\s*\{[\s\S]*?\.auth-panel-header\s*\{[^}]*padding:18px/,
    )
  })
})
