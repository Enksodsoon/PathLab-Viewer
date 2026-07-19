import { readFileSync } from 'node:fs'

import { describe, expect, test } from 'vitest'

describe('Vite commands', () => {
  test('always load the authoritative TypeScript config', () => {
    const packageJson = JSON.parse(
      readFileSync('package.json', 'utf8'),
    ) as { scripts: Record<string, string> }

    expect(packageJson.scripts.dev).toContain('--config vite.config.ts')
    expect(packageJson.scripts.build).toContain('vite build --config vite.config.ts')
  })
})
