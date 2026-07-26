import { AnnotationApiError } from './api'
import {
  AUTOSAVE_DELAY_MS,
  MAX_BATCH_OPERATIONS,
  type AnnotationBatchResult,
  type AnnotationMutation,
} from './types'

const DEFAULT_RETRY_DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000] as const
const MAX_BATCH_BYTES = 250 * 1024

export interface AnnotationAutosaveTransport {
  save(
    mutationId: string,
    baseVersion: number,
    operations: AnnotationMutation[],
  ): Promise<AnnotationBatchResult>
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
  onSaveAsDuplicate?: (operations: readonly AnnotationMutation[]) => Promise<number>
  onChange?: (snapshot: AutosaveSnapshot) => void
}

function requestBytes(operations: readonly AnnotationMutation[]): number {
  return new TextEncoder().encode(JSON.stringify({ operations })).byteLength
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
  ) => Promise<number>
  private readonly onChange?: (snapshot: AutosaveSnapshot) => void

  private queue: AnnotationMutation[] = []
  private version: number
  private status: AutosaveStatus = 'idle'
  private retryAt: number | null = null
  private error: string | null = null
  private conflict: AutosaveSnapshot['conflict'] = null
  private retryIndex = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private active: Promise<void> | null = null
  private currentMutationId: string | null = null
  private disposed = false

  constructor(options: AnnotationAutosaveOptions) {
    this.transport = options.transport
    this.version = options.baseVersion
    this.debounceMs = options.debounceMs ?? AUTOSAVE_DELAY_MS
    this.retryDelays = options.retryDelaysMs ?? DEFAULT_RETRY_DELAYS
    this.idFactory = options.idFactory ?? (() => crypto.randomUUID())
    this.now = options.now ?? Date.now
    this.onReload = options.onReload
    this.onSaveAsDuplicate = options.onSaveAsDuplicate
    this.onChange = options.onChange
  }

  snapshot(): AutosaveSnapshot {
    return {
      status: this.status,
      dirtyCount: this.queue.length,
      version: this.version,
      retryAt: this.retryAt,
      error: this.error,
      conflict: this.conflict ? { ...this.conflict } : null,
    }
  }

  enqueue(operation: AnnotationMutation): void {
    if (this.disposed) throw new Error('Annotation autosave has been disposed')
    this.queue.push(structuredClone(operation))
    this.status = 'dirty'
    this.error = null
    this.notify()
    this.schedule(this.debounceMs)
  }

  replacePending(operations: readonly AnnotationMutation[]): void {
    this.queue = structuredClone([...operations])
    this.currentMutationId = null
    this.status = this.queue.length > 0 ? 'dirty' : 'idle'
    this.notify()
    if (this.queue.length > 0) this.schedule(this.debounceMs)
  }

  async flush(): Promise<void> {
    this.clearTimer()
    if (this.active) await this.active
    if (this.queue.length > 0 && this.status !== 'conflict') {
      await this.run()
    }
  }

  async resolveConflict(choice: ConflictChoice): Promise<void> {
    if (this.status !== 'conflict') return
    if (choice === 'reload') {
      if (!this.onReload) throw new Error('Conflict reload is not configured')
      this.version = await this.onReload()
    } else {
      if (!this.onSaveAsDuplicate) throw new Error('Save-as-duplicate is not configured')
      this.version = await this.onSaveAsDuplicate(structuredClone(this.queue))
    }
    this.queue = []
    this.currentMutationId = null
    this.conflict = null
    this.error = null
    this.retryAt = null
    this.status = 'saved'
    this.notify()
  }

  dispose(): void {
    this.disposed = true
    this.clearTimer()
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

  private nextBatch(): AnnotationMutation[] {
    const batch: AnnotationMutation[] = []
    for (const operation of this.queue.slice(0, MAX_BATCH_OPERATIONS)) {
      const candidate = [...batch, operation]
      if (batch.length > 0 && requestBytes(candidate) > MAX_BATCH_BYTES) break
      batch.push(operation)
    }
    return batch
  }

  private async run(): Promise<void> {
    if (this.active) return this.active
    this.active = this.drain().finally(() => {
      this.active = null
    })
    return this.active
  }

  private async drain(): Promise<void> {
    while (this.queue.length > 0 && !this.disposed) {
      const batch = this.nextBatch()
      this.currentMutationId ??= this.idFactory()
      this.status = 'saving'
      this.error = null
      this.retryAt = null
      this.notify()
      try {
        const result = await this.transport.save(
          this.currentMutationId,
          this.version,
          structuredClone(batch),
        )
        this.version = result.version
        this.queue.splice(0, batch.length)
        this.currentMutationId = null
        this.retryIndex = 0
        this.status = this.queue.length > 0 ? 'dirty' : 'saved'
        this.notify()
      } catch (caught) {
        if (
          caught instanceof AnnotationApiError
          && caught.status === 409
          && caught.code === 'ANNOTATION_CONFLICT'
        ) {
          const currentVersion = typeof caught.detail.currentVersion === 'number'
            ? caught.detail.currentVersion
            : null
          this.status = 'conflict'
          this.conflict = {
            currentVersion,
            choices: ['reload', 'save-as-duplicate'],
          }
          this.notify()
          return
        }
        if (caught instanceof AnnotationApiError && caught.status < 500) {
          this.status = 'error'
          this.error = caught.code
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
    }
  }
}
