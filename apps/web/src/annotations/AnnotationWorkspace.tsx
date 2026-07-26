import OpenSeadragon from 'openseadragon'
import {
  ArrowClockwise,
  CaretDown,
  CaretUp,
  Copy,
  DownloadSimple,
  FloppyDisk,
  FolderOpen,
  MagnifyingGlass,
  Plus,
  SidebarSimple,
  Trash,
  UploadSimple,
  X,
} from '@phosphor-icons/react'
import {
  Component,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import type { ViewerAttachmentCallback } from '../components/OpenSeadragonViewer'
import { AnnotationApiClient } from './api'
import {
  AnnotationAutosave,
  type AutosaveSnapshot,
  type ConflictChoice,
} from './autosave'
import {
  AnnotationDraftRepository,
  type AnnotationDraft,
} from './drafts'
import { attachAnnotationOverlay } from './AnnotationOverlay'
import { createAnnotationStore, type AnnotationStore, type AnnotationStoreState } from './store'
import type {
  AnnotationBatchRequest,
  AnnotationBatchResult,
  AnnotationGeometry,
  AnnotationItemsPage,
  AnnotationLayer,
  AnnotationManifest,
  AnnotationMetadata,
  AnnotationRecord,
  AnnotationStyle,
  AnnotationTool,
  PolygonBooleanOperation,
} from './types'
import './annotation.css'

const DEFAULT_STYLE: AnnotationStyle = {
  strokeColor: '#ffb400',
  fillColor: '#ffb400',
  strokeWidth: 2,
  opacity: 0.9,
  labelVisible: true,
}

const DEFAULT_METADATA: AnnotationMetadata = {
  title: '',
  classification: '',
  tags: [],
  notes: '',
}

const EMPTY_AUTOSAVE: AutosaveSnapshot = {
  status: 'idle',
  dirtyCount: 0,
  version: 0,
  retryAt: null,
  error: null,
  conflict: null,
}

const TOOLS: Array<{
  tool: AnnotationTool
  label: string
  glyph: string
  shortcut: string
}> = [
  { tool: 'hand', label: 'Pan', glyph: 'H', shortcut: 'H' },
  { tool: 'select', label: 'Select', glyph: 'V', shortcut: 'V' },
  { tool: 'marquee', label: 'Marquee select', glyph: 'M', shortcut: 'M' },
  { tool: 'point', label: 'Point marker', glyph: '•', shortcut: 'P' },
  { tool: 'ruler', label: 'Ruler', glyph: '↔', shortcut: 'R' },
  { tool: 'polyline', label: 'Polyline', glyph: '⌁', shortcut: 'L' },
  { tool: 'angle', label: 'Three-point angle', glyph: '∠', shortcut: 'A' },
  { tool: 'rectangle', label: 'Rectangle', glyph: '□', shortcut: 'B' },
  { tool: 'ellipse', label: 'Ellipse', glyph: '○', shortcut: 'E' },
  { tool: 'polygon', label: 'Polygon', glyph: '⬡', shortcut: 'G' },
  { tool: 'freehand', label: 'Freehand ROI', glyph: '∿', shortcut: 'F' },
  { tool: 'brush-add', label: 'Brush add', glyph: '+', shortcut: ']' },
  { tool: 'brush-subtract', label: 'Brush subtract', glyph: '−', shortcut: '[' },
  { tool: 'text', label: 'Text callout', glyph: 'T', shortcut: 'T' },
]

const SHORTCUT_TO_TOOL = new Map(
  TOOLS.map((item) => [item.shortcut.toLowerCase(), item.tool]),
)

export interface AnnotationWorkspaceServices {
  getManifest(): Promise<AnnotationManifest>
  getItems(offset: number, includeDeleted?: boolean): Promise<AnnotationItemsPage>
  batch(request: AnnotationBatchRequest): Promise<AnnotationBatchResult>
  createLayer(request: {
    mutationId: string
    baseVersion: number
    name: string
    sortOrder: number
  }): Promise<AnnotationLayer>
  updateLayer(
    layerId: string,
    request: {
      mutationId: string
      baseVersion: number
      name?: string
      sortOrder?: number
      visible?: boolean
      locked?: boolean
      opacity?: number
    },
  ): Promise<{ version: number; layer: AnnotationLayer }>
  importDocument(request: {
    mutationId: string
    baseVersion: number
    format: 'pathlab' | 'geojson'
    layerName: string
    data: Record<string, unknown>
  }): Promise<AnnotationBatchResult>
  exportDocument(format: 'pathlab' | 'geojson' | 'csv'): Promise<Response>
  revisions(annotationId: string): Promise<{
    items: Array<{ id: string; version: number }>
  }>
  restoreRevision(
    annotationId: string,
    revisionId: string,
    request: { mutationId: string; baseVersion: number; version: number },
  ): Promise<{ version: number; item: AnnotationRecord }>
  loadDraft(): Promise<AnnotationDraft | null>
  saveDraft(draft: Omit<AnnotationDraft, 'byteSize'>): Promise<unknown>
  acknowledgeDraft(): Promise<void>
  discardDraft(): Promise<void>
}

function defaultServices(slideId: string): AnnotationWorkspaceServices {
  const api = new AnnotationApiClient()
  const drafts = new AnnotationDraftRepository()
  return {
    getManifest: () => api.getManifest(slideId),
    getItems: (offset, includeDeleted = true) => api.getItems(slideId, {
      offset,
      includeDeleted,
      limit: 5_000,
    }),
    batch: (request) => api.batch(slideId, request),
    createLayer: (request) => api.createLayer(slideId, request),
    updateLayer: (layerId, request) => api.updateLayer(slideId, layerId, request),
    importDocument: (request) => api.import(slideId, request),
    exportDocument: (format) => api.export(slideId, format),
    revisions: (annotationId) => api.revisions(slideId, annotationId),
    restoreRevision: (annotationId, revisionId, request) => (
      api.restoreRevision(slideId, annotationId, revisionId, request)
    ),
    loadDraft: () => drafts.load(slideId),
    saveDraft: (draft) => drafts.save(draft),
    acknowledgeDraft: () => drafts.acknowledge(slideId),
    discardDraft: () => drafts.discard(slideId),
  }
}

interface ErrorBoundaryProps {
  children: ReactNode
  resetKey: number
  onRetry: () => void
}

interface ErrorBoundaryState {
  failed: boolean
}

export class AnnotationErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch() {
    // The private viewer remains mounted; the retry surface is intentionally data-safe.
  }

  componentDidUpdate(previous: ErrorBoundaryProps) {
    if (previous.resetKey !== this.props.resetKey && this.state.failed) {
      this.setState({ failed: false })
    }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="annotation-failure" role="alert">
        <strong>Annotations paused</strong>
        <span>The slide viewer is still available and your local draft is retained.</span>
        <button type="button" onClick={this.props.onRetry}>Retry annotations</button>
      </div>
    )
  }
}

function isEditingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || (target instanceof HTMLElement && target.isContentEditable)
}

function replayDraft(store: AnnotationStore, draft: AnnotationDraft) {
  for (const mutation of draft.mutations) {
    if (mutation.type === 'create') store.create(mutation.item)
    else if (mutation.type === 'update') {
      store.update(mutation.id, {
        ...(mutation.layerId === undefined ? {} : { layerId: mutation.layerId }),
        ...(mutation.geometry === undefined ? {} : { geometry: mutation.geometry }),
        ...(mutation.style === undefined ? {} : { style: mutation.style }),
        ...(mutation.metadata === undefined ? {} : { metadata: mutation.metadata }),
      })
    } else if (mutation.type === 'delete') store.delete([mutation.id])
    else store.restore([mutation.id])
  }
}

function stateDraft(
  slideId: string,
  state: AnnotationStoreState,
): Omit<AnnotationDraft, 'byteSize'> {
  return {
    schema: 'pathlab-annotation-draft/v1',
    slideId,
    baseVersion: state.version,
    mutations: state.pendingMutations,
    snapshot: {
      version: state.version,
      layers: [...state.layers.values()],
      annotations: [...state.annotations.values()],
    },
    savedAt: Date.now(),
    dirty: state.pendingMutations.length > 0,
  }
}

function selectionRecords(state: AnnotationStoreState | null): AnnotationRecord[] {
  if (!state) return []
  return [...state.selection]
    .map((id) => state.annotations.get(id))
    .filter((record): record is AnnotationRecord => Boolean(record))
}

function hasEditablePoints(
  record: AnnotationRecord,
): record is AnnotationRecord & {
  geometry: Extract<AnnotationGeometry, { points: unknown }> & {
    points: Array<{ x: number; y: number }>
  }
} {
  return 'points' in record.geometry
}

function triggerDownload(response: Response, filename: string) {
  void response.blob().then((blob) => {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  })
}

export interface AnnotationWorkspaceProps {
  slideId: string
  slideName: string
  services?: AnnotationWorkspaceServices
  onAttachmentChange: (attachment?: ViewerAttachmentCallback) => void
}

export function AnnotationWorkspace({
  slideId,
  slideName,
  services: providedServices,
  onAttachmentChange,
}: AnnotationWorkspaceProps) {
  const services = useMemo(
    () => providedServices ?? defaultServices(slideId),
    [providedServices, slideId],
  )
  const storeRef = useRef<AnnotationStore | null>(null)
  const autosaveRef = useRef<AnnotationAutosave | null>(null)
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null)
  const activeLayerRef = useRef<string | null>(null)
  const styleRef = useRef<AnnotationStyle>(DEFAULT_STYLE)
  const metadataRef = useRef<AnnotationMetadata>(DEFAULT_METADATA)
  const textRef = useRef('Callout')
  const draftTimerRef = useRef<number | null>(null)
  const pendingSignatureRef = useRef('[]')
  const inspectorTriggerRef = useRef<HTMLButtonElement>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const [storeState, setStoreState] = useState<AnnotationStoreState | null>(null)
  const [autosave, setAutosave] = useState(EMPTY_AUTOSAVE)
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [style, setStyle] = useState(DEFAULT_STYLE)
  const [metadata, setMetadata] = useState(DEFAULT_METADATA)
  const [calloutText, setCalloutText] = useState('Callout')
  const [initializing, setInitializing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [densityPrompt, setDensityPrompt] = useState<string | null>(null)
  const [coordinate, setCoordinate] = useState<{ x: number; y: number } | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(() => window.innerWidth > 760)
  const [resetKey, setResetKey] = useState(0)
  const [operationStatus, setOperationStatus] = useState('Opening annotation workspace…')
  const [importPreview, setImportPreview] = useState<string | null>(null)
  const attachmentReady = Boolean(storeState)

  activeLayerRef.current = activeLayerId
  styleRef.current = style
  metadataRef.current = metadata
  textRef.current = calloutText

  const loadRemote = useCallback(async (store: AnnotationStore): Promise<number> => {
    const manifest = await services.getManifest()
    const items: AnnotationRecord[] = []
    let offset = 0
    do {
      const page = await services.getItems(offset, true)
      items.push(...page.items)
      if (page.nextOffset === null) break
      offset = page.nextOffset
    } while (items.length < manifest.limits.activeAnnotations + manifest.trashedCount)
    store.load({
      version: manifest.version,
      layers: manifest.layers,
      annotations: items,
    })
    const firstEditable = manifest.layers.find((layer) => !layer.locked)
      ?? manifest.layers[0]
      ?? null
    setActiveLayerId(firstEditable?.id ?? null)
    return manifest.version
  }, [services])

  useEffect(() => {
    let active = true
    let unsubscribe: () => void = () => undefined
    setInitializing(true)
    setError(null)
    setOperationStatus('Opening annotation workspace…')

    void (async () => {
      try {
        const manifest = await services.getManifest()
        if (!active) return
        const store = createAnnotationStore({
          slideId,
          bounds: manifest.bounds,
          calibration: manifest.calibration,
          maxAnnotations: manifest.limits.activeAnnotations,
          maxLayers: manifest.limits.layers,
        })
        storeRef.current = store
        const items: AnnotationRecord[] = []
        let offset = 0
        do {
          const page = await services.getItems(offset, true)
          if (!active) return
          items.push(...page.items)
          if (page.nextOffset === null) break
          offset = page.nextOffset
        } while (items.length < manifest.limits.activeAnnotations + manifest.trashedCount)
        store.load({
          version: manifest.version,
          layers: manifest.layers,
          annotations: items,
        })
        const firstEditable = manifest.layers.find((layer) => !layer.locked)
          ?? manifest.layers[0]
          ?? null
        setActiveLayerId(firstEditable?.id ?? null)
        activeLayerRef.current = firstEditable?.id ?? null

        const storeHooks = store.autosaveHooks()
        const saver = new AnnotationAutosave({
          baseVersion: manifest.version,
          transport: {
            save: (mutationId, baseVersion, operations) => services.batch({
              mutationId,
              baseVersion,
              operations,
            }),
          },
          ...storeHooks,
          onReload: async () => {
            const version = await loadRemote(store)
            await services.discardDraft()
            return version
          },
          onSaveAsDuplicate: async (operations) => {
            const creates = operations.flatMap((operation) => {
              const id = operation.type === 'create' ? operation.item.id : operation.id
              const record = store.getState().annotations.get(id)
              if (!record || record.deletedAt) return []
              return [{
                type: 'create' as const,
                item: {
                  id: crypto.randomUUID(),
                  layerId: record.layerId,
                  geometry: structuredClone(record.geometry),
                  style: structuredClone(record.style),
                  metadata: {
                    ...structuredClone(record.metadata),
                    title: `${record.metadata.title || 'Annotation'} copy`,
                  },
                },
              }]
            })
            if (creates.length === 0) return store.getState().version
            const result = await services.batch({
              mutationId: crypto.randomUUID(),
              baseVersion: store.getState().version,
              operations: creates,
            })
            await loadRemote(store)
            await services.acknowledgeDraft()
            return result.version
          },
          onChange: (snapshot) => {
            if (!active) return
            setAutosave(snapshot)
            if (snapshot.status === 'saved' && snapshot.dirtyCount === 0) {
              void services.acknowledgeDraft().catch(() => undefined)
            }
          },
        })
        autosaveRef.current = saver
        unsubscribe = store.subscribe((next) => {
          if (!active) return
          setStoreState(next)
          const signature = JSON.stringify(next.pendingMutations)
          if (signature !== pendingSignatureRef.current) {
            pendingSignatureRef.current = signature
            saver.replacePending(next.pendingMutations)
          }
          if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current)
          draftTimerRef.current = window.setTimeout(() => {
            void services.saveDraft(stateDraft(slideId, next)).catch((caught) => {
              if (active) {
                setError(caught instanceof Error ? caught.message : 'Local draft could not be saved')
              }
            })
          }, 250)
        })
        setStoreState(store.getState())
        const draft = await services.loadDraft()
        if (!active) return
        if (draft?.dirty) {
          replayDraft(store, draft)
          setOperationStatus('Recovered unsaved local changes')
        } else {
          setOperationStatus('Annotations ready')
        }
        setInitializing(false)
      } catch (caught) {
        if (!active) return
        setError(caught instanceof Error ? caught.message : 'Annotations could not be initialized')
        setOperationStatus('Annotations paused; slide navigation remains available')
        setInitializing(false)
      }
    })()

    return () => {
      active = false
      unsubscribe()
      autosaveRef.current?.dispose()
      autosaveRef.current = null
      storeRef.current?.detachOverlay()
      storeRef.current = null
      if (draftTimerRef.current !== null) {
        window.clearTimeout(draftTimerRef.current)
        draftTimerRef.current = null
      }
    }
  }, [loadRemote, resetKey, services, slideId])

  useEffect(() => {
    if (!attachmentReady || error) {
      onAttachmentChange(undefined)
      return
    }
    const attachment: ViewerAttachmentCallback = (viewer) => {
      const store = storeRef.current
      if (!store) return undefined
      viewerRef.current = viewer
      let cleanup: () => void
      try {
        cleanup = attachAnnotationOverlay(viewer, {
          store,
          activeLayerId: () => activeLayerRef.current,
          style: () => structuredClone(styleRef.current),
          metadata: () => structuredClone(metadataRef.current),
          text: () => textRef.current,
          onCoordinate: setCoordinate,
          onDensity: setDensityPrompt,
          onError: (message) => {
            setError(message)
            setOperationStatus('Annotation overlay paused; pan and zoom restored')
          },
        })
      } catch (caught) {
        viewer.setMouseNavEnabled(true)
        viewer.setKeyboardNavEnabled(true)
        setError(caught instanceof Error ? caught.message : 'Annotation overlay could not attach')
        setOperationStatus('Annotation overlay paused; pan and zoom restored')
        return undefined
      }
      return () => {
        cleanup()
        if (viewerRef.current === viewer) viewerRef.current = null
      }
    }
    onAttachmentChange(attachment)
    return () => onAttachmentChange(undefined)
  }, [attachmentReady, error, onAttachmentChange])

  const store = storeRef.current
  const selected = selectionRecords(storeState)
  const primary = selected[0] ?? null
  const currentTool = storeState?.tool ?? 'hand'
  const classifications = useMemo(() => (
    [...new Set(
      [...(storeState?.annotations.values() ?? [])]
        .map((record) => record.metadata.classification)
        .filter(Boolean),
    )].sort((left, right) => left.localeCompare(right))
  ), [storeState])
  const tags = useMemo(() => (
    [...new Set(
      [...(storeState?.annotations.values() ?? [])]
        .flatMap((record) => record.metadata.tags),
    )].sort((left, right) => left.localeCompare(right))
  ), [storeState])

  const setTool = useCallback((tool: AnnotationTool) => {
    storeRef.current?.setTool(tool)
    setOperationStatus(`${TOOLS.find((item) => item.tool === tool)?.label ?? tool} active`)
  }, [])

  const flush = useCallback(async () => {
    const saver = autosaveRef.current
    if (!saver || saver.snapshot().dirtyCount === 0) {
      setOperationStatus('No changes to save')
      return
    }
    setOperationStatus('Saving annotations…')
    await saver.flush()
    const next = saver.snapshot()
    setOperationStatus(next.status === 'saved'
      ? 'Annotations saved'
      : next.error ?? `Save ${next.status}`)
  }, [])

  const prepareVersionedOperation = useCallback(async (): Promise<number> => {
    await flush()
    const saver = autosaveRef.current
    const snapshot = saver?.snapshot()
    if (
      snapshot
      && (
        snapshot.dirtyCount > 0
        || snapshot.status === 'conflict'
        || snapshot.status === 'error'
        || snapshot.status === 'retrying'
      )
    ) {
      throw new Error(snapshot.error ?? 'Save pending annotation edits before continuing')
    }
    const localStore = storeRef.current
    if (!localStore) throw new Error('Annotation workspace is not ready')
    return localStore.getState().version
  }, [flush])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const editing = isEditingTarget(event.target)
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void flush()
        return
      }
      if (editing) return
      const localStore = storeRef.current
      if (!localStore) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        if (event.shiftKey) localStore.redo()
        else localStore.undo()
        return
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
        event.preventDefault()
        localStore.copy()
        return
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'v') {
        event.preventDefault()
        localStore.paste()
        return
      }
      const shortcutTool = SHORTCUT_TO_TOOL.get(event.key.toLowerCase())
      if (shortcutTool) {
        event.preventDefault()
        setTool(shortcutTool)
        return
      }
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault()
        localStore.delete(localStore.getState().selection)
      } else if (event.key === 'Escape') {
        setTool('hand')
        setInspectorOpen(false)
      } else if (event.key.startsWith('Arrow')) {
        const distance = event.shiftKey ? 10 : 1
        const delta = {
          ArrowLeft: [-distance, 0],
          ArrowRight: [distance, 0],
          ArrowUp: [0, -distance],
          ArrowDown: [0, distance],
        }[event.key]
        if (delta) {
          event.preventDefault()
          localStore.move(localStore.getState().selection, delta[0], delta[1])
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [flush, setTool])

  const retry = () => {
    setError(null)
    setResetKey((value) => value + 1)
    setOperationStatus('Retrying annotations…')
  }

  const reload = async () => {
    const localStore = storeRef.current
    if (!localStore) return
    setOperationStatus('Reloading annotations…')
    try {
      const version = await loadRemote(localStore)
      autosaveRef.current?.reset(version)
      await services.discardDraft()
      setOperationStatus('Annotations reloaded from server')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Reload failed')
    }
  }

  const resolveConflict = async (choice: ConflictChoice) => {
    try {
      await autosaveRef.current?.resolveConflict(choice)
      setOperationStatus(choice === 'reload'
        ? 'Reloaded server annotations'
        : 'Saved local edits as duplicates')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Conflict could not be resolved')
    }
  }

  const updateStyle = (patch: Partial<AnnotationStyle>) => {
    const next = { ...(primary?.style ?? style), ...patch }
    setStyle(next)
    if (store && selected.length > 0) store.bulkUpdate(selected.map((record) => record.id), {
      style: next,
    })
  }

  const updateMetadata = (patch: Partial<AnnotationMetadata>) => {
    const next = { ...(primary?.metadata ?? metadata), ...patch }
    setMetadata(next)
    if (store && selected.length > 0) store.bulkUpdate(selected.map((record) => record.id), {
      metadata: next,
    })
  }

  const applyBoolean = async (operation: PolygonBooleanOperation) => {
    if (!store || selected.length < 2) {
      setOperationStatus('Select at least two closed annotations')
      return
    }
    try {
      await flush()
      await store.boolean(operation, selected.map((record) => record.id))
      setOperationStatus(`${operation} completed`)
    } catch (caught) {
      setOperationStatus(caught instanceof Error ? caught.message : `${operation} failed`)
    }
  }

  const zoomTo = (record: AnnotationRecord) => {
    const viewer = viewerRef.current
    if (!viewer) return
    const item = viewer.world.getItemAt(0)
    if (!item) return
    const { minX, minY, maxX, maxY } = record.bounds
    const rectangle = item.imageToViewportRectangle(
      new OpenSeadragon.Rect(minX, minY, Math.max(1, maxX - minX), Math.max(1, maxY - minY)),
    )
    viewer.viewport.fitBounds(rectangle, false)
  }

  const createLayer = async () => {
    if (!storeState) return
    try {
      const baseVersion = await prepareVersionedOperation()
      const layer = await services.createLayer({
        mutationId: crypto.randomUUID(),
        baseVersion,
        name: `Layer ${storeState.layers.size + 1}`,
        sortOrder: storeState.layers.size,
      })
      const localStore = storeRef.current
      if (!localStore) return
      const version = await loadRemote(localStore)
      autosaveRef.current?.reset(version)
      setActiveLayerId(layer.id)
      setOperationStatus(`${layer.name} created`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Layer could not be created')
    }
  }

  const updateLayer = async (
    layer: AnnotationLayer,
    patch: Partial<Pick<AnnotationLayer, 'name' | 'sortOrder' | 'visible' | 'locked' | 'opacity'>>,
  ) => {
    if (!storeState) return
    try {
      const baseVersion = await prepareVersionedOperation()
      storeRef.current?.updateLayer(layer.id, patch)
      await services.updateLayer(layer.id, {
        mutationId: crypto.randomUUID(),
        baseVersion,
        ...patch,
      })
      const localStore = storeRef.current
      if (!localStore) return
      const version = await loadRemote(localStore)
      autosaveRef.current?.reset(version)
      setActiveLayerId((current) => current ?? layer.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Layer update failed')
      await reload()
    }
  }

  const restoreRevision = async () => {
    if (!primary || !storeState) {
      setOperationStatus('Select an annotation to restore a revision')
      return
    }
    try {
      const baseVersion = await prepareVersionedOperation()
      const current = storeRef.current?.getState().annotations.get(primary.id)
      if (!current) throw new Error('Selected annotation is no longer available')
      const revisions = await services.revisions(current.id)
      const revision = revisions.items[0]
      if (!revision) {
        setOperationStatus('No earlier revision is available')
        return
      }
      await services.restoreRevision(current.id, revision.id, {
        mutationId: crypto.randomUUID(),
        baseVersion,
        version: current.version,
      })
      await reload()
      setOperationStatus('Annotation revision restored')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Revision restore failed')
    }
  }

  const importFile = async (file: File | undefined) => {
    if (!file || !store || !storeState) return
    try {
      const baseVersion = await prepareVersionedOperation()
      const text = await file.text()
      const data = JSON.parse(text) as Record<string, unknown>
      const preview = store.previewImport(data)
      setImportPreview(
        `${preview.annotationCount.toLocaleString()} annotations · ${preview.vertexCount.toLocaleString()} vertices`,
      )
      if (!preview.valid || preview.format === 'unknown') {
        throw new Error(preview.errors[0] ?? 'Import is not valid')
      }
      await services.importDocument({
        mutationId: crypto.randomUUID(),
        baseVersion,
        format: preview.format,
        layerName: file.name.replace(/\.[^.]+$/, '').slice(0, 160) || 'Imported annotations',
        data,
      })
      await reload()
      setOperationStatus('Import completed in a new layer')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Import failed')
    } finally {
      if (importRef.current) importRef.current.value = ''
    }
  }

  const exportDocument = async (format: 'pathlab' | 'geojson' | 'csv') => {
    try {
      const response = await services.exportDocument(format)
      triggerDownload(response, `${slideName}-annotations.${format === 'pathlab' ? 'json' : format}`)
      setOperationStatus(`${format.toUpperCase()} export ready`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Export failed')
    }
  }

  const measurement = primary && store ? store.measure(primary.id) : null

  return (
    <AnnotationErrorBoundary resetKey={resetKey} onRetry={retry}>
      <section
        className={`annotation-workspace${inspectorOpen ? ' annotation-workspace--inspector' : ''}`}
        aria-label="Annotations"
      >
        <div className="annotation-focus-rail" aria-hidden="true">
          <span>CANVAS FOCUS</span>
          <i />
          <span>{storeState?.annotations.size.toLocaleString() ?? '0'} OBJECTS</span>
        </div>

        <div className="annotation-toolstrip" role="toolbar" aria-label="Annotation tools">
          {TOOLS.map((item) => (
            <button
              type="button"
              key={item.tool}
              aria-label={item.label}
              aria-pressed={currentTool === item.tool}
              title={`${item.label} (${item.shortcut})`}
              onClick={() => setTool(item.tool)}
            >
              <span aria-hidden="true">{item.glyph}</span>
            </button>
          ))}
        </div>

        <div className="annotation-commandbar" aria-label="Annotation commands">
          <div className="annotation-save-cluster">
            <button type="button" aria-label="Save annotations" onClick={() => void flush()}>
              <FloppyDisk />
              <span>Save</span>
            </button>
            <button type="button" aria-label="Reload annotations" onClick={() => void reload()}>
              <ArrowClockwise />
            </button>
            <output
              className={`annotation-save-status annotation-save-status--${autosave.status}`}
              role="status"
              aria-live="polite"
            >
              {initializing
                ? 'Opening…'
                : autosave.status === 'saved'
                  ? 'Saved'
                  : autosave.dirtyCount > 0
                    ? `${autosave.dirtyCount} unsaved`
                    : 'No changes'}
            </output>
          </div>
          <label className="annotation-search">
            <MagnifyingGlass aria-hidden="true" />
            <span className="visually-hidden">Search annotations</span>
            <input
              type="search"
              aria-label="Search annotations"
              placeholder="Search title, class, tag…"
              value={storeState?.filter.search ?? ''}
              onChange={(event) => store?.setFilter({ search: event.target.value })}
            />
          </label>
          <button
            ref={inspectorTriggerRef}
            type="button"
            className="annotation-inspector-toggle"
            aria-label={inspectorOpen ? 'Close annotation inspector' : 'Open annotation inspector'}
            aria-expanded={inspectorOpen}
            onClick={() => setInspectorOpen((open) => !open)}
          >
            <SidebarSimple />
          </button>
        </div>

        <div className="annotation-list" aria-label="Annotation list">
          <div className="annotation-panel-heading">
            <div>
              <span className="annotation-kicker">OBJECT REGISTER</span>
              <strong>Annotations</strong>
            </div>
            <span>{store?.visibleAnnotations().length.toLocaleString() ?? 0}</span>
          </div>
          <div className="annotation-filterbar" aria-label="Annotation filters">
            <select
              aria-label="Filter by classification"
              value={[...(storeState?.filter.classifications ?? [])][0] ?? ''}
              onChange={(event) => store?.setFilter({
                classifications: new Set(event.target.value ? [event.target.value] : []),
              })}
            >
              <option value="">All classes</option>
              {classifications.map((classification) => (
                <option key={classification} value={classification}>{classification}</option>
              ))}
            </select>
            <select
              aria-label="Filter by tag"
              value={[...(storeState?.filter.tags ?? [])][0] ?? ''}
              onChange={(event) => store?.setFilter({
                tags: new Set(event.target.value ? [event.target.value] : []),
              })}
            >
              <option value="">All tags</option>
              {tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
            </select>
            <label>
              <input
                type="checkbox"
                checked={storeState?.filter.includeDeleted ?? false}
                onChange={(event) => store?.setFilter({ includeDeleted: event.target.checked })}
              />
              <span>Trash</span>
            </label>
          </div>
          <div className="annotation-list-scroll">
            {store?.visibleAnnotations().map((record, index) => (
              <button
                type="button"
                key={record.id}
                className={storeState?.selection.has(record.id) ? 'is-selected' : ''}
                onClick={(event) => store.select([record.id], event.shiftKey)}
                onDoubleClick={() => zoomTo(record)}
              >
                <span>{String(index + 1).padStart(3, '0')}</span>
                <span>
                  <strong>{record.metadata.title || `${record.geometry.type} annotation`}</strong>
                  <small>{record.metadata.classification || record.geometry.type}</small>
                </span>
                <i style={{ background: record.style.strokeColor }} />
              </button>
            ))}
            {!initializing && store?.visibleAnnotations().length === 0 ? (
              <p className="annotation-empty">Choose a tool and mark the slide.</p>
            ) : null}
          </div>
        </div>

        {inspectorOpen ? (
          <aside className="annotation-inspector" role="region" aria-label="Annotation inspector">
            <div className="annotation-panel-heading">
              <div>
                <span className="annotation-kicker">CONTROL SURFACE</span>
                <strong>Inspector</strong>
              </div>
              <button
                type="button"
                aria-label="Close annotation inspector"
                onClick={() => {
                  setInspectorOpen(false)
                  window.setTimeout(() => inspectorTriggerRef.current?.focus(), 0)
                }}
              >
                <X />
              </button>
            </div>

            <div className="annotation-inspector-scroll">
              <section>
                <div className="annotation-section-heading">
                  <h2>Selection</h2>
                  <span>{selected.length}</span>
                </div>
                <div className="annotation-action-grid">
                  <button type="button" aria-label="Undo" onClick={() => store?.undo()}>Undo</button>
                  <button type="button" aria-label="Redo" onClick={() => store?.redo()}>Redo</button>
                  <button type="button" onClick={() => store?.duplicate(storeState?.selection ?? [])}>Duplicate</button>
                  <button type="button" onClick={() => store?.copy()}><Copy /> Copy</button>
                  <button type="button" onClick={() => store?.paste()}>Paste</button>
                  <button type="button" onClick={() => primary && zoomTo(primary)}>Zoom to</button>
                  <button type="button" onClick={() => store?.delete(storeState?.selection ?? [])}><Trash /> Delete</button>
                  <button type="button" onClick={() => store?.restore(storeState?.selection ?? [])}>Restore</button>
                </div>
                <div className="annotation-boolean-grid" aria-label="Boolean operations">
                  {(['union', 'subtract', 'intersection', 'split'] as const).map((operation) => (
                    <button type="button" key={operation} onClick={() => void applyBoolean(operation)}>
                      {operation}
                    </button>
                  ))}
                </div>
              </section>

              <section>
                <h2>Details</h2>
                <label>
                  <span>{primary ? 'Annotation layer' : 'Drawing layer'}</span>
                  <select
                    aria-label={primary ? 'Annotation layer' : 'Drawing layer'}
                    value={primary?.layerId ?? activeLayerId ?? ''}
                    onChange={(event) => {
                      const layerId = event.target.value
                      setActiveLayerId(layerId)
                      if (store && selected.length > 0) {
                        store.bulkUpdate(selected.map((record) => record.id), { layerId })
                      }
                    }}
                  >
                    {[...(storeState?.layers.values() ?? [])]
                      .sort((left, right) => left.sortOrder - right.sortOrder)
                      .map((layer) => (
                        <option key={layer.id} value={layer.id} disabled={layer.locked}>
                          {layer.name}{layer.locked ? ' · locked' : ''}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  <span>Title</span>
                  <input
                    value={primary?.metadata.title ?? metadata.title}
                    maxLength={200}
                    onChange={(event) => updateMetadata({ title: event.target.value })}
                  />
                </label>
                <label>
                  <span>Classification</span>
                  <input
                    value={primary?.metadata.classification ?? metadata.classification}
                    maxLength={120}
                    onChange={(event) => updateMetadata({ classification: event.target.value })}
                  />
                </label>
                <label>
                  <span>Tags</span>
                  <input
                    value={(primary?.metadata.tags ?? metadata.tags).join(', ')}
                    onChange={(event) => updateMetadata({
                      tags: event.target.value.split(',').map((tag) => tag.trim()).filter(Boolean).slice(0, 50),
                    })}
                  />
                </label>
                <label>
                  <span>Notes</span>
                  <textarea
                    value={primary?.metadata.notes ?? metadata.notes}
                    maxLength={4_000}
                    onChange={(event) => updateMetadata({ notes: event.target.value })}
                  />
                </label>
                <label>
                  <span>Callout text</span>
                  <input
                    value={calloutText}
                    maxLength={4_000}
                    onChange={(event) => setCalloutText(event.target.value)}
                  />
                </label>
              </section>

              <section>
                <h2>Style</h2>
                <div className="annotation-color-grid">
                  <label>
                    <span>Stroke</span>
                    <input
                      type="color"
                      value={primary?.style.strokeColor ?? style.strokeColor}
                      onChange={(event) => updateStyle({ strokeColor: event.target.value })}
                    />
                  </label>
                  <label>
                    <span>Fill</span>
                    <input
                      type="color"
                      value={primary?.style.fillColor ?? style.fillColor}
                      onChange={(event) => updateStyle({ fillColor: event.target.value })}
                    />
                  </label>
                </div>
                <label>
                  <span>Stroke width</span>
                  <input
                    type="range"
                    min="0.25"
                    max="32"
                    step="0.25"
                    value={primary?.style.strokeWidth ?? style.strokeWidth}
                    onChange={(event) => updateStyle({ strokeWidth: Number(event.target.value) })}
                  />
                </label>
                <label>
                  <span>Opacity</span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={primary?.style.opacity ?? style.opacity}
                    onChange={(event) => updateStyle({ opacity: Number(event.target.value) })}
                  />
                </label>
                <label className="annotation-check">
                  <input
                    type="checkbox"
                    checked={primary?.style.labelVisible ?? style.labelVisible}
                    onChange={(event) => updateStyle({ labelVisible: event.target.checked })}
                  />
                  <span>Show label</span>
                </label>
              </section>

              <section>
                <div className="annotation-section-heading">
                  <h2>Layers</h2>
                  <button type="button" aria-label="Add annotation layer" onClick={() => void createLayer()}>
                    <Plus /> Add
                  </button>
                </div>
                <div className="annotation-layers">
                  {[...(storeState?.layers.values() ?? [])]
                    .sort((left, right) => left.sortOrder - right.sortOrder)
                    .map((layer, index, layers) => (
                      <div key={layer.id} className={activeLayerId === layer.id ? 'is-active' : ''}>
                        <button
                          type="button"
                          className="annotation-layer-name"
                          onClick={() => setActiveLayerId(layer.id)}
                        >
                          {layer.name}
                        </button>
                        <button
                          type="button"
                          aria-label={`Move ${layer.name} up`}
                          disabled={index === 0}
                          onClick={() => void updateLayer(layer, { sortOrder: Math.max(0, layer.sortOrder - 1) })}
                        >
                          <CaretUp />
                        </button>
                        <button
                          type="button"
                          aria-label={`Move ${layer.name} down`}
                          disabled={index === layers.length - 1}
                          onClick={() => void updateLayer(layer, { sortOrder: layer.sortOrder + 1 })}
                        >
                          <CaretDown />
                        </button>
                        <label title="Visible">
                          <input
                            type="checkbox"
                            aria-label={`Show ${layer.name}`}
                            checked={layer.visible}
                            onChange={(event) => void updateLayer(layer, { visible: event.target.checked })}
                          />
                        </label>
                        <label title="Locked">
                          <input
                            type="checkbox"
                            aria-label={`Lock ${layer.name}`}
                            checked={layer.locked}
                            onChange={(event) => void updateLayer(layer, { locked: event.target.checked })}
                          />
                        </label>
                        <label className="annotation-layer-opacity">
                          <span className="visually-hidden">{layer.name} opacity</span>
                          <input
                            type="range"
                            aria-label={`${layer.name} opacity`}
                            min="0"
                            max="1"
                            step="0.05"
                            value={layer.opacity}
                            onChange={(event) => void updateLayer(layer, { opacity: Number(event.target.value) })}
                          />
                        </label>
                      </div>
                    ))}
                </div>
              </section>

              <section>
                <h2>Measurements</h2>
                {measurement ? (
                  <dl className="annotation-measurements">
                    {Object.entries(measurement.values).map(([name, value]) => (
                      <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>
                    ))}
                  </dl>
                ) : <p className="annotation-muted">Select an annotation to inspect calibrated values.</p>}
                {measurement?.warning ? <p className="annotation-calibration-warning">{measurement.warning}</p> : null}
                {primary ? (
                  <p className="annotation-coordinates">
                    X {primary.bounds.minX.toFixed(1)}–{primary.bounds.maxX.toFixed(1)} ·
                    Y {primary.bounds.minY.toFixed(1)}–{primary.bounds.maxY.toFixed(1)} px
                  </p>
                ) : null}
                {primary && store && hasEditablePoints(primary) ? (
                  <VertexEditor record={primary} store={store} />
                ) : null}
                {primary && store ? <BoundsEditor record={primary} store={store} /> : null}
              </section>

              <section>
                <h2>Interchange</h2>
                <input
                  ref={importRef}
                  className="visually-hidden"
                  type="file"
                  accept=".json,.geojson,application/json,application/geo+json"
                  onChange={(event) => void importFile(event.target.files?.[0])}
                />
                <div className="annotation-action-grid">
                  <button type="button" aria-label="Import annotations" onClick={() => importRef.current?.click()}>
                    <UploadSimple /> Import
                  </button>
                  <button type="button" aria-label="Export PathLab JSON" onClick={() => void exportDocument('pathlab')}>
                    <DownloadSimple /> JSON
                  </button>
                  <button type="button" aria-label="Export GeoJSON" onClick={() => void exportDocument('geojson')}>
                    GeoJSON
                  </button>
                  <button type="button" aria-label="Export measurements CSV" onClick={() => void exportDocument('csv')}>
                    CSV
                  </button>
                </div>
                {importPreview ? <p className="annotation-muted">{importPreview}</p> : null}
                <button
                  type="button"
                  className="annotation-restore-revision"
                  aria-label="Restore annotation revision"
                  onClick={() => void restoreRevision()}
                >
                  <FolderOpen /> Restore revision
                </button>
              </section>
            </div>
          </aside>
        ) : null}

        <div className="annotation-data-cue" aria-hidden="true">
          <span>
            {coordinate
              ? `X ${coordinate.x.toFixed(1)}  Y ${coordinate.y.toFixed(1)}`
              : `SLIDE ${slideId.slice(0, 8).toUpperCase()}`}
          </span>
          <span>{densityPrompt ?? `${currentTool.toUpperCase()} · IMAGE PX`}</span>
        </div>

        {error ? (
          <div className="annotation-failure" role="alert">
            <strong>Annotations paused</strong>
            <span>{error}. Pan, zoom, and the unsaved local draft remain available.</span>
            <button type="button" onClick={retry}>Retry annotations</button>
          </div>
        ) : null}

        {autosave.conflict ? (
          <div className="annotation-conflict" role="alertdialog" aria-label="Annotation save conflict">
            <strong>Server changes detected</strong>
            <span>Choose how to resolve the version conflict.</span>
            <button type="button" onClick={() => void resolveConflict('reload')}>Reload server</button>
            <button type="button" onClick={() => void resolveConflict('save-as-duplicate')}>
              Save as duplicate
            </button>
          </div>
        ) : null}

        <output className="annotation-operation-status" aria-live="polite">
          {operationStatus}
        </output>
      </section>
    </AnnotationErrorBoundary>
  )
}

function VertexEditor({
  record,
  store,
}: {
  record: AnnotationRecord & { geometry: AnnotationGeometry & { points: Array<{ x: number; y: number }> } }
  store: AnnotationStore
}) {
  const point = record.geometry.points[0]
  const [x, setX] = useState(String(point.x))
  const [y, setY] = useState(String(point.y))
  useEffect(() => {
    setX(String(point.x))
    setY(String(point.y))
  }, [point.x, point.y])
  return (
    <fieldset className="annotation-vertex-editor">
      <legend>First vertex</legend>
      <label><span>X</span><input type="number" value={x} onChange={(event) => setX(event.target.value)} /></label>
      <label><span>Y</span><input type="number" value={y} onChange={(event) => setY(event.target.value)} /></label>
      <button
        type="button"
        onClick={() => store.editVertex(record.id, 0, { x: Number(x), y: Number(y) })}
      >
        Apply vertex
      </button>
    </fieldset>
  )
}

function BoundsEditor({
  record,
  store,
}: {
  record: AnnotationRecord
  store: AnnotationStore
}) {
  const [x, setX] = useState(String(record.bounds.minX))
  const [y, setY] = useState(String(record.bounds.minY))
  const [width, setWidth] = useState(String(Math.max(1, record.bounds.maxX - record.bounds.minX)))
  const [height, setHeight] = useState(String(Math.max(1, record.bounds.maxY - record.bounds.minY)))
  useEffect(() => {
    setX(String(record.bounds.minX))
    setY(String(record.bounds.minY))
    setWidth(String(Math.max(1, record.bounds.maxX - record.bounds.minX)))
    setHeight(String(Math.max(1, record.bounds.maxY - record.bounds.minY)))
  }, [
    record.bounds.maxX,
    record.bounds.maxY,
    record.bounds.minX,
    record.bounds.minY,
  ])
  return (
    <fieldset className="annotation-bounds-editor">
      <legend>Image-pixel bounds</legend>
      <label><span>X</span><input type="number" value={x} onChange={(event) => setX(event.target.value)} /></label>
      <label><span>Y</span><input type="number" value={y} onChange={(event) => setY(event.target.value)} /></label>
      <label>
        <span>Width</span>
        <input type="number" min="1" value={width} onChange={(event) => setWidth(event.target.value)} />
      </label>
      <label>
        <span>Height</span>
        <input type="number" min="1" value={height} onChange={(event) => setHeight(event.target.value)} />
      </label>
      <button
        type="button"
        onClick={() => {
          const minX = Number(x)
          const minY = Number(y)
          const nextWidth = Math.max(1, Number(width))
          const nextHeight = Math.max(1, Number(height))
          if (![minX, minY, nextWidth, nextHeight].every(Number.isFinite)) return
          store.resize(record.id, {
            minX,
            minY,
            maxX: minX + nextWidth,
            maxY: minY + nextHeight,
          })
        }}
      >
        Apply bounds
      </button>
    </fieldset>
  )
}
