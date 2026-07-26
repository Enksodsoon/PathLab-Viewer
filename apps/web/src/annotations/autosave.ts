import { AnnotationApiError } from './api'
import {
  coalesceMutationSequence,
  mutationTargetId,
  rebaseForResults,
} from './mutationQueue'
import {
  AUTOSAVE_DELAY_MS,
  MAX_BATCH_OPERATIONS,
  type AnnotationBatchResult,
  type AnnotationMutation,
} from './types'

const DEFAULT_RETRY_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000] as const
export const MAX_ANNOTATION_BATCH_BYTES = 256 * 1024

export interface AnnotationAutosaveTransport {
  save(
    mutationId: string,
    baseVersion: number,
    operations: AnnotationMutation[],
  ): Promise<AnnotationBatchResult>
}

export interface AnnotationAutosaveBatch {
  mutationId: string
  operations: AnnotationMutation[]
}

export interface AnnotationAutosaveAcknowledgement extends AnnotationAutosaveBatch {
  result: AnnotationBatchResult
}

export type ConflictChoice = 'reload' | 'save-as-duplicate'
export type AutosaveStatus =
  | 'idle'
  | 'dirty'
  | 'saving'
  | 'retrying'
  | 'conflict'
  | 'error'
  | 'saved'

export interface AutosaveSnapshot {
  status: AutosaveStatus
  dirtyCount: number
  version: number
  retryAt: number | null
  error: string | null
  conflict: {
    currentVersion: number | null
    choices: readonly ConflictChoice[]
  } | null
}

export interface AnnotationAutosaveOptions {
  transport: AnnotationAutosaveTransport
  baseVersion: number
  debounceMs?: number
  retryDelaysMs?: readonly number[]
  idFactory?: () => string
  now?: () => number
  onReload?: () => Promise<number>
  onSaveAsDuplicate?: (
    operations: readonly AnnotationMutation[],
    currentVersion: number,
  ) => Promise<number>
  onBatchStart?: (batch: AnnotationAutosaveBatch) => void
  onAcknowledged?: (
    acknowledgement: AnnotationAutosaveAcknowledgement,
  ) => void | Promise<void>
  onBatchFailed?: (batch: AnnotationAutosaveBatch, error: unknown) => void
  onChange?: (snapshot: AutosaveSnapshot) => void
}

interface QueueEntry {
  token: number
  mutation: AnnotationMutation
}

interface InFlightBatch {
  mutationId: string
  entries: QueueEntry[]
}

export function annotationBatchRequestBytes(
  mutationId: string,
  baseVersion: number,
  operations: readonly AnnotationMutation[],
): number {
  return new TextEncoder().encode(JSON.stringify({
    mutationId,
    baseVersion,
    operations,
  })).byteLength
}

function cloneOperations(entries: readonly QueueEntry[]): AnnotationMutation[] {
  return entries.map((entry) => structuredClone(entry.mutation))
}

export class AnnotationAutosave {
  private readonly transport: AnnotationAutosaveTransport
  private readonly debounceMs: number
  private readonly retryDelays: readonly number[]
  private readonly idFactory: () => string
  private readonly now: () => number
  private readonly onReload?: () => Promise<number>
  private readonly onSaveAsDuplicate?: (
    operations: readonly AnnotationMutation[],
    currentVersion: number,
  ) => Promise<number>
  private readonly onBatchStart?: (batch: AnnotationAutosaveBatch) => void
  private readonly onAcknowledged?: (
    acknowledgement: AnnotationAutosaveAcknowledgement,
  ) => void | Promise<void>
  private readonly onBatchFailed?: (batch: AnnotationAutosaveBatch, error: unknown) => void
  private readonly onChange?: (snapshot: AutosaveSnapshot) => void

  private queue: QueueEntry[] = []
  private inFlight: InFlightBatch | null = null
  private nextToken = 1
  private version: number
  private status: AutosaveStatus = 'idle'
  private retryAt: number | null = null
  private error: string | null = null
  private conflict: AutosaveSnapshot['conflict'] = null
  private retryIndex = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private active: Promise<void> | null = null
  private disposed = false
  private generation = 0

  constructor(options: AnnotationAutosaveOptions) {
    this.transport = options.transport
    this.version = options.baseVersion
    this.debounceMs = options.debounceMs ?? AUTOSAVE_DELAY_MS
    this.retryDelays = options.retryDelaysMs ?? DEFAULT_RETRY_DELAYS
    this.idFactory = options.idFactory ?? (() => crypto.randomUUID())
    this.now = options.now ?? Date.now
    this.onReload = options.onReload
    this.onSaveAsDuplicate = options.onSaveAsDuplicate
    this.onBatchStart = options.onBatchStart
    this.onAcknowledged = options.onAcknowledged
    this.onBatchFailed = options.onBatchFailed
    this.onChange = options.onChange
  }

  snapshot(): AutosaveSnapshot {
    return {
      status: this.status,
      dirtyCount: this.queue.length + (this.inFlight?.entries.length ?? 0),
      version: this.version,
      retryAt: this.retryAt,
      error: this.error,
      conflict: this.conflict ? { ...this.conflict } : null,
    }
  }

  enqueue(operation: AnnotationMutation): void {
    if (this.disposed) throw new Error('Annotation autosave has been disposed')
    this.enqueueInternal(operation)
    if (
      !this.inFlight
      && this.status !== 'conflict'
      && this.status !== 'retrying'
      && this.status !== 'error'
    ) {
      this.status = this.queue.length > 0 ? 'dirty' : 'idle'
    }
    this.error = null
    this.notify()
    if (!this.inFlight && this.queue.length > 0 && this.status === 'dirty') {
      this.schedule(this.debounceMs)
    } else if (!this.inFlight && this.queue.length === 0) {
      this.clearTimer()
      this.retryAt = null
    }
  }

  replacePending(operations: readonly AnnotationMutation[]): void {
    this.queue = []
    for (const operation of operations) this.enqueueInternal(operation)
    if (!this.inFlight && this.status !== 'conflict') {
      this.status = this.snapshot().dirtyCount > 0 ? 'dirty' : 'idle'
    }
    this.error = null
    this.notify()
    if (!this.inFlight && this.queue.length > 0 && this.status === 'dirty') {
      this.schedule(this.debounceMs)
    }
  }

  async flush(): Promise<void> {
    this.clearTimer()
    if (this.active) await this.active
    this.clearTimer()
    if (
      (this.queue.length > 0 || this.inFlight)
      && this.status !== 'conflict'
      && this.status !== 'error'
    ) {
      await this.run()
    }
  }

  async resolveConflict(choice: ConflictChoice): Promise<void> {
    if (this.status !== 'conflict') return
    const dirty = this.allDirtyOperations()
    if (this.inFlight) {
      this.onBatchFailed?.(this.batchContext(this.inFlight), new Error('Conflict resolved'))
    }
    if (choice === 'reload') {
      if (!this.onReload) throw new Error('Conflict reload is not configured')
      this.version = await this.onReload()
    } else {
      if (!this.onSaveAsDuplicate) throw new Error('Save-as-duplicate is not configured')
      const currentVersion = this.conflict?.currentVersion
      if (currentVersion === null || currentVersion === undefined) {
        throw new Error('Conflict response did not include the current annotation version')
      }
      this.version = await this.onSaveAsDuplicate(dirty, currentVersion)
    }
    this.queue = []
    this.inFlight = null
    this.conflict = null
    this.error = null
    this.retryAt = null
    this.status = 'saved'
    this.notify()
  }

  reset(baseVersion: number): void {
    if (this.disposed) throw new Error('Annotation autosave has been disposed')
    if (!Number.isSafeInteger(baseVersion) || baseVersion < 0) {
      throw new RangeError('Annotation version must be a non-negative safe integer')
    }
    this.generation += 1
    this.clearTimer()
    if (this.inFlight) {
      this.onBatchFailed?.(this.batchContext(this.inFlight), new Error('Annotation autosave reset'))
    }
    this.queue = []
    this.inFlight = null
    this.version = baseVersion
    this.status = 'idle'
    this.retryAt = null
    this.error = null
    this.conflict = null
    this.retryIndex = 0
    this.notify()
  }

  dispose(): void {
    this.disposed = true
    this.generation += 1
    this.clearTimer()
  }

  private enqueueInternal(operation: AnnotationMutation): void {
    const target = mutationTargetId(operation)
    const targetEntries = this.queue.filter(
      (entry) => mutationTargetId(entry.mutation) === target,
    )
    if (targetEntries.length === 0) {
      this.queue.push({ token: this.nextToken++, mutation: structuredClone(operation) })
      return
    }
    const firstIndex = this.queue.findIndex(
      (entry) => mutationTargetId(entry.mutation) === target,
    )
    const insertionIndex = this.queue
      .slice(0, firstIndex)
      .filter((entry) => mutationTargetId(entry.mutation) !== target)
      .length
    const normalized = coalesceMutationSequence([
      ...targetEntries.map((entry) => entry.mutation),
      operation,
    ])
    const replacement = normalized.map((mutation, index): QueueEntry => ({
      token: targetEntries[index]?.token ?? this.nextToken++,
      mutation: structuredClone(mutation),
    }))
    const withoutTarget = this.queue.filter(
      (entry) => mutationTargetId(entry.mutation) !== target,
    )
    withoutTarget.splice(insertionIndex, 0, ...replacement)
    this.queue = withoutTarget
  }

  private allDirtyOperations(): AnnotationMutation[] {
    return [
      ...(this.inFlight ? cloneOperations(this.inFlight.entries) : []),
      ...cloneOperations(this.queue),
    ]
  }

  private notify(): void {
    this.onChange?.(this.snapshot())
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
  }

  private schedule(delayMs: number): void {
    if (this.status === 'conflict' || this.disposed) return
    this.clearTimer()
    this.retryAt = this.now() + delayMs
    this.timer = setTimeout(() => {
      this.timer = null
      this.retryAt = null
      void this.run()
    }, delayMs)
  }

  private createInFlight(): boolean {
    if (this.inFlight) return true
    if (this.queue.length === 0) return false
    const mutationId = this.idFactory()
    const entries: QueueEntry[] = []
    const targets = new Set<string>()
    for (const entry of this.queue) {
      const target = mutationTargetId(entry.mutation)
      if (targets.has(target)) continue
      const candidate = [...entries, entry]
      const candidateOperations = cloneOperations(candidate)
      const bytes = annotationBatchRequestBytes(
        mutationId,
        this.version,
        candidateOperations,
      )
      if (entries.length === 0 && bytes > MAX_ANNOTATION_BATCH_BYTES) {
        this.status = 'error'
        this.error = 'ANNOTATION_REQUEST_TOO_LARGE'
        this.retryAt = null
        this.notify()
        return false
      }
      if (
        bytes > MAX_ANNOTATION_BATCH_BYTES
        || entries.length >= MAX_BATCH_OPERATIONS
      ) break
      entries.push(entry)
      targets.add(target)
    }
    const selected = new Set(entries.map((entry) => entry.token))
    this.queue = this.queue.filter((entry) => !selected.has(entry.token))
    this.inFlight = { mutationId, entries }
    this.onBatchStart?.(this.batchContext(this.inFlight))
    return true
  }

  private batchContext(batch: InFlightBatch): AnnotationAutosaveBatch {
    return {
      mutationId: batch.mutationId,
      operations: cloneOperations(batch.entries),
    }
  }

  private async run(): Promise<void> {
    if (this.active) return this.active
    const generation = this.generation
    this.active = this.drain(generation).finally(() => {
      this.active = null
      if (
        !this.disposed
        && this.queue.length > 0
        && this.status === 'dirty'
        && this.timer === null
      ) {
        this.schedule(0)
      }
    })
    return this.active
  }

  private async drain(generation: number): Promise<void> {
    while (
      !this.disposed
      && generation === this.generation
      && (this.inFlight || this.queue.length > 0)
    ) {
      if (!this.createInFlight()) return
      const batch = this.inFlight
      if (!batch) return
      const context = this.batchContext(batch)
      this.status = 'saving'
      this.error = null
      this.retryAt = null
      this.notify()
      let result: AnnotationBatchResult
      try {
        result = await this.transport.save(
          batch.mutationId,
          this.version,
          structuredClone(context.operations),
        )
      } catch (caught) {
        if (this.disposed || generation !== this.generation) return
        if (
          caught instanceof AnnotationApiError
          && caught.status === 409
          && caught.code === 'ANNOTATION_CONFLICT'
        ) {
          this.status = 'conflict'
          this.conflict = {
            currentVersion: typeof caught.detail.currentVersion === 'number'
              ? caught.detail.currentVersion
              : null,
            choices: ['reload', 'save-as-duplicate'],
          }
          this.notify()
          return
        }
        if (caught instanceof AnnotationApiError && caught.status < 500) {
          this.status = 'error'
          this.error = caught.code
          this.onBatchFailed?.(context, caught)
          this.notify()
          return
        }
        this.status = 'retrying'
        this.error = caught instanceof Error ? caught.message : 'Annotation save failed'
        const delay = this.retryDelays[
          Math.min(this.retryIndex, Math.max(0, this.retryDelays.length - 1))
        ] ?? 30_000
        this.retryIndex += 1
        this.schedule(delay)
        this.notify()
        return
      }
      if (this.disposed || generation !== this.generation) return

      try {
        await this.onAcknowledged?.({ ...context, result: structuredClone(result) })
      } catch (caught) {
        if (this.disposed || generation !== this.generation) return
        this.status = 'error'
        this.error = 'ANNOTATION_ACKNOWLEDGEMENT_FAILED'
        this.onBatchFailed?.(context, caught)
        this.notify()
        return
      }
      if (this.disposed || generation !== this.generation) return
      this.version = result.version
      this.inFlight = null
      this.queue = this.queue.map((entry) => ({
        ...entry,
        mutation: rebaseForResults([entry.mutation], result.results)[0],
      }))
      this.retryIndex = 0
      this.status = this.queue.length > 0 ? 'dirty' : 'saved'
      this.notify()
    }
  }
}
