export const ANNOTATION_SCHEMA = 'pathlab-annotations/v1' as const
export const MAX_MOUNTED_ANNOTATIONS = 2_000
export const MAX_CACHED_ANNOTATIONS = 5_000
export const MAX_DRAFT_BYTES = 5 * 1024 * 1024
export const MAX_DRAFT_AGE_MS = 7 * 24 * 60 * 60 * 1_000
export const AUTOSAVE_DELAY_MS = 750
export const MAX_BATCH_OPERATIONS = 50
export const BOOLEAN_TIMEOUT_MS = 2_000
export const MAX_ACTIVE_ANNOTATIONS = 25_000
export const MAX_ANNOTATION_LAYERS = 100
export const MAX_VERTICES_PER_SHAPE = 8_192
export const MAX_VERTICES_PER_IMPORT = 250_000

export interface AnnotationPoint {
  x: number
  y: number
}

export interface PointGeometry {
  type: 'point'
  x: number
  y: number
}

export interface PolylineGeometry {
  type: 'polyline'
  points: AnnotationPoint[]
}

export interface AngleGeometry {
  type: 'angle'
  points: [AnnotationPoint, AnnotationPoint, AnnotationPoint]
}

export interface RectangleGeometry {
  type: 'rectangle'
  x: number
  y: number
  width: number
  height: number
}

export interface EllipseGeometry {
  type: 'ellipse'
  cx: number
  cy: number
  rx: number
  ry: number
}

export interface PolygonGeometry {
  type: 'polygon'
  points: AnnotationPoint[]
}

export interface TextGeometry {
  type: 'text'
  x: number
  y: number
  text: string
}

export type AnnotationGeometry =
  | PointGeometry
  | PolylineGeometry
  | AngleGeometry
  | RectangleGeometry
  | EllipseGeometry
  | PolygonGeometry
  | TextGeometry

export interface AnnotationStyle {
  strokeColor: string
  fillColor: string
  strokeWidth: number
  opacity: number
  labelVisible: boolean
}

export interface AnnotationMetadata {
  title: string
  classification: string
  tags: string[]
  notes: string
}

export interface AnnotationBounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export type MeasurementValue = number | string

export interface AnnotationInput {
  id: string
  layerId: string
  geometry: AnnotationGeometry
  style: AnnotationStyle
  metadata: AnnotationMetadata
}

export interface AnnotationRecord extends AnnotationInput {
  version: number
  deletedAt: string | null
  createdAt: string
  updatedAt: string
  bounds: AnnotationBounds
  measurements: Record<string, MeasurementValue>
}

export interface AnnotationLayer {
  id: string
  slideId: string
  name: string
  sortOrder: number
  visible: boolean
  locked: boolean
  opacity: number
  createdAt: string
  updatedAt: string
}

export interface AnnotationLayerInput {
  id: string
  name: string
  sortOrder: number
  visible: boolean
  locked: boolean
  opacity: number
}

export type AnnotationMutation =
  | { type: 'create'; item: AnnotationInput }
  | {
    type: 'update'
    id: string
    version: number
    layerId?: string
    geometry?: AnnotationGeometry
    style?: AnnotationStyle
    metadata?: AnnotationMetadata
  }
  | { type: 'delete'; id: string; version: number }
  | { type: 'restore'; id: string; version: number }

export interface AnnotationBatchRequest {
  mutationId: string
  baseVersion: number
  operations: AnnotationMutation[]
}

export interface AnnotationMutationResult {
  id: string
  operation: AnnotationMutation['type']
  version: number
  deleted: boolean
}

export interface AnnotationBatchResult {
  mutationId: string
  version: number
  results: AnnotationMutationResult[]
  purged: number
}

export interface AnnotationSlideBounds {
  width: number
  height: number
}

export interface AnnotationCalibration {
  x: number
  y: number
  unit: string
}

export interface AnnotationLimits {
  activeAnnotations: number
  layers: number
  verticesPerShape: number
  verticesPerImport: number
  batchOperations: number
}

export interface AnnotationManifest {
  slideId: string
  version: number
  bounds: AnnotationSlideBounds
  calibration: AnnotationCalibration | null
  activeCount: number
  trashedCount: number
  layers: AnnotationLayer[]
  limits: AnnotationLimits
}

export interface AnnotationItemsPage {
  items: AnnotationRecord[]
  total: number
  nextOffset: number | null
}

export interface PathLabAnnotationDocument {
  schema: typeof ANNOTATION_SCHEMA
  slide: {
    id: string
    width: number
    height: number
    annotationVersion: number
  }
  layers: AnnotationLayerInput[]
  annotations: AnnotationInput[]
}

export type AnnotationTool =
  | 'hand'
  | 'select'
  | 'marquee'
  | 'point'
  | 'ruler'
  | 'polyline'
  | 'angle'
  | 'rectangle'
  | 'ellipse'
  | 'polygon'
  | 'freehand'
  | 'brush-add'
  | 'brush-subtract'
  | 'text'

export type PolygonBooleanOperation = 'union' | 'subtract' | 'intersection' | 'split'

export interface AnnotationFilter {
  search: string
  layerIds: Set<string>
  classifications?: Set<string>
  tags?: Set<string>
  includeDeleted?: boolean
}

export interface ImportPreview {
  valid: boolean
  format: 'pathlab' | 'geojson' | 'unknown'
  annotationCount: number
  vertexCount: number
  byteSize: number
  target: 'new-layer'
  errors: string[]
}

export interface MeasurementValues {
  x?: number
  xUnit?: string
  y?: number
  yUnit?: string
  count?: number
  length?: number
  lengthUnit?: string
  angle?: number
  angleUnit?: string
  perimeter?: number
  perimeterUnit?: string
  area?: number
  areaUnit?: string
}
