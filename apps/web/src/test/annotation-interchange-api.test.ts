import { afterEach, describe, expect, it, vi } from 'vitest'

import { AnnotationApiClient, AnnotationApiError } from '../annotations/api'
import {
  exportMeasurementsCsv,
  fromGeoJson,
  parsePathLab,
  previewImport,
  toGeoJson,
} from '../annotations/interchange'
import type { PathLabAnnotationDocument } from '../annotations/types'

const pathlabFixture: PathLabAnnotationDocument = {
  schema: 'pathlab-annotations/v1',
  slide: {
    id: 'slide-1',
    width: 10_000,
    height: 8_000,
    annotationVersion: 7,
  },
  layers: [{
    id: '00000000-0000-4000-8000-000000000010',
    name: 'Diagnostic',
    sortOrder: 0,
    visible: true,
    locked: false,
    opacity: 1,
  }],
  annotations: [{
    id: '00000000-0000-4000-8000-000000000001',
    layerId: '00000000-0000-4000-8000-000000000010',
    geometry: {
      type: 'polygon',
      points: [{ x: 1, y: 2 }, { x: 5, y: 2 }, { x: 5, y: 7 }],
    },
    style: {
      strokeColor: '#112233',
      fillColor: '#445566',
      strokeWidth: 2,
      opacity: 0.4,
      labelVisible: true,
    },
    metadata: {
      title: 'Literal fixture',
      classification: 'Tumour',
      tags: ['review', 'A'],
      notes: 'No derived values',
    },
  }],
}

describe('annotation interchange fixtures', () => {
  it('round-trips the exact PathLab v1 document losslessly', () => {
    const literal = JSON.stringify(pathlabFixture)
    expect(parsePathLab(literal)).toEqual(pathlabFixture)
    expect(JSON.parse(JSON.stringify(parsePathLab(literal)))).toEqual(pathlabFixture)
  })

  it('maps a literal polygon fixture to QuPath GeoJSON and back', () => {
    const geoJson = toGeoJson(pathlabFixture)
    expect(geoJson).toEqual({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        id: '00000000-0000-4000-8000-000000000001',
        geometry: {
          type: 'Polygon',
          coordinates: [[[1, 2], [5, 2], [5, 7], [1, 2]]],
        },
        properties: {
          name: 'Literal fixture',
          classification: { name: 'Tumour', color: '#112233' },
          tags: ['review', 'A'],
          notes: 'No derived values',
          layerName: 'Diagnostic',
          style: pathlabFixture.annotations[0].style,
        },
      }],
    })
    const imported = fromGeoJson(geoJson, {
      slideId: 'slide-1',
      width: 10_000,
      height: 8_000,
      layerId: '00000000-0000-4000-8000-000000000010',
      idFactory: () => '00000000-0000-4000-8000-000000000001',
    })
    expect(imported.annotations[0]).toEqual(pathlabFixture.annotations[0])
  })

  it('exports an independently checked literal CSV measurement row', () => {
    const csv = exportMeasurementsCsv([{
      id: 'a-1',
      layer: 'Diagnostic',
      title: 'A, quoted',
      classification: 'Tumour',
      geometryType: 'rectangle',
      values: {
        area: 6,
        areaUnit: 'mm²',
        perimeter: 10,
        perimeterUnit: 'mm',
      },
    }])
    expect(csv).toBe(
      '\uFEFFid,layer,title,classification,geometryType,area,areaUnit,perimeter,'
      + 'perimeterUnit,length,lengthUnit,angle,angleUnit,x,xUnit,y,yUnit,count\r\n'
      + 'a-1,Diagnostic,"A, quoted",Tumour,rectangle,6,mm²,10,mm,,,,,,,,,\r\n',
    )
  })

  it('previews import size, vertices, format, and default new layer without mutating input', () => {
    const before = structuredClone(pathlabFixture)
    expect(previewImport(pathlabFixture, { maxBytes: 8 * 1024 * 1024, maxVertices: 250_000 }))
      .toEqual({
        valid: true,
        format: 'pathlab',
        annotationCount: 1,
        vertexCount: 3,
        byteSize: new TextEncoder().encode(JSON.stringify(pathlabFixture)).byteLength,
        target: 'new-layer',
        errors: [],
    })
    expect(pathlabFixture).toEqual(before)
    expect(previewImport(pathlabFixture, { maxVertices: 2 })).toMatchObject({
      valid: false,
      vertexCount: 3,
      errors: [expect.stringMatching(/vertex limit/i)],
    })
  })

  it('rejects malformed, out-of-bounds, per-shape, annotation, and layer overflows', () => {
    const malformed = structuredClone(pathlabFixture)
    malformed.annotations[0].geometry = {
      type: 'point',
      x: 10_001,
      y: Number.NaN,
    }
    malformed.annotations[0].style.opacity = 2
    malformed.annotations[0].metadata.title = '<b>unsafe</b>'
    expect(previewImport(malformed)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([
        expect.stringMatching(/finite/i),
        expect.stringMatching(/bounds/i),
        expect.stringMatching(/style/i),
        expect.stringMatching(/metadata/i),
      ]),
    })

    const oversizedShape = structuredClone(pathlabFixture)
    oversizedShape.annotations[0].geometry = {
      type: 'polygon',
      points: Array.from({ length: 8_193 }, (_, index) => ({
        x: index % 100,
        y: Math.floor(index / 100),
      })),
    }
    expect(previewImport(oversizedShape).errors).toEqual(
      expect.arrayContaining([expect.stringMatching(/8,192/)]),
    )

    const tooManyAnnotations = structuredClone(pathlabFixture)
    tooManyAnnotations.annotations = Array.from(
      { length: 25_001 },
      (_, index) => ({ ...structuredClone(pathlabFixture.annotations[0]), id: `a-${index}` }),
    )
    expect(previewImport(tooManyAnnotations).errors).toEqual(
      expect.arrayContaining([expect.stringMatching(/25,000 annotation/i)]),
    )

    const tooManyLayers = structuredClone(pathlabFixture)
    tooManyLayers.layers = Array.from(
      { length: 101 },
      (_, index) => ({ ...pathlabFixture.layers[0], id: `layer-${index}` }),
    )
    expect(previewImport(tooManyLayers).errors).toEqual(
      expect.arrayContaining([expect.stringMatching(/100 layer/i)]),
    )
  })

  it('matches the backend PathLab field, UUID, color, and extra-forbid contracts', () => {
    const invalidMetadata = [
      {
        label: 'title above 200',
        metadata: { ...pathlabFixture.annotations[0].metadata, title: 't'.repeat(201) },
      },
      {
        label: 'classification above 120',
        metadata: {
          ...pathlabFixture.annotations[0].metadata,
          classification: 'c'.repeat(121),
        },
      },
      {
        label: 'notes above 4,000',
        metadata: { ...pathlabFixture.annotations[0].metadata, notes: 'n'.repeat(4_001) },
      },
      {
        label: 'more than 50 tags',
        metadata: {
          ...pathlabFixture.annotations[0].metadata,
          tags: Array.from({ length: 51 }, (_, index) => `tag-${index}`),
        },
      },
      {
        label: 'tag above 80',
        metadata: { ...pathlabFixture.annotations[0].metadata, tags: ['x'.repeat(81)] },
      },
      {
        label: 'blank tag',
        metadata: { ...pathlabFixture.annotations[0].metadata, tags: [''] },
      },
    ]
    for (const fixture of invalidMetadata) {
      const document = structuredClone(pathlabFixture)
      document.annotations[0].metadata = fixture.metadata
      expect(previewImport(document), fixture.label).toMatchObject({
        valid: false,
        errors: expect.arrayContaining([expect.stringMatching(/metadata/i)]),
      })
    }

    const eightDigitColor = structuredClone(pathlabFixture)
    eightDigitColor.annotations[0].style.strokeColor = '#11223344'
    expect(previewImport(eightDigitColor)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/style/i)]),
    })

    const longLayer = structuredClone(pathlabFixture)
    longLayer.layers[0].name = 'l'.repeat(161)
    expect(previewImport(longLayer)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/layer/i)]),
    })

    const negativeSort = structuredClone(pathlabFixture)
    negativeSort.layers[0].sortOrder = -1
    expect(previewImport(negativeSort)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/layer/i)]),
    })

    const unboundedSort = structuredClone(pathlabFixture)
    unboundedSort.layers[0].sortOrder = Number.MAX_SAFE_INTEGER + 1
    expect(previewImport(unboundedSort)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/layer/i)]),
    })

    const invalidLayerUuid = structuredClone(pathlabFixture)
    invalidLayerUuid.layers[0].id = 'not-a-uuid'
    invalidLayerUuid.annotations[0].layerId = 'not-a-uuid'
    expect(previewImport(invalidLayerUuid)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/uuid/i)]),
    })

    const orphanLayerReference = structuredClone(pathlabFixture)
    orphanLayerReference.annotations[0].layerId = '00000000-0000-4000-8000-000000000099'
    expect(previewImport(orphanLayerReference)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/reference|layer/i)]),
    })

    const invalidAnnotationUuid = structuredClone(pathlabFixture)
    invalidAnnotationUuid.annotations[0].id = 'not-a-uuid'
    expect(previewImport(invalidAnnotationUuid)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/uuid/i)]),
    })

    const unknownRoot = Object.assign(structuredClone(pathlabFixture), { unexpected: true })
    expect(previewImport(unknownRoot)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/unknown|extra/i)]),
    })

    const unknownGeometry = structuredClone(pathlabFixture)
    Object.assign(unknownGeometry.annotations[0].geometry, { unexpected: true })
    expect(previewImport(unknownGeometry)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/unknown|extra/i)]),
    })
  })

  it('matches the backend GeoJSON single-ring, metadata, color, and extra contracts', () => {
    const base = toGeoJson(pathlabFixture)

    const interiorRing = structuredClone(base)
    if (interiorRing.features[0].geometry.type !== 'Polygon') {
      throw new Error('Literal fixture must remain a polygon')
    }
    const polygonCoordinates = interiorRing.features[0].geometry.coordinates as Array<
      Array<[number, number]>
    >
    polygonCoordinates.push([[2, 3], [3, 3], [3, 4], [2, 3]])
    expect(previewImport(interiorRing)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/one|single|interior|ring/i)]),
    })

    const longName = structuredClone(base)
    longName.features[0].properties.name = 'n'.repeat(201)
    expect(previewImport(longName)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/metadata|properties/i)]),
    })

    const longLayerName = structuredClone(base)
    longLayerName.features[0].properties.layerName = 'l'.repeat(161)
    expect(previewImport(longLayerName)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/layerName/i)]),
    })

    const classificationColor = structuredClone(base)
    classificationColor.features[0].properties.classification = {
      name: 'Tumour',
      color: '#11223344',
    }
    expect(previewImport(classificationColor)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/classification|color/i)]),
    })

    const unknownProperty = structuredClone(base)
    Object.assign(unknownProperty.features[0].properties, { unexpected: true })
    expect(previewImport(unknownProperty)).toMatchObject({
      valid: false,
      errors: expect.arrayContaining([expect.stringMatching(/unknown|extra/i)]),
    })
  })
})

describe('private annotation API client', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    sessionStorage.clear()
  })

  it('uses only encoded admin routes, same-origin credentials, and CSRF on mutation', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        slideId: 'slide/1',
        version: 0,
        bounds: { width: 10, height: 10 },
        calibration: null,
        activeCount: 0,
        trashedCount: 0,
        layers: [],
        limits: {
          activeAnnotations: 25_000,
          layers: 100,
          verticesPerShape: 8_192,
          verticesPerImport: 250_000,
          batchOperations: 50,
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        mutationId: 'm-1',
        version: 1,
        results: [],
        purged: 0,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const client = new AnnotationApiClient({
      fetcher,
      csrfToken: () => 'csrf-secret',
    })

    await client.getManifest('slide/1')
    await client.batch('slide/1', {
      mutationId: 'm-1',
      baseVersion: 0,
      operations: [{ type: 'delete', id: 'a-1', version: 1 }],
    })

    expect(fetcher.mock.calls[0][0]).toBe(
      '/api/v2/admin/annotations/slides/slide%2F1/manifest',
    )
    expect(fetcher.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin' })
    expect(fetcher.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf-secret',
      },
    })
  })

  it('preserves conflict detail from backend errors', async () => {
    const client = new AnnotationApiClient({
      fetcher: vi.fn(async () => new Response(JSON.stringify({
        detail: { code: 'ANNOTATION_CONFLICT', currentVersion: 12 },
      }), { status: 409, headers: { 'Content-Type': 'application/json' } })),
      csrfToken: () => 'csrf',
    })
    await expect(client.getManifest('slide-1')).rejects.toEqual(
      new AnnotationApiError(409, 'ANNOTATION_CONFLICT', { currentVersion: 12 }),
    )
  })

  it('reuses the application CSRF refresh-and-retry path for a rotated token', async () => {
    sessionStorage.setItem('pathlab-csrf', 'stale')
    const fetcher = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({
        detail: { code: 'CSRF_INVALID' },
      }), { status: 403, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        csrfToken: 'rotated',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        mutationId: 'm-1',
        version: 2,
        results: [],
        purged: 0,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const client = new AnnotationApiClient()

    await client.batch('slide-1', {
      mutationId: 'm-1',
      baseVersion: 1,
      operations: [{ type: 'delete', id: 'a-1', version: 1 }],
    })

    expect(fetcher).toHaveBeenCalledTimes(3)
    expect(fetcher.mock.calls[1][0]).toBe('/api/v1/auth/session')
    expect(fetcher.mock.calls[2][1]).toMatchObject({
      credentials: 'same-origin',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'rotated' }),
    })
  })
})
