// @vitest-environment node

import { gzipSync } from 'node:zlib'
import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

import { afterEach, describe, expect, it } from 'vitest'

const script = resolve('scripts/check-annotation-bundle-budget.mjs')
const temporaryDirectories: string[] = []

function temporaryDirectory(name: string): string {
  const directory = mkdtempSync(join(tmpdir(), `${name}-`))
  temporaryDirectories.push(directory)
  return directory
}

function write(directory: string, path: string, content: string): void {
  const target = join(directory, path)
  mkdirSync(resolve(target, '..'), { recursive: true })
  writeFileSync(target, content)
}

function fixture(
  directory: string,
  {
    theme = 'theme',
    annotation = 'annotation',
    helper = 'helper',
    worker = 'worker',
  }: {
    theme?: string
    annotation?: string
    helper?: string
    worker?: string
  } = {},
): void {
  write(directory, 'index.html', [
    '<script src="/theme-init.js"></script>',
    '<script type="module" src="/assets/index.js"></script>',
    '<link rel="stylesheet" href="/assets/index.css">',
  ].join(''))
  write(directory, 'theme-init.js', theme)
  write(directory, 'assets/index.js', 'index')
  write(directory, 'assets/index.css', 'index-css')
  write(directory, 'assets/viewer.js', 'viewer')
  write(directory, 'assets/shared.js', 'shared')
  write(
    directory,
    'assets/annotation.js',
    `${annotation};new Worker(new URL("/assets/boolean.worker.js",import.meta.url))`,
  )
  write(directory, 'assets/helper.js', helper)
  write(directory, 'assets/dynamic-helper.js', 'dynamic helper')
  write(directory, 'assets/annotation.css', 'annotation-css')
  write(directory, 'assets/boolean.worker.js', worker)
  write(directory, '.vite/manifest.json', JSON.stringify({
    'index.html': {
      file: 'assets/index.js',
      src: 'index.html',
      isEntry: true,
      imports: ['_shared.js'],
      css: ['assets/index.css'],
    },
    '_shared.js': {
      file: 'assets/shared.js',
    },
    'src/pages/ViewerPage.tsx': {
      file: 'assets/viewer.js',
      src: 'src/pages/ViewerPage.tsx',
      isDynamicEntry: true,
      imports: ['index.html', '_shared.js'],
      dynamicImports: ['src/annotations/AnnotationWorkspace.tsx'],
    },
    'src/annotations/AnnotationWorkspace.tsx': {
      file: 'assets/annotation.js',
      src: 'src/annotations/AnnotationWorkspace.tsx',
      isDynamicEntry: true,
      imports: ['index.html', '_shared.js', '_helper.js'],
      dynamicImports: ['_dynamic-helper.js'],
      css: ['assets/annotation.css'],
    },
    '_helper.js': {
      file: 'assets/helper.js',
      imports: ['_shared.js'],
    },
    '_dynamic-helper.js': {
      file: 'assets/dynamic-helper.js',
    },
  }))
}

function run(current: string, baseline?: string) {
  return spawnSync(
    process.execPath,
    [
      script,
      '--dist',
      current,
      ...(baseline ? ['--baseline', baseline] : []),
    ],
    { encoding: 'utf8' },
  )
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

describe('annotation bundle budget', () => {
  it('fails closed when the real baseline is unavailable', () => {
    const current = temporaryDirectory('annotation-bundle-current')
    fixture(current)

    const result = run(current)

    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/--baseline is required/i)
  })

  it('includes theme-init and every incremental annotation asset', () => {
    const baseline = temporaryDirectory('annotation-bundle-baseline')
    const current = temporaryDirectory('annotation-bundle-current')
    fixture(baseline, { theme: '' })
    fixture(current, {
      theme: 'changed theme',
      annotation: 'annotation entry',
      helper: 'transitive helper',
      worker: 'boolean worker',
    })

    const result = run(current, baseline)
    expect(result.status).toBe(0)
    const report = JSON.parse(result.stdout) as {
      currentInitialGzipBytes: number
      baselineInitialGzipBytes: number
      publicInitialGzipDeltaBytes: number
      annotationLazyRawBytes: number
      annotationAssets: Array<{ name: string; rawBytes: number }>
    }

    const baselineInitial = ['index', 'index-css', ''].reduce(
      (total, content) => total + gzipSync(content, { level: 9 }).byteLength,
      0,
    )
    const currentInitial = ['index', 'index-css', 'changed theme'].reduce(
      (total, content) => total + gzipSync(content, { level: 9 }).byteLength,
      0,
    )
    expect(report.baselineInitialGzipBytes).toBe(baselineInitial)
    expect(report.currentInitialGzipBytes).toBe(currentInitial)
    expect(report.publicInitialGzipDeltaBytes).toBe(
      currentInitial - baselineInitial,
    )
    expect(report.annotationAssets.map((asset) => asset.name).sort()).toEqual([
      'assets/annotation.css',
      'assets/annotation.js',
      'assets/boolean.worker.js',
      'assets/dynamic-helper.js',
      'assets/helper.js',
    ])
    expect(report.annotationLazyRawBytes).toBe(
      'annotation entry'.length +
      ';new Worker(new URL("/assets/boolean.worker.js",import.meta.url))'.length +
      'transitive helper'.length +
      'annotation-css'.length +
      'boolean worker'.length +
      'dynamic helper'.length,
    )
  })

  it('rejects a total lazy payload over 300 KiB even when each chunk is smaller', () => {
    const baseline = temporaryDirectory('annotation-bundle-baseline')
    const current = temporaryDirectory('annotation-bundle-current')
    fixture(baseline)
    fixture(current, {
      annotation: 'a'.repeat(180 * 1024),
      helper: 'b'.repeat(130 * 1024),
    })

    const result = run(current, baseline)

    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/total annotation lazy payload/i)
  })
})
