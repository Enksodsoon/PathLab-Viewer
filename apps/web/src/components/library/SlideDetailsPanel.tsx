import { Lock, LockOpen, PencilSimple as Edit3, X } from '@phosphor-icons/react'

import type { LibrarySlide, LibrarySlideDetails } from '../../types'
import { Link } from 'react-router-dom'
import { canPreview } from './viewerNavigation'
import { formatBytes } from './format'
import { SlideStackSection } from './SlideStackSection'

interface SlideDetailsPanelProps {
  slide: LibrarySlideDetails | LibrarySlide | null
  onClose: () => void
  onEdit: () => void
  onPreview?: (slide: LibrarySlide) => void
  folderName?: string
  collectionNames?: string[]
  stackEnabled?: boolean
}

export function SlideDetailsPanel({
  slide,
  onClose,
  onEdit,
  onPreview,
  folderName,
  collectionNames = [],
  stackEnabled = false,
}: SlideDetailsPanelProps) {
  if (!slide) return null
  const adminNote = 'adminNotes' in slide ? slide.adminNotes : ''
  const isPublished = slide.state === 'published'
  return (
    <aside
      className="slide-details-panel"
      aria-label="Slide details"
      data-overlay="inspector"
    >
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
        <div>
          <dt>Publication</dt>
          <dd
            className={`publication-state ${isPublished ? 'is-published' : 'is-private'}`}
            aria-label={`Publication: ${isPublished ? 'Public' : 'Private'}`}
          >
            <span>{isPublished ? 'Public' : 'Private'}</span>
            {isPublished
              ? <LockOpen aria-hidden="true" color="currentColor" data-lock-state="open" />
              : <Lock aria-hidden="true" color="currentColor" data-lock-state="closed" />}
          </dd>
        </div>
      </dl>
      <section>
        <h4>Admin note</h4>
        <p className="admin-note">{adminNote || 'No administrator note.'}</p>
      </section>
      <SlideStackSection slide={slide} enabled={stackEnabled} />
      <div className="details-actions">
        {canPreview(slide) ? (
          <>{onPreview ? <button type="button" onClick={() => onPreview(slide)}>Open viewer</button> : <Link to={`/admin/preview/${encodeURIComponent(slide.id)}`}>Open viewer</Link>}</>
        ) : null}
        <button type="button" onClick={onEdit}><Edit3 /> Edit details</button>
      </div>
    </aside>
  )
}
