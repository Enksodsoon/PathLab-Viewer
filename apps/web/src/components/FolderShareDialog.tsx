import type { LibraryFolder } from '../types'

export function FolderShareDialog({ folder, onClose, onShare, onRevoke, onRotate }: {
  folder: LibraryFolder | null
  onClose: () => void
  onShare: () => Promise<void>
  onRevoke: () => Promise<void>
  onRotate: () => Promise<void>
}) {
  if (!folder) return null
  const url = folder.share ? `${location.origin}/f/${folder.share.publicId}` : ''
  return <div className="modal-backdrop"><section role="dialog" aria-modal="true" className="library-dialog">
    <h2>Share {folder.name}</h2>
    <p>Unlisted links are bearer links, not authenticated access control.</p>
    {folder.share ? <><input aria-label="Folder link" readOnly value={url} /><button onClick={() => void navigator.clipboard.writeText(url)}>Copy link</button><button onClick={() => void onRotate()}>Rotate link</button><button className="danger-action" onClick={() => void onRevoke()}>Revoke share</button></> : <button onClick={() => void onShare()}>Create folder link</button>}
    <div className="dialog-actions"><button onClick={onClose}>Close</button></div>
  </section></div>
}
