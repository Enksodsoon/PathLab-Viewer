import type { LibraryFolder } from '../types'

export function MoveSlidesDialog({ open, folders, onClose, onMove }: {
  open: boolean
  folders: LibraryFolder[]
  onClose: () => void
  onMove: (folderId: string | null) => Promise<void>
}) {
  if (!open) return null
  return <div className="modal-backdrop"><section role="dialog" aria-modal="true" className="library-dialog">
    <h2>Move slides</h2><p>Choose one virtual folder. Image files remain in place.</p>
    <button onClick={() => void onMove(null).then(onClose)}>Unfiled</button>
    {folders.map((folder) => <button key={folder.id} onClick={() => void onMove(folder.id).then(onClose)}>{folder.name}</button>)}
    <div className="dialog-actions"><button onClick={onClose}>Cancel</button></div>
  </section></div>
}
