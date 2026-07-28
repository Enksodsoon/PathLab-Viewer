import {
  CheckCircle,
  FileArrowUp,
  UploadSimple,
  WarningCircle,
  X,
} from '@phosphor-icons/react'
import { useRef, useState, type DragEvent } from 'react'

import { formatBytes } from './format'

const ACCEPTED_FILE_PATTERN = /\.ome\.tiff?$/i

interface UploadWorkspaceProps {
  file: File | null
  displayName: string
  progress: number | null
  preparing: boolean
  error: string
  onFileChange: (file: File | null) => void
  onDisplayNameChange: (name: string) => void
  onUpload: () => void
}

export function UploadWorkspace({
  file,
  displayName,
  progress,
  preparing,
  error,
  onFileChange,
  onDisplayNameChange,
  onUpload,
}: UploadWorkspaceProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const uploading = progress !== null && progress < 100 && !error
  const complete = progress === 100 && !error
  const locked = preparing || uploading
  const percent = Math.min(100, Math.max(0, Math.round(progress ?? 0)))

  function chooseFile(next: File | null) {
    if (locked) return
    onFileChange(next)
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files?.[0] ?? null)
  }

  return (
    <section className="upload-workspace" aria-label="Upload slide">
      {!file ? (
        <div
          className={`upload-workspace-drop${dragging ? ' is-dragging' : ''}`}
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
            <strong>Drop an OME-TIFF here</strong>
            <p>or choose a file from this device</p>
          </div>
          <button type="button" className="upload-workspace-choose" onClick={() => inputRef.current?.click()}>
            Choose file
          </button>
          <small>OME-TIFF only · up to 5 GiB · resumable</small>
        </div>
      ) : (
        <div className={`upload-workspace-file${error ? ' has-error' : complete ? ' is-complete' : ''}`}>
          <span className="upload-workspace-file-icon" aria-hidden="true">
            {error ? <WarningCircle /> : complete ? <CheckCircle /> : <FileArrowUp />}
          </span>
          <div className="upload-workspace-file-copy">
            <strong title={file.name}>{file.name}</strong>
            <span>
              {formatBytes(file.size)}
              {' · '}
              {error
                ? 'Upload paused'
                : complete
                  ? 'Upload complete'
                  : preparing
                    ? 'Preparing resumable upload'
                    : uploading
                      ? `Uploading ${percent}%`
                      : 'Ready to upload'}
            </span>
          </div>
          {!locked ? (
            <button
              type="button"
              className="upload-workspace-remove"
              aria-label={`Remove ${file.name}`}
              onClick={() => chooseFile(null)}
            >
              <X />
            </button>
          ) : null}
          {(preparing || uploading || complete) ? (
            <div
              className={`upload-workspace-progress${preparing ? ' is-indeterminate' : ''}`}
              role="progressbar"
              aria-label={`${file.name} upload progress`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={preparing ? undefined : percent}
              aria-valuetext={preparing ? 'Preparing upload' : `${percent}%`}
            >
              <span style={{ width: preparing ? '34%' : `${percent}%` }} />
            </div>
          ) : null}
          {error ? <p className="upload-workspace-error" role="alert">{error}</p> : null}
        </div>
      )}

      <input
        ref={inputRef}
        className="upload-file-input"
        type="file"
        accept=".ome.tif,.ome.tiff,image/tiff"
        aria-label="Choose OME-TIFF"
        onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
      />

      {file ? (
        <div className="upload-workspace-details">
          <label>
            Display name
            <input
              value={displayName}
              disabled={locked}
              onChange={(event) => onDisplayNameChange(event.target.value)}
            />
          </label>
          <button
            type="button"
            className="primary"
            disabled={locked || complete || !ACCEPTED_FILE_PATTERN.test(file.name)}
            onClick={onUpload}
          >
            {error ? 'Resume upload' : complete ? 'Uploaded' : uploading ? `Uploading ${percent}%` : 'Upload slide'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
