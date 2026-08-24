import {
  ArrowClockwise,
  ArrowLeft,
  Archive,
  Database,
  File,
  HardDrives,
  MagnifyingGlass,
  Trash,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  deleteLibrarySlide,
  getStorageInventory,
  mutateLibrarySlide,
} from '../../api'
import type { StorageInventory, StorageItem } from '../../types'
import { Loader } from '../Loader'
import { StatusMessage } from '../StatusMessage'
import { LibraryDialog } from '../library/LibraryDialog'
import './StorageWorkspace.css'

type StorageScope = 'all' | 'active' | 'trash'
type StorageSort = 'size_desc' | 'name_asc' | 'updated_desc'

interface StorageWorkspaceProps {
  onBack: () => void
  onStorageChanged: () => void
}

export function StorageWorkspace({ onBack, onStorageChanged }: StorageWorkspaceProps) {
  const [inventory, setInventory] = useState<StorageInventory | null>(null)
  const [scope, setScope] = useState<StorageScope>('all')
  const [sort, setSort] = useState<StorageSort>('size_desc')
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<StorageItem | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchDraft.trim())
      setOffset(0)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchDraft])

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError('')
    try {
      setInventory(await getStorageInventory({ scope, q: search, sort, offset, signal }))
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === 'AbortError') return
      setError('Storage details could not load. Try again.')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [offset, scope, search, sort])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const refreshAfterMutation = useCallback(async () => {
    await load()
    onStorageChanged()
  }, [load, onStorageChanged])

  async function moveToTrash(item: StorageItem) {
    setBusyId(item.id)
    setNotice('')
    setError('')
    try {
      await mutateLibrarySlide(item.id, 'trash')
      setNotice(`${item.displayName} moved to Trash. It can be restored.`)
      await refreshAfterMutation()
    } catch {
      setError('The file could not be moved to Trash.')
    } finally {
      setBusyId(null)
    }
  }

  async function restore(item: StorageItem) {
    setBusyId(item.id)
    setNotice('')
    setError('')
    try {
      await mutateLibrarySlide(item.id, 'restore')
      setNotice(`${item.displayName} restored to the slide library.`)
      await refreshAfterMutation()
    } catch {
      setError('The file could not be restored.')
    } finally {
      setBusyId(null)
    }
  }

  async function permanentlyDelete() {
    if (!deleteTarget) return
    setBusyId(deleteTarget.id)
    setNotice('')
    setError('')
    try {
      await deleteLibrarySlide(deleteTarget.id)
      setNotice(`${deleteTarget.displayName} is queued for permanent deletion.`)
      setDeleteTarget(null)
      await refreshAfterMutation()
    } catch {
      setError('Permanent deletion could not be queued. The file remains in Trash.')
    } finally {
      setBusyId(null)
    }
  }

  const summary = inventory?.summary
  const physicalOtherBytes = summary
    ? Math.max(0, summary.physicalUsedBytes - summary.managedBytes)
    : 0
  const applicationPercent = summary && summary.effectiveCapacityBytes > 0
    ? Math.min(100, (summary.managedBytes / summary.effectiveCapacityBytes) * 100)
    : 0
  const categories = useMemo(() => summary ? [
    { label: 'Library', bytes: summary.libraryBytes, count: summary.libraryCount, tone: 'library' },
    { label: 'Processing', bytes: summary.processingBytes, count: summary.processingCount, tone: 'processing' },
    { label: 'Trash', bytes: summary.trashBytes, count: summary.trashCount, tone: 'trash' },
    { label: 'Deleting', bytes: summary.deletingBytes, count: summary.deletingCount, tone: 'deleting' },
  ] : [], [summary])
  const pageNumber = inventory ? Math.floor(inventory.offset / inventory.limit) + 1 : 1
  const pageCount = inventory ? Math.max(1, Math.ceil(inventory.total / inventory.limit)) : 1

  return (
    <div className="storage-workspace">
      <header className="storage-workspace-header">
        <div className="storage-workspace-title-row">
          <button type="button" className="storage-icon-button" aria-label="Back to slide library" onClick={onBack}>
            <ArrowLeft />
          </button>
          <div>
            <span className="storage-eyebrow">Managed storage</span>
            <h1>Storage</h1>
            <p>Review slide data, recover items from Trash, and remove files safely.</p>
          </div>
        </div>
        <button
          type="button"
          className="storage-refresh-button"
          disabled={loading}
          onClick={() => void load()}
        >
          <ArrowClockwise /> Refresh
        </button>
      </header>

      {error ? <StatusMessage tone="error">{error}</StatusMessage> : null}
      {notice ? <StatusMessage tone="success">{notice}</StatusMessage> : null}

      {loading && !inventory ? (
        <div className="storage-workspace-loading"><Loader label="Measuring storage…" /></div>
      ) : null}

      {summary ? (
        <section className="storage-overview" aria-labelledby="storage-overview-title">
          <article className="storage-capacity-card">
            <div className="storage-card-heading">
              <div>
                <span id="storage-overview-title">Application capacity</span>
                <strong>{formatBytes(summary.usableBytes)} available</strong>
              </div>
              <HardDrives aria-hidden="true" />
            </div>
            <div
              className="storage-capacity-track"
              role="meter"
              aria-label="Application storage used"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(applicationPercent)}
            >
              <span style={{ width: `${applicationPercent}%` }} />
            </div>
            <div className="storage-capacity-meta">
              <span><b>{formatBytes(summary.managedBytes)}</b> managed</span>
              <span>{formatBytes(summary.effectiveCapacityBytes)} usable capacity</span>
            </div>
          </article>

          <div className="storage-breakdown" aria-label="Managed storage breakdown">
            {categories.map((category) => (
              <div className="storage-breakdown-row" key={category.label}>
                <span className={`storage-breakdown-dot ${category.tone}`} aria-hidden="true" />
                <span>{category.label}</span>
                <small>{category.count} {category.count === 1 ? 'file' : 'files'}</small>
                <strong>{formatBytes(category.bytes)}</strong>
              </div>
            ))}
          </div>

          <article className="storage-volume-card">
            <div>
              <Database aria-hidden="true" />
              <span>OCI data volume</span>
            </div>
            <strong>{formatBytes(summary.physicalFreeBytes)} physically free</strong>
            <p>
              {formatBytes(physicalOtherBytes)} is used by backups, database files,
              delivery manifests, and filesystem overhead outside managed slide accounting.
            </p>
          </article>
        </section>
      ) : null}

      <section className="storage-files" aria-labelledby="storage-files-title">
        <div className="storage-files-heading">
          <div>
            <span className="storage-eyebrow">Content inventory</span>
            <h2 id="storage-files-title">Files and derivatives</h2>
          </div>
          <span>{inventory?.total ?? 0} {(inventory?.total ?? 0) === 1 ? 'item' : 'items'}</span>
        </div>

        <div className="storage-controls">
          <div className="storage-scope-tabs" role="group" aria-label="Storage location">
            {([
              ['all', 'All files'],
              ['active', 'Library'],
              ['trash', 'Trash'],
            ] as const).map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={scope === value ? 'active' : ''}
                aria-pressed={scope === value}
                onClick={() => {
                  setScope(value)
                  setOffset(0)
                }}
              >{label}</button>
            ))}
          </div>
          <label className="storage-search">
            <MagnifyingGlass aria-hidden="true" />
            <span className="sr-only">Search stored files</span>
            <input
              type="search"
              value={searchDraft}
              placeholder="Search files"
              onChange={(event) => setSearchDraft(event.target.value)}
            />
          </label>
          <label className="storage-sort">
            <span>Sort</span>
            <select value={sort} onChange={(event) => {
              setSort(event.target.value as StorageSort)
              setOffset(0)
            }}>
              <option value="size_desc">Largest first</option>
              <option value="updated_desc">Recently updated</option>
              <option value="name_asc">Name</option>
            </select>
          </label>
        </div>

        {loading && inventory ? <div className="storage-inline-loading"><Loader label="Updating files…" size="small" inline /></div> : null}
        {!loading && inventory?.items.length === 0 ? (
          <div className="storage-empty">
            <Archive />
            <h3>No stored files match this view</h3>
            <p>Change the location or clear the search.</p>
          </div>
        ) : null}
        {inventory?.items.length ? (
          <div className="storage-table-wrap">
            <table className="storage-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Location</th>
                  <th>Original</th>
                  <th>Derivative</th>
                  <th>Accounted</th>
                  <th><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {inventory.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="storage-file-name">
                        <span><File aria-hidden="true" /></span>
                        <div>
                          <strong>{item.displayName}</strong>
                          <small title={item.originalFilename}>{item.originalFilename}</small>
                        </div>
                      </div>
                    </td>
                    <td><StorageState item={item} /></td>
                    <td data-label="Original">{formatBytes(item.sourceBytes)}</td>
                    <td data-label="Derivative">{formatBytes(item.derivativeBytes)}</td>
                    <td data-label="Accounted"><strong>{formatBytes(item.accountedBytes)}</strong></td>
                    <td>
                      <div className="storage-row-actions">
                        {item.canTrash ? (
                          <button type="button" disabled={busyId === item.id} onClick={() => void moveToTrash(item)}>
                            <Trash /> Move to Trash
                          </button>
                        ) : null}
                        {item.canRestore ? (
                          <button type="button" disabled={busyId === item.id} onClick={() => void restore(item)}>
                            <ArrowClockwise /> Restore
                          </button>
                        ) : null}
                        {item.canDelete ? (
                          <button type="button" className="danger" disabled={busyId === item.id} onClick={() => setDeleteTarget(item)}>
                            Delete permanently
                          </button>
                        ) : null}
                        {!item.canTrash && !item.canRestore && !item.canDelete ? <small>Action pending</small> : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {inventory && pageCount > 1 ? (
          <div className="storage-pagination" aria-label="Storage pages">
            <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - inventory.limit))}>Previous</button>
            <span>Page {pageNumber} of {pageCount}</span>
            <button type="button" disabled={offset + inventory.limit >= inventory.total || loading} onClick={() => setOffset(offset + inventory.limit)}>Next</button>
          </div>
        ) : null}
      </section>

      <LibraryDialog
        open={deleteTarget !== null}
        title="Delete permanently?"
        description="This queues removal of the original and its managed derivatives. This action cannot be undone."
        onClose={() => setDeleteTarget(null)}
      >
        <div className="library-dialog-body">
          <p><strong>{deleteTarget?.displayName}</strong> will be removed from PathLab storage.</p>
        </div>
        <div className="library-dialog-actions">
          <button type="button" onClick={() => setDeleteTarget(null)}>Keep file</button>
          <button type="button" className="danger" disabled={busyId === deleteTarget?.id} onClick={() => void permanentlyDelete()}>
            Delete permanently
          </button>
        </div>
      </LibraryDialog>
    </div>
  )
}

function StorageState({ item }: { item: StorageItem }) {
  const label = item.state === 'deleting'
    ? 'Deleting'
    : item.trashedAt
      ? 'Trash'
      : ['uploading', 'queued', 'validating', 'converting'].includes(item.state)
        ? 'Processing'
        : 'Library'
  return <span className={`storage-state storage-state-${label.toLowerCase()}`}>{label}</span>
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}
