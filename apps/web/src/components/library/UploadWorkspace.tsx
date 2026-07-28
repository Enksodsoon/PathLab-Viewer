import {
  ArrowClockwise,
  CheckCircle,
  FileArrowUp,
  UploadSimple,
  WarningCircle,
  X,
} from '@phosphor-icons/react'
import { useRef, useState, type DragEvent } from 'react'

import { StatusMessage } from '../StatusMessage'
import { formatBytes } from './format'

export type UploadQueuePhase = 'queued' | 'preparing' | 'uploading' | 'complete' | 'error'

export interface UploadQueueItemView {
  id: string
  file: File
  displayName: string
  phase: UploadQueuePhase
  progress: number
  error: string
}

interface UploadWorkspaceProps {
  items: UploadQueueItemView[]
  running: boolean
  onFilesAdded: (files: File[]) => void
  onDisplayNameChange: (id: string, name: string) => void
  onRemove: (id: string) => void
  onRetry: (id: string) => void
  onStart: () => void
}

function itemStatus(item: UploadQueueItemView) {
  if (item.phase === 'error') return 'Upload paused'
  if (item.phase === 'complete') return 'Upload complete'
  if (item.phase === 'preparing') return 'Preparing resumable upload'
  if (item.phase === 'uploading') return `Uploading ${item.progress}%`
  return 'Queued'
}

export function UploadWorkspace({
  items,
  running,
  onFilesAdded,
  onDisplayNameChange,
  onRemove,
  onRetry,
  onStart,
}: UploadWorkspaceProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const queuedCount = items.filter((item) => item.phase === 'queued').length
  const errorCount = items.filter((item) => item.phase === 'error').length
  const activeIndex = items.findIndex(
    (item) => item.phase === 'preparing' || item.phase === 'uploading',
  )

  function addFiles(next: File[]) {
    if (next.length) onFilesAdded(next)
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  return (
    <section className="upload-workspace" aria-label="Upload slides">
      <div
        className={`upload-workspace-drop${dragging ? ' is-dragging' : ''}${items.length ? ' is-compact' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
        }}
        onDrop={handleDrop}
      >
        <span className="upload-workspace-icon" aria-hidden="true"><UploadSimple /></span>
        <div>
          <strong>Drop OME-TIFF files here</strong>
          <p>Files upload one at a time to protect server capacity.</p>
        </div>
        <button type="button" className="upload-workspace-choose" onClick={() => inputRef.current?.click()}>
          {items.length ? 'Add files' : 'Choose files'}
        </button>
        <small>OME-TIFF only · up to 5 GiB each · resumable</small>
      </div>

      <input
        ref={inputRef}
        className="upload-file-input"
        type="file"
        multiple
        accept=".ome.tif,.ome.tiff,image/tiff"
        aria-label="Choose OME-TIFF files"
        onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
      />

      {items.length ? (
        <div className="upload-workspace-queue" aria-label="Upload queue">
          {items.map((item, index) => {
            const active = item.phase === 'preparing' || item.phase === 'uploading'
            const percent = Math.min(100, Math.max(0, Math.round(item.progress)))
            return (
              <article
                key={item.id}
                className={[
                  'upload-workspace-file',
                  item.phase === 'error' ? 'has-error' : '',
                  item.phase === 'complete' ? 'is-complete' : '',
                ].filter(Boolean).join(' ')}
              >
                <span className="upload-workspace-file-icon" aria-hidden="true">
                  {item.phase === 'error'
                    ? <WarningCircle />
                    : item.phase === 'complete'
                      ? <CheckCircle />
                      : <FileArrowUp />}
                </span>
                <div className="upload-workspace-file-copy">
                  <strong title={item.file.name}>{item.file.name}</strong>
                  <span>
                    {formatBytes(item.file.size)} · {itemStatus(item)}
                    {activeIndex >= 0 && index > activeIndex && item.phase === 'queued'
                      ? ` · ${index - activeIndex} ahead`
                      : ''}
                  </span>
                </div>
                <div className="upload-workspace-file-actions">
                  {item.phase === 'error' ? (
                    <button
                      type="button"
                      aria-label={`Retry ${item.file.name}`}
                      onClick={() => onRetry(item.id)}
                    >
                      <ArrowClockwise />
                    </button>
                  ) : null}
                  {!active ? (
                    <button
                      type="button"
                      aria-label={`Remove ${item.file.name}`}
                      onClick={() => onRemove(item.id)}
                    >
                      <X />
                    </button>
                  ) : null}
                </div>
                <label className="upload-workspace-name">
                  <span>Display name</span>
                  <input
                    value={item.displayName}
                    disabled={item.phase !== 'queued'}
                    onChange={(event) => onDisplayNameChange(item.id, event.target.value)}
                  />
                </label>
                {active || item.phase === 'complete' ? (
                  <div
                    className={`upload-workspace-progress${item.phase === 'preparing' ? ' is-indeterminate' : ''}`}
                    role="progressbar"
                    aria-label={`${item.file.name} upload progress`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={item.phase === 'preparing' ? undefined : percent}
                    aria-valuetext={item.phase === 'preparing' ? 'Preparing upload' : `${percent}%`}
                  >
                    <span style={{ width: item.phase === 'preparing' ? '34%' : `${percent}%` }} />
                  </div>
                ) : null}
                {item.error ? (
                  <StatusMessage className="upload-workspace-error" tone="error">
                    {item.error}
                  </StatusMessage>
                ) : null}
              </article>
            )
          })}
        </div>
      ) : null}

      {items.length ? (
        <footer className="upload-workspace-footer">
          <span>
            {running
              ? 'Sequential upload active'
              : errorCount
                ? 'Queue paused'
              : queuedCount
                ? `${queuedCount} ${queuedCount === 1 ? 'file' : 'files'} ready`
                : 'Queue complete'}
          </span>
          <button
            type="button"
            className="primary"
            disabled={running || queuedCount === 0}
            onClick={onStart}
          >
            {running
              ? 'Uploading…'
              : `Upload ${queuedCount || ''} ${queuedCount === 1 ? 'file' : 'files'}`.replace('  ', ' ')}
          </button>
        </footer>
      ) : null}
    </section>
  )
}
