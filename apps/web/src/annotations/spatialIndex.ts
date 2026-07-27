import RBush from 'rbush'

import {
  MAX_CACHED_ANNOTATIONS,
  MAX_MOUNTED_ANNOTATIONS,
  type AnnotationBounds,
  type AnnotationRecord,
} from './types'

interface IndexedAnnotation extends AnnotationBounds {
  id: string
  annotation: AnnotationRecord
}

export interface DensityCell {
  x: number
  y: number
  count: number
  imageX: number
  imageY: number
}

export interface AnnotationRenderPlan {
  mounted: AnnotationRecord[]
  cached: AnnotationRecord[]
  totalVisible: number
  density: {
    enabled: boolean
    cells: DensityCell[]
  }
  prompt: string | null
}

function indexed(annotation: AnnotationRecord): IndexedAnnotation {
  return { ...annotation.bounds, id: annotation.id, annotation }
}

function densityCells(
  items: readonly IndexedAnnotation[],
  viewport: AnnotationBounds,
  divisions = 32,
): DensityCell[] {
  const width = Math.max(1, viewport.maxX - viewport.minX)
  const height = Math.max(1, viewport.maxY - viewport.minY)
  const counts = new Map<string, DensityCell>()
  for (const item of items) {
    const centreX = (item.minX + item.maxX) / 2
    const centreY = (item.minY + item.maxY) / 2
    const x = Math.max(0, Math.min(divisions - 1, Math.floor(
      ((centreX - viewport.minX) / width) * divisions,
    )))
    const y = Math.max(0, Math.min(divisions - 1, Math.floor(
      ((centreY - viewport.minY) / height) * divisions,
    )))
    const key = `${x}:${y}`
    const existing = counts.get(key)
    if (existing) {
      existing.count += 1
      existing.imageX += centreX
      existing.imageY += centreY
    } else {
      counts.set(key, { x, y, count: 1, imageX: centreX, imageY: centreY })
    }
  }
  return [...counts.values()].map((cell) => ({
    ...cell,
    imageX: cell.imageX / cell.count,
    imageY: cell.imageY / cell.count,
  }))
}

export class AnnotationSpatialIndex {
  private readonly tree = new RBush<IndexedAnnotation>()
  private readonly byId = new Map<string, IndexedAnnotation>()
  private readonly cache = new Map<string, AnnotationRecord>()

  load(annotations: readonly AnnotationRecord[]): void {
    this.tree.clear()
    this.byId.clear()
    this.cache.clear()
    const items = annotations.map(indexed)
    this.tree.load(items)
    for (const item of items) this.byId.set(item.id, item)
  }

  upsert(annotation: AnnotationRecord): void {
    this.remove(annotation.id)
    const item = indexed(annotation)
    this.tree.insert(item)
    this.byId.set(annotation.id, item)
  }

  remove(id: string): void {
    const existing = this.byId.get(id)
    if (!existing) return
    this.tree.remove(existing)
    this.byId.delete(id)
    this.cache.delete(id)
  }

  query(viewport: AnnotationBounds): AnnotationRecord[] {
    return this.tree.search(viewport).map((item) => item.annotation)
  }

  plan(
    viewport: AnnotationBounds,
    predicate: (annotation: AnnotationRecord) => boolean = () => true,
  ): AnnotationRenderPlan {
    const visible = this.tree.search(viewport)
      .filter((item) => predicate(item.annotation))
    for (const item of visible.slice(0, MAX_CACHED_ANNOTATIONS)) {
      if (this.cache.get(item.id) !== item.annotation) {
        this.cache.set(item.id, item.annotation)
      }
    }
    while (this.cache.size > MAX_CACHED_ANNOTATIONS) {
      const oldest = this.cache.keys().next().value as string | undefined
      if (oldest === undefined) break
      this.cache.delete(oldest)
    }
    const densityEnabled = visible.length > MAX_MOUNTED_ANNOTATIONS
    return {
      mounted: densityEnabled
        ? []
        : visible
          .slice(0, MAX_MOUNTED_ANNOTATIONS)
          .map((item) => item.annotation),
      cached: [...this.cache.values()],
      totalVisible: visible.length,
      density: {
        enabled: densityEnabled,
        cells: densityEnabled ? densityCells(visible, viewport) : [],
      },
      prompt: densityEnabled ? 'Zoom in to render individual annotations' : null,
    }
  }
}
