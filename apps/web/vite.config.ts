import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const apiTarget = process.env.PATHLAB_DEV_API_URL ?? 'http://127.0.0.1:8000'
const phosphorImport = /import\s*\{\s*([^}]+)\s*\}\s*from\s*['"]@phosphor-icons\/react['"]/g

function directPhosphorImports() {
  return {
    name: 'pathlab:direct-phosphor-imports',
    enforce: 'pre' as const,
    transform(code: string, id: string) {
      const sourcePath = id.split('?', 1)[0]
      if (
        sourcePath.includes('/node_modules/')
        || !/\.[cm]?[jt]sx?$/.test(sourcePath)
        || !code.includes('@phosphor-icons/react')
      ) return null

      let changed = false
      const transformed = code.replace(phosphorImport, (original, specifierText: string) => {
        const specifiers = specifierText
          .split(',')
          .map((specifier) => specifier.trim())
          .filter(Boolean)
        const typeSpecifiers = specifiers.filter((specifier) => specifier.startsWith('type '))
        const runtimeSpecifiers = specifiers.filter((specifier) => !specifier.startsWith('type '))
        if (!runtimeSpecifiers.length) return original

        changed = true
        const imports = runtimeSpecifiers.map((specifier) => {
          const exportName = specifier.split(/\s+as\s+/, 1)[0]
          return `import { ${specifier} } from '@phosphor-icons/react/dist/csr/${exportName}'`
        })
        if (typeSpecifiers.length) {
          imports.push(
            `import type { ${typeSpecifiers.map((specifier) => specifier.slice(5)).join(', ')} } from '@phosphor-icons/react'`,
          )
        }
        return imports.join('\n')
      })

      return changed ? { code: transformed, map: null } : null
    },
  }
}

export default defineConfig({
  plugins: [directPhosphorImports(), react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  test: {
    environment: 'jsdom',
    include: ['src/test/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: './src/test/setup.ts',
    server: {
      deps: {
        inline: ['@phosphor-icons/react'],
      },
    },
  },
  server: {
    proxy: {
      '/api/v1/uploads': 'http://127.0.0.1:8080',
      '/api': apiTarget,
      '/livez': apiTarget,
      '/readyz': apiTarget,
      '/tiles': apiTarget,
    },
  },
})
