import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const appSource = readFileSync('src/App.tsx', 'utf8')

describe('public viewer bootstrap contract', () => {
  it('lazy-loads the administrator application away from public routes', () => {
    expect(appSource).not.toContain("import { AdminPage } from './pages/AdminPage'")
    expect(appSource).toContain("import('./pages/AdminPage')")
  })
})
