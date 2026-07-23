import {
  FolderInput,
  RefreshCw,
  RotateCcw,
  Share,
  Tags,
  Trash2,
  Undo2,
  Unlink,
  X,
} from 'lucide-react'

interface SelectionActionBarProps {
  count: number
  mode?: 'default' | 'trash'
  onClear: () => void
  onMove: () => void
  onCollection: () => void
  onTags: () => void
  onPublish: () => void
  onUnpublish: () => void
  onRetry: () => void
  onTrash: () => void
  onRestore: () => void
  onDelete: () => void
  canPublish?: boolean
  canUnpublish?: boolean
  canRetry?: boolean
  inCollection?: boolean
  onRemoveCollection: () => void
}

export function SelectionActionBar({
  count,
  mode = 'default',
  onClear,
  onMove,
  onCollection,
  onTags,
  onPublish,
  onUnpublish,
  onRetry,
  onTrash,
  onRestore,
  onDelete,
  canPublish = false,
  canUnpublish = false,
  canRetry = false,
  inCollection = false,
  onRemoveCollection,
}: SelectionActionBarProps) {
  if (count === 0) return null
  return (
    <div className="selection-action-bar" role="toolbar" aria-label="Selection actions">
      <strong>{count} selected</strong>
      <button type="button" aria-label="Clear selection" onClick={onClear}><X /></button>
      <span />
      {mode === 'trash' ? (
        <>
          <button type="button" onClick={onRestore}><RotateCcw /> Restore</button>
          <button type="button" className="danger" onClick={onDelete}>
            <Trash2 /> Delete permanently
          </button>
        </>
      ) : (
        <>
          <button type="button" onClick={onMove}><FolderInput /> Move</button>
          <button type="button" onClick={onCollection}><FolderInput /> Add to collection</button>
          {inCollection ? (
            <button type="button" onClick={onRemoveCollection}>
              <Unlink /> Remove from collection
            </button>
          ) : null}
          <button type="button" onClick={onTags}><Tags /> Edit tags</button>
          {canPublish ? <button type="button" onClick={onPublish}><Share /> Publish</button> : null}
          {canUnpublish ? <button type="button" onClick={onUnpublish}><Undo2 /> Unpublish</button> : null}
          {canRetry ? <button type="button" onClick={onRetry}><RefreshCw /> Retry</button> : null}
          <button type="button" className="danger" onClick={onTrash}><Trash2 /> Trash</button>
        </>
      )}
    </div>
  )
}
