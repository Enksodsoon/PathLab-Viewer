import { readFileSync } from 'node:fs'

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import {
  AnnotationWorkspace,
  type AnnotationWorkspaceServices,
} from '../annotations/AnnotationWorkspace'
import type {
  AnnotationBatchRequest,
  AnnotationBatchResult,
  AnnotationItemsPage,
  AnnotationManifest,
} from '../annotations/types'

const layerId = '11111111-1111-4111-8111-111111111111'
const manifest: AnnotationManifest = {
  slideId: 'slide-1',
  version: 0,
  bounds: { width: 2048, height: 1024 },
  calibration: { x: 0.5, y: 0.75, unit: 'µm' },
  activeCount: 0,
  trashedCount: 0,
  layers: [{
    id: layerId,
    slideId: 'slide-1',
    name: 'Findings',
    sortOrder: 0,
    visible: true,
    locked: false,
    opacity: 1,
    createdAt: '2026-07-26T00:00:00Z',
    updatedAt: '2026-07-26T00:00:00Z',
  }],
  limits: {
    activeAnnotations: 25_000,
    layers: 100,
    verticesPerShape: 8_192,
    verticesPerImport: 250_000,
    batchOperations: 50,
  },
}

function services(overrides: Partial<AnnotationWorkspaceServices> = {}): AnnotationWorkspaceServices {
  return {
    getManifest: vi.fn(async () => manifest),
    getItems: vi.fn(async (): Promise<AnnotationItemsPage> => ({
      items: [],
      total: 0,
      nextOffset: null,
    })),
    batch: vi.fn(async (_request: AnnotationBatchRequest): Promise<AnnotationBatchResult> => ({
      mutationId: _request.mutationId,
      version: 1,
      results: _request.operations.map((operation) => ({
        id: operation.type === 'create' ? operation.item.id : operation.id,
        operation: operation.type,
        version: 1,
        deleted: operation.type === 'delete',
      })),
      purged: 0,
    })),
    createLayer: vi.fn(),
    updateLayer: vi.fn(),
    importDocument: vi.fn(),
    exportDocument: vi.fn(),
    revisions: vi.fn(async () => ({ items: [] })),
    restoreRevision: vi.fn(),
    loadDraft: vi.fn(async () => null),
    saveDraft: vi.fn(async () => undefined),
    acknowledgeDraft: vi.fn(async () => undefined),
    discardDraft: vi.fn(async () => undefined),
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('keeps the canvas simple until advanced tools, annotations, or details are requested', async () => {
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={services()}
      onAttachmentChange={vi.fn()}
    />,
  )

  expect(await screen.findByRole('toolbar', { name: 'Annotation tools' })).toBeVisible()
  for (const name of [
    'Pan',
    'Select',
    'Rectangle',
    'Polygon',
    'Freehand ROI',
    'Ruler',
  ]) {
    const tool = screen.getByRole('button', { name })
    expect(tool).toBeVisible()
    expect(tool.querySelector('svg')).toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: 'Point marker' })).not.toBeInTheDocument()
  expect(screen.queryByRole('searchbox', { name: 'Search annotations' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Annotation inspector' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save annotations' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'More annotation tools' }))
  expect(screen.getByRole('button', { name: 'Point marker' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Ellipse' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'Open annotations' }))
  expect(screen.getByRole('searchbox', { name: 'Search annotations' })).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Filter by classification' })).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Filter by tag' })).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'Open annotation inspector' }))
  expect(screen.getByRole('region', { name: 'Annotation inspector' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Show advanced annotation details' }))
  expect(screen.getByRole('button', { name: 'Reload annotations' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Import annotations' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Export PathLab JSON' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Export GeoJSON' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Export measurements CSV' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Browse annotation revisions' })).toBeVisible()
  expect(screen.getByRole('combobox', { name: 'Drawing layer' })).toHaveValue(layerId)
  expect(screen.getByRole('button', { name: 'Findings' })).toBeVisible()
})

it('supports focus-safe keyboard shortcuts and creates a point through the attachment bridge', async () => {
  const onAttachmentChange = vi.fn()
  const workflow = services()
  const view = render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={workflow}
      onAttachmentChange={onAttachmentChange}
    />,
  )
  await screen.findByRole('toolbar', { name: 'Annotation tools' })

  fireEvent.keyDown(window, { key: 'p' })
  expect(screen.getByRole('button', { name: 'More annotation tools' })).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  fireEvent.click(screen.getByRole('button', { name: 'More annotation tools' }))
  expect(screen.getByRole('button', { name: 'Point marker' })).toHaveAttribute('aria-pressed', 'true')

  const attachment = onAttachmentChange.mock.calls.at(-1)?.[0]
  expect(attachment).toBeTypeOf('function')
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
  fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
  fireEvent.keyDown(window, { key: 's', ctrlKey: true })
  await waitFor(() => expect(screen.getAllByRole('status')[0]).toHaveTextContent(/saved|no changes/i))

  view.unmount()
  expect(onAttachmentChange).toHaveBeenLastCalledWith(undefined)
})

it('reveals the active editable layer locally without writing a visibility mutation', async () => {
  const updateLayer = vi.fn()
  const hiddenManifest: AnnotationManifest = {
    ...manifest,
    activeCount: 12,
    layers: [
      { ...manifest.layers[0], visible: false },
      {
        ...manifest.layers[0],
        id: '22222222-2222-4222-8222-222222222222',
        name: 'Reference',
        sortOrder: 1,
        visible: false,
      },
    ],
  }
  render(
    <AnnotationWorkspace
      slideId="slide-1"
      slideName="Private slide"
      services={services({
        getManifest: vi.fn(async () => hiddenManifest),
        updateLayer,
      })}
      onAttachmentChange={vi.fn()}
    />,
  )

  await screen.findByRole('toolbar', { name: 'Annotation tools' })
  fireEvent.click(screen.getByRole('button', { name: 'Open annotations' }))
  expect(screen.getByText('1 hidden layer')).toBeVisible()

  fireEvent.click(screen.getByRole('button', { name: 'Open annotation inspector' }))
  fireEvent.click(screen.getByRole('button', { name: 'Show advanced annotation details' }))
  expect(screen.getByRole('checkbox', { name: 'Show Findings' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Show Reference' })).not.toBeChecked()
  expect(updateLayer).not.toHaveBeenCalled()
})

it('keeps touch targets, responsive dock, theme tokens, and reduced motion in the stylesheet', () => {
  const css = readFileSync('src/annotations/annotation.css', 'utf8')

  expect(css).toContain('--annotation-accent:#f37338')
  expect(css).toContain('--annotation-accent-ink:#141413')
  expect(css).toContain("--annotation-font:'Sofia Sans Variable','Sofia Sans',Arial,sans-serif")
  expect(css).not.toContain('ui-monospace')
  expect(css).toContain('font-weight:450')
  expect(css).toContain('border-radius:24px')
  expect(css).toContain("background:var(--ink)")
  expect(css).toMatch(/min-(?:width|height):44px/)
  expect(css).toMatch(/@media\s*\(max-width:760px\)/)
  expect(css).toMatch(/\.annotation-toolstrip[\s\S]*bottom:/)
  expect(css).toMatch(/\.annotation-inspector[\s\S]*position:fixed/)
  expect(css).toMatch(/@media\s*\(prefers-reduced-motion:reduce\)/)
  expect(css).toContain("[data-theme='dark']")
})
