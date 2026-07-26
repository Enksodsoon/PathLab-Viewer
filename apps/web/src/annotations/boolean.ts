import { executePolygonBoolean } from './booleanCore'
import type {
  BooleanWorkerRequest,
  BooleanWorkerResponse,
} from './boolean.worker'
import {
  BOOLEAN_TIMEOUT_MS,
  type PolygonBooleanOperation,
  type PolygonGeometry,
} from './types'

export { executePolygonBoolean }

export class BooleanOperationTimeoutError extends Error {
  constructor() {
    super('Annotation boolean operation exceeded the two second stability limit')
  }
}

export interface BooleanWorkerLike {
  postMessage(message: BooleanWorkerRequest): void
  terminate(): void
  onmessage: ((event: MessageEvent<BooleanWorkerResponse>) => void) | null
  onerror: ((event: ErrorEvent) => void) | null
}

export interface BooleanWorkerClient {
  run(
    operation: PolygonBooleanOperation,
    geometries: readonly PolygonGeometry[],
  ): Promise<PolygonGeometry[]>
}

function browserWorkerFactory(): BooleanWorkerLike {
  return new Worker(new URL('./boolean.worker.ts', import.meta.url), { type: 'module' })
}

export function createBooleanWorkerClient(
  workerFactory: () => BooleanWorkerLike = browserWorkerFactory,
  timeoutMs = BOOLEAN_TIMEOUT_MS,
): BooleanWorkerClient {
  return {
    run(operation, geometries) {
      const sourceCopy = structuredClone(geometries)
      return new Promise<PolygonGeometry[]>((resolve, reject) => {
        const worker = workerFactory()
        const requestId = crypto.randomUUID()
        let settled = false
        const finish = (callback: () => void) => {
          if (settled) return
          settled = true
          clearTimeout(timeout)
          worker.terminate()
          callback()
        }
        const timeout = setTimeout(() => {
          finish(() => reject(new BooleanOperationTimeoutError()))
        }, timeoutMs)
        worker.onmessage = (event) => {
          const response = event.data
          if (response.requestId !== requestId) return
          if ('error' in response) {
            const message = response.error
            finish(() => reject(new Error(message)))
          } else {
            const result = structuredClone(response.result)
            finish(() => resolve(result))
          }
        }
        worker.onerror = (event) => {
          finish(() => reject(new Error(event.message || 'Annotation boolean worker failed')))
        }
        worker.postMessage({
          requestId,
          operation,
          geometries: [...sourceCopy],
        })
      })
    },
  }
}
