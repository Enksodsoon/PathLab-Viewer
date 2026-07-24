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
})
