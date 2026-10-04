// SPDX-License-Identifier: Apache-2.0
// Observe compiled graphs without changing application imports or build options.
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const argv = process.argv.slice(2)
const argument = name => {
  const index = argv.indexOf(name)
  return index === -1 ? undefined : argv[index + 1]
}
const subject = argument('--subject')
if (!/^[0-9a-f]{40}$/.test(subject ?? '')) throw Error('An immutable --subject is required')
const python = argument('--python') ?? 'python'
const command = args => execFileSync(python, ['-m', 'scripts.browser_distribution', ...args], { cwd: root, encoding: 'utf8' })
const before = JSON.parse(command(['inputs', '--subject', subject]))
const output = join(root, 'var', `browser-distribution-${subject.slice(0, 7)}-${Date.now()}`)
if (existsSync(output)) throw Error('Refuse to replace an existing qualification directory')
mkdirSync(output, { recursive: true })
const normalizeId = id => {
  const value = id.replaceAll('\\', '/')
  const boundary = value.indexOf('/node_modules/')
  if (boundary !== -1) return (value.startsWith('\0') ? '\0' : '') + value.slice(boundary + 1)
  return value.replaceAll(root.replaceAll('\\', '/') + '/', '')
}
const graphs = []
function observe(role) {
  return {
    name: `pathlab-observe-${role}`,
    generateBundle(_options, bundle) {
      const chunks = Object.values(bundle).filter(item => item.type === 'chunk').map(chunk => ({
        fileName: chunk.fileName,
        entry: chunk.facadeModuleId ? normalizeId(chunk.facadeModuleId) : null,
        modules: [...new Set(Object.keys(chunk.modules).map(normalizeId))].sort(),
      })).sort((a, b) => a.fileName.localeCompare(b.fileName))
      graphs.push({ role, modules: [...new Set([...this.getModuleIds()].map(normalizeId))].sort(), chunks })
    },
  }
}
const require = createRequire(join(root, 'apps/web/package.json'))
const { build } = await import(pathToFileURL(join(dirname(require.resolve('vite/package.json')), 'dist/node/index.js')).href)
await build({
  root: join(root, 'apps/web'), configFile: join(root, 'apps/web/vite.config.ts'),
  plugins: [observe('main')], worker: { plugins: () => [observe('worker')] },
  build: { outDir: join(output, 'dist'), emptyOutDir: false, manifest: true },
})
const after = JSON.parse(command(['inputs', '--subject', subject]))
if (JSON.stringify(before) !== JSON.stringify(after)) throw Error('Build inputs changed during qualification')
const assets = []
function walk(directory) {
  for (const name of readdirSync(directory).sort()) {
    const path = join(directory, name)
    if (lstatSync(path).isSymbolicLink()) throw Error('Refuse linked build output')
    if (statSync(path).isDirectory()) walk(path)
    else assets.push({
      path: relative(join(output, 'dist'), path).replaceAll('\\', '/'),
      bytes: statSync(path).size,
      sha256: createHash('sha256').update(readFileSync(path)).digest('hex'),
    })
  }
}
walk(join(output, 'dist'))
graphs.sort((a, b) => JSON.stringify(a.chunks).localeCompare(JSON.stringify(b.chunks)))
const usesOrt = graphs.some(graph => graph.modules.some(id => id.includes('/node_modules/onnxruntime-web/')))
const ortDist = usesOrt ? dirname(require.resolve('onnxruntime-web/wasm')) : null
const prebuiltInputs = ortDist ? ['ort.wasm.bundle.min.mjs', 'ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.wasm'].map(name => {
  const bytes = readFileSync(join(ortDist, name))
  return { path: `dist/${name}`, sha256: createHash('sha256').update(bytes).digest('hex'), bytes: bytes.length }
}).sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0) : []
const receipt = {
  ...before, sourceSnapshotStableDuringBuild: true, graphs, emittedAssets: assets, prebuiltInputs,
  scope: 'Current compiled browser only; source notice blockers and admission remain unchanged',
}
const receiptPath = join(output, 'receipt.json')
writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n')
command(['verify', '--receipt', receiptPath, '--dist', join(output, 'dist')])
console.log(JSON.stringify({ subject, graphCount: graphs.length, assetCount: assets.length, receiptPath }))
