import { Edit3, Eye, Lock, X } from 'lucide-react'

import type { LibrarySlide, LibrarySlideDetails } from '../../types'
import { formatBytes } from './format'

interface SlideDetailsPanelProps {
  slide: LibrarySlideDetails | LibrarySlide | null
  onClose: () => void
  onEdit: () => void
  folderName?: string
  collectionNames?: string[]
}

export function SlideDetailsPanel({
  slide,
  onClose,
  onEdit,
  folderName,
  collectionNames = [],
}: SlideDetailsPanelProps) {
  if (!slide) return null
  const adminNote = 'adminNotes' in slide ? slide.adminNotes : ''
  return (
    <aside className="slide-details-panel" aria-label="Slide details">
      <div className="details-heading">
        <h2>Slide details</h2>
        <button type="button" aria-label="Close slide details" onClick={onClose}><X /></button>
      </div>
      <div className="details-thumbnail">
        {slide.thumbnailUrl
          ? <img src={slide.thumbnailUrl} alt="" />
          : <div className="thumbnail-fallback"><span>WSI</span></div>}
      </div>
      <h3>{slide.displayName}</h3>
      <p>{[slide.organSite, slide.stain].filter(Boolean).join(' · ') || 'Metadata pending'}</p>
      <div className="details-tags">
        {[slide.diagnosis, ...slide.tags].filter(Boolean).map((tag) => (
          <span key={tag}>{tag}</span>
        ))}
      </div>
      <dl>
        <div><dt>Case ID</dt><dd>{slide.caseId || '—'}</dd></div>
        <div><dt>Status</dt><dd>{slide.state.replace('_', ' ')}</dd></div>
        <div><dt>File size</dt><dd>{formatBytes(slide.sourceBytes)}</dd></div>
        <div><dt>Folder</dt><dd>{slide.folderId ? folderName ?? 'Folder' : 'Unfiled'}</dd></div>
        <div><dt>Collections</dt><dd>{collectionNames.join(', ') || '—'}</dd></div>
        <div><dt>Publication</dt><dd>{slide.state === 'published' ? 'Published' : 'Private'} <Lock /></dd></div>
      </dl>
      <section>
        <h4>Admin note</h4>
        <p className="admin-note">{adminNote || 'No administrator note.'}</p>
      </section>
      <div className="details-actions">
        {slide.state === 'ready_private' || slide.state === 'published' ? (
          <a href={`/admin/preview/${slide.id}`}><Eye /> Preview</a>
        ) : null}
        <button type="button" onClick={onEdit}><Edit3 /> Edit details</button>
      </div>
    </aside>
  )
}
