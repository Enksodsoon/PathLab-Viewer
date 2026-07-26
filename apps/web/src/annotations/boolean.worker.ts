/// <reference lib="webworker" />

import { executePolygonBoolean } from './booleanCore'
import type { PolygonBooleanOperation, PolygonGeometry } from './types'

export interface BooleanWorkerRequest {
  requestId: string
  operation: PolygonBooleanOperation
  geometries: PolygonGeometry[]
}

export type BooleanWorkerResponse =
  | { requestId: string; result: PolygonGeometry[] }
  | { requestId: string; error: string }

const workerScope = self as DedicatedWorkerGlobalScope

workerScope.onmessage = (event: MessageEvent<BooleanWorkerRequest>) => {
  const { requestId, operation, geometries } = event.data
  try {
    workerScope.postMessage({
      requestId,
      result: executePolygonBoolean(operation, geometries),
    } satisfies BooleanWorkerResponse)
  } catch (caught) {
    workerScope.postMessage({
      requestId,
      error: caught instanceof Error ? caught.message : 'Boolean operation failed',
    } satisfies BooleanWorkerResponse)
  }
}
