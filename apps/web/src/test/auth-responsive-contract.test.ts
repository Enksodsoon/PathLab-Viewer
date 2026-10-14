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

  it('keeps the phone layout fluid and the theme control available', () => {
    expect(authCss).toMatch(
      /@media \(max-width:767px\)\s*\{[\s\S]*?\.auth-layout\s*\{[^}]*padding-inline:24px/,
    )
    expect(authCss).toMatch(
      /@media \(max-width:767px\)\s*\{[\s\S]*?\.auth-form-wrap\s*\{[^}]*width:min\(460px,100%\)/,
    )
    expect(authCss).toMatch(
      /@media \(max-width:520px\)\s*\{[\s\S]*?\.auth-panel-header\s*\{[^}]*padding:18px/,
    )
  })
})
