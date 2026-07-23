import { FolderInput, Share, Tags, Trash2, X } from 'lucide-react'

interface SelectionActionBarProps {
  count: number
  onClear: () => void
  onMove: () => void
  onCollection: () => void
  onTags: () => void
  onPublish: () => void
  onTrash: () => void
}

export function SelectionActionBar({
  count,
  onClear,
  onMove,
  onCollection,
  onTags,
  onPublish,
  onTrash,
}: SelectionActionBarProps) {
  if (count === 0) return null
  return (
    <div className="selection-action-bar" role="toolbar" aria-label="Selection actions">
      <strong>{count} selected</strong>
      <button type="button" aria-label="Clear selection" onClick={onClear}><X /></button>
      <span />
      <button type="button" onClick={onMove}><FolderInput /> Move</button>
      <button type="button" onClick={onCollection}><FolderInput /> Add to collection</button>
      <button type="button" onClick={onTags}><Tags /> Edit tags</button>
      <button type="button" onClick={onPublish}><Share /> Publish</button>
      <button type="button" className="danger" onClick={onTrash}><Trash2 /> Trash</button>
    </div>
  )
}
