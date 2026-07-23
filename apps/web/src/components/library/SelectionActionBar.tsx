import { FolderInput, RotateCcw, Share, Tags, Trash2, X } from 'lucide-react'

interface SelectionActionBarProps {
  count: number
  mode?: 'default' | 'trash'
  onClear: () => void
  onMove: () => void
  onCollection: () => void
  onTags: () => void
  onPublish: () => void
  onTrash: () => void
  onRestore: () => void
  onDelete: () => void
}

export function SelectionActionBar({
  count,
  mode = 'default',
  onClear,
  onMove,
  onCollection,
  onTags,
  onPublish,
  onTrash,
  onRestore,
  onDelete,
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
          <button type="button" onClick={onTags}><Tags /> Edit tags</button>
          <button type="button" onClick={onPublish}><Share /> Publish</button>
          <button type="button" className="danger" onClick={onTrash}><Trash2 /> Trash</button>
        </>
      )}
    </div>
  )
}
