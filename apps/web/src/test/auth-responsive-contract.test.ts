import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const themeCss = readFileSync('src/theme/theme.css', 'utf8')
const appCss = readFileSync('src/styles.css', 'utf8')

describe('mobile authentication control contract', () => {
  it('keeps compact theme choices at least 44 by 44 pixels', () => {
    const compactControl = themeCss.match(
      /\.theme-control--compact \.theme-control__option\s*\{([^}]*)\}/,
    )?.[1]

    expect(compactControl).toBeDefined()
    expect(compactControl).toMatch(/min-width:\s*44px/)
    expect(compactControl).toMatch(/min-height:\s*44px/)
  })

  it('stacks the brand and theme choices at narrow mobile widths', () => {
    expect(appCss).toMatch(
      /@media \(max-width:420px\)\s*\{[\s\S]*?\.auth-story-header\s*\{[^}]*flex-direction:\s*column/,
    )
    expect(appCss).toMatch(
      /@media \(max-width:420px\)\s*\{[\s\S]*?\.auth-theme-control\s*\{[^}]*align-self:\s*flex-start/,
    )
  })
})
