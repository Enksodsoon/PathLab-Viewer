import type { BooleanWorkerClient } from './boolean'
import { createBooleanWorkerClient } from './boolean'
import {
  duplicateAnnotation,
  editVertex as editGeometryVertex,
  geometryBounds,
  geometryVertexCount,
  moveGeometry,
  resizeGeometry,
} from './geometry'
import {
  exportMeasurementsCsv,
  previewImport,
  toGeoJson,
  type CsvMeasurementRow,
  type GeoJsonFeatureCollection,
} from './interchange'
import { measureGeometry } from './measurement'
import type {
  AnnotationBounds,
  AnnotationCalibration,
  AnnotationFilter,
  AnnotationInput,
  AnnotationLayer,
  AnnotationMetadata,
  AnnotationMutation,
  AnnotationRecord,
  AnnotationStyle,
  AnnotationTool,
  ImportPreview,
  PathLabAnnotationDocument,
  PolygonBooleanOperation,
  PolygonGeometry,
} from './types'
import {
  ANNOTATION_SCHEMA,
  MAX_ACTIVE_ANNOTATIONS,
  MAX_ANNOTATION_LAYERS,
  MAX_VERTICES_PER_SHAPE,
} from './types'

export interface AnnotationOverlayAttachment {
  render(): void
  detach(): void
  restoreNavigation(): void
}

export interface AnnotationStoreState {
  slideId: string
  version: number
  tool: AnnotationTool
  layers: Map<string, AnnotationLayer>
  annotations: Map<string, AnnotationRecord>
  selection: Set<string>
  filter: AnnotationFilter
  pendingMutations: AnnotationMutation[]
  autosaveStatus: string
  overlayError: string | null
}

interface HistoryEntry {
  before: Map<string, AnnotationRecord | null>
  after: Map<string, AnnotationRecord | null>
  mutations: AnnotationMutation[]
}

export interface AnnotationStoreOptions {
  slideId: string
  calibration?: AnnotationCalibration | null
  bounds?: { width: number; height: number }
  idFactory?: () => string
  booleanClient?: BooleanWorkerClient
  now?: () => Date
  maxAnnotations?: number
  maxLayers?: number
}

export interface AnnotationStore {
  getState(): AnnotationStoreState
  subscribe(listener: (state: AnnotationStoreState) => void): () => void
  load(payload: {
    version: number
    layers: AnnotationLayer[]
    annotations: AnnotationRecord[]
  }): void
  setTool(tool: AnnotationTool): void
  select(ids: Iterable<string>, additive?: boolean): void
  clearSelection(): void
  setFilter(filter: Partial<AnnotationFilter>): void
  visibleAnnotations(): AnnotationRecord[]
  create(input: AnnotationInput): void
  update(
    id: string,
    patch: Partial<Pick<AnnotationInput, 'layerId' | 'geometry' | 'style' | 'metadata'>>,
  ): void
  bulkUpdate(
    ids: Iterable<string>,
    patch: Partial<Pick<AnnotationInput, 'layerId' | 'style' | 'metadata'>>,
  ): void
  move(ids: Iterable<string>, deltaX: number, deltaY: number): void
  resize(id: string, bounds: AnnotationBounds): void
  editVertex(id: string, vertexIndex: number, point: { x: number; y: number }): void
  duplicate(ids: Iterable<string>, offset?: { x: number; y: number }): string[]
  copy(): void
  paste(offset?: { x: number; y: number }): string[]
  boolean(operation: PolygonBooleanOperation, ids: Iterable<string>): Promise<string[]>
  delete(ids: Iterable<string>): void
  restore(ids: Iterable<string>): void
  undo(): void
  redo(): void
  canUndo(): boolean
  canRedo(): boolean
  setLayers(layers: AnnotationLayer[]): void
  updateLayer(id: string, patch: Partial<AnnotationLayer>): void
  zoomTarget(id: string): AnnotationBounds | null
  measure(id: string): ReturnType<typeof measureGeometry> | null
  previewImport(source: unknown): ImportPreview
  exportPathLab(): PathLabAnnotationDocument
  exportGeoJson(): GeoJsonFeatureCollection
  exportCsv(): string
  attachOverlay(attachment: AnnotationOverlayAttachment): void
  detachOverlay(): void
  setAutosaveStatus(status: string): void
  takePendingMutations(): AnnotationMutation[]
}

const EMPTY_FILTER: AnnotationFilter = {
  search: '',
  layerIds: new Set(),
  classifications: new Set(),
  tags: new Set(),
  includeDeleted: false,
}

function cloneRecord(record: AnnotationRecord): AnnotationRecord {
  return structuredClone(record)
}

function cloneMutation(mutation: AnnotationMutation): AnnotationMutation {
  return structuredClone(mutation)
}

export function createAnnotationStore(options: AnnotationStoreOptions): AnnotationStore {
  const idFactory = options.idFactory ?? (() => crypto.randomUUID())
  const now = options.now ?? (() => new Date())
  const booleanClient = options.booleanClient ?? createBooleanWorkerClient()
  const maxAnnotations = options.maxAnnotations ?? MAX_ACTIVE_ANNOTATIONS
  const maxLayers = options.maxLayers ?? MAX_ANNOTATION_LAYERS
  const bounds = options.bounds ?? { width: 0, height: 0 }
  const listeners = new Set<(state: AnnotationStoreState) => void>()
  const undoStack: HistoryEntry[] = []
  const redoStack: HistoryEntry[] = []
  let clipboard: AnnotationRecord[] = []
  let overlay: AnnotationOverlayAttachment | null = null
  let activeCount = 0
  const state: AnnotationStoreState = {
    slideId: options.slideId,
    version: 0,
    tool: 'hand',
    layers: new Map(),
    annotations: new Map(),
    selection: new Set(),
    filter: { ...EMPTY_FILTER, layerIds: new Set(), classifications: new Set(), tags: new Set() },
    pendingMutations: [],
    autosaveStatus: 'idle',
    overlayError: null,
  }

  const emit = () => {
    for (const listener of listeners) listener(state)
  }

  const layerEditable = (record: AnnotationRecord): boolean => {
    const layer = state.layers.get(record.layerId)
    return !layer?.locked
  }

  const applyHistoryRecords = (records: Map<string, AnnotationRecord | null>) => {
    for (const [id, record] of records) {
      const current = state.annotations.get(id)
      const wasActive = Boolean(current && !current.deletedAt)
      const willBeActive = Boolean(record && !record.deletedAt)
      if (wasActive !== willBeActive) activeCount += willBeActive ? 1 : -1
      if (record) state.annotations.set(id, cloneRecord(record))
      else state.annotations.delete(id)
    }
  }

  const recordCommand = (
    ids: Iterable<string>,
    mutations: AnnotationMutation[],
    mutate: () => void,
  ) => {
    const uniqueIds = [...new Set(ids)]
    const before = new Map<string, AnnotationRecord | null>()
    for (const id of uniqueIds) {
      const record = state.annotations.get(id)
      before.set(id, record ? cloneRecord(record) : null)
    }
    mutate()
    const after = new Map<string, AnnotationRecord | null>()
    for (const id of uniqueIds) {
      const record = state.annotations.get(id)
      after.set(id, record ? cloneRecord(record) : null)
    }
    for (const id of uniqueIds) {
      const wasActive = Boolean(before.get(id) && !before.get(id)?.deletedAt)
      const isActive = Boolean(after.get(id) && !after.get(id)?.deletedAt)
      if (wasActive !== isActive) activeCount += isActive ? 1 : -1
    }
    const entry = { before, after, mutations: mutations.map(cloneMutation) }
    undoStack.push(entry)
    if (undoStack.length > 100) undoStack.shift()
    redoStack.length = 0
    state.pendingMutations.push(...entry.mutations.map(cloneMutation))
    emit()
  }

  const updateRecords = (
    ids: Iterable<string>,
    patch: Partial<Pick<AnnotationInput, 'layerId' | 'geometry' | 'style' | 'metadata'>>,
  ) => {
    if (patch.geometry && geometryVertexCount(patch.geometry) > MAX_VERTICES_PER_SHAPE) {
      throw new RangeError('Annotation shapes cannot exceed 8,192 vertices')
    }
    const records = [...new Set(ids)]
      .map((id) => state.annotations.get(id))
      .filter((record): record is AnnotationRecord => Boolean(record && layerEditable(record)))
    const mutations: AnnotationMutation[] = records.map((record) => ({
      type: 'update',
      id: record.id,
      version: Math.max(1, record.version),
      ...(patch.layerId === undefined ? {} : { layerId: patch.layerId }),
      ...(patch.geometry === undefined ? {} : { geometry: structuredClone(patch.geometry) }),
      ...(patch.style === undefined ? {} : { style: structuredClone(patch.style) }),
      ...(patch.metadata === undefined ? {} : { metadata: structuredClone(patch.metadata) }),
    }))
    recordCommand(records.map((record) => record.id), mutations, () => {
      for (const record of records) {
        const geometry = patch.geometry
          ? structuredClone(patch.geometry)
          : structuredClone(record.geometry)
        state.annotations.set(record.id, {
          ...cloneRecord(record),
          ...structuredClone(patch),
          geometry,
          bounds: geometryBounds(geometry),
          updatedAt: now().toISOString(),
        })
      }
    })
  }

  const store: AnnotationStore = {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    load(payload) {
      if (payload.layers.length > maxLayers) {
        throw new RangeError('Annotation layer limit exceeded')
      }
      if (payload.annotations.filter((annotation) => !annotation.deletedAt).length > maxAnnotations) {
        throw new RangeError('Active annotation limit exceeded')
      }
      state.version = payload.version
      state.layers = new Map(payload.layers.map((layer) => [layer.id, structuredClone(layer)]))
      state.annotations = new Map(
        payload.annotations.map((annotation) => [annotation.id, cloneRecord(annotation)]),
      )
      activeCount = payload.annotations.filter((annotation) => !annotation.deletedAt).length
      state.selection.clear()
      state.pendingMutations = []
      undoStack.length = 0
      redoStack.length = 0
      emit()
    },
    setTool(tool) {
      state.tool = tool
      emit()
    },
    select(ids, additive = false) {
      if (!additive) state.selection.clear()
      for (const id of ids) {
        if (state.annotations.has(id)) state.selection.add(id)
      }
      emit()
    },
    clearSelection() {
      state.selection.clear()
      emit()
    },
    setFilter(filter) {
      state.filter = {
        ...state.filter,
        ...filter,
        layerIds: filter.layerIds ? new Set(filter.layerIds) : state.filter.layerIds,
        classifications: filter.classifications
          ? new Set(filter.classifications)
          : state.filter.classifications,
        tags: filter.tags ? new Set(filter.tags) : state.filter.tags,
      }
      emit()
    },
    visibleAnnotations() {
      const search = state.filter.search.trim().toLocaleLowerCase()
      return [...state.annotations.values()].filter((annotation) => {
        if (annotation.deletedAt && !state.filter.includeDeleted) return false
        const layer = state.layers.get(annotation.layerId)
        if (layer && !layer.visible) return false
        if (state.filter.layerIds.size > 0 && !state.filter.layerIds.has(annotation.layerId)) {
          return false
        }
        if (
          state.filter.classifications
          && state.filter.classifications.size > 0
          && !state.filter.classifications.has(annotation.metadata.classification)
        ) {
          return false
        }
        if (
          state.filter.tags
          && state.filter.tags.size > 0
          && !annotation.metadata.tags.some((tag) => state.filter.tags?.has(tag))
        ) {
          return false
        }
        if (!search) return true
        return [
          annotation.metadata.title,
          annotation.metadata.classification,
          annotation.metadata.notes,
          ...annotation.metadata.tags,
        ].some((value) => value.toLocaleLowerCase().includes(search))
      })
    },
    create(input) {
      if (state.annotations.has(input.id)) {
        throw new Error(`Annotation ${input.id} already exists`)
      }
      if (activeCount >= maxAnnotations) {
        throw new RangeError('Active annotation limit exceeded')
      }
      if (geometryVertexCount(input.geometry) > MAX_VERTICES_PER_SHAPE) {
        throw new RangeError('Annotation shapes cannot exceed 8,192 vertices')
      }
      const timestamp = now().toISOString()
      const record: AnnotationRecord = {
        ...structuredClone(input),
        version: 0,
        deletedAt: null,
        createdAt: timestamp,
        updatedAt: timestamp,
        bounds: geometryBounds(input.geometry),
        measurements: measureGeometry(
          input.geometry,
          options.calibration,
        ).values as Record<string, string | number>,
      }
      recordCommand(
        [input.id],
        [{ type: 'create', item: structuredClone(input) }],
        () => state.annotations.set(record.id, record),
      )
    },
    update(id, patch) {
      updateRecords([id], patch)
    },
    bulkUpdate(ids, patch) {
      updateRecords(ids, patch)
    },
    move(ids, deltaX, deltaY) {
      for (const id of ids) {
        const record = state.annotations.get(id)
        if (record) updateRecords([id], { geometry: moveGeometry(record.geometry, deltaX, deltaY) })
      }
    },
    resize(id, targetBounds) {
      const record = state.annotations.get(id)
      if (record) updateRecords([id], { geometry: resizeGeometry(record.geometry, targetBounds) })
    },
    editVertex(id, vertexIndex, point) {
      const record = state.annotations.get(id)
      if (record) {
        updateRecords([id], {
          geometry: editGeometryVertex(record.geometry, vertexIndex, point),
        })
      }
    },
    duplicate(ids, offset = { x: 12, y: 12 }) {
      const created: string[] = []
      for (const id of ids) {
        const source = state.annotations.get(id)
        if (!source) continue
        const newId = idFactory()
        const copy = duplicateAnnotation(source, newId, offset)
        const input: AnnotationInput = {
          id: copy.id,
          layerId: copy.layerId,
          geometry: copy.geometry,
          style: copy.style,
          metadata: copy.metadata,
        }
        store.create(input)
        created.push(newId)
      }
      return created
    },
    copy() {
      clipboard = [...state.selection]
        .map((id) => state.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record))
        .map(cloneRecord)
    },
    paste(offset = { x: 12, y: 12 }) {
      const ids: string[] = []
      for (const source of clipboard) {
        const id = idFactory()
        const copy = duplicateAnnotation(source, id, offset)
        store.create({
          id,
          layerId: copy.layerId,
          geometry: copy.geometry,
          style: copy.style,
          metadata: copy.metadata,
        })
        ids.push(id)
      }
      store.select(ids)
      return ids
    },
    async boolean(operation, ids) {
      const sources = [...new Set(ids)]
        .map((id) => state.annotations.get(id))
        .filter((record): record is AnnotationRecord => (
          Boolean(record)
          && record?.geometry.type === 'polygon'
          && layerEditable(record)
        ))
      if (sources.length === 0) return []
      const result = await booleanClient.run(
        operation,
        sources.map((record) => record.geometry as PolygonGeometry),
      )
      const created: string[] = []
      const source = sources[0]
      if (result.length > 0) {
        updateRecords([source.id], { geometry: result[0] })
        created.push(source.id)
      }
      for (const geometry of result.slice(1)) {
        const id = idFactory()
        store.create({
          id,
          layerId: source.layerId,
          geometry,
          style: structuredClone(source.style),
          metadata: structuredClone(source.metadata),
        })
        created.push(id)
      }
      if (operation !== 'intersection') {
        store.delete(sources.slice(1).map((record) => record.id))
      }
      store.select(created)
      return created
    },
    delete(ids) {
      const records = [...new Set(ids)]
        .map((id) => state.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record && layerEditable(record)))
      const timestamp = now().toISOString()
      recordCommand(
        records.map((record) => record.id),
        records.map((record) => ({
          type: 'delete',
          id: record.id,
          version: Math.max(1, record.version),
        })),
        () => {
          for (const record of records) {
            state.annotations.set(record.id, { ...cloneRecord(record), deletedAt: timestamp })
            state.selection.delete(record.id)
          }
        },
      )
    },
    restore(ids) {
      const records = [...new Set(ids)]
        .map((id) => state.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record?.deletedAt))
      recordCommand(
        records.map((record) => record.id),
        records.map((record) => ({
          type: 'restore',
          id: record.id,
          version: Math.max(1, record.version),
        })),
        () => {
          for (const record of records) {
            state.annotations.set(record.id, { ...cloneRecord(record), deletedAt: null })
          }
        },
      )
    },
    undo() {
      const entry = undoStack.pop()
      if (!entry) return
      applyHistoryRecords(entry.before)
      state.pendingMutations.splice(-entry.mutations.length, entry.mutations.length)
      redoStack.push(entry)
      emit()
    },
    redo() {
      const entry = redoStack.pop()
      if (!entry) return
      applyHistoryRecords(entry.after)
      state.pendingMutations.push(...entry.mutations.map(cloneMutation))
      undoStack.push(entry)
      emit()
    },
    canUndo: () => undoStack.length > 0,
    canRedo: () => redoStack.length > 0,
    setLayers(layers) {
      if (layers.length > maxLayers) throw new RangeError('Annotation layer limit exceeded')
      state.layers = new Map(layers.map((layer) => [layer.id, structuredClone(layer)]))
      emit()
    },
    updateLayer(id, patch) {
      const layer = state.layers.get(id)
      if (!layer) return
      state.layers.set(id, { ...structuredClone(layer), ...structuredClone(patch) })
      emit()
    },
    zoomTarget(id) {
      const record = state.annotations.get(id)
      return record ? { ...record.bounds } : null
    },
    measure(id) {
      const record = state.annotations.get(id)
      return record ? measureGeometry(record.geometry, options.calibration) : null
    },
    previewImport(source) {
      return previewImport(source)
    },
    exportPathLab() {
      return {
        schema: ANNOTATION_SCHEMA,
        slide: {
          id: state.slideId,
          width: bounds.width,
          height: bounds.height,
          annotationVersion: state.version,
        },
        layers: [...state.layers.values()].map((layer) => ({
          id: layer.id,
          name: layer.name,
          sortOrder: layer.sortOrder,
          visible: layer.visible,
          locked: layer.locked,
          opacity: layer.opacity,
        })),
        annotations: [...state.annotations.values()]
          .filter((record) => !record.deletedAt)
          .map((record) => ({
            id: record.id,
            layerId: record.layerId,
            geometry: structuredClone(record.geometry),
            style: structuredClone(record.style),
            metadata: structuredClone(record.metadata),
          })),
      }
    },
    exportGeoJson() {
      return toGeoJson(store.exportPathLab())
    },
    exportCsv() {
      const rows: CsvMeasurementRow[] = [...state.annotations.values()]
        .filter((record) => !record.deletedAt)
        .map((record) => ({
          id: record.id,
          layer: state.layers.get(record.layerId)?.name ?? '',
          title: record.metadata.title,
          classification: record.metadata.classification,
          geometryType: record.geometry.type,
          values: measureGeometry(record.geometry, options.calibration).values,
        }))
      return exportMeasurementsCsv(rows)
    },
    attachOverlay(attachment) {
      store.detachOverlay()
      overlay = attachment
      state.overlayError = null
      try {
        attachment.render()
      } catch (caught) {
        state.overlayError = caught instanceof Error ? caught.message : 'Annotation overlay failed'
        attachment.detach()
        attachment.restoreNavigation()
        overlay = null
      }
      emit()
    },
    detachOverlay() {
      if (!overlay) return
      overlay.detach()
      overlay.restoreNavigation()
      overlay = null
      emit()
    },
    setAutosaveStatus(status) {
      state.autosaveStatus = status
      emit()
    },
    takePendingMutations() {
      const pending = state.pendingMutations.map(cloneMutation)
      state.pendingMutations = []
      emit()
      return pending
    },
  }
  return store
}

export type AnnotationBulkPatch = {
  style?: AnnotationStyle
  metadata?: AnnotationMetadata
  layerId?: string
}
