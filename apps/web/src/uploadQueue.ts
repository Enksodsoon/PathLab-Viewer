import { useSyncExternalStore } from 'react'
import { ApiError, getPrivateSlide, renewUploadReservation, reserveUpload, type UploadReservation } from './api'
import { startTusUpload } from './upload'
import type { UploadQueueItemView } from './components/library/UploadWorkspace'

export interface UploadQueueItem extends UploadQueueItemView {
  folderId: string | null
  reservation?: UploadReservation
  uploadedBytes: number
  bytesPerSecond: number | null
  etaSeconds: number | null
  lastSampleAt?: number
  lastSampleBytes?: number
}
interface QueueState { items: UploadQueueItem[]; running: boolean; authorized: boolean; notice: string }
let state: QueueState = { items: [], running: false, authorized: false, notice: '' }
let epoch = 0
let active: AbortController | null = null
const listeners = new Set<() => void>()
const polls = new Map<string, ReturnType<typeof setTimeout>>()
function boundedQueueName(name: string) { return name.slice(0, 200) }
function defaultQueueName(file: File) { return boundedQueueName(file.name.replace(/\.ome\.tiff?$/i, '')) }
function publish(changes: Partial<QueueState>) {
  state = { ...state, ...changes }
  listeners.forEach((listener) => listener())
}
function update(id: string, changes: Partial<UploadQueueItem>) {
  publish({ items: state.items.map((item) => item.id === id ? { ...item, ...changes } : item) })
}
export function getUploadQueueSnapshot() { return state }
export function subscribeUploadQueue(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
export function useUploadQueue() { return useSyncExternalStore(subscribeUploadQueue, getUploadQueueSnapshot, getUploadQueueSnapshot) }
export function authorizeUploadQueue() { if (!state.authorized) publish({ authorized: true }) }
export function resetUploadQueue() {
  epoch += 1
  active?.abort(); active = null
  polls.forEach(clearTimeout); polls.clear()
  publish({ items: [], running: false, authorized: false, notice: '' })
}
if (typeof window !== 'undefined') window.addEventListener('pathlab-session-ended', resetUploadQueue)

export function addUploadFiles(files: File[], folderId: string | null = null) {
  if (!state.authorized) return
  const existing = new Set(state.items.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`))
  const accepted: UploadQueueItem[] = []
  let skipped = 0
  for (const file of files) {
    const identity = `${file.name}:${file.size}:${file.lastModified}`
    if (!/\.ome\.tiff?$/i.test(file.name) || !file.size || file.size > 5 * 1024 ** 3 || existing.has(identity)) { skipped += 1; continue }
    existing.add(identity)
    accepted.push({ id: crypto.randomUUID(), file, folderId, displayName: defaultQueueName(file), phase: 'queued', progress: 0, error: '', uploadedBytes: 0, bytesPerSecond: null, etaSeconds: null })
  }
  publish({ items: [...state.items, ...accepted], notice: skipped ? `${skipped} duplicate, unsupported, empty, or oversized files skipped.` : '' })
}
export function renameUploadItem(id: string, displayName: string) {
  if (state.items.find((item) => item.id === id)?.phase === 'queued') update(id, { displayName: boundedQueueName(displayName) })
}
export function removeUploadItem(id: string) {
  const item = state.items.find((entry) => entry.id === id)
  if (!item || item.phase === 'preparing' || item.phase === 'uploading') return
  const poll = polls.get(id); if (poll) clearTimeout(poll); polls.delete(id)
  publish({ items: state.items.filter((entry) => entry.id !== id) })
}
export function cancelUploadItem(id: string) {
  const item = state.items.find((entry) => entry.id === id)
  if (!item || !['queued', 'preparing', 'uploading'].includes(item.phase)) return
  update(id, { phase: 'cancelled', etaSeconds: null, bytesPerSecond: null, error: 'Transfer paused. The source is retained. Any upload reservation remains allocated; storage has not been released.' })
  if (item.phase === 'preparing' || item.phase === 'uploading') active?.abort()
}
function failureMessage(error: unknown) {
  if (error instanceof ApiError && (error.code === 'STORAGE_CAPACITY_EXCEEDED' || error.status === 507)) return 'Not enough usable storage remains for this file.'
  return 'Upload paused. Check the connection and retry; the source and reservation are retained.'
}
async function checkProcessing(id: string, generation: number) {
  const item = state.items.find((entry) => entry.id === id)
  if (!item?.reservation || generation !== epoch || item.phase !== 'processing') return
  try {
    const slide = await getPrivateSlide(item.reservation.slide.id)
    if (generation !== epoch || !state.items.some((entry) => entry.id === id)) return
    if (slide.state === 'ready_private' || slide.state === 'published') { update(id, { phase: 'ready', error: '' }); return }
    if (slide.state === 'failed' || slide.state === 'deleting') { update(id, { phase: 'processing_failed', error: slide.state === 'failed' ? 'Processing failed. Review the source or retry conversion from the library.' : 'This slide is being deleted.' }); return }
    update(id, { processingState: slide.state, error: '' })
  } catch (error) {
    if (generation !== epoch) return
    if (error instanceof ApiError && error.status === 401) { resetUploadQueue(); return }
    if (error instanceof ApiError && (error.status === 404 || error.status === 410)) { update(id, { phase: 'processing_failed', error: 'The uploaded slide is no longer available.' }); return }
    update(id, { error: 'Processing status is unavailable. Checking again shortly.' })
  }
  if (generation === epoch && state.items.some((entry) => entry.id === id && entry.phase === 'processing')) polls.set(id, setTimeout(() => { polls.delete(id); void checkProcessing(id, generation) }, 5000))
}
export async function startUploadQueue() {
  if (!state.authorized || state.running) return
  const generation = epoch
  publish({ running: true, notice: '' })
  try {
    while (generation === epoch && state.authorized) {
      const item = state.items.find((entry) => entry.phase === 'queued')
      if (!item) break
      const controller = new AbortController(); active = controller
      update(item.id, { phase: 'preparing', error: '', bytesPerSecond: null, etaSeconds: null })
      try {
        const reservation = item.reservation ? await renewUploadReservation(item.reservation.slide.id) : await reserveUpload(item.file, item.displayName.trim() || defaultQueueName(item.file), item.folderId)
        if (generation !== epoch) return
        update(item.id, { reservation })
        // A cancelled reservation request may still have reached the server. Retain it, never start transfer.
        if (controller.signal.aborted) continue
        update(item.id, { phase: 'uploading', lastSampleAt: undefined, lastSampleBytes: undefined })
        await startTusUpload(item.file, reservation.uploadUrl, reservation.uploadToken, {
          progress: (progress) => { if (generation === epoch && !controller.signal.aborted) update(item.id, { progress }) },
          bytes: (uploadedBytes, total) => {
            if (generation !== epoch || controller.signal.aborted) return
            const now = performance.now()
            const current = state.items.find((entry) => entry.id === item.id)
            if (!current || current.lastSampleBytes === uploadedBytes) return
            const elapsed = current.lastSampleAt === undefined ? 0 : (now - current.lastSampleAt) / 1000
            const delta = uploadedBytes - (current.lastSampleBytes ?? uploadedBytes)
            const bytesPerSecond = elapsed > 0 && delta > 0 ? delta / elapsed : null
            update(item.id, { uploadedBytes, bytesPerSecond, etaSeconds: bytesPerSecond ? Math.max(0, total - uploadedBytes) / bytesPerSecond : null, lastSampleAt: now, lastSampleBytes: uploadedBytes })
          },
          success: () => undefined,
          error: () => undefined,
        }, reservation.slide.id, controller.signal)
        if (generation !== epoch || controller.signal.aborted) continue
        update(item.id, { phase: 'processing', progress: 100, uploadedBytes: item.file.size, bytesPerSecond: null, etaSeconds: null, processingState: 'queued', error: '' })
        void checkProcessing(item.id, generation)
      } catch (error) {
        if (generation !== epoch) return
        if (error instanceof ApiError && error.status === 401) { resetUploadQueue(); return }
        if (controller.signal.aborted) continue
        update(item.id, { phase: 'error', bytesPerSecond: null, etaSeconds: null, error: failureMessage(error) })
        publish({ notice: 'Queue paused. Retry the failed transfer when the service is available.' })
        break
      } finally { if (active === controller) active = null }
    }
  } finally { if (generation === epoch) publish({ running: false }) }
}
export function retryUploadItem(id: string) {
  const item = state.items.find((entry) => entry.id === id)
  if (!item || !['cancelled', 'error'].includes(item.phase)) return
  update(id, { phase: 'queued', error: '', progress: 0 })
  void startUploadQueue()
}
