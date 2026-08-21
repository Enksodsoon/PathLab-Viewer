/// <reference lib="webworker" />

import * as ort from 'onnxruntime-web/wasm'
import wasmModuleUrl from '../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs?url'
import wasmUrl from '../../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm?url'

import type { LocalStudyRecord, StudyAction, StudyModelManifest } from './types'

type PrepareMessage = { id: string; type: 'prepare'; manifest: StudyModelManifest }
type InferMessage = { id: string; type: 'infer'; records: LocalStudyRecord[] }
type WorkerMessage = PrepareMessage | InferMessage

const OUTPUTS = ['retention', 'effort', 'hint_need', 'calibration_risk', 'source_risk'] as const
const ALLOWED_ACTIONS = new Set<StudyAction>([
  'continue', 'offer_hint', 'ask_confidence', 'ask_source_check', 'retrieve', 'pause',
])
const CONTEXT = 32
const MAX_MEMORY_BYTES = 192 * 1024 * 1024

let session: ort.InferenceSession | null = null
let manifest: StudyModelManifest | null = null

ort.env.wasm.numThreads = 1
ort.env.wasm.proxy = false
ort.env.wasm.wasmPaths = { wasm: wasmUrl, mjs: wasmModuleUrl }

function heapBytes(): number | null {
  const memory = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory
  return typeof memory?.usedJSHeapSize === 'number' ? memory.usedJSHeapSize : null
}

async function sha256(value: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', value)
  return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('')
}

async function stableToken(taskId: string): Promise<bigint> {
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(taskId)))
  let value = 0n
  for (const byte of digest.slice(0, 8)) value = (value << 8n) | BigInt(byte)
  return BigInt.asIntN(64, value % 20000n)
}

async function feeds(records: LocalStudyRecord[]) {
  const recent = records.slice(-CONTEXT)
  const tokens = new BigInt64Array(CONTEXT)
  const features = new Float32Array(CONTEXT * 12)
  const offset = CONTEXT - recent.length
  for (let index = 0; index < recent.length; index += 1) {
    tokens[offset + index] = await stableToken(recent[index].taskId)
    features.set(recent[index].features, (offset + index) * 12)
  }
  return {
    tokens: new ort.Tensor('int64', tokens, [1, CONTEXT]),
    features: new ort.Tensor('float32', features, [1, CONTEXT, 12]),
  }
}

function values(outputs: ort.InferenceSession.OnnxValueMapType): Record<string, number> {
  const result: Record<string, number> = {}
  for (const name of OUTPUTS) {
    const value = Number(outputs[name]?.data[0])
    if (!Number.isFinite(value)) throw new Error('TRACE_SIM_NONFINITE_OUTPUT')
    result[name] = 1 / (1 + Math.exp(-value))
  }
  return result
}

function actionFor(result: Record<string, number>): StudyAction {
  let action: StudyAction = 'continue'
  if (result.source_risk >= 0.65) action = 'ask_source_check'
  else if (result.calibration_risk >= 0.65) action = 'ask_confidence'
  else if (result.hint_need >= 0.65) action = 'offer_hint'
  else if (result.retention < 0.45) action = 'retrieve'
  else if (result.effort >= 0.8) action = 'pause'
  return ALLOWED_ACTIONS.has(action) ? action : 'continue'
}

async function prepare(next: StudyModelManifest) {
  if (next.approvalStatus !== 'public_beta_bounded_safe_actions') {
    throw new Error('TRACE_SIM_NOT_APPROVED')
  }
  if (!next.knownVector.expectedOutputs) throw new Error('TRACE_SIM_SELF_TEST_VECTOR_MISSING')
  const before = heapBytes()
  const cache = await caches.open('pathlab-study-ai-v1')
  let artifact: ArrayBuffer | undefined
  try {
    const response = await fetch(next.assetUrl, { cache: 'no-store', credentials: 'same-origin' })
    if (response.ok) artifact = await response.arrayBuffer()
  } catch { /* offline preparation must use the previously verified cache */ }
  if (!artifact) artifact = await (await cache.match(next.assetUrl))?.arrayBuffer()
  if (!artifact) throw new Error('TRACE_SIM_DOWNLOAD_FAILED')
  if (artifact.byteLength !== next.artifactBytes || await sha256(artifact) !== next.artifactSha256) {
    throw new Error('TRACE_SIM_ARTIFACT_TAMPERED')
  }
  await cache.put(next.assetUrl, new Response(artifact.slice(0), {
    headers: { 'Content-Type': 'application/octet-stream', 'X-PathLab-SHA256': next.artifactSha256 },
  }))
  const cached = await (await cache.match(next.assetUrl))?.arrayBuffer()
  if (!cached || await sha256(cached) !== next.artifactSha256) {
    throw new Error('TRACE_SIM_CACHE_VERIFY_FAILED')
  }
  session = await ort.InferenceSession.create(artifact, { executionProviders: ['wasm'] })
  manifest = next
  const outputs = values(await session.run(await feeds([])))
  for (const [name, expected] of Object.entries(next.knownVector.expectedOutputs)) {
    if (!Number.isFinite(outputs[name]) || Math.abs(outputs[name] - expected) > next.knownVector.expectedOutputTolerance) {
      session = null
      manifest = null
      throw new Error('TRACE_SIM_SELF_TEST_MISMATCH')
    }
  }
  const after = heapBytes()
  const memoryBytes = before !== null && after !== null ? Math.max(0, after - before) : null
  if (memoryBytes !== null && memoryBytes > MAX_MEMORY_BYTES) {
    session = null
    manifest = null
    throw new Error('TRACE_SIM_MEMORY_LIMIT')
  }
  return {
    ready: true,
    runtime: 'wasm-single-thread',
    artifactSha256: next.artifactSha256,
    cacheVerified: true,
    memoryBytes,
    memoryMeasured: memoryBytes !== null,
    requiresPhysicalMemoryCertification: memoryBytes === null,
  }
}

async function infer(records: LocalStudyRecord[]) {
  if (!session || !manifest) throw new Error('TRACE_SIM_NOT_READY')
  const completed = new Set(records.filter((item) => item.completed).map((item) => item.taskId))
  if (completed.size < 5) throw new Error('TRACE_SIM_COLD_START')
  const output = values(await session.run(await feeds(records.slice(-256))))
  return { action: actionFor(output), modelManifestId: manifest.id }
}

self.onmessage = (event: MessageEvent<WorkerMessage>) => {
  const message = event.data
  const operation = message.type === 'prepare' ? prepare(message.manifest) : infer(message.records)
  void operation.then(
    (result) => self.postMessage({ id: message.id, ok: true, result }),
    (error: unknown) => self.postMessage({
      id: message.id, ok: false,
      error: error instanceof Error ? error.message : 'TRACE_SIM_FAILED',
    }),
  )
}
