import type {
  AnnotationAutosaveAcknowledgement,
  AnnotationAutosaveBatch,
} from './autosave'
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
import {
  coalesceMutationSequence,
  mutationTargetId,
  rebaseMutation,
  sameMutation,
} from './mutationQueue'
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
  MAX_BATCH_OPERATIONS,
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
  annotations: Map<string, AnnotationRecord>
  layers: Map<string, AnnotationLayer>
  selection: Set<string>
  filter: AnnotationFilter
  pendingMutations: AnnotationMutation[]
  autosaveStatus: string
  overlayError: string | null
}

export interface AnnotationStoreAcknowledgement extends AnnotationAutosaveAcknowledgement {
  records?: AnnotationRecord[]
}

interface MutableState {
  slideId: string
  version: number
  tool: AnnotationTool
  annotations: Map<string, AnnotationRecord>
  layers: Map<string, AnnotationLayer>
  selection: Set<string>
  filter: AnnotationFilter
  autosaveStatus: string
  overlayError: string | null
}

interface PendingEntry {
  token: number
  mutation: AnnotationMutation
  inFlight: string | null
}

interface HistoryEntry {
  before: Map<string, AnnotationRecord | null>
  after: Map<string, AnnotationRecord | null>
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
  peekPendingMutations(): AnnotationMutation[]
  takePendingMutations(): AnnotationMutation[]
  beginSave(mutationId: string, operations: readonly AnnotationMutation[]): void
  acknowledgeSave(acknowledgement: AnnotationStoreAcknowledgement): void
  failSave(mutationId: string): void
  autosaveHooks(): {
    onBatchStart(batch: AnnotationAutosaveBatch): void
    onAcknowledged(acknowledgement: AnnotationAutosaveAcknowledgement): void
    onBatchFailed(batch: AnnotationAutosaveBatch): void
  }
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

function readonlyMap<K, V>(entries: Iterable<readonly [K, V]>): Map<K, V> {
  const map = new Map(entries)
  const fail = () => {
    throw new TypeError('Annotation store snapshots are read-only')
  }
  Object.defineProperties(map, {
    set: { value: fail },
    delete: { value: fail },
    clear: { value: fail },
  })
  return map
}

function readonlySet<T>(values: Iterable<T>): Set<T> {
  const set = new Set(values)
  const fail = () => {
    throw new TypeError('Annotation store snapshots are read-only')
  }
  Object.defineProperties(set, {
    add: { value: fail },
    delete: { value: fail },
    clear: { value: fail },
  })
  return set
}

function inputFromRecord(record: AnnotationRecord): AnnotationInput {
  return {
    id: record.id,
    layerId: record.layerId,
    geometry: structuredClone(record.geometry),
    style: structuredClone(record.style),
    metadata: structuredClone(record.metadata),
  }
}

function equal(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function createAnnotationStore(options: AnnotationStoreOptions): AnnotationStore {
  const idFactory = options.idFactory ?? (() => crypto.randomUUID())
  const now = options.now ?? (() => new Date())
  const booleanClient = options.booleanClient ?? createBooleanWorkerClient()
  const maxAnnotations = options.maxAnnotations ?? MAX_ACTIVE_ANNOTATIONS
  const maxLayers = options.maxLayers ?? MAX_ANNOTATION_LAYERS
  const slideBounds = options.bounds ?? { width: 0, height: 0 }
  const listeners = new Set<(state: AnnotationStoreState) => void>()
  const undoStack: HistoryEntry[] = []
  const redoStack: HistoryEntry[] = []
  const pending: PendingEntry[] = []
  let nextPendingToken = 1
  let clipboard: AnnotationRecord[] = []
  let overlay: AnnotationOverlayAttachment | null = null
  let activeCount = 0
  const internal: MutableState = {
    slideId: options.slideId,
    version: 0,
    tool: 'hand',
    annotations: new Map(),
    layers: new Map(),
    selection: new Set(),
    filter: {
      ...EMPTY_FILTER,
      layerIds: new Set(),
      classifications: new Set(),
      tags: new Set(),
    },
    autosaveStatus: 'idle',
    overlayError: null,
  }

  const sendableEntries = (): PendingEntry[] => {
    const blocked = new Set<string>()
    for (const entry of pending) {
      if (entry.inFlight) blocked.add(mutationTargetId(entry.mutation))
    }
    const selected = new Set<string>()
    const result: PendingEntry[] = []
    for (const entry of pending) {
      const target = mutationTargetId(entry.mutation)
      if (entry.inFlight || blocked.has(target) || selected.has(target)) continue
      selected.add(target)
      result.push(entry)
    }
    return result
  }

  const makeSnapshot = (): AnnotationStoreState => ({
    slideId: internal.slideId,
    version: internal.version,
    tool: internal.tool,
    annotations: readonlyMap(
      [...internal.annotations].map(([id, record]) => [id, cloneRecord(record)] as const),
    ),
    layers: readonlyMap(
      [...internal.layers].map(([id, layer]) => [id, structuredClone(layer)] as const),
    ),
    selection: readonlySet(internal.selection),
    filter: {
      ...internal.filter,
      layerIds: readonlySet(internal.filter.layerIds),
      classifications: internal.filter.classifications
        ? readonlySet(internal.filter.classifications)
        : undefined,
      tags: internal.filter.tags ? readonlySet(internal.filter.tags) : undefined,
    },
    pendingMutations: sendableEntries().map((entry) => cloneMutation(entry.mutation)),
    autosaveStatus: internal.autosaveStatus,
    overlayError: internal.overlayError,
  })

  let snapshot = makeSnapshot()
  const emit = () => {
    snapshot = makeSnapshot()
    for (const listener of listeners) listener(snapshot)
  }

  const setRecord = (id: string, record: AnnotationRecord | null) => {
    const previous = internal.annotations.get(id)
    const wasActive = Boolean(previous && !previous.deletedAt)
    const willBeActive = Boolean(record && !record.deletedAt)
    if (wasActive !== willBeActive) activeCount += willBeActive ? 1 : -1
    if (record) internal.annotations.set(id, cloneRecord(record))
    else internal.annotations.delete(id)
  }

  const layerEditable = (record: AnnotationRecord): boolean => (
    !internal.layers.get(record.layerId)?.locked
  )

  const queueMutation = (mutation: AnnotationMutation) => {
    const target = mutationTargetId(mutation)
    const targetEntries = pending.filter((entry) => (
      !entry.inFlight && mutationTargetId(entry.mutation) === target
    ))
    if (targetEntries.length === 0) {
      pending.push({
        token: nextPendingToken++,
        mutation: cloneMutation(mutation),
        inFlight: null,
      })
      return
    }
    const firstIndex = pending.findIndex((entry) => (
      !entry.inFlight && mutationTargetId(entry.mutation) === target
    ))
    const insertionIndex = pending
      .slice(0, firstIndex)
      .filter((entry) => entry.inFlight || mutationTargetId(entry.mutation) !== target)
      .length
    const normalized = coalesceMutationSequence([
      ...targetEntries.map((entry) => entry.mutation),
      mutation,
    ])
    const replacements = normalized.map((entry, index): PendingEntry => ({
      token: targetEntries[index]?.token ?? nextPendingToken++,
      mutation: cloneMutation(entry),
      inFlight: null,
    }))
    const withoutTarget = pending.filter((entry) => (
      entry.inFlight || mutationTargetId(entry.mutation) !== target
    ))
    withoutTarget.splice(insertionIndex, 0, ...replacements)
    pending.splice(0, pending.length, ...withoutTarget)
  }

  const recordCommand = (
    ids: Iterable<string>,
    mutations: readonly AnnotationMutation[],
    mutate: () => void,
  ) => {
    const affected = [...new Set(ids)]
    const before = new Map<string, AnnotationRecord | null>()
    for (const id of affected) {
      const record = internal.annotations.get(id)
      before.set(id, record ? cloneRecord(record) : null)
    }
    mutate()
    const after = new Map<string, AnnotationRecord | null>()
    for (const id of affected) {
      const record = internal.annotations.get(id)
      after.set(id, record ? cloneRecord(record) : null)
    }
    for (const mutation of mutations) queueMutation(mutation)
    undoStack.push({ before, after })
    if (undoStack.length > 100) undoStack.shift()
    redoStack.length = 0
    emit()
  }

  const patchBetween = (
    current: AnnotationRecord,
    target: AnnotationRecord,
  ): Extract<AnnotationMutation, { type: 'update' }> | null => {
    const patch: Extract<AnnotationMutation, { type: 'update' }> = {
      type: 'update',
      id: current.id,
      version: Math.max(1, current.version),
    }
    if (current.layerId !== target.layerId) patch.layerId = target.layerId
    if (!equal(current.geometry, target.geometry)) patch.geometry = structuredClone(target.geometry)
    if (!equal(current.style, target.style)) patch.style = structuredClone(target.style)
    if (!equal(current.metadata, target.metadata)) patch.metadata = structuredClone(target.metadata)
    return Object.keys(patch).length > 3 ? patch : null
  }

  const desiredRecord = (
    target: AnnotationRecord,
    serverVersion: number,
  ): AnnotationRecord => {
    const geometry = structuredClone(target.geometry)
    return {
      ...cloneRecord(target),
      version: serverVersion,
      geometry,
      bounds: geometryBounds(geometry),
      measurements: measureGeometry(geometry, options.calibration).values as Record<
        string,
        string | number
      >,
      updatedAt: now().toISOString(),
    }
  }

  const applyHistoryTarget = (targets: Map<string, AnnotationRecord | null>) => {
    const compensations: AnnotationMutation[] = []
    for (const [id, target] of targets) {
      const current = internal.annotations.get(id) ?? null
      if (!current && target) {
        const restored = desiredRecord(target, 0)
        setRecord(id, restored)
        compensations.push({ type: 'create', item: inputFromRecord(restored) })
        continue
      }
      if (!current) continue
      if (!target) {
        compensations.push({
          type: 'delete',
          id,
          version: Math.max(1, current.version),
        })
        if (current.version === 0) setRecord(id, null)
        else setRecord(id, { ...cloneRecord(current), deletedAt: now().toISOString() })
        internal.selection.delete(id)
        continue
      }
      if (!current.deletedAt && target.deletedAt) {
        compensations.push({
          type: 'delete',
          id,
          version: Math.max(1, current.version),
        })
        setRecord(id, { ...desiredRecord(target, current.version), deletedAt: target.deletedAt })
        continue
      }
      if (current.deletedAt && !target.deletedAt) {
        if (activeCount >= maxAnnotations) throw new RangeError('Active annotation limit exceeded')
        compensations.push({
          type: 'restore',
          id,
          version: Math.max(1, current.version),
        })
        const restored = desiredRecord(target, current.version)
        const update = patchBetween({ ...current, deletedAt: null }, restored)
        if (update) compensations.push(update)
        setRecord(id, { ...restored, deletedAt: null })
        continue
      }
      const update = patchBetween(current, target)
      if (update) compensations.push(update)
      setRecord(id, desiredRecord(target, current.version))
    }
    for (const compensation of compensations) queueMutation(compensation)
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
      .map((id) => internal.annotations.get(id))
      .filter((record): record is AnnotationRecord => Boolean(
        record && !record.deletedAt && layerEditable(record),
      ))
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
        setRecord(record.id, {
          ...cloneRecord(record),
          ...structuredClone(patch),
          geometry,
          bounds: geometryBounds(geometry),
          measurements: patch.geometry
            ? measureGeometry(geometry, options.calibration).values as Record<string, string | number>
            : structuredClone(record.measurements),
          updatedAt: now().toISOString(),
        })
      }
    })
  }

  const store: AnnotationStore = {
    getState: () => snapshot,
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    load(payload) {
      if (payload.layers.length > maxLayers) throw new RangeError('Annotation layer limit exceeded')
      const loadedActive = payload.annotations.filter((annotation) => !annotation.deletedAt).length
      if (loadedActive > maxAnnotations) throw new RangeError('Active annotation limit exceeded')
      internal.version = payload.version
      internal.layers = new Map(payload.layers.map((layer) => [layer.id, structuredClone(layer)]))
      internal.annotations = new Map(
        payload.annotations.map((annotation) => [annotation.id, cloneRecord(annotation)]),
      )
      activeCount = loadedActive
      internal.selection.clear()
      pending.length = 0
      undoStack.length = 0
      redoStack.length = 0
      emit()
    },
    setTool(tool) {
      internal.tool = tool
      emit()
    },
    select(ids, additive = false) {
      if (!additive) internal.selection.clear()
      for (const id of ids) {
        if (internal.annotations.has(id)) internal.selection.add(id)
      }
      emit()
    },
    clearSelection() {
      internal.selection.clear()
      emit()
    },
    setFilter(filter) {
      internal.filter = {
        ...internal.filter,
        ...filter,
        layerIds: filter.layerIds ? new Set(filter.layerIds) : internal.filter.layerIds,
        classifications: filter.classifications
          ? new Set(filter.classifications)
          : internal.filter.classifications,
        tags: filter.tags ? new Set(filter.tags) : internal.filter.tags,
      }
      emit()
    },
    visibleAnnotations() {
      const search = internal.filter.search.trim().toLocaleLowerCase()
      return [...internal.annotations.values()].filter((record) => {
        if (record.deletedAt && !internal.filter.includeDeleted) return false
        const layer = internal.layers.get(record.layerId)
        if (layer && !layer.visible) return false
        if (
          internal.filter.layerIds.size > 0
          && !internal.filter.layerIds.has(record.layerId)
        ) return false
        if (
          internal.filter.classifications
          && internal.filter.classifications.size > 0
          && !internal.filter.classifications.has(record.metadata.classification)
        ) return false
        if (
          internal.filter.tags
          && internal.filter.tags.size > 0
          && !record.metadata.tags.some((tag) => internal.filter.tags?.has(tag))
        ) return false
        if (!search) return true
        return [
          record.metadata.title,
          record.metadata.classification,
          record.metadata.notes,
          ...record.metadata.tags,
        ].some((value) => value.toLocaleLowerCase().includes(search))
      }).map(cloneRecord)
    },
    create(input) {
      if (internal.annotations.has(input.id)) throw new Error(`Annotation ${input.id} already exists`)
      if (activeCount >= maxAnnotations) throw new RangeError('Active annotation limit exceeded')
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
      recordCommand([input.id], [{ type: 'create', item: structuredClone(input) }], () => {
        setRecord(record.id, record)
      })
    },
    update(id, patch) {
      updateRecords([id], patch)
    },
    bulkUpdate(ids, patch) {
      updateRecords(ids, patch)
    },
    move(ids, deltaX, deltaY) {
      const records = [...ids]
        .map((id) => internal.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record))
      for (const record of records) {
        updateRecords([record.id], {
          geometry: moveGeometry(record.geometry, deltaX, deltaY),
        })
      }
    },
    resize(id, targetBounds) {
      const record = internal.annotations.get(id)
      if (record) updateRecords([id], { geometry: resizeGeometry(record.geometry, targetBounds) })
    },
    editVertex(id, vertexIndex, point) {
      const record = internal.annotations.get(id)
      if (record) {
        updateRecords([id], {
          geometry: editGeometryVertex(record.geometry, vertexIndex, point),
        })
      }
    },
    duplicate(ids, offset = { x: 12, y: 12 }) {
      const created: string[] = []
      for (const id of ids) {
        const source = internal.annotations.get(id)
        if (!source) continue
        const newId = idFactory()
        const copy = duplicateAnnotation(source, newId, offset)
        store.create(inputFromRecord(copy))
        created.push(newId)
      }
      return created
    },
    copy() {
      clipboard = [...internal.selection]
        .map((id) => internal.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record))
        .map(cloneRecord)
    },
    paste(offset = { x: 12, y: 12 }) {
      const ids: string[] = []
      for (const source of clipboard) {
        const id = idFactory()
        const copy = duplicateAnnotation(source, id, offset)
        store.create(inputFromRecord(copy))
        ids.push(id)
      }
      store.select(ids)
      return ids
    },
    async boolean(operation, ids) {
      const sources = [...new Set(ids)]
        .map((id) => internal.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(
          record
          && !record.deletedAt
          && record.geometry.type === 'polygon'
          && layerEditable(record),
        ))
      if (sources.length === 0) return []
      const results = await booleanClient.run(
        operation,
        sources.map((record) => record.geometry as PolygonGeometry),
      )
      if (results.some((geometry) => geometryVertexCount(geometry) > MAX_VERTICES_PER_SHAPE)) {
        throw new RangeError('Boolean results cannot exceed 8,192 vertices per shape')
      }
      const deletedSourceCount = results.length > 0 ? sources.length - 1 : sources.length
      if (results.length + deletedSourceCount > MAX_BATCH_OPERATIONS) {
        throw new RangeError('Boolean result exceeds the 50-operation transaction limit')
      }
      const resultingActive = activeCount - sources.length + results.length
      if (resultingActive > maxAnnotations) {
        throw new RangeError('Active annotation limit exceeded')
      }
      const newIds = results.slice(1).map(() => idFactory())
      const reserved = new Set([...internal.annotations.keys(), ...sources.map((record) => record.id)])
      for (const id of newIds) {
        if (reserved.has(id)) throw new Error(`Annotation ${id} already exists`)
        reserved.add(id)
      }
      const affected = [...sources.map((record) => record.id), ...newIds]
      const timestamp = now().toISOString()
      const mutations: AnnotationMutation[] = []
      if (results.length > 0) {
        mutations.push({
          type: 'update',
          id: sources[0].id,
          version: Math.max(1, sources[0].version),
          geometry: structuredClone(results[0]),
        })
        results.slice(1).forEach((geometry, index) => {
          mutations.push({
            type: 'create',
            item: {
              id: newIds[index],
              layerId: sources[0].layerId,
              geometry: structuredClone(geometry),
              style: structuredClone(sources[0].style),
              metadata: structuredClone(sources[0].metadata),
            },
          })
        })
      }
      const deletedSources = results.length > 0 ? sources.slice(1) : sources
      mutations.push(...deletedSources.map((record) => ({
        type: 'delete' as const,
        id: record.id,
        version: Math.max(1, record.version),
      })))
      recordCommand(affected, mutations, () => {
        if (results.length > 0) {
          const geometry = structuredClone(results[0])
          setRecord(sources[0].id, {
            ...cloneRecord(sources[0]),
            geometry,
            bounds: geometryBounds(geometry),
            measurements: measureGeometry(
              geometry,
              options.calibration,
            ).values as Record<string, string | number>,
            updatedAt: timestamp,
          })
          results.slice(1).forEach((geometry, index) => {
            setRecord(newIds[index], {
              id: newIds[index],
              layerId: sources[0].layerId,
              geometry: structuredClone(geometry),
              style: structuredClone(sources[0].style),
              metadata: structuredClone(sources[0].metadata),
              version: 0,
              deletedAt: null,
              createdAt: timestamp,
              updatedAt: timestamp,
              bounds: geometryBounds(geometry),
              measurements: measureGeometry(
                geometry,
                options.calibration,
              ).values as Record<string, string | number>,
            })
          })
        }
        for (const source of deletedSources) {
          if (source.version === 0) setRecord(source.id, null)
          else setRecord(source.id, { ...cloneRecord(source), deletedAt: timestamp })
          internal.selection.delete(source.id)
        }
      })
      const selected = results.length > 0 ? [sources[0].id, ...newIds] : []
      internal.selection = new Set(selected)
      emit()
      return selected
    },
    delete(ids) {
      const records = [...new Set(ids)]
        .map((id) => internal.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(
          record && !record.deletedAt && layerEditable(record),
        ))
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
            if (record.version === 0) setRecord(record.id, null)
            else setRecord(record.id, { ...cloneRecord(record), deletedAt: timestamp })
            internal.selection.delete(record.id)
          }
        },
      )
    },
    restore(ids) {
      const records = [...new Set(ids)]
        .map((id) => internal.annotations.get(id))
        .filter((record): record is AnnotationRecord => Boolean(record?.deletedAt))
      if (activeCount + records.length > maxAnnotations) {
        throw new RangeError('Active annotation limit exceeded')
      }
      recordCommand(
        records.map((record) => record.id),
        records.map((record) => ({
          type: 'restore',
          id: record.id,
          version: Math.max(1, record.version),
        })),
        () => {
          for (const record of records) {
            setRecord(record.id, { ...cloneRecord(record), deletedAt: null })
          }
        },
      )
    },
    undo() {
      const entry = undoStack.pop()
      if (!entry) return
      applyHistoryTarget(entry.before)
      redoStack.push(entry)
    },
    redo() {
      const entry = redoStack.pop()
      if (!entry) return
      applyHistoryTarget(entry.after)
      undoStack.push(entry)
    },
    canUndo: () => undoStack.length > 0,
    canRedo: () => redoStack.length > 0,
    setLayers(layers) {
      if (layers.length > maxLayers) throw new RangeError('Annotation layer limit exceeded')
      internal.layers = new Map(layers.map((layer) => [layer.id, structuredClone(layer)]))
      emit()
    },
    updateLayer(id, patch) {
      const layer = internal.layers.get(id)
      if (!layer) return
      internal.layers.set(id, { ...structuredClone(layer), ...structuredClone(patch) })
      emit()
    },
    zoomTarget(id) {
      const record = internal.annotations.get(id)
      return record ? { ...record.bounds } : null
    },
    measure(id) {
      const record = internal.annotations.get(id)
      return record ? measureGeometry(record.geometry, options.calibration) : null
    },
    previewImport(source) {
      return previewImport(source, {
        ...(slideBounds.width > 0 && slideBounds.height > 0
          ? { bounds: slideBounds }
          : {}),
      })
    },
    exportPathLab() {
      return {
        schema: ANNOTATION_SCHEMA,
        slide: {
          id: internal.slideId,
          width: slideBounds.width,
          height: slideBounds.height,
          annotationVersion: internal.version,
        },
        layers: [...internal.layers.values()].map((layer) => ({
          id: layer.id,
          name: layer.name,
          sortOrder: layer.sortOrder,
          visible: layer.visible,
          locked: layer.locked,
          opacity: layer.opacity,
        })),
        annotations: [...internal.annotations.values()]
          .filter((record) => !record.deletedAt)
          .map(inputFromRecord),
      }
    },
    exportGeoJson() {
      return toGeoJson(store.exportPathLab())
    },
    exportCsv() {
      const rows: CsvMeasurementRow[] = [...internal.annotations.values()]
        .filter((record) => !record.deletedAt)
        .map((record) => ({
          id: record.id,
          layer: internal.layers.get(record.layerId)?.name ?? '',
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
      internal.overlayError = null
      try {
        attachment.render()
      } catch (caught) {
        internal.overlayError = caught instanceof Error ? caught.message : 'Annotation overlay failed'
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
      internal.autosaveStatus = status
      emit()
    },
    peekPendingMutations() {
      return sendableEntries().map((entry) => cloneMutation(entry.mutation))
    },
    takePendingMutations() {
      return store.peekPendingMutations()
    },
    beginSave(mutationId, operations) {
      if (!mutationId || pending.some((entry) => entry.inFlight === mutationId)) {
        throw new Error('Annotation mutation ID is already in flight')
      }
      const available = sendableEntries()
      const selected: PendingEntry[] = []
      const targets = new Set<string>()
      for (const operation of operations) {
        const target = mutationTargetId(operation)
        if (targets.has(target)) throw new Error(`Duplicate annotation target ${target}`)
        const entry = available.find((candidate) => (
          !selected.includes(candidate)
          && mutationTargetId(candidate.mutation) === target
          && sameMutation(candidate.mutation, operation)
        ))
        if (!entry) throw new Error(`Pending annotation mutation ${target} was not found`)
        selected.push(entry)
        targets.add(target)
      }
      for (const entry of selected) entry.inFlight = mutationId
      emit()
    },
    acknowledgeSave(acknowledgement) {
      if (acknowledgement.result.mutationId !== acknowledgement.mutationId) {
        throw new Error('Annotation acknowledgement mutation ID mismatch')
      }
      const entries = pending.filter((entry) => entry.inFlight === acknowledgement.mutationId)
      if (
        entries.length !== acknowledgement.operations.length
        || entries.some((entry) => !acknowledgement.operations.some(
          (operation) => sameMutation(entry.mutation, operation),
        ))
      ) {
        throw new Error('Annotation acknowledgement does not match the in-flight batch')
      }
      const results = new Map(acknowledgement.result.results.map((result) => [result.id, result]))
      const acknowledgedTokens = new Set(entries.map((entry) => entry.token))
      const hasNewerMutation = (target: string): boolean => pending.some((entry) => (
        !acknowledgedTokens.has(entry.token)
        && mutationTargetId(entry.mutation) === target
      ))
      for (const entry of entries) {
        const target = mutationTargetId(entry.mutation)
        const result = results.get(target)
        if (!result || result.operation !== entry.mutation.type) {
          throw new Error(`Annotation acknowledgement is missing ${target}`)
        }
        const isMissingTerminalDelete = entry.mutation.type === 'delete' && result.deleted
        if (
          !internal.annotations.has(target)
          && !hasNewerMutation(target)
          && !isMissingTerminalDelete
        ) {
          throw new Error(`Annotation acknowledgement target ${target} is missing locally`)
        }
      }
      const returnedRecords = new Map(
        (acknowledgement.records ?? []).map((record) => [record.id, record]),
      )
      for (const entry of entries) {
        const target = mutationTargetId(entry.mutation)
        const result = results.get(target)
        if (!result) continue
        const returned = returnedRecords.get(target)
        const current = internal.annotations.get(target)
        if (!current) continue
        const reconciled = hasNewerMutation(target)
          ? {
            ...cloneRecord(current),
            version: result.version,
          }
          : returned
            ? cloneRecord(returned)
          : {
            ...cloneRecord(current),
            version: result.version,
            deletedAt: result.deleted ? current.deletedAt ?? now().toISOString() : null,
            updatedAt: now().toISOString(),
          }
        setRecord(target, reconciled)
      }
      for (let index = pending.length - 1; index >= 0; index -= 1) {
        if (acknowledgedTokens.has(pending[index].token)) pending.splice(index, 1)
      }
      for (const result of acknowledgement.result.results) {
        for (const entry of pending) {
          if (mutationTargetId(entry.mutation) === result.id) {
            entry.mutation = rebaseMutation(entry.mutation, result.version)
          }
        }
      }
      internal.version = acknowledgement.result.version
      emit()
    },
    failSave(mutationId) {
      let changed = false
      for (const entry of pending) {
        if (entry.inFlight === mutationId) {
          entry.inFlight = null
          changed = true
        }
      }
      if (changed) emit()
    },
    autosaveHooks() {
      return {
        onBatchStart(batch) {
          store.beginSave(batch.mutationId, batch.operations)
        },
        onAcknowledged(acknowledgement) {
          store.acknowledgeSave(acknowledgement)
        },
        onBatchFailed(batch) {
          store.failSave(batch.mutationId)
        },
      }
    },
  }
  return store
}

export type AnnotationBulkPatch = {
  style?: AnnotationStyle
  metadata?: AnnotationMetadata
  layerId?: string
}
