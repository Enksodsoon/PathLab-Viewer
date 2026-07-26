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
import {
  ANNOTATION_SCHEMA,
  MAX_ACTIVE_ANNOTATIONS,
  MAX_ANNOTATION_LAYERS,
  MAX_VERTICES_PER_IMPORT,
  MAX_VERTICES_PER_SHAPE,
} from './types'

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

interface ImportPreviewLimits {
  maxBytes?: number
  maxVertices?: number
  maxAnnotations?: number
  maxLayers?: number
  maxVerticesPerShape?: number
  bounds?: { width: number; height: number }
}

interface PreviewValidation {
  add(message: string): void
  point(value: unknown, path: string, bounds: { width: number; height: number }): boolean
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const HTML_TAG = /<\s*\/?\s*[a-zA-Z][^>]*>/

function validationCollector(errors: string[]): PreviewValidation {
  const seen = new Set<string>()
  return {
    add(message) {
      if (seen.has(message) || errors.length >= 50) return
      seen.add(message)
      errors.push(message)
    },
    point(value, path, bounds) {
      if (
        !isObject(value)
        || typeof value.x !== 'number'
        || typeof value.y !== 'number'
        || !Number.isFinite(value.x)
        || !Number.isFinite(value.y)
      ) {
        this.add(`${path} must contain finite x/y coordinates`)
        this.add(`${path} is outside the slide bounds`)
        return false
      }
      if (value.x < 0 || value.y < 0 || value.x > bounds.width || value.y > bounds.height) {
        this.add(`${path} is outside the slide bounds`)
        return false
      }
      return true
    },
  }
}

function validPlainText(
  value: unknown,
  maxLength: number,
): value is string {
  return (
    typeof value === 'string'
    && value.length <= maxLength
    && !HTML_TAG.test(value)
    && !Array.from(value).some((character) => {
      const codePoint = character.codePointAt(0) ?? 0
      return (
        codePoint <= 8
        || codePoint === 11
        || codePoint === 12
        || (codePoint >= 14 && codePoint <= 31)
        || codePoint === 127
      )
    })
  )
}

function validNonblankPlainText(value: unknown, maxLength: number): value is string {
  return validPlainText(value, maxLength) && value.trim().length > 0
}

function validateExactKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
  path: string,
  validation: PreviewValidation,
): void {
  const allowedKeys = new Set(allowed)
  for (const key of Object.keys(value)) {
    if (!allowedKeys.has(key)) {
      validation.add(`${path} contains unknown extra field ${key}`)
    }
  }
}

function validUuid(value: unknown): value is string {
  return typeof value === 'string' && UUID.test(value)
}

function validateStyle(value: unknown, path: string, validation: PreviewValidation): void {
  if (value === undefined) return
  if (!isObject(value)) {
    validation.add(`${path} has invalid annotation style values`)
    return
  }
  validateExactKeys(
    value,
    ['strokeColor', 'fillColor', 'strokeWidth', 'opacity', 'labelVisible'],
    path,
    validation,
  )
  if (
    (value.strokeColor !== undefined
      && (typeof value.strokeColor !== 'string' || !HEX_COLOR.test(value.strokeColor)))
    || (value.fillColor !== undefined
      && (typeof value.fillColor !== 'string' || !HEX_COLOR.test(value.fillColor)))
    || (value.strokeWidth !== undefined
      && (
        typeof value.strokeWidth !== 'number'
        || !Number.isFinite(value.strokeWidth)
        || value.strokeWidth < 0.25
        || value.strokeWidth > 64
      ))
    || (value.opacity !== undefined
      && (
        typeof value.opacity !== 'number'
        || !Number.isFinite(value.opacity)
        || value.opacity < 0
        || value.opacity > 1
      ))
    || (value.labelVisible !== undefined && typeof value.labelVisible !== 'boolean')
  ) {
    validation.add(`${path} has invalid annotation style values`)
  }
}

function validateMetadata(value: unknown, path: string, validation: PreviewValidation): void {
  if (value === undefined) return
  if (!isObject(value)) {
    validation.add(`${path} has invalid or unsafe annotation metadata`)
    return
  }
  validateExactKeys(value, ['title', 'classification', 'tags', 'notes'], path, validation)
  if (
    (value.title !== undefined && !validPlainText(value.title, 200))
    || (value.classification !== undefined && !validPlainText(value.classification, 120))
    || (value.notes !== undefined && !validPlainText(value.notes, 4_000))
    || (value.tags !== undefined && (
      !Array.isArray(value.tags)
      || value.tags.length > 50
      || value.tags.some((tag) => !validNonblankPlainText(tag, 80))
    ))
  ) {
    validation.add(`${path} has invalid or unsafe annotation metadata`)
  }
}

function validateGeometry(
  value: unknown,
  path: string,
  bounds: { width: number; height: number },
  maxVerticesPerShape: number,
  validation: PreviewValidation,
): number {
  if (!isObject(value) || typeof value.type !== 'string') {
    validation.add(`${path} is not a supported annotation geometry`)
    return 0
  }
  const geometryKeys: Record<string, readonly string[]> = {
    point: ['type', 'x', 'y'],
    text: ['type', 'x', 'y', 'text'],
    polyline: ['type', 'points'],
    angle: ['type', 'points'],
    polygon: ['type', 'points'],
    rectangle: ['type', 'x', 'y', 'width', 'height'],
    ellipse: ['type', 'cx', 'cy', 'rx', 'ry'],
  }
  const allowedGeometryKeys = geometryKeys[value.type]
  if (allowedGeometryKeys) {
    validateExactKeys(value, allowedGeometryKeys, path, validation)
  }

  let vertexCount = 0
  const validatePoints = (candidate: unknown, minimum: number, exact?: number): void => {
    if (!Array.isArray(candidate)) {
      validation.add(`${path}.points must be an array`)
      return
    }
    vertexCount = candidate.length
    if (candidate.length < minimum || (exact !== undefined && candidate.length !== exact)) {
      validation.add(`${path} has an invalid number of vertices`)
    }
    for (let index = 0; index < candidate.length; index += 1) {
      if (isObject(candidate[index])) {
        validateExactKeys(candidate[index], ['x', 'y'], `${path}.points[${index}]`, validation)
      }
      validation.point(candidate[index], `${path}.points[${index}]`, bounds)
    }
  }

  switch (value.type) {
    case 'point':
      vertexCount = 1
      validation.point(value, path, bounds)
      break
    case 'text':
      vertexCount = 1
      validation.point(value, path, bounds)
      if (!validPlainText(value.text, 2_000) || value.text.length === 0) {
        validation.add(`${path}.text must be safe plain text between 1 and 2,000 characters`)
      }
      break
    case 'polyline':
      validatePoints(value.points, 2)
      break
    case 'angle':
      validatePoints(value.points, 3, 3)
      break
    case 'polygon':
      validatePoints(value.points, 3)
      break
    case 'rectangle': {
      vertexCount = 4
      const x = value.x
      const y = value.y
      const width = value.width
      const height = value.height
      if (
        typeof x !== 'number'
        || typeof y !== 'number'
        || typeof width !== 'number'
        || typeof height !== 'number'
        || !Number.isFinite(x)
        || !Number.isFinite(y)
        || !Number.isFinite(width)
        || !Number.isFinite(height)
      ) {
        validation.add(`${path} must contain finite rectangle coordinates`)
      }
      if (typeof width !== 'number' || typeof height !== 'number' || width <= 0 || height <= 0) {
        validation.add(`${path} rectangle dimensions must be positive`)
      }
      if (
        typeof x !== 'number'
        || typeof y !== 'number'
        || typeof width !== 'number'
        || typeof height !== 'number'
        || !Number.isFinite(x)
        || !Number.isFinite(y)
        || !Number.isFinite(width)
        || !Number.isFinite(height)
        || x < 0
        || y < 0
        || x + width > bounds.width
        || y + height > bounds.height
      ) {
        validation.add(`${path} is outside the slide bounds`)
      }
      break
    }
    case 'ellipse': {
      vertexCount = 64
      const cx = value.cx
      const cy = value.cy
      const rx = value.rx
      const ry = value.ry
      if (
        typeof cx !== 'number'
        || typeof cy !== 'number'
        || typeof rx !== 'number'
        || typeof ry !== 'number'
        || !Number.isFinite(cx)
        || !Number.isFinite(cy)
        || !Number.isFinite(rx)
        || !Number.isFinite(ry)
      ) {
        validation.add(`${path} must contain finite ellipse coordinates`)
      }
      if (typeof rx !== 'number' || typeof ry !== 'number' || rx <= 0 || ry <= 0) {
        validation.add(`${path} ellipse radii must be positive`)
      }
      if (
        typeof cx !== 'number'
        || typeof cy !== 'number'
        || typeof rx !== 'number'
        || typeof ry !== 'number'
        || !Number.isFinite(cx)
        || !Number.isFinite(cy)
        || !Number.isFinite(rx)
        || !Number.isFinite(ry)
        || cx - rx < 0
        || cy - ry < 0
        || cx + rx > bounds.width
        || cy + ry > bounds.height
      ) {
        validation.add(`${path} is outside the slide bounds`)
      }
      break
    }
    default:
      validation.add(`${path} uses unsupported geometry type ${value.type}`)
  }

  if (vertexCount > maxVerticesPerShape) {
    validation.add(
      `${path} exceeds the ${maxVerticesPerShape.toLocaleString('en-US')} vertices per shape limit`,
    )
  }
  return vertexCount
}

function validBounds(value: unknown): value is { width: number; height: number } {
  return (
    isObject(value)
    && typeof value.width === 'number'
    && typeof value.height === 'number'
    && Number.isFinite(value.width)
    && Number.isFinite(value.height)
    && value.width > 0
    && value.height > 0
  )
}

function validatePathLabPreview(
  source: Record<string, unknown>,
  limits: Required<Pick<
    ImportPreviewLimits,
    'maxAnnotations' | 'maxLayers' | 'maxVerticesPerShape'
  >> & { bounds?: { width: number; height: number } },
  validation: PreviewValidation,
): { annotationCount: number; vertexCount: number } {
  validateExactKeys(source, ['schema', 'slide', 'layers', 'annotations'], 'document', validation)
  if (!isObject(source.slide) || !Array.isArray(source.layers) || !Array.isArray(source.annotations)) {
    validation.add('Invalid PathLab annotation document')
    return { annotationCount: 0, vertexCount: 0 }
  }
  validateExactKeys(
    source.slide,
    ['id', 'width', 'height', 'annotationVersion'],
    'slide',
    validation,
  )
  const annotationVersion = source.slide.annotationVersion
  if (
    typeof source.slide.id !== 'string'
    || !validBounds(source.slide)
    || typeof annotationVersion !== 'number'
    || !Number.isSafeInteger(annotationVersion)
    || annotationVersion < 0
  ) {
    validation.add('PathLab slide fields are invalid')
  }
  const annotationCount = source.annotations.length
  if (annotationCount > limits.maxAnnotations) {
    validation.add(
      `Import exceeds the ${limits.maxAnnotations.toLocaleString('en-US')} annotation limit`,
    )
  }
  if (source.layers.length > limits.maxLayers) {
    validation.add(`Import exceeds the ${limits.maxLayers.toLocaleString('en-US')} layer limit`)
  }

  const documentBounds = limits.bounds ?? source.slide
  if (!validBounds(documentBounds)) {
    validation.add('PathLab slide dimensions must be finite positive bounds')
  }
  const bounds = validBounds(documentBounds)
    ? documentBounds
    : { width: 0, height: 0 }
  const layerIds = new Set<string>()
  source.layers.forEach((layer, index) => {
    if (isObject(layer)) {
      validateExactKeys(
        layer,
        ['id', 'name', 'sortOrder', 'visible', 'locked', 'opacity'],
        `layers[${index}]`,
        validation,
      )
      if (!validUuid(layer.id)) validation.add(`layers[${index}].id must be a UUID`)
    }
    if (
      !isObject(layer)
      || !validUuid(layer.id)
      || !validNonblankPlainText(layer.name, 160)
      || typeof layer.sortOrder !== 'number'
      || !Number.isSafeInteger(layer.sortOrder)
      || layer.sortOrder < 0
      || typeof layer.visible !== 'boolean'
      || typeof layer.locked !== 'boolean'
      || typeof layer.opacity !== 'number'
      || !Number.isFinite(layer.opacity)
      || layer.opacity < 0
      || layer.opacity > 1
    ) {
      validation.add(`layers[${index}] is invalid`)
      return
    }
    if (layerIds.has(layer.id)) validation.add(`layers[${index}] has a duplicate id`)
    layerIds.add(layer.id)
  })

  const annotationIds = new Set<string>()
  let vertexCount = 0
  source.annotations.forEach((annotation, index) => {
    const path = `annotations[${index}]`
    if (!isObject(annotation)) {
      validation.add(`${path} is invalid`)
      return
    }
    validateExactKeys(
      annotation,
      ['id', 'layerId', 'geometry', 'style', 'metadata'],
      path,
      validation,
    )
    if (!validUuid(annotation.id)) {
      validation.add(`${path}.id must be a UUID`)
    } else if (annotationIds.has(annotation.id)) {
      validation.add(`${path}.id is duplicated`)
    } else {
      annotationIds.add(annotation.id)
    }
    if (!validUuid(annotation.layerId)) {
      validation.add(`${path}.layerId must be a UUID`)
    }
    if (typeof annotation.layerId !== 'string' || !layerIds.has(annotation.layerId)) {
      validation.add(`${path}.layerId does not reference an imported layer`)
    }
    vertexCount += validateGeometry(
      annotation.geometry,
      `${path}.geometry`,
      bounds,
      limits.maxVerticesPerShape,
      validation,
    )
    validateStyle(annotation.style, `${path}.style`, validation)
    validateMetadata(annotation.metadata, `${path}.metadata`, validation)
  })
  return { annotationCount, vertexCount }
}

function geoJsonPositionCount(
  value: unknown,
  path: string,
  bounds: { width: number; height: number } | undefined,
  validation: PreviewValidation,
): number {
  if (!Array.isArray(value) || value.length !== 2) {
    validation.add(`${path} must contain finite x/y coordinates`)
    return 0
  }
  const x = value[0]
  const y = value[1]
  if (
    typeof x !== 'number'
    || typeof y !== 'number'
    || !Number.isFinite(x)
    || !Number.isFinite(y)
  ) {
    validation.add(`${path} must contain finite x/y coordinates`)
    if (bounds) validation.add(`${path} is outside the slide bounds`)
    return 1
  }
  if (bounds && (x < 0 || y < 0 || x > bounds.width || y > bounds.height)) {
    validation.add(`${path} is outside the slide bounds`)
  }
  return 1
}

function validateGeoJsonPreview(
  source: Record<string, unknown>,
  limits: Required<Pick<
    ImportPreviewLimits,
    'maxAnnotations' | 'maxLayers' | 'maxVerticesPerShape'
  >> & { bounds?: { width: number; height: number } },
  validation: PreviewValidation,
): { annotationCount: number; vertexCount: number } {
  validateExactKeys(source, ['type', 'features'], 'GeoJSON document', validation)
  if (!Array.isArray(source.features)) {
    validation.add('GeoJSON import requires a FeatureCollection')
    return { annotationCount: 0, vertexCount: 0 }
  }
  const annotationCount = source.features.length
  if (annotationCount > limits.maxAnnotations) {
    validation.add(
      `Import exceeds the ${limits.maxAnnotations.toLocaleString('en-US')} annotation limit`,
    )
  }
  if (limits.bounds && !validBounds(limits.bounds)) {
    validation.add('GeoJSON target slide dimensions must be finite positive bounds')
  }
  const bounds = limits.bounds && validBounds(limits.bounds) ? limits.bounds : undefined
  const layerNames = new Set<string>()
  let vertexCount = 0
  source.features.forEach((feature, featureIndex) => {
    const path = `features[${featureIndex}]`
    if (!isObject(feature) || feature.type !== 'Feature' || !isObject(feature.geometry)) {
      validation.add(`${path} is not a valid GeoJSON feature`)
      return
    }
    validateExactKeys(feature, ['type', 'id', 'geometry', 'properties'], path, validation)
    if (
      feature.id !== undefined
      && feature.id !== null
      && typeof feature.id !== 'string'
      && (typeof feature.id !== 'number' || !Number.isFinite(feature.id))
    ) {
      validation.add(`${path}.id must be a string, number, or null`)
    }
    if (!isObject(feature.properties)) {
      validation.add(`${path}.properties is required`)
    }
    const properties = isObject(feature.properties) ? feature.properties : {}
    validateExactKeys(
      properties,
      ['name', 'classification', 'tags', 'notes', 'layerName', 'style', 'text'],
      `${path}.properties`,
      validation,
    )
    const layerName = properties.layerName ?? 'Imported annotations'
    if (!validNonblankPlainText(layerName, 160)) {
      validation.add(`${path}.properties.layerName is invalid`)
    } else {
      layerNames.add(layerName)
    }
    let shapeVertices = 0
    const geometry = feature.geometry
    validateExactKeys(geometry, ['type', 'coordinates'], `${path}.geometry`, validation)
    if (geometry.type === 'Point') {
      shapeVertices += geoJsonPositionCount(
        geometry.coordinates,
        `${path}.geometry.coordinates`,
        bounds,
        validation,
      )
    } else if (geometry.type === 'LineString') {
      if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length < 2) {
        validation.add(`${path}.geometry requires at least 2 positions`)
      } else {
        geometry.coordinates.forEach((position, index) => {
          shapeVertices += geoJsonPositionCount(
            position,
            `${path}.geometry.coordinates[${index}]`,
            bounds,
            validation,
          )
        })
      }
    } else if (geometry.type === 'Polygon') {
      if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) {
        validation.add(`${path}.geometry requires a polygon ring`)
      } else {
        if (geometry.coordinates.length !== 1) {
          validation.add(`${path}.geometry must contain exactly one ring; interior rings are unsupported`)
        }
        geometry.coordinates.forEach((ring, ringIndex) => {
          if (
            !Array.isArray(ring)
            || ring.length < 4
            || ring.length > limits.maxVerticesPerShape + 1
          ) {
            validation.add(
              `${path}.geometry ring ${ringIndex} requires 4 to ${(
                limits.maxVerticesPerShape + 1
              ).toLocaleString('en-US')} positions`,
            )
            return
          }
          ring.forEach((position, positionIndex) => {
            shapeVertices += geoJsonPositionCount(
              position,
              `${path}.geometry.coordinates[${ringIndex}][${positionIndex}]`,
              bounds,
              validation,
            )
          })
          const first = ring[0]
          const last = ring[ring.length - 1]
          if (
            Array.isArray(first)
            && Array.isArray(last)
            && first[0] === last[0]
            && first[1] === last[1]
          ) {
            shapeVertices -= 1
          } else {
            validation.add(`${path}.geometry polygon rings must be closed`)
          }
        })
      }
    } else {
      validation.add(`${path}.geometry has an unsupported GeoJSON type`)
    }
    if (shapeVertices > limits.maxVerticesPerShape) {
      validation.add(
        `${path} exceeds the ${limits.maxVerticesPerShape.toLocaleString('en-US')} vertices per shape limit`,
      )
    }
    vertexCount += shapeVertices
    if (properties.style !== undefined) {
      validateStyle(properties.style, `${path}.properties.style`, validation)
    }
    validateMetadata({
      title: properties.name ?? '',
      classification: isObject(properties.classification)
        ? properties.classification.name ?? ''
        : '',
      tags: properties.tags ?? [],
      notes: properties.notes ?? '',
    }, `${path}.properties metadata`, validation)
    if (
      properties.classification !== undefined
      && properties.classification !== null
    ) {
      if (!isObject(properties.classification)) {
        validation.add(`${path}.properties.classification is invalid`)
      } else {
        validateExactKeys(
          properties.classification,
          ['name', 'color'],
          `${path}.properties.classification`,
          validation,
        )
        if (
          !validNonblankPlainText(properties.classification.name, 120)
          || typeof properties.classification.color !== 'string'
          || !HEX_COLOR.test(properties.classification.color)
        ) {
          validation.add(`${path}.properties.classification has invalid name or color`)
        }
      }
    }
    if (
      properties.text !== undefined
      && properties.text !== null
      && !validPlainText(properties.text, 2_000)
    ) {
      validation.add(`${path}.properties.text has invalid or unsafe metadata`)
    }
    if (geometry.type === 'Point' && properties.text === '') {
      validation.add(`${path}.properties.text must be non-empty for a text point`)
    }
  })
  if (layerNames.size > limits.maxLayers) {
    validation.add(`Import exceeds the ${limits.maxLayers.toLocaleString('en-US')} layer limit`)
  }
  return { annotationCount, vertexCount }
}

export function previewImport(
  source: unknown,
  limits: ImportPreviewLimits = {},
): ImportPreview {
  const serialized = JSON.stringify(source) ?? ''
  const byteSize = new TextEncoder().encode(serialized).byteLength
  const maxBytes = limits.maxBytes ?? 8 * 1024 * 1024
  const maxVertices = limits.maxVertices ?? MAX_VERTICES_PER_IMPORT
  const maxAnnotations = limits.maxAnnotations ?? MAX_ACTIVE_ANNOTATIONS
  const maxLayers = limits.maxLayers ?? MAX_ANNOTATION_LAYERS
  const maxVerticesPerShape = limits.maxVerticesPerShape ?? MAX_VERTICES_PER_SHAPE
  let format: ImportPreview['format'] = 'unknown'
  let annotationCount = 0
  let vertexCount = 0
  const errors: string[] = []
  const validation = validationCollector(errors)
  if (isObject(source) && source.schema === ANNOTATION_SCHEMA) {
    format = 'pathlab'
    const counts = validatePathLabPreview(source, {
      maxAnnotations,
      maxLayers,
      maxVerticesPerShape,
      ...(limits.bounds === undefined ? {} : { bounds: limits.bounds }),
    }, validation)
    annotationCount = counts.annotationCount
    vertexCount = counts.vertexCount
  } else if (isObject(source) && source.type === 'FeatureCollection') {
    format = 'geojson'
    const counts = validateGeoJsonPreview(source, {
      maxAnnotations,
      maxLayers,
      maxVerticesPerShape,
      ...(limits.bounds === undefined ? {} : { bounds: limits.bounds }),
    }, validation)
    annotationCount = counts.annotationCount
    vertexCount = counts.vertexCount
  } else {
    validation.add('Unsupported annotation import format')
  }
  if (byteSize > maxBytes) validation.add('Import exceeds the 8 MiB limit')
  if (vertexCount > maxVertices) validation.add('Import exceeds the 250,000 vertex limit')
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
