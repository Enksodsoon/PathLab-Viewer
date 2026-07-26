// @vitest-environment node

import { readFileSync } from 'node:fs'

import { build, type Rollup } from 'vite'
import { describe, expect, it } from 'vitest'

const adminSource = readFileSync('src/pages/AdminPage.tsx', 'utf8')
const authSource = readFileSync('src/components/AuthPanel.tsx', 'utf8')
const securitySource = readFileSync('src/components/AccountSecurityDialog.tsx', 'utf8')
const styles = readFileSync('src/styles.css', 'utf8')

function outputChunks(result: Awaited<ReturnType<typeof build>>) {
  const outputs = (Array.isArray(result) ? result : [result]) as Rollup.RollupOutput[]
  return outputs.flatMap(({ output }) => output)
    .filter((entry): entry is Rollup.OutputChunk => entry.type === 'chunk')
}

function moduleIds(chunk: Rollup.OutputChunk) {
  return Object.keys(chunk.modules).map((id) => id.replaceAll('\\', '/'))
}

describe('authentication performance contract', () => {
  it('keeps GSAP in the lazy unauthorized authentication surface', () => {
    expect(adminSource).toContain("lazy(() => import('../components/AuthPanel')")
    expect(adminSource).toContain("from '../components/AccountSecurityDialog'")
    expect(adminSource).not.toContain("from '../components/AuthPanels'")
    expect(authSource).toContain("from '@gsap/react'")
    expect(authSource).toContain("from 'gsap'")
    expect(securitySource).not.toMatch(/@gsap\/react|from 'gsap'/)
  })

  it('keeps the authored entrance visible by default and bypasses reduced motion', () => {
    const reducedMotionCheck = authSource.indexOf("matchMedia('(prefers-reduced-motion: reduce)')")
    const timelineCreation = authSource.indexOf('gsap.timeline(')

    expect(reducedMotionCheck).toBeGreaterThan(-1)
    expect(timelineCreation).toBeGreaterThan(reducedMotionCheck)
    expect(authSource).toContain("ease: 'expo.out'")
    expect(authSource).toContain('timeline.kill()')
    expect(styles).not.toMatch(/\.auth-(?:story|panel)[^{]*\{[^}]*opacity:\s*0/s)
  })

  it('excludes GSAP from the built authorized admin dependency graph', async () => {
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
    const gsapChunks = chunks.filter((chunk) => (
      moduleIds(chunk).some((id) => /\/node_modules\/(?:@gsap\/react|gsap)\//.test(id))
    ))

    expect(adminChunk).toBeDefined()
    expect(authChunk).toBeDefined()
    expect(gsapChunks.length).toBeGreaterThan(0)

    const byFileName = new Map(chunks.map((chunk) => [chunk.fileName, chunk]))
    const staticClosure = (root: Rollup.OutputChunk) => {
      const seen = new Set<string>()
      const visit = (chunk: Rollup.OutputChunk) => {
        if (seen.has(chunk.fileName)) return
        seen.add(chunk.fileName)
        chunk.imports.forEach((fileName) => {
          const imported = byFileName.get(fileName)
          if (imported) visit(imported)
        })
      }
      visit(root)
      return seen
    }

    const adminStaticFiles = staticClosure(adminChunk!)
    const authStaticFiles = staticClosure(authChunk!)
    expect(gsapChunks.every((chunk) => !adminStaticFiles.has(chunk.fileName))).toBe(true)
    expect(gsapChunks.every((chunk) => authStaticFiles.has(chunk.fileName))).toBe(true)
  }, 30_000)
})
