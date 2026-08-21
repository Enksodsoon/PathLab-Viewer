import type { LocalStudyRecord, StudyAction, StudyModelManifest, StudyReason } from './types'

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: number }
const pending = new Map<string, Pending>()
let worker: Worker | null = null

function runtime(): Worker {
  if (worker) return worker
  worker = new Worker(new URL('./traceSim.worker.ts', import.meta.url), { type: 'module' })
  worker.onmessage = (event: MessageEvent<{ id: string; ok: boolean; result?: unknown; error?: string }>) => {
    const operation = pending.get(event.data.id)
    if (!operation) return
    pending.delete(event.data.id)
    window.clearTimeout(operation.timer)
    if (event.data.ok) operation.resolve(event.data.result)
    else operation.reject(new Error(event.data.error ?? 'TRACE_SIM_FAILED'))
  }
  worker.onerror = () => resetTraceSim()
  return worker
}

function request<T>(message: Record<string, unknown>, timeoutMs = 15_000): Promise<T> {
  const id = crypto.randomUUID()
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pending.delete(id)
      resetTraceSim()
      reject(new Error('TRACE_SIM_TIMEOUT'))
    }, timeoutMs)
    pending.set(id, { resolve: resolve as (value: unknown) => void, reject, timer })
    runtime().postMessage({ ...message, id })
  })
}

export function prepareTraceSim(manifest: StudyModelManifest) {
  return request<{ ready: true; memoryBytes: number | null; memoryMeasured: boolean }>(
    { type: 'prepare', manifest }, 60_000,
  )
}

export function inferTraceSim(records: LocalStudyRecord[]) {
  return request<{ action: StudyAction; modelManifestId: string }>({ type: 'infer', records })
}

export function resetTraceSim(): void {
  worker?.terminate()
  worker = null
  for (const operation of pending.values()) {
    window.clearTimeout(operation.timer)
    operation.reject(new Error('TRACE_SIM_RESET'))
  }
  pending.clear()
}

const actionReasons: Record<StudyAction, StudyReason> = {
  continue: 'CONTINUE_PRACTICE',
  offer_hint: 'HINT_SUPPORT',
  ask_confidence: 'CHECK_CONFIDENCE',
  ask_source_check: 'VERIFY_SOURCE',
  retrieve: 'REVIEW_PREVIOUS',
  pause: 'TAKE_BREAK',
}

export function reasonForAction(action: StudyAction, records: LocalStudyRecord[]): StudyReason {
  const latest = records.at(-1)
  if (!latest) return 'MODEL_SUGGESTION'
  const candidate = actionReasons[action]
  const factual = (
    candidate === 'HINT_SUPPORT' ? latest.features[2] > 0
      : candidate === 'CHECK_CONFIDENCE' ? latest.features[3] > 0
        : candidate === 'VERIFY_SOURCE' ? latest.features[4] === 0
          : candidate === 'TAKE_BREAK' ? latest.features[1] >= 0.8
            : candidate === 'REVIEW_PREVIOUS' ? latest.features[0] === 0
              : candidate === 'CONTINUE_PRACTICE'
  )
  return factual ? candidate : 'MODEL_SUGGESTION'
}
