import { CaretDown, CaretUp, Pause, UploadSimple, X } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { cancelUploadItem, removeUploadItem, retryUploadItem, startUploadQueue, useUploadQueue } from '../../uploadQueue'
import { formatBytes } from './format'
import './uploadDock.css'

export function UploadDock() {
  const queue = useUploadQueue()
  const [minimized, setMinimized] = useState(false)
  if (!queue.authorized || !queue.items.length) return null
  const active = queue.items.filter((item) => ['preparing', 'uploading', 'processing'].includes(item.phase)).length
  const queued = queue.items.filter((item) => item.phase === 'queued').length
  return <aside className={`upload-dock${minimized ? ' is-minimized' : ''}`} aria-label="Background uploads">
    <header><UploadSimple aria-hidden="true" /><strong>Uploads</strong><span aria-live="polite">{active ? `${active} active` : `${queue.items.filter((item) => item.phase === 'ready').length} ready`}</span>
      <button type="button" aria-label={minimized ? 'Expand uploads' : 'Minimize uploads'} aria-expanded={!minimized} onClick={() => setMinimized((value) => !value)}>{minimized ? <CaretUp /> : <CaretDown />}</button>
    </header>
    {!minimized ? <>
      <div className="upload-dock-items">{queue.items.map((item) => <article key={item.id}>
        <strong>{item.displayName}</strong><small>{formatBytes(item.file.size)} · {item.phase === 'processing' ? `Processing: ${item.processingState ?? 'queued'}` : item.phase === 'ready' ? 'Ready to view' : item.phase === 'cancelled' ? 'Paused' : item.phase === 'processing_failed' ? 'Processing stopped' : item.phase === 'error' ? 'Transfer failed' : item.phase === 'uploading' ? `Uploading ${item.progress}%` : item.phase === 'preparing' ? 'Preparing upload' : 'Queued'}</small>
        {item.phase === 'uploading' ? <><progress aria-label={`${item.displayName} transfer`} max={100} value={item.progress} /><small>{formatBytes(item.uploadedBytes)} sent{item.bytesPerSecond ? ` · ${formatBytes(item.bytesPerSecond)}/s` : ''}{item.etaSeconds !== null ? ` · ~${Math.ceil(item.etaSeconds)} s at that rate` : ''}</small></> : null}
        {item.error ? <p role={item.phase === 'error' || item.phase === 'processing_failed' ? 'alert' : 'status'}>{item.error}</p> : null}
        <div className="upload-dock-actions">
          {['queued','preparing','uploading'].includes(item.phase) ? <button type="button" onClick={() => cancelUploadItem(item.id)} aria-label={`Pause ${item.displayName}`}><Pause /> Pause</button> : null}
          {item.phase === 'error' || item.phase === 'cancelled' ? <button type="button" onClick={() => retryUploadItem(item.id)}>Resume transfer</button> : null}
          {item.phase === 'ready' && item.reservation ? <Link to={`/admin/preview/${encodeURIComponent(item.reservation.slide.id)}`}>Open viewer</Link> : null}
          {!['preparing','uploading'].includes(item.phase) ? <button type="button" aria-label={`${['cancelled','error'].includes(item.phase) ? 'Cancel upload for' : 'Dismiss'} ${item.displayName}`} onClick={() => void removeUploadItem(item.id)}><X /></button> : null}
        </div>
      </article>)}</div>
      <footer>{queue.notice ? <p role="status">{queue.notice}</p> : null}<span>Transfers continue while you browse. Keep this browser tab open.</span>{queued ? <button type="button" disabled={queue.running} onClick={() => void startUploadQueue()}>Upload {queued} {queued === 1 ? 'file' : 'files'}</button> : null}</footer>
    </> : null}
  </aside>
}
