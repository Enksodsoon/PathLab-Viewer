import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import type { AdminSlide } from '../types'

export function SlideEditDialog({ slide, onClose, onSave }: {
  slide: AdminSlide | null
  onClose: () => void
  onSave: (update: Record<string, unknown>) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [stain, setStain] = useState('')
  const [organSite, setOrganSite] = useState('')
  const [tags, setTags] = useState('')
  const [teachingNote, setTeachingNote] = useState('')
  const [adminNotes, setAdminNotes] = useState('')
  useEffect(() => {
    setName(slide?.displayName ?? ''); setDescription(slide?.description ?? '')
    setStain(slide?.stain ?? ''); setOrganSite(slide?.organSite ?? '')
    setTags(slide?.tags?.join(', ') ?? ''); setTeachingNote(slide?.teachingNote ?? '')
    setAdminNotes(slide?.adminNotes ?? '')
  }, [slide])
  if (!slide) return null
  async function submit(event: FormEvent) {
    event.preventDefault()
    await onSave({ displayName: name, description, stain, organSite, tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean), teachingNote, adminNotes })
    onClose()
  }
  return <div className="modal-backdrop"><section role="dialog" aria-modal="true" className="library-dialog">
    <form onSubmit={(event) => void submit(event)}><h2>Edit slide details</h2>
      <label>Display name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label>Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <label>Stain<input value={stain} onChange={(event) => setStain(event.target.value)} /></label>
      <label>Organ or site<input value={organSite} onChange={(event) => setOrganSite(event.target.value)} /></label>
      <label>Tags<input value={tags} onChange={(event) => setTags(event.target.value)} /></label>
      <label>Teaching note<textarea value={teachingNote} onChange={(event) => setTeachingNote(event.target.value)} /></label>
      <label>Administrator note<textarea value={adminNotes} onChange={(event) => setAdminNotes(event.target.value)} /></label>
      <p className="privacy-note">De-identify public names, notes, and visible slide pixels.</p>
      <div className="dialog-actions"><button type="button" onClick={onClose}>Cancel</button><button>Save</button></div>
    </form>
  </section></div>
}
