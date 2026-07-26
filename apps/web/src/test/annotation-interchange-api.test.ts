import { describe, expect, it, vi } from 'vitest'

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
})

describe('private annotation API client', () => {
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
})
