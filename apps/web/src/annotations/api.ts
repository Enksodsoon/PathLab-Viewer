import type {
  AnnotationBatchRequest,
  AnnotationBatchResult,
  AnnotationBounds,
  AnnotationItemsPage,
  AnnotationLayer,
  AnnotationManifest,
  AnnotationRecord,
} from './types'
import { csrfFetch } from '../api'

const BASE = '/api/v2/admin/annotations/slides'
const NORMAL_REQUEST_BYTES = 256 * 1024
const IMPORT_REQUEST_BYTES = 8 * 1024 * 1024

type AnnotationFetcher = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>

export class AnnotationApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: Record<string, unknown> = {},
  ) {
    super(code)
  }
}

export interface AnnotationApiClientOptions {
  fetcher?: AnnotationFetcher
  mutationFetcher?: AnnotationFetcher
  csrfToken?: () => string
}

export interface AnnotationItemsQuery {
  includeDeleted?: boolean
  layerId?: string
  viewport?: AnnotationBounds
  limit?: number
  offset?: number
  signal?: AbortSignal
}

export interface LayerMutation {
  mutationId: string
  baseVersion: number
  name: string
  sortOrder?: number
  visible?: boolean
  locked?: boolean
  opacity?: number
}

export interface LayerUpdate {
  mutationId: string
  baseVersion: number
  name?: string
  sortOrder?: number
  visible?: boolean
  locked?: boolean
  opacity?: number
}

export interface AnnotationRevision {
  id: string
  version: number
  layerId: string
  geometry: AnnotationRecord['geometry']
  style: AnnotationRecord['style']
  metadata: AnnotationRecord['metadata']
  deletedAt: string | null
  createdAt: string
}

function slideRoute(slideId: string): string {
  return `${BASE}/${encodeURIComponent(slideId)}`
}

function encodedBytes(value: unknown): number {
  return new TextEncoder().encode(JSON.stringify(value)).byteLength
}

export class AnnotationApiClient {
  private readonly fetcher: AnnotationFetcher
  private readonly mutationFetcher: AnnotationFetcher
  private readonly csrfToken: () => string

  constructor(options: AnnotationApiClientOptions = {}) {
    this.fetcher = options.fetcher ?? fetch
    this.mutationFetcher = options.mutationFetcher ?? options.fetcher ?? csrfFetch
    this.csrfToken = options.csrfToken ?? (() => sessionStorage.getItem('pathlab-csrf') ?? '')
  }

  private async parse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let code = `HTTP_${response.status}`
      let detail: Record<string, unknown> = {}
      try {
        const body = await response.json() as {
          detail?: Record<string, unknown> & { code?: string }
        }
        if (body.detail) {
          const { code: responseCode, ...responseDetail } = body.detail
          code = responseCode ?? code
          detail = responseDetail
        }
      } catch {
        // Proxy responses are not guaranteed to be JSON.
      }
      throw new AnnotationApiError(response.status, code, detail)
    }
    return await response.json() as T
  }

  private async get<T>(route: string, signal?: AbortSignal): Promise<T> {
    return this.parse<T>(await this.fetcher(route, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    }))
  }

  private async mutate<T>(
    route: string,
    method: 'POST' | 'PATCH' | 'DELETE',
    payload: unknown,
    maxBytes = NORMAL_REQUEST_BYTES,
  ): Promise<T> {
    if (encodedBytes(payload) > maxBytes) {
      throw new AnnotationApiError(413, 'ANNOTATION_REQUEST_TOO_LARGE')
    }
    return this.parse<T>(await this.mutationFetcher(route, {
      method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': this.csrfToken(),
      },
      body: JSON.stringify(payload),
    }))
  }

  getManifest(slideId: string, signal?: AbortSignal): Promise<AnnotationManifest> {
    return this.get(`${slideRoute(slideId)}/manifest`, signal)
  }

  getItems(slideId: string, query: AnnotationItemsQuery = {}): Promise<AnnotationItemsPage> {
    const params = new URLSearchParams()
    if (query.includeDeleted) params.set('includeDeleted', 'true')
    if (query.layerId) params.set('layerId', query.layerId)
    if (query.viewport) {
      params.set('minX', String(query.viewport.minX))
      params.set('minY', String(query.viewport.minY))
      params.set('maxX', String(query.viewport.maxX))
      params.set('maxY', String(query.viewport.maxY))
    }
    params.set('limit', String(Math.max(1, Math.min(5_000, query.limit ?? 1_000))))
    params.set('offset', String(Math.max(0, query.offset ?? 0)))
    return this.get(`${slideRoute(slideId)}/items?${params.toString()}`, query.signal)
  }

  batch(slideId: string, request: AnnotationBatchRequest): Promise<AnnotationBatchResult> {
    if (request.operations.length > 50) {
      return Promise.reject(new AnnotationApiError(422, 'ANNOTATION_BATCH_LIMIT'))
    }
    return this.mutate(`${slideRoute(slideId)}/batch`, 'POST', request)
  }

  listLayers(slideId: string): Promise<{ items: AnnotationLayer[] }> {
    return this.get(`${slideRoute(slideId)}/layers`)
  }

  createLayer(slideId: string, request: LayerMutation): Promise<AnnotationLayer> {
    return this.mutate(`${slideRoute(slideId)}/layers`, 'POST', request)
  }

  updateLayer(
    slideId: string,
    layerId: string,
    request: LayerUpdate,
  ): Promise<{ version: number; layer: AnnotationLayer }> {
    return this.mutate(
      `${slideRoute(slideId)}/layers/${encodeURIComponent(layerId)}`,
      'PATCH',
      request,
    )
  }

  deleteLayer(
    slideId: string,
    layerId: string,
    request: { mutationId: string; baseVersion: number },
  ): Promise<{ version: number }> {
    return this.mutate(
      `${slideRoute(slideId)}/layers/${encodeURIComponent(layerId)}`,
      'DELETE',
      request,
    )
  }

  import(
    slideId: string,
    request: {
      mutationId: string
      baseVersion: number
      format: 'pathlab' | 'geojson'
      layerName?: string
      data: Record<string, unknown>
    },
  ): Promise<AnnotationBatchResult> {
    return this.mutate(
      `${slideRoute(slideId)}/import`,
      'POST',
      request,
      IMPORT_REQUEST_BYTES,
    )
  }

  async export(
    slideId: string,
    format: 'pathlab' | 'geojson' | 'csv',
  ): Promise<Response> {
    const response = await this.fetcher(
      `${slideRoute(slideId)}/export?format=${encodeURIComponent(format)}`,
      { credentials: 'same-origin', cache: 'no-store' },
    )
    if (!response.ok) await this.parse<never>(response)
    return response
  }

  revisions(
    slideId: string,
    annotationId: string,
  ): Promise<{ items: AnnotationRevision[] }> {
    return this.get(
      `${slideRoute(slideId)}/items/${encodeURIComponent(annotationId)}/revisions`,
    )
  }

  restore(
    slideId: string,
    annotationId: string,
    request: { mutationId: string; baseVersion: number; version: number },
  ): Promise<{ version: number; item: AnnotationRecord; purged: number }> {
    return this.mutate(
      `${slideRoute(slideId)}/items/${encodeURIComponent(annotationId)}/restore`,
      'POST',
      request,
    )
  }

  restoreRevision(
    slideId: string,
    annotationId: string,
    revisionId: string,
    request: { mutationId: string; baseVersion: number; version: number },
  ): Promise<{ version: number; item: AnnotationRecord; purged: number }> {
    return this.mutate(
      `${slideRoute(slideId)}/items/${encodeURIComponent(annotationId)}`
      + `/revisions/${encodeURIComponent(revisionId)}/restore`,
      'POST',
      request,
    )
  }
}
