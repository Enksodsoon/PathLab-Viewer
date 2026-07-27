import '@fontsource-variable/sofia-sans'
import OpenSeadragon from 'openseadragon'
import {
  Angle,
  ArrowCounterClockwise,
  ArrowClockwise,
  CaretDown,
  CaretUp,
  Circle,
  ClipboardText,
  Copy,
  Crosshair,
  Cursor,
  DotsSixVertical,
  DotsThree,
  DownloadSimple,
  FloppyDisk,
  FolderOpen,
  Hand,
  LineSegment,
  MagnifyingGlass,
  MinusCircle,
  PlusCircle,
  Plus,
  Polygon,
  Rectangle,
  Ruler,
  Scribble,
  Selection,
  SidebarSimple,
  TextT,
  Trash,
  UploadSimple,
  X,
  type Icon,
} from '@phosphor-icons/react'
import {
  Component,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import type { ViewerAttachmentCallback } from '../components/OpenSeadragonViewer'
import {
  AnnotationApiClient,
  MAX_ANNOTATION_IMPORT_REQUEST_BYTES,
  annotationImportRequestBytes,
  type AnnotationRevision,
} from './api'
import {
  AnnotationAutosave,
  type AutosaveSnapshot,
  type ConflictChoice,
} from './autosave'
import {
  AnnotationDraftRepository,
  createCompactAnnotationDraft,
  type AnnotationDraft,
} from './drafts'
import { replayDraft } from './draftRecovery'
import { attachAnnotationOverlay } from './AnnotationOverlay'
import { createAnnotationStore, type AnnotationStore, type AnnotationStoreState } from './store'
import type {
  AnnotationBatchRequest,
  AnnotationBatchResult,
  AnnotationCalibration,
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
import { ANNOTATION_ACCENT } from './palette'
import './annotation.css'

const DEFAULT_STYLE: AnnotationStyle = {
  strokeColor: ANNOTATION_ACCENT,
  fillColor: ANNOTATION_ACCENT,
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

const MAX_IMPORT_FILE_BYTES = 8 * 1024 * 1024
const OBJECT_REGISTER_PAGE_SIZE = 200

const TOOLS: Array<{
  tool: AnnotationTool
  label: string
  icon: Icon
  shortcut: string
}> = [
  { tool: 'hand', label: 'Pan', icon: Hand, shortcut: 'H' },
  { tool: 'select', label: 'Select', icon: Cursor, shortcut: 'V' },
  { tool: 'marquee', label: 'Marquee select', icon: Selection, shortcut: 'M' },
  { tool: 'point', label: 'Point marker', icon: Crosshair, shortcut: 'P' },
  { tool: 'ruler', label: 'Ruler', icon: Ruler, shortcut: 'R' },
  { tool: 'polyline', label: 'Polyline', icon: LineSegment, shortcut: 'L' },
  { tool: 'angle', label: 'Three-point angle', icon: Angle, shortcut: 'A' },
  { tool: 'rectangle', label: 'Rectangle', icon: Rectangle, shortcut: 'B' },
  { tool: 'ellipse', label: 'Ellipse', icon: Circle, shortcut: 'E' },
  { tool: 'polygon', label: 'Polygon', icon: Polygon, shortcut: 'G' },
  { tool: 'freehand', label: 'Freehand ROI', icon: Scribble, shortcut: 'F' },
  { tool: 'brush-add', label: 'Paint ROI or add to selected ROI', icon: PlusCircle, shortcut: ']' },
  { tool: 'brush-subtract', label: 'Erase from selected ROI', icon: MinusCircle, shortcut: '[' },
  { tool: 'text', label: 'Text callout', icon: TextT, shortcut: 'T' },
]

const TOOL_BY_ID = new Map(TOOLS.map((item) => [item.tool, item]))
const CORE_TOOLS = ([
  'hand',
  'select',
  'rectangle',
  'polygon',
  'freehand',
  'ruler',
] as AnnotationTool[]).map((tool) => TOOL_BY_ID.get(tool)!)
const MORE_TOOLS = TOOLS.filter((item) => !CORE_TOOLS.includes(item))

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
    layerName?: string
    data: Record<string, unknown>
  }): Promise<AnnotationBatchResult>
  exportDocument(format: 'pathlab' | 'geojson' | 'csv'): Promise<Response>
  revisions(annotationId: string): Promise<{ items: AnnotationRevision[] }>
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

function stateDraft(
  slideId: string,
  state: AnnotationStoreState,
): Omit<AnnotationDraft, 'byteSize'> {
  return createCompactAnnotationDraft({
    slideId,
    baseVersion: state.version,
    mutations: state.recoveryMutations,
    savedAt: Date.now(),
  })
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(
    'button:not([disabled]),input:not([disabled]),select:not([disabled]),'
    + 'textarea:not([disabled]),[href],[tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hasAttribute('hidden'))
}

interface PendingImport {
  format: 'pathlab' | 'geojson'
  layerName?: string
  data: Record<string, unknown>
}

class StaleWorkspaceOperationError extends Error {
  constructor() {
    super('Annotation operation belongs to a previous slide')
  }
}

function selectionRecords(state: AnnotationStoreState | null): AnnotationRecord[] {
  if (!state) return []
  return [...state.selection]
    .map((id) => state.annotations.get(id))
    .filter((record): record is AnnotationRecord => Boolean(record))
}

function editableClosedTarget(state: AnnotationStoreState | null): AnnotationRecord | null {
  if (!state) return null
  const isEligible = (record: AnnotationRecord) => (
    !record.deletedAt
    && !state.layers.get(record.layerId)?.locked
    && state.layers.get(record.layerId)?.visible !== false
    && (
      record.geometry.type === 'polygon'
      || record.geometry.type === 'rectangle'
      || record.geometry.type === 'ellipse'
    )
  )
  const selected = selectionRecords(state).find(isEligible)
  if (selected) return selected
  const candidates = [...state.annotations.values()].filter(isEligible)
  return candidates.length === 1 ? candidates[0] : null
}

function hasEditableClosedSelection(state: AnnotationStoreState | null): boolean {
  return editableClosedTarget(state) !== null
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

function prepareLayers(layers: AnnotationLayer[]): {
  layers: AnnotationLayer[]
  activeLayer: AnnotationLayer | null
  revealed: boolean
} {
  const activeLayer = layers.find((layer) => !layer.locked) ?? null
  if (!activeLayer || activeLayer.visible) {
    return { layers, activeLayer, revealed: false }
  }
  const prepared = layers.map((layer) => (
    layer.id === activeLayer.id ? { ...layer, visible: true } : layer
  ))
  return {
    layers: prepared,
    activeLayer: prepared.find((layer) => layer.id === activeLayer.id) ?? activeLayer,
    revealed: true,
  }
}

async function triggerDownload(response: Response, filename: string): Promise<void> {
  const blob = await response.blob()
  if (typeof URL.createObjectURL !== 'function') return
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
  } finally {
    URL.revokeObjectURL(url)
  }
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
  const calibrationRef = useRef<AnnotationCalibration | null>(null)
  const styleRef = useRef<AnnotationStyle>(DEFAULT_STYLE)
  const metadataRef = useRef<AnnotationMetadata>(DEFAULT_METADATA)
  const textRef = useRef('Callout')
  const draftTimerRef = useRef<number | null>(null)
  const latestStateRef = useRef<AnnotationStoreState | null>(null)
  const draftPipelineRef = useRef<Promise<void>>(Promise.resolve())
  const workspaceGenerationRef = useRef(0)
  const layerPipelineRef = useRef<{
    generation: number
    promise: Promise<void>
  }>({ generation: 0, promise: Promise.resolve() })
  const layerOpacityDraftRef = useRef(new Map<string, number>())
  const pendingSignatureRef = useRef('[]')
  const recoverySignatureRef = useRef('[]')
  const inspectorTriggerRef = useRef<HTMLButtonElement>(null)
  const inspectorRef = useRef<HTMLElement>(null)
  const workspaceRef = useRef<HTMLElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const listDragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    originX: number
    originY: number
    minX: number
    maxX: number
    minY: number
    maxY: number
  } | null>(null)
  const conflictRef = useRef<HTMLDivElement>(null)
  const conflictReturnFocusRef = useRef<HTMLElement | null>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const coordinateOutputRef = useRef<HTMLOutputElement>(null)
  const [storeState, setStoreState] = useState<AnnotationStoreState | null>(null)
  const [autosave, setAutosave] = useState(EMPTY_AUTOSAVE)
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null)
  const [style, setStyle] = useState(DEFAULT_STYLE)
  const [metadata, setMetadata] = useState(DEFAULT_METADATA)
  const [calloutText, setCalloutText] = useState('Callout')
  const [initializing, setInitializing] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [densityPrompt, setDensityPrompt] = useState<string | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [listOpen, setListOpen] = useState(false)
  const [moreToolsOpen, setMoreToolsOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 760)
  const [resetKey, setResetKey] = useState(0)
  const [operationStatus, setOperationStatus] = useState('Opening annotation workspace…')
  const [importPreview, setImportPreview] = useState<string | null>(null)
  const [pendingImport, setPendingImport] = useState<PendingImport | null>(null)
  const [revisions, setRevisions] = useState<AnnotationRevision[]>([])
  const [selectedRevisionId, setSelectedRevisionId] = useState('')
  const [listOffset, setListOffset] = useState(0)
  const [listPosition, setListPosition] = useState({ x: 0, y: 0 })
  const [listDragging, setListDragging] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const deferredSearch = useDeferredValue(searchInput)
  const attachmentReady = Boolean(storeState)

  activeLayerRef.current = activeLayerId
  styleRef.current = style
  metadataRef.current = metadata
  textRef.current = calloutText

  const moveListBy = useCallback((deltaX: number, deltaY: number) => {
    const workspace = workspaceRef.current
    const list = listRef.current
    if (!workspace || !list || isMobile) return
    const workspaceBounds = workspace.getBoundingClientRect()
    const listBounds = list.getBoundingClientRect()
    const boundedX = Math.max(
      workspaceBounds.left + 8 - listBounds.left,
      Math.min(workspaceBounds.right - 8 - listBounds.right, deltaX),
    )
    const boundedY = Math.max(
      workspaceBounds.top + 8 - listBounds.top,
      Math.min(workspaceBounds.bottom - 8 - listBounds.bottom, deltaY),
    )
    setListPosition((position) => ({
      x: position.x + boundedX,
      y: position.y + boundedY,
    }))
  }, [isMobile])

  const beginListDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (isMobile || event.button !== 0) return
    const workspace = workspaceRef.current
    const list = listRef.current
    if (!workspace || !list) return
    const workspaceBounds = workspace.getBoundingClientRect()
    const listBounds = list.getBoundingClientRect()
    listDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: listPosition.x,
      originY: listPosition.y,
      minX: listPosition.x + workspaceBounds.left + 8 - listBounds.left,
      maxX: listPosition.x + workspaceBounds.right - 8 - listBounds.right,
      minY: listPosition.y + workspaceBounds.top + 8 - listBounds.top,
      maxY: listPosition.y + workspaceBounds.bottom - 8 - listBounds.bottom,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    setListDragging(true)
    event.preventDefault()
  }, [isMobile, listPosition])

  const dragList = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = listDragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    setListPosition({
      x: Math.max(drag.minX, Math.min(drag.maxX, drag.originX + event.clientX - drag.startX)),
      y: Math.max(drag.minY, Math.min(drag.maxY, drag.originY + event.clientY - drag.startY)),
    })
  }, [])

  const endListDrag = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (listDragRef.current?.pointerId !== event.pointerId) return
    listDragRef.current = null
    setListDragging(false)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }, [])

  const moveListWithKeyboard = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    const movement = {
      ArrowLeft: [-24, 0],
      ArrowRight: [24, 0],
      ArrowUp: [0, -24],
      ArrowDown: [0, 24],
    }[event.key]
    if (!movement) return
    event.preventDefault()
    moveListBy(movement[0], movement[1])
  }, [moveListBy])

  const updateCoordinate = useCallback((point: { x: number; y: number } | null) => {
    if (coordinateOutputRef.current) {
      coordinateOutputRef.current.textContent = point
        ? `X ${point.x.toFixed(1)}  Y ${point.y.toFixed(1)}`
        : `SLIDE ${slideId.slice(0, 8).toUpperCase()}`
    }
  }, [slideId])

  const isCurrentWorkspace = useCallback((
    generation: number,
    expectedStore?: AnnotationStore | null,
  ): boolean => (
    workspaceGenerationRef.current === generation
    && (expectedStore === undefined || storeRef.current === expectedStore)
  ), [])

  const requireCurrentWorkspace = useCallback((
    generation: number,
    expectedStore?: AnnotationStore | null,
  ): void => {
    if (!isCurrentWorkspace(generation, expectedStore)) {
      throw new StaleWorkspaceOperationError()
    }
  }, [isCurrentWorkspace])

  const persistDraft = useCallback((state: AnnotationStoreState): Promise<void> => {
    const draft = stateDraft(slideId, state)
    if (!draft.dirty) return draftPipelineRef.current
    const write = draftPipelineRef.current
      .catch(() => undefined)
      .then(() => services.saveDraft(draft))
      .then(() => undefined)
    draftPipelineRef.current = write
    return write
  }, [services, slideId])

  const acknowledgePersistedDraft = useCallback((): Promise<void> => {
    const acknowledgement = draftPipelineRef.current
      .catch(() => undefined)
      .then(() => services.acknowledgeDraft())
    draftPipelineRef.current = acknowledgement
    return acknowledgement
  }, [services])

  const discardPersistedDraft = useCallback((): Promise<void> => {
    const discard = draftPipelineRef.current
      .catch(() => undefined)
      .then(() => services.discardDraft())
    draftPipelineRef.current = discard
    return discard
  }, [services])

  const serializeLayerMutation = useCallback((
    generation: number,
    operation: () => Promise<void>,
  ): Promise<void> => {
    if (layerPipelineRef.current.generation !== generation) {
      layerPipelineRef.current = { generation, promise: Promise.resolve() }
    }
    const pipeline = layerPipelineRef.current
    const result = pipeline.promise
      .catch(() => undefined)
      .then(() => {
        requireCurrentWorkspace(generation)
        return operation()
      })
    pipeline.promise = result.catch(() => undefined)
    return result
  }, [requireCurrentWorkspace])

  const loadRemote = useCallback(async (
    store: AnnotationStore,
    generation = workspaceGenerationRef.current,
  ): Promise<number> => {
    const manifest = await services.getManifest()
    requireCurrentWorkspace(generation, store)
    const items: AnnotationRecord[] = []
    let offset = 0
    do {
      const page = await services.getItems(offset, true)
      requireCurrentWorkspace(generation, store)
      items.push(...page.items)
      if (page.nextOffset === null) break
      offset = page.nextOffset
    } while (items.length < manifest.limits.activeAnnotations + manifest.trashedCount)
    const prepared = prepareLayers(manifest.layers)
    store.load({
      version: manifest.version,
      layers: prepared.layers,
      annotations: items,
    })
    requireCurrentWorkspace(generation, store)
    setActiveLayerId(prepared.activeLayer?.id ?? null)
    activeLayerRef.current = prepared.activeLayer?.id ?? null
    return manifest.version
  }, [requireCurrentWorkspace, services])

  useEffect(() => {
    const generation = workspaceGenerationRef.current + 1
    workspaceGenerationRef.current = generation
    layerPipelineRef.current = { generation, promise: Promise.resolve() }
    let active = true
    let unsubscribe: () => void = () => undefined
    let loadedDraft: AnnotationDraft | null = null
    let draftLoadFailed = false
    latestStateRef.current = null
    pendingSignatureRef.current = '[]'
    recoverySignatureRef.current = '[]'
    storeRef.current = null
    autosaveRef.current = null
    setStoreState(null)
    setAutosave(EMPTY_AUTOSAVE)
    setActiveLayerId(null)
    activeLayerRef.current = null
    calibrationRef.current = null
    setPendingImport(null)
    setImportPreview(null)
    setRevisions([])
    setSelectedRevisionId('')
    setDensityPrompt(null)
    setListOffset(0)
    setListPosition({ x: 0, y: 0 })
    setListDragging(false)
    listDragRef.current = null
    setSearchInput('')
    setInspectorOpen(false)
    setListOpen(false)
    setMoreToolsOpen(false)
    setAdvancedOpen(false)
    layerOpacityDraftRef.current.clear()
    if (coordinateOutputRef.current) {
      coordinateOutputRef.current.textContent = `SLIDE ${slideId.slice(0, 8).toUpperCase()}`
    }
    setInitializing(true)
    setError(null)
    setOperationStatus('Opening annotation workspace…')

    void (async () => {
      try {
        try {
          loadedDraft = await services.loadDraft()
        } catch {
          draftLoadFailed = true
        }
        if (!active) return
        const manifest = await services.getManifest()
        if (!active) return
        calibrationRef.current = manifest.calibration
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
        const prepared = prepareLayers(manifest.layers)
        store.load({
          version: manifest.version,
          layers: prepared.layers,
          annotations: items,
        })
        setActiveLayerId(prepared.activeLayer?.id ?? null)
        activeLayerRef.current = prepared.activeLayer?.id ?? null

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
            const version = await loadRemote(store, generation)
            requireCurrentWorkspace(generation, store)
            await discardPersistedDraft()
            requireCurrentWorkspace(generation, store)
            return version
          },
          onSaveAsDuplicate: async (operations, currentVersion) => {
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
            if (creates.length === 0) return currentVersion
            const result = await services.batch({
              mutationId: crypto.randomUUID(),
              baseVersion: currentVersion,
              operations: creates,
            })
            requireCurrentWorkspace(generation, store)
            await loadRemote(store, generation)
            requireCurrentWorkspace(generation, store)
            await acknowledgePersistedDraft()
            requireCurrentWorkspace(generation, store)
            return result.version
          },
          onChange: (snapshot) => {
            if (!active) return
            setAutosave(snapshot)
            if (snapshot.status === 'saved' && snapshot.dirtyCount === 0) {
              void acknowledgePersistedDraft().catch(() => undefined)
            }
          },
        })
        autosaveRef.current = saver
        unsubscribe = store.subscribe((next) => {
          if (!active) return
          latestStateRef.current = next
          setStoreState(next)
          const signature = JSON.stringify(next.pendingMutationBatches)
          if (signature !== pendingSignatureRef.current) {
            pendingSignatureRef.current = signature
            saver.replacePendingBatches(next.pendingMutationBatches)
          }
          const recoverySignature = JSON.stringify(next.recoveryMutations)
          if (recoverySignature !== recoverySignatureRef.current) {
            recoverySignatureRef.current = recoverySignature
            if (draftTimerRef.current !== null) window.clearTimeout(draftTimerRef.current)
            draftTimerRef.current = null
            if (next.recoveryMutations.length > 0) {
              draftTimerRef.current = window.setTimeout(() => {
                draftTimerRef.current = null
                void persistDraft(next).catch((caught) => {
                  if (active) {
                    setError(caught instanceof Error ? caught.message : 'Local draft could not be saved')
                  }
                })
              }, 250)
            }
          }
        })
        latestStateRef.current = store.getState()
        setStoreState(store.getState())
        if (loadedDraft?.dirty) {
          replayDraft(store, loadedDraft)
          if (store.getState().recoveryMutations.length === 0) {
            await acknowledgePersistedDraft()
            if (!active) return
            setOperationStatus('Reconciled saved local changes')
          } else {
            setOperationStatus('Recovered unsaved local changes')
          }
        } else {
          setOperationStatus(draftLoadFailed
            ? 'Annotations ready; local draft recovery unavailable'
            : prepared.revealed
              ? 'Annotations ready; active layer shown'
              : 'Annotations ready')
        }
        setInitializing(false)
      } catch (caught) {
        if (!active) return
        if (loadedDraft?.dirty) {
          setError('Server unavailable; unsaved local draft retained for recovery')
          setOperationStatus('Annotations offline; unsaved local draft retained')
        } else {
          setError(caught instanceof Error ? caught.message : 'Annotations could not be initialized')
          setOperationStatus('Annotations paused; slide navigation remains available')
        }
        setInitializing(false)
      }
    })()

    return () => {
      const latest = latestStateRef.current
      if (latest?.recoveryMutations.length) {
        void persistDraft(latest).catch(() => undefined)
      }
      active = false
      if (workspaceGenerationRef.current === generation) {
        workspaceGenerationRef.current += 1
      }
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
  }, [
    acknowledgePersistedDraft,
    discardPersistedDraft,
    loadRemote,
    persistDraft,
    requireCurrentWorkspace,
    resetKey,
    services,
    slideId,
  ])

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
          calibration: () => calibrationRef.current,
          onCoordinate: updateCoordinate,
          onDensity: setDensityPrompt,
          onNotice: setOperationStatus,
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
  }, [attachmentReady, error, onAttachmentChange, updateCoordinate])

  useEffect(() => {
    const updateMobile = () => setIsMobile(window.innerWidth <= 760)
    window.addEventListener('resize', updateMobile)
    return () => window.removeEventListener('resize', updateMobile)
  }, [])

  useEffect(() => {
    const inspector = inspectorRef.current
    if (!isMobile || !inspectorOpen || !inspector) return
    const trigger = inspectorTriggerRef.current
    const focusable = focusableElements(inspector)
    focusable[0]?.focus()
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const current = focusableElements(inspector)
      const first = current[0]
      const last = current.at(-1)
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    inspector.addEventListener('keydown', trap)
    return () => {
      inspector.removeEventListener('keydown', trap)
      trigger?.focus()
    }
  }, [inspectorOpen, isMobile])

  const conflictOpen = Boolean(autosave.conflict)
  useEffect(() => {
    const dialog = conflictRef.current
    if (!conflictOpen || !dialog) return
    conflictReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    const focusable = focusableElements(dialog)
    focusable[0]?.focus()
    const trap = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const current = focusableElements(dialog)
      const first = current[0]
      const last = current.at(-1)
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    dialog.addEventListener('keydown', trap)
    return () => {
      dialog.removeEventListener('keydown', trap)
      conflictReturnFocusRef.current?.focus()
      conflictReturnFocusRef.current = null
    }
  }, [conflictOpen])

  const store = storeRef.current
  useEffect(() => {
    store?.setFilter({ search: deferredSearch })
  }, [deferredSearch, store])
  const selected = selectionRecords(storeState)
  const primary = selected[0] ?? null
  const selectedLayer = primary ? storeState?.layers.get(primary.layerId) : null
  const selectionTitle = selected.length === 1
    ? primary?.metadata.title
      || primary?.metadata.classification
      || `${primary?.geometry.type ?? 'Annotation'} annotation`
    : `${selected.length} annotations`
  const selectionKind = selected.length === 1
    ? `${primary?.geometry.type.replace('-', ' ') ?? 'Annotation'}${selectedLayer ? ` · ${selectedLayer.name}` : ''}`
    : 'Multiple selection'
  const hasActiveSelection = selected.some((record) => !record.deletedAt)
  const hasDeletedSelection = selected.some((record) => Boolean(record.deletedAt))
  const booleanReady = selected.length >= 2 && selected.every((record) => (
    !record.deletedAt
    && record.geometry.type === 'polygon'
    && !storeState?.layers.get(record.layerId)?.locked
  ))
  const brushSubtractReady = hasEditableClosedSelection(storeState)
  const currentTool = storeState?.tool ?? 'hand'
  const activeAnnotationCount = useMemo(() => (
    [...(storeState?.annotations.values() ?? [])]
      .filter((record) => !record.deletedAt)
      .length
  ), [storeState?.annotations])
  const hiddenLayerCount = useMemo(() => (
    [...(storeState?.layers.values() ?? [])]
      .filter((layer) => !layer.visible)
      .length
  ), [storeState?.layers])
  const classifications = useMemo(() => (
    [...new Set(
      [...(storeState?.annotations.values() ?? [])]
        .map((record) => record.metadata.classification)
        .filter(Boolean),
    )].sort((left, right) => left.localeCompare(right))
  ), [storeState?.annotations])
  const tags = useMemo(() => (
    [...new Set(
      [...(storeState?.annotations.values() ?? [])]
        .flatMap((record) => record.metadata.tags),
    )].sort((left, right) => left.localeCompare(right))
  ), [storeState?.annotations])
  const visibleRecords = store?.visibleAnnotations() ?? []
  const visibleListRecords = visibleRecords.slice(
    listOffset,
    listOffset + OBJECT_REGISTER_PAGE_SIZE,
  )
  const filterSignature = storeState
    ? [
      storeState.filter.search,
      [...storeState.filter.layerIds].join(','),
      [...(storeState.filter.classifications ?? [])].join(','),
      [...(storeState.filter.tags ?? [])].join(','),
      String(storeState.filter.includeDeleted),
    ].join('|')
    : ''
  useEffect(() => {
    setListOffset(0)
  }, [filterSignature])

  const setTool = useCallback((tool: AnnotationTool) => {
    if (tool === 'brush-subtract') {
      const localStore = storeRef.current
      const target = editableClosedTarget(localStore?.getState() ?? null)
      if (!localStore || !target) {
        setOperationStatus('Select an unlocked polygon, rectangle, or ellipse before erasing')
        return
      }
      if (!localStore.getState().selection.has(target.id)) localStore.select([target.id])
    }
    storeRef.current?.setTool(tool)
    setOperationStatus(`${TOOLS.find((item) => item.tool === tool)?.label ?? tool} active`)
    setMoreToolsOpen(false)
  }, [])

  useEffect(() => {
    if ((storeState?.selection.size ?? 0) > 0) setInspectorOpen(true)
  }, [storeState?.selection])

  const flush = useCallback(async (
    generation = workspaceGenerationRef.current,
    expectedStore = storeRef.current,
  ) => {
    const saver = autosaveRef.current
    if (!saver || saver.snapshot().dirtyCount === 0) {
      setOperationStatus('No changes to save')
      return
    }
    setOperationStatus('Saving annotations…')
    await saver.flush()
    requireCurrentWorkspace(generation, expectedStore)
    const next = saver.snapshot()
    setOperationStatus(next.status === 'saved'
      ? 'Annotations saved'
      : next.error ?? `Save ${next.status}`)
  }, [requireCurrentWorkspace])

  const prepareVersionedOperation = useCallback(async (
    generation = workspaceGenerationRef.current,
    expectedStore = storeRef.current,
  ): Promise<number> => {
    await flush(generation, expectedStore)
    requireCurrentWorkspace(generation, expectedStore)
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
    const localStore = expectedStore
    if (!localStore) throw new Error('Annotation workspace is not ready')
    return localStore.getState().version
  }, [flush, requireCurrentWorkspace])

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
        setListOpen(false)
        setMoreToolsOpen(false)
        setAdvancedOpen(false)
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

  const reload = async (
    generation = workspaceGenerationRef.current,
    localStore = storeRef.current,
  ) => {
    if (!localStore) return
    setOperationStatus('Reloading annotations…')
    try {
      const version = await loadRemote(localStore, generation)
      requireCurrentWorkspace(generation, localStore)
      autosaveRef.current?.reset(version)
      await discardPersistedDraft()
      requireCurrentWorkspace(generation, localStore)
      setOperationStatus('Annotations reloaded from server')
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
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
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    await serializeLayerMutation(generation, async () => {
      try {
        const baseVersion = await prepareVersionedOperation(generation, expectedStore)
        requireCurrentWorkspace(generation, expectedStore)
        const layer = await services.createLayer({
          mutationId: crypto.randomUUID(),
          baseVersion,
          name: `Layer ${(expectedStore?.getState().layers.size ?? 0) + 1}`,
          sortOrder: expectedStore?.getState().layers.size ?? 0,
        })
        requireCurrentWorkspace(generation, expectedStore)
        if (!expectedStore) return
        const version = await loadRemote(expectedStore, generation)
        requireCurrentWorkspace(generation, expectedStore)
        autosaveRef.current?.reset(version)
        if (!layer.locked) {
          setActiveLayerId(layer.id)
          activeLayerRef.current = layer.id
        }
        setOperationStatus(`${layer.name} created`)
      } catch (caught) {
        if (caught instanceof StaleWorkspaceOperationError) return
        setError(caught instanceof Error ? caught.message : 'Layer could not be created')
      }
    })
  }

  const persistLayerPatch = async (
    layer: AnnotationLayer,
    patch: Partial<Pick<AnnotationLayer, 'name' | 'visible' | 'locked' | 'opacity'>>,
  ) => {
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    await serializeLayerMutation(generation, async () => {
      try {
        const baseVersion = await prepareVersionedOperation(generation, expectedStore)
        requireCurrentWorkspace(generation, expectedStore)
        expectedStore?.updateLayer(layer.id, patch)
        await services.updateLayer(layer.id, {
          mutationId: crypto.randomUUID(),
          baseVersion,
          ...patch,
        })
        requireCurrentWorkspace(generation, expectedStore)
        if (!expectedStore) return
        const version = await loadRemote(expectedStore, generation)
        requireCurrentWorkspace(generation, expectedStore)
        autosaveRef.current?.reset(version)
      } catch (caught) {
        if (caught instanceof StaleWorkspaceOperationError) return
        setError(caught instanceof Error ? caught.message : 'Layer update failed')
        await reload(generation, expectedStore)
      }
    })
  }

  const reorderLayer = async (layerId: string, direction: -1 | 1) => {
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    await serializeLayerMutation(generation, async () => {
      try {
        const baseVersion = await prepareVersionedOperation(generation, expectedStore)
        requireCurrentWorkspace(generation, expectedStore)
        if (!expectedStore) return
        const ordered = [...expectedStore.getState().layers.values()]
          .sort((left, right) => left.sortOrder - right.sortOrder)
        const index = ordered.findIndex((layer) => layer.id === layerId)
        const destination = index + direction
        if (index < 0 || destination < 0 || destination >= ordered.length) return
        const [moved] = ordered.splice(index, 1)
        ordered.splice(destination, 0, moved)
        const normalized = ordered.map((layer, sortOrder) => ({ ...layer, sortOrder }))
        expectedStore.setLayers(normalized)
        let version = baseVersion
        for (const layer of normalized) {
          const previous = storeState?.layers.get(layer.id)
          if (previous?.sortOrder === layer.sortOrder) continue
          const result = await services.updateLayer(layer.id, {
            mutationId: crypto.randomUUID(),
            baseVersion: version,
            sortOrder: layer.sortOrder,
          })
          requireCurrentWorkspace(generation, expectedStore)
          version = result.version
        }
        const loadedVersion = await loadRemote(expectedStore, generation)
        requireCurrentWorkspace(generation, expectedStore)
        autosaveRef.current?.reset(loadedVersion)
      } catch (caught) {
        if (caught instanceof StaleWorkspaceOperationError) return
        setError(caught instanceof Error ? caught.message : 'Layer reorder failed')
        await reload(generation, expectedStore)
      }
    })
  }

  const stageLayerOpacity = (layer: AnnotationLayer, opacity: number) => {
    layerOpacityDraftRef.current.set(layer.id, opacity)
    storeRef.current?.updateLayer(layer.id, { opacity })
  }

  const commitLayerOpacity = async (layer: AnnotationLayer) => {
    const opacity = layerOpacityDraftRef.current.get(layer.id)
    if (opacity === undefined) return
    layerOpacityDraftRef.current.delete(layer.id)
    await persistLayerPatch(layer, { opacity })
  }

  const browseRevisions = async () => {
    if (!primary || !storeState) {
      setOperationStatus('Select an annotation to browse revisions')
      return
    }
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    try {
      await prepareVersionedOperation(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      const current = expectedStore?.getState().annotations.get(primary.id)
      if (!current) throw new Error('Selected annotation is no longer available')
      const history = await services.revisions(current.id)
      requireCurrentWorkspace(generation, expectedStore)
      const bounded = history.items.slice(0, 25)
      setRevisions(bounded)
      setSelectedRevisionId('')
      if (bounded.length === 0) {
        setOperationStatus('No earlier revision is available')
        return
      }
      setOperationStatus(`Loaded ${bounded.length} revisions; choose one to preview`)
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
      setError(caught instanceof Error ? caught.message : 'Revision history failed')
    }
  }

  const restoreSelectedRevision = async () => {
    if (!primary || !selectedRevisionId) {
      setOperationStatus('Choose a revision before restoring')
      return
    }
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    try {
      const baseVersion = await prepareVersionedOperation(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      const current = expectedStore?.getState().annotations.get(primary.id)
      if (!current) throw new Error('Selected annotation is no longer available')
      await services.restoreRevision(current.id, selectedRevisionId, {
        mutationId: crypto.randomUUID(),
        baseVersion,
        version: current.version,
      })
      requireCurrentWorkspace(generation, expectedStore)
      await reload(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      setRevisions([])
      setSelectedRevisionId('')
      setOperationStatus('Annotation revision restored')
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
      setError(caught instanceof Error ? caught.message : 'Revision restore failed')
    }
  }

  const importFile = async (file: File | undefined) => {
    if (!file || !store || !storeState) return
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    try {
      setPendingImport(null)
      if (file.size > MAX_IMPORT_FILE_BYTES) {
        throw new Error('Import exceeds the 8 MiB limit')
      }
      const text = await file.text()
      requireCurrentWorkspace(generation, expectedStore)
      const data = JSON.parse(text) as Record<string, unknown>
      const preview = expectedStore?.previewImport(data)
      if (!preview) throw new Error('Annotation workspace is not ready')
      setImportPreview(
        `${preview.annotationCount.toLocaleString()} annotations · ${preview.vertexCount.toLocaleString()} vertices`,
      )
      if (!preview.valid || preview.format === 'unknown') {
        throw new Error(preview.errors[0] ?? 'Import is not valid')
      }
      const candidate: PendingImport = {
        format: preview.format,
        ...(preview.format === 'geojson' ? {
          layerName: file.name.replace(/\.[^.]+$/, '').slice(0, 160)
            || 'Imported annotations',
        } : {}),
        data,
      }
      const baseVersion = storeRef.current?.getState().version ?? storeState.version
      if (annotationImportRequestBytes({
        mutationId: '00000000-0000-4000-8000-000000000000',
        baseVersion,
        ...candidate,
      }) > MAX_ANNOTATION_IMPORT_REQUEST_BYTES) {
        throw new Error('Serialized import request exceeds the 8 MiB limit')
      }
      setPendingImport(candidate)
      setOperationStatus('Import preview ready; confirm to create a new layer')
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
      const message = caught instanceof Error ? caught.message : 'Import failed'
      setImportPreview(message)
      setOperationStatus(message)
    } finally {
      if (isCurrentWorkspace(generation, expectedStore) && importRef.current) {
        importRef.current.value = ''
      }
    }
  }

  const confirmImport = async () => {
    if (!pendingImport) return
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    try {
      const baseVersion = await prepareVersionedOperation(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      const request = {
        mutationId: crypto.randomUUID(),
        baseVersion,
        ...pendingImport,
      }
      if (annotationImportRequestBytes(request) > MAX_ANNOTATION_IMPORT_REQUEST_BYTES) {
        throw new Error('Serialized import request exceeds the 8 MiB limit')
      }
      await services.importDocument(request)
      requireCurrentWorkspace(generation, expectedStore)
      setPendingImport(null)
      setImportPreview(null)
      await reload(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      setOperationStatus('Import completed')
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
      setError(caught instanceof Error ? caught.message : 'Import failed')
    }
  }

  const exportDocument = async (format: 'pathlab' | 'geojson' | 'csv') => {
    const generation = workspaceGenerationRef.current
    const expectedStore = storeRef.current
    try {
      await prepareVersionedOperation(generation, expectedStore)
      requireCurrentWorkspace(generation, expectedStore)
      const response = await services.exportDocument(format)
      requireCurrentWorkspace(generation, expectedStore)
      await triggerDownload(
        response,
        `${slideName}-annotations.${format === 'pathlab' ? 'json' : format}`,
      )
      requireCurrentWorkspace(generation, expectedStore)
      setOperationStatus(`${format.toUpperCase()} export ready`)
    } catch (caught) {
      if (caught instanceof StaleWorkspaceOperationError) return
      setError(caught instanceof Error ? caught.message : 'Export failed')
    }
  }

  const measurement = primary && store ? store.measure(primary.id) : null
  const selectedRevision = revisions.find((revision) => revision.id === selectedRevisionId) ?? null

  return (
    <AnnotationErrorBoundary resetKey={resetKey} onRetry={retry}>
      <section
        ref={workspaceRef}
        className={`annotation-workspace${inspectorOpen ? ' annotation-workspace--inspector' : ''}`}
        aria-label="Annotations"
      >
        <div className="annotation-toolstrip" role="toolbar" aria-label="Annotation tools">
          {CORE_TOOLS.map((item) => {
            const ToolIcon = item.icon
            const active = currentTool === item.tool
            return (
              <button
                type="button"
                key={item.tool}
                aria-label={item.label}
                aria-pressed={active}
                title={`${item.label} (${item.shortcut})`}
                onClick={() => setTool(item.tool)}
              >
                <span aria-hidden="true">
                  <ToolIcon size={18} weight={active ? 'fill' : 'regular'} />
                </span>
              </button>
            )
          })}
          <button
            type="button"
            className="annotation-more-trigger"
            aria-label="More annotation tools"
            aria-pressed={MORE_TOOLS.some((item) => item.tool === currentTool)}
            aria-expanded={moreToolsOpen}
            aria-controls="annotation-more-tools"
            onClick={() => setMoreToolsOpen((open) => !open)}
          >
            <span aria-hidden="true"><DotsThree size={19} weight="bold" /></span>
          </button>
          {moreToolsOpen ? (
            <div
              id="annotation-more-tools"
              className="annotation-more-tools"
              role="group"
              aria-label="More annotation tools"
            >
              {MORE_TOOLS.map((item) => {
                const ToolIcon = item.icon
                const active = currentTool === item.tool
                const unavailable = item.tool === 'brush-subtract' && !brushSubtractReady
                return (
                  <button
                    type="button"
                    key={item.tool}
                    aria-label={item.label}
                    aria-pressed={active}
                    aria-disabled={unavailable}
                    title={unavailable
                      ? 'Select an unlocked polygon, rectangle, or ellipse before erasing'
                      : `${item.label} (${item.shortcut})`}
                    onClick={() => setTool(item.tool)}
                  >
                    <span aria-hidden="true">
                      <ToolIcon size={18} weight={active ? 'fill' : 'regular'} />
                    </span>
                  </button>
                )
              })}
            </div>
          ) : null}
        </div>

        <div className="annotation-commandbar" aria-label="Annotation commands">
          <div className="annotation-save-cluster">
            <button
              type="button"
              aria-label="Undo"
              disabled={!store?.canUndo()}
              onClick={() => store?.undo()}
            >
              <ArrowCounterClockwise aria-hidden="true" />
              Undo
            </button>
            <button
              type="button"
              aria-label="Redo"
              disabled={!store?.canRedo()}
              onClick={() => store?.redo()}
            >
              <ArrowClockwise aria-hidden="true" />
              Redo
            </button>
            <button
              type="button"
              aria-label="Save annotations"
              disabled={initializing || autosave.dirtyCount === 0}
              onClick={() => void flush()}
            >
              <FloppyDisk />
              <span>Save</span>
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
          <button
            type="button"
            className="annotation-list-toggle"
            aria-label={listOpen ? 'Close annotations' : 'Open annotations'}
            aria-expanded={listOpen}
            onClick={() => setListOpen((open) => !open)}
          >
            <MagnifyingGlass aria-hidden="true" />
            <span>Annotations</span>
            <strong>{activeAnnotationCount.toLocaleString()}</strong>
          </button>
          <button
            ref={inspectorTriggerRef}
            type="button"
            className="annotation-inspector-toggle"
            aria-label={inspectorOpen ? 'Close annotation inspector' : 'Open annotation inspector'}
            aria-expanded={inspectorOpen}
            onClick={() => {
              if (inspectorOpen) setAdvancedOpen(false)
              setInspectorOpen((open) => !open)
            }}
          >
            <SidebarSimple />
          </button>
        </div>

        {listOpen ? (
          <div
            ref={listRef}
            className="annotation-list"
            aria-label="Annotation list"
            data-dragging={listDragging ? 'true' : undefined}
            style={{
              transform: isMobile
                ? undefined
                : `translate3d(${listPosition.x}px, ${listPosition.y}px, 0)`,
            }}
          >
            <div
              className="annotation-panel-heading annotation-list-drag-handle"
              role="button"
              tabIndex={isMobile ? -1 : 0}
              aria-label="Move annotation list"
              aria-describedby="annotation-list-move-hint"
              onPointerDown={beginListDrag}
              onPointerMove={dragList}
              onPointerUp={endListDrag}
              onPointerCancel={endListDrag}
              onKeyDown={moveListWithKeyboard}
            >
              <div>
                <span className="annotation-kicker">Annotations</span>
                <strong>{slideName}</strong>
              </div>
              <div className="annotation-panel-heading-actions">
                <span>{activeAnnotationCount.toLocaleString()}</span>
                <DotsSixVertical aria-hidden="true" />
              </div>
              <span id="annotation-list-move-hint" className="visually-hidden">
                Drag this header or use the arrow keys to move the annotation list.
              </span>
            </div>
            {hiddenLayerCount > 0 ? (
              <p className="annotation-hidden-notice">
                {hiddenLayerCount} hidden {hiddenLayerCount === 1 ? 'layer' : 'layers'}
              </p>
            ) : null}
            <label className="annotation-search">
              <MagnifyingGlass aria-hidden="true" />
              <span className="visually-hidden">Search annotations</span>
              <input
                type="search"
                aria-label="Search annotations"
                placeholder="Search title, class, tag…"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
            </label>
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
              {visibleListRecords.map((record, index) => (
                <button
                  type="button"
                  key={record.id}
                  data-annotation-row=""
                  className={storeState?.selection.has(record.id) ? 'is-selected' : ''}
                  onClick={(event) => store?.select([record.id], event.shiftKey)}
                  onDoubleClick={() => zoomTo(record)}
                >
                  <span>{String(listOffset + index + 1).padStart(3, '0')}</span>
                  <span>
                    <strong>{record.metadata.title || `${record.geometry.type} annotation`}</strong>
                    <small>{record.metadata.classification || record.geometry.type}</small>
                  </span>
                  <i style={{ background: record.style.strokeColor }} />
                </button>
              ))}
              {listOffset > 0 ? (
                <button
                  type="button"
                  className="annotation-list-more"
                  onClick={() => setListOffset((offset) => Math.max(
                    0,
                    offset - OBJECT_REGISTER_PAGE_SIZE,
                  ))}
                >
                  Show previous annotations
                </button>
              ) : null}
              {listOffset + visibleListRecords.length < visibleRecords.length ? (
                <button
                  type="button"
                  className="annotation-list-more"
                  onClick={() => setListOffset((offset) => Math.min(
                    offset + OBJECT_REGISTER_PAGE_SIZE,
                    Math.max(0, visibleRecords.length - 1),
                  ))}
                >
                  Show {Math.min(
                    OBJECT_REGISTER_PAGE_SIZE,
                    visibleRecords.length - listOffset - visibleListRecords.length,
                  )} more annotations
                </button>
              ) : null}
              {!initializing && visibleRecords.length === 0 ? (
                <p className="annotation-empty">Choose a tool and mark the slide.</p>
              ) : null}
            </div>
          </div>
        ) : null}

        {inspectorOpen ? (
          <aside
            ref={inspectorRef}
            className="annotation-inspector"
            role={isMobile ? 'dialog' : 'region'}
            aria-modal={isMobile ? true : undefined}
            aria-label="Annotation inspector"
          >
            <div className="annotation-panel-heading">
              <div>
                <span className="annotation-kicker">CONTROL SURFACE</span>
                <strong>Inspector</strong>
              </div>
              <button
                type="button"
                aria-label="Close annotation inspector"
                onClick={() => {
                  setAdvancedOpen(false)
                  setInspectorOpen(false)
                }}
              >
                <X />
              </button>
            </div>

            <div className="annotation-inspector-scroll">
              {selected.length > 0 ? (
                <section className="annotation-selection-card">
                  <div className="annotation-selection-summary">
                    <span className="annotation-selection-icon" aria-hidden="true">
                      <Selection />
                    </span>
                    <div>
                      <h2>Selected</h2>
                      <strong>{selectionTitle}</strong>
                      <small>{selectionKind}</small>
                    </div>
                    <span className="annotation-selection-count">{selected.length}</span>
                  </div>
                  <div className="annotation-quick-actions" aria-label="Selection actions">
                    <button
                      type="button"
                      className="is-primary"
                      aria-label="Zoom to selected annotation"
                      disabled={!primary}
                      onClick={() => primary && zoomTo(primary)}
                    >
                      <Crosshair />
                      <span>Zoom</span>
                    </button>
                    <button
                      type="button"
                      aria-label="Duplicate selected annotations"
                      disabled={!hasActiveSelection}
                      onClick={() => store?.duplicate(storeState?.selection ?? [])}
                    >
                      <Plus />
                      <span>Duplicate</span>
                    </button>
                    <button
                      type="button"
                      className="is-danger"
                      aria-label="Delete selected annotations"
                      disabled={!hasActiveSelection}
                      onClick={() => store?.delete(storeState?.selection ?? [])}
                    >
                      <Trash />
                      <span>Delete</span>
                    </button>
                  </div>
                  <div className="annotation-clipboard-actions" aria-label="Clipboard actions">
                    <button
                      type="button"
                      aria-label="Copy selected annotations"
                      disabled={!hasActiveSelection}
                      onClick={() => store?.copy()}
                    >
                      <Copy /> Copy
                    </button>
                    <button
                      type="button"
                      aria-label="Paste annotations"
                      disabled={!store?.canPaste()}
                      onClick={() => store?.paste()}
                    >
                      <ClipboardText /> Paste
                    </button>
                    {hasDeletedSelection ? (
                      <button
                        type="button"
                        aria-label="Restore selected annotations"
                        onClick={() => store?.restore(storeState?.selection ?? [])}
                      >
                        Restore
                      </button>
                    ) : null}
                  </div>
                  {booleanReady ? (
                    <div className="annotation-shape-operations">
                      <div>
                        <strong>Combine polygons</strong>
                        <small>Apply one operation to the selected shapes.</small>
                      </div>
                      <div className="annotation-boolean-grid" aria-label="Boolean operations">
                        {(['union', 'subtract', 'intersection', 'split'] as const).map((operation) => (
                          <button
                            type="button"
                            key={operation}
                            onClick={() => void applyBoolean(operation)}
                          >
                            {operation === 'intersection' ? 'Intersect' : operation}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>
              ) : null}

              <section className="annotation-details-section">
                <h2>Details</h2>
                <label>
                  <span>{primary ? 'Annotation layer' : 'Drawing layer'}</span>
                  <select
                    aria-label={primary ? 'Annotation layer' : 'Drawing layer'}
                    value={primary?.layerId ?? activeLayerId ?? ''}
                    onChange={(event) => {
                      const layerId = event.target.value
                      const targetLayer = storeState?.layers.get(layerId)
                      if (!layerId || targetLayer?.locked) return
                      setActiveLayerId(layerId)
                      activeLayerRef.current = layerId
                      if (store && selected.length > 0) {
                        store.bulkUpdate(selected.map((record) => record.id), { layerId })
                      }
                    }}
                  >
                    <option value="">No editable layer</option>
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
              </section>

              <button
                type="button"
                className="annotation-advanced-toggle"
                aria-label={advancedOpen
                  ? 'Hide advanced annotation details'
                  : 'Show advanced annotation details'}
                aria-expanded={advancedOpen}
                onClick={() => setAdvancedOpen((open) => !open)}
              >
                <span>Advanced details</span>
                <CaretDown aria-hidden="true" />
              </button>

              {advancedOpen ? (
                <>
              <section>
                <h2>More details</h2>
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
                          disabled={layer.locked}
                          onClick={() => {
                            setActiveLayerId(layer.id)
                            activeLayerRef.current = layer.id
                          }}
                        >
                          {layer.name}
                        </button>
                        <button
                          type="button"
                          aria-label={`Move ${layer.name} up`}
                          disabled={index === 0}
                          onClick={() => void reorderLayer(layer.id, -1)}
                        >
                          <CaretUp />
                        </button>
                        <button
                          type="button"
                          aria-label={`Move ${layer.name} down`}
                          disabled={index === layers.length - 1}
                          onClick={() => void reorderLayer(layer.id, 1)}
                        >
                          <CaretDown />
                        </button>
                        <label title="Visible">
                          <input
                            type="checkbox"
                            aria-label={`Show ${layer.name}`}
                            checked={layer.visible}
                            onChange={(event) => void persistLayerPatch(
                              layer,
                              { visible: event.target.checked },
                            )}
                          />
                        </label>
                        <label title="Locked">
                          <input
                            type="checkbox"
                            aria-label={`Lock ${layer.name}`}
                            checked={layer.locked}
                            onChange={(event) => void persistLayerPatch(
                              layer,
                              { locked: event.target.checked },
                            )}
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
                            onChange={(event) => stageLayerOpacity(layer, Number(event.target.value))}
                            onPointerUp={() => void commitLayerOpacity(layer)}
                            onKeyUp={() => void commitLayerOpacity(layer)}
                            onBlur={() => void commitLayerOpacity(layer)}
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
                {pendingImport ? (
                  <div className="annotation-confirm-row">
                    <button
                      type="button"
                      aria-label="Confirm annotation import"
                      onClick={() => void confirmImport()}
                    >
                      Confirm import
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setPendingImport(null)
                        setImportPreview(null)
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="annotation-restore-revision"
                  aria-label="Browse annotation revisions"
                  onClick={() => void browseRevisions()}
                >
                  <FolderOpen /> Revision history
                </button>
                <button
                  type="button"
                  className="annotation-reload"
                  aria-label="Reload annotations"
                  onClick={() => void reload()}
                >
                  <ArrowClockwise /> Reload from server
                </button>
                {revisions.length > 0 ? (
                  <div className="annotation-revision-browser">
                    <label>
                      <span>Revision</span>
                      <select
                        aria-label="Annotation revisions"
                        value={selectedRevisionId}
                        onChange={(event) => setSelectedRevisionId(event.target.value)}
                      >
                        <option value="">Choose a revision</option>
                        {revisions.map((revision) => (
                          <option key={revision.id} value={revision.id}>
                            v{revision.version} · {new Date(revision.createdAt).toLocaleString()}
                          </option>
                        ))}
                      </select>
                    </label>
                    {selectedRevision ? (
                      <div className="annotation-revision-preview" aria-live="polite">
                        <strong>{selectedRevision.metadata.title || 'Untitled annotation'}</strong>
                        <span>{selectedRevision.metadata.classification || selectedRevision.geometry.type}</span>
                        <small>Version {selectedRevision.version}</small>
                      </div>
                    ) : null}
                    <button
                      type="button"
                      aria-label="Restore selected revision"
                      disabled={!selectedRevision}
                      onClick={() => void restoreSelectedRevision()}
                    >
                      Restore selected revision
                    </button>
                  </div>
                ) : null}
              </section>
                </>
              ) : null}
            </div>
          </aside>
        ) : null}

        <div className="annotation-data-cue" aria-hidden="true">
          <output ref={coordinateOutputRef}>
            {`SLIDE ${slideId.slice(0, 8).toUpperCase()}`}
          </output>
          <span>
            {densityPrompt ?? `${currentTool.toUpperCase()} · HOLD SPACE TO PAN · IMAGE PX`}
          </span>
        </div>

        {error ? (
          <div className="annotation-failure" role="alert">
            <strong>Annotations paused</strong>
            <span>{error}. Pan, zoom, and the unsaved local draft remain available.</span>
            <button type="button" onClick={retry}>Retry annotations</button>
          </div>
        ) : null}

        {autosave.conflict ? (
          <div
            ref={conflictRef}
            className="annotation-conflict"
            role="alertdialog"
            aria-modal="true"
            aria-label="Annotation save conflict"
          >
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
