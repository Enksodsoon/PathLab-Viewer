// @vitest-environment node

import { readFileSync } from 'node:fs'

import { build, type Rollup } from 'vite'
import { describe, expect, it } from 'vitest'

const adminSource = readFileSync('src/pages/AdminPage.tsx', 'utf8')
const authSource = readFileSync('src/components/AuthPanel.tsx', 'utf8')
const securitySource = readFileSync('src/components/AccountSecurityDialog.tsx', 'utf8')
const authStyles = readFileSync('src/auth.css', 'utf8')

function outputChunks(result: Awaited<ReturnType<typeof build>>) {
  const outputs = (Array.isArray(result) ? result : [result]) as Rollup.RollupOutput[]
  return outputs.flatMap(({ output }) => output)
    .filter((entry): entry is Rollup.OutputChunk => entry.type === 'chunk')
}

function moduleIds(chunk: Rollup.OutputChunk) {
  return Object.keys(chunk.modules).map((id) => id.replaceAll('\\', '/'))
}

describe('authentication performance contract', () => {
  it('keeps authentication lazy and free of a runtime animation dependency', () => {
    expect(adminSource).toContain("lazy(() => import('../components/AuthPanel')")
    expect(adminSource).toContain("from '../components/AccountSecurityDialog'")
    expect(adminSource).not.toContain("from '../components/AuthPanels'")
    expect(authSource).not.toMatch(/@gsap\/react|from 'gsap'|framer-motion/)
    expect(securitySource).not.toMatch(/@gsap\/react|from 'gsap'|framer-motion/)
  })

  it('uses lightweight CSS motion with a reduced-motion bypass', () => {
    expect(authStyles).toContain('@keyframes auth-panel-enter')
    expect(authStyles).toContain('@keyframes auth-form-enter')
    expect(authStyles).toContain('@media (prefers-reduced-motion:reduce)')
    expect(authStyles).toMatch(/prefers-reduced-motion:reduce[\s\S]*animation:none!important/)
  })

  it('keeps the unauthorized authentication surface out of the authorized admin chunk', async () => {
    const chunks = outputChunks(await build({
      configFile: 'vite.config.ts',
      logLevel: 'silent',
      build: { write: false },
    }))
    const adminChunk = chunks.find((chunk) => (
      moduleIds(chunk).some((id) => id.endsWith('/src/pages/AdminPage.tsx'))
    ))
    const authChunk = chunks.find((chunk) => (
      moduleIds(chunk).some((id) => id.endsWith('/src/components/AuthPanel.tsx'))
    ))

    expect(adminChunk).toBeDefined()
    expect(authChunk).toBeDefined()
    expect(adminChunk?.fileName).not.toBe(authChunk?.fileName)
    expect(adminChunk?.imports).not.toContain(authChunk?.fileName)
  }, 30_000)
})
