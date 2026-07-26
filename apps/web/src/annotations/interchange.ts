import { asPolygon } from './geometry'
import type {
  AnnotationGeometry,
  AnnotationInput,
  AnnotationMetadata,
  AnnotationStyle,
  ImportPreview,
  MeasurementValues,
  PathLabAnnotationDocument,
} from './types'
import { ANNOTATION_SCHEMA, MAX_VERTICES_PER_IMPORT } from './types'

type GeoJsonPosition = [number, number]

interface GeoJsonGeometry {
  type: 'Point' | 'LineString' | 'Polygon'
  coordinates: GeoJsonPosition | GeoJsonPosition[] | GeoJsonPosition[][]
}

interface GeoJsonProperties {
  name?: string
  classification?: { name: string; color: string } | null
  tags?: string[]
  notes?: string
  layerName?: string
  style?: AnnotationStyle
  text?: string
}

interface GeoJsonFeature {
  type: 'Feature'
  id?: string
  geometry: GeoJsonGeometry
  properties: GeoJsonProperties
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection'
  features: GeoJsonFeature[]
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function validatePathLab(value: unknown): asserts value is PathLabAnnotationDocument {
  if (!isObject(value) || value.schema !== ANNOTATION_SCHEMA) {
    throw new TypeError('Unsupported PathLab annotation schema')
  }
  if (!isObject(value.slide) || !Array.isArray(value.layers) || !Array.isArray(value.annotations)) {
    throw new TypeError('Invalid PathLab annotation document')
  }
}

export function parsePathLab(
  source: string | PathLabAnnotationDocument,
): PathLabAnnotationDocument {
  const parsed: unknown = typeof source === 'string' ? JSON.parse(source) : structuredClone(source)
  validatePathLab(parsed)
  return parsed
}

function closedCoordinates(geometry: AnnotationGeometry): GeoJsonPosition[] {
  const polygon = asPolygon(geometry)
  const coordinates = polygon.points.map(({ x, y }) => [x, y] satisfies GeoJsonPosition)
  coordinates.push([...coordinates[0]] as GeoJsonPosition)
  return coordinates
}

function geoGeometry(geometry: AnnotationGeometry): {
  geometry: GeoJsonGeometry
  text?: string
} {
  switch (geometry.type) {
    case 'point':
      return { geometry: { type: 'Point', coordinates: [geometry.x, geometry.y] } }
    case 'text':
      return {
        geometry: { type: 'Point', coordinates: [geometry.x, geometry.y] },
        text: geometry.text,
      }
    case 'polyline':
    case 'angle':
      return {
        geometry: {
          type: 'LineString',
          coordinates: geometry.points.map(
            ({ x, y }) => [x, y] satisfies GeoJsonPosition,
          ),
        },
      }
    case 'rectangle':
    case 'ellipse':
    case 'polygon':
      return {
        geometry: {
          type: 'Polygon',
          coordinates: [closedCoordinates(geometry)],
        },
      }
  }
}

export function toGeoJson(document: PathLabAnnotationDocument): GeoJsonFeatureCollection {
  const layers = new Map(document.layers.map((layer) => [layer.id, layer.name]))
  return {
    type: 'FeatureCollection',
    features: document.annotations.map((annotation) => {
      const mapped = geoGeometry(annotation.geometry)
      return {
        type: 'Feature',
        id: annotation.id,
        geometry: mapped.geometry,
        properties: {
          name: annotation.metadata.title,
          classification: annotation.metadata.classification
            ? {
              name: annotation.metadata.classification,
              color: annotation.style.strokeColor,
            }
            : null,
          tags: [...annotation.metadata.tags],
          notes: annotation.metadata.notes,
          layerName: layers.get(annotation.layerId) ?? 'Imported annotations',
          style: structuredClone(annotation.style),
          ...(mapped.text === undefined ? {} : { text: mapped.text }),
        },
      }
    }),
  }
}

const DEFAULT_STYLE: AnnotationStyle = {
  strokeColor: '#c43d3d',
  fillColor: '#c43d3d',
  strokeWidth: 2,
  opacity: 0.35,
  labelVisible: true,
}

function points(value: unknown): GeoJsonPosition[] {
  if (!Array.isArray(value)) throw new TypeError('GeoJSON coordinates must be an array')
  return value.map((position) => {
    if (
      !Array.isArray(position)
      || position.length < 2
      || typeof position[0] !== 'number'
      || typeof position[1] !== 'number'
      || !Number.isFinite(position[0])
      || !Number.isFinite(position[1])
    ) {
      throw new TypeError('GeoJSON coordinates must contain finite x/y positions')
    }
    return [position[0], position[1]]
  })
}

function fromGeoGeometry(
  geometry: GeoJsonGeometry,
  properties: GeoJsonProperties,
): AnnotationGeometry {
  if (geometry.type === 'Point') {
    const point = points([geometry.coordinates])[0]
    return properties.text === undefined
      ? { type: 'point', x: point[0], y: point[1] }
      : { type: 'text', x: point[0], y: point[1], text: properties.text }
  }
  if (geometry.type === 'LineString') {
    return {
      type: 'polyline',
      points: points(geometry.coordinates).map(([x, y]) => ({ x, y })),
    }
  }
  const rings = geometry.coordinates
  if (!Array.isArray(rings) || !Array.isArray(rings[0])) {
    throw new TypeError('GeoJSON polygon requires a linear ring')
  }
  const ring = points(rings[0])
  const [firstX, firstY] = ring[0]
  const [lastX, lastY] = ring[ring.length - 1]
  if (firstX === lastX && firstY === lastY) ring.pop()
  return {
    type: 'polygon',
    points: ring.map(([x, y]) => ({ x, y })),
  }
}

export interface GeoJsonImportOptions {
  slideId: string
  width: number
  height: number
  layerId: string
  idFactory?: () => string
}

export function fromGeoJson(
  source: GeoJsonFeatureCollection,
  options: GeoJsonImportOptions,
): PathLabAnnotationDocument {
  if (source.type !== 'FeatureCollection' || !Array.isArray(source.features)) {
    throw new TypeError('GeoJSON import requires a FeatureCollection')
  }
  const idFactory = options.idFactory ?? (() => crypto.randomUUID())
  const annotations = source.features.map((feature): AnnotationInput => {
    if (
      feature.type !== 'Feature'
      || !feature.geometry
      || !isObject(feature.properties as unknown)
    ) {
      throw new TypeError('Invalid GeoJSON feature')
    }
    const properties = feature.properties as GeoJsonProperties
    const style = structuredClone(properties.style ?? DEFAULT_STYLE)
    const metadata: AnnotationMetadata = {
      title: properties.name ?? '',
      classification: properties.classification?.name ?? '',
      tags: [...(properties.tags ?? [])],
      notes: properties.notes ?? '',
    }
    return {
      id: feature.id ?? idFactory(),
      layerId: options.layerId,
      geometry: fromGeoGeometry(feature.geometry, properties),
      style,
      metadata,
    }
  })
  return {
    schema: ANNOTATION_SCHEMA,
    slide: {
      id: options.slideId,
      width: options.width,
      height: options.height,
      annotationVersion: 0,
    },
    layers: [{
      id: options.layerId,
      name: source.features[0]?.properties.layerName ?? 'Imported annotations',
      sortOrder: 0,
      visible: true,
      locked: false,
      opacity: 1,
    }],
    annotations,
  }
}

function geometryVertices(geometry: AnnotationGeometry): number {
  switch (geometry.type) {
    case 'angle':
    case 'polyline':
    case 'polygon':
      return geometry.points.length
    case 'rectangle':
      return 4
    case 'ellipse':
      return 64
    case 'point':
    case 'text':
      return 1
  }
}

function geoJsonVertices(collection: GeoJsonFeatureCollection): number {
  let total = 0
  for (const feature of collection.features) {
    const coordinates = feature.geometry.coordinates
    if (feature.geometry.type === 'Point') total += 1
    else if (feature.geometry.type === 'LineString') total += points(coordinates).length
    else {
      const rings = coordinates as GeoJsonPosition[][]
      for (const ring of rings) total += points(ring).length - 1
    }
  }
  return total
}

export function previewImport(
  source: unknown,
  limits: { maxBytes?: number; maxVertices?: number } = {},
): ImportPreview {
  const byteSize = new TextEncoder().encode(JSON.stringify(source)).byteLength
  const maxBytes = limits.maxBytes ?? 8 * 1024 * 1024
  const maxVertices = limits.maxVertices ?? MAX_VERTICES_PER_IMPORT
  let format: ImportPreview['format'] = 'unknown'
  let annotationCount = 0
  let vertexCount = 0
  const errors: string[] = []
  try {
    if (isObject(source) && source.schema === ANNOTATION_SCHEMA) {
      const document = parsePathLab(source as unknown as PathLabAnnotationDocument)
      format = 'pathlab'
      annotationCount = document.annotations.length
      vertexCount = document.annotations.reduce(
        (sum, annotation) => sum + geometryVertices(annotation.geometry),
        0,
      )
    } else if (isObject(source) && source.type === 'FeatureCollection') {
      const collection = source as unknown as GeoJsonFeatureCollection
      format = 'geojson'
      annotationCount = collection.features.length
      vertexCount = geoJsonVertices(collection)
    } else {
      errors.push('Unsupported annotation import format')
    }
  } catch (caught) {
    errors.push(caught instanceof Error ? caught.message : 'Invalid annotation import')
  }
  if (byteSize > maxBytes) errors.push('Import exceeds the 8 MiB limit')
  if (vertexCount > maxVertices) errors.push('Import exceeds the 250,000 vertex limit')
  return {
    valid: errors.length === 0,
    format,
    annotationCount,
    vertexCount,
    byteSize,
    target: 'new-layer',
    errors,
  }
}

export interface CsvMeasurementRow {
  id: string
  layer: string
  title: string
  classification: string
  geometryType: AnnotationGeometry['type']
  values: MeasurementValues
}

const CSV_FIELDS = [
  'id',
  'layer',
  'title',
  'classification',
  'geometryType',
  'area',
  'areaUnit',
  'perimeter',
  'perimeterUnit',
  'length',
  'lengthUnit',
  'angle',
  'angleUnit',
  'x',
  'xUnit',
  'y',
  'yUnit',
  'count',
] as const

function csvCell(value: unknown): string {
  if (value === undefined || value === null) return ''
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function exportMeasurementsCsv(rows: readonly CsvMeasurementRow[]): string {
  const body = rows.map((row) => {
    const values: Record<(typeof CSV_FIELDS)[number], unknown> = {
      id: row.id,
      layer: row.layer,
      title: row.title,
      classification: row.classification,
      geometryType: row.geometryType,
      area: row.values.area,
      areaUnit: row.values.areaUnit,
      perimeter: row.values.perimeter,
      perimeterUnit: row.values.perimeterUnit,
      length: row.values.length,
      lengthUnit: row.values.lengthUnit,
      angle: row.values.angle,
      angleUnit: row.values.angleUnit,
      x: row.values.x,
      xUnit: row.values.xUnit,
      y: row.values.y,
      yUnit: row.values.yUnit,
      count: row.values.count,
    }
    return CSV_FIELDS.map((field) => csvCell(values[field])).join(',')
  })
  return `\uFEFF${CSV_FIELDS.join(',')}\r\n${body.map((row) => `${row}\r\n`).join('')}`
}
