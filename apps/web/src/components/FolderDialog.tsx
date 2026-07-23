import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

interface Props {
  open: boolean
  title: string
  initialName?: string
  initialDescription?: string
  onClose: () => void
  onSave: (name: string, description: string) => Promise<void>
}

export function FolderDialog({
  open, title, initialName = '', initialDescription = '', onClose, onSave,
}: Props) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setName(initialName); setDescription(initialDescription) }, [initialDescription, initialName, open])
  if (!open) return null
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true)
    try { await onSave(name, description); onClose() } finally { setBusy(false) }
  }
  return <div className="modal-backdrop">
    <section role="dialog" aria-modal="true" aria-labelledby="folder-dialog-title" className="library-dialog">
      <form onSubmit={(event) => void submit(event)}>
        <h2 id="folder-dialog-title">{title}</h2>
        <label>Folder name<input autoFocus maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Description<textarea maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <div className="dialog-actions"><button type="button" onClick={onClose}>Cancel</button><button disabled={busy || !name.trim()}>{busy ? 'Saving…' : 'Save'}</button></div>
      </form>
    </section>
  </div>
}
