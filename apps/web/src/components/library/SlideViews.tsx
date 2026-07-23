import {
  Check,
  CircleAlert,
  CircleDashed,
  MoreVertical,
} from 'lucide-react'

import type { LibrarySlide } from '../../types'
import { formatBytes } from './format'
import type { LibraryViewMode } from './LibraryToolbar'

const STATUS: Record<LibrarySlide['state'], string> = {
  uploading: 'Uploading',
  queued: 'Queued',
  validating: 'Validating',
  converting: 'Processing',
  ready_private: 'Ready private',
  published: 'Published',
  failed: 'Failed',
  deleting: 'Deleting',
}

interface CommonProps {
  slides: LibrarySlide[]
  selected: Set<string>
  onSelect: (slideId: string, index: number, shift: boolean) => void
  onOpen: (slide: LibrarySlide) => void
}

function Thumbnail({ slide }: { slide: LibrarySlide }) {
  return (
    <div className="library-slide-thumbnail">
      {slide.thumbnailUrl ? (
        <img src={slide.thumbnailUrl} alt="" loading="lazy" decoding="async" />
      ) : (
        <div className="thumbnail-fallback" aria-label="Thumbnail unavailable">
          <CircleDashed />
          <span>{slide.state === 'converting' ? 'Processing' : 'WSI'}</span>
        </div>
      )}
    </div>
  )
}

function Status({ slide }: { slide: LibrarySlide }) {
  return (
    <span className={`library-state state-${slide.state}`}>
      {slide.state === 'failed' ? <CircleAlert /> : <Check />}
      {STATUS[slide.state]}
    </span>
  )
}

function SlideCard({
  slide,
  index,
  selected,
  onSelect,
  onOpen,
}: {
  slide: LibrarySlide
  index: number
  selected: boolean
  onSelect: CommonProps['onSelect']
  onOpen: CommonProps['onOpen']
}) {
  return (
    <article
      className={`library-slide-card ${selected ? 'selected' : ''}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData(
          'application/x-pathlab-slide-ids',
          selected ? slide.id : slide.id,
        )
      }}
      onDoubleClick={() => onOpen(slide)}
    >
      <div className="card-actions">
        <label>
          <input
            type="checkbox"
            checked={selected}
            aria-label={`Select ${slide.displayName}`}
            onChange={(event) => onSelect(slide.id, index, 'shiftKey' in event.nativeEvent
              && Boolean((event.nativeEvent as MouseEvent).shiftKey))}
          />
          <span><Check /></span>
        </label>
        <button type="button" aria-label={`More actions for ${slide.displayName}`}>
          <MoreVertical />
        </button>
      </div>
      <button
        type="button"
        className="card-preview"
        aria-label={`Open details for ${slide.displayName}`}
        onClick={() => onOpen(slide)}
      >
        <Thumbnail slide={slide} />
      </button>
      <div className="card-content">
        <h3>{slide.displayName}</h3>
        <p>{[slide.organSite, slide.stain].filter(Boolean).join(' · ') || 'Metadata pending'}</p>
        <div className="card-tags">
          {[slide.diagnosis, ...slide.tags].filter(Boolean).slice(0, 2).map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
        <p>Case {slide.caseId || '—'}</p>
        <p>{formatBytes(slide.sourceBytes)}</p>
        <Status slide={slide} />
      </div>
    </article>
  )
}

function SlideTable({ slides, selected, onSelect, onOpen }: CommonProps) {
  return (
    <div className="library-table-wrap">
      <table className="library-table">
        <thead>
          <tr>
            <th><span className="visually-hidden">Select</span></th>
            <th>Name</th>
            <th>Organ</th>
            <th>Stain</th>
            <th>Diagnosis</th>
            <th>Case</th>
            <th>Size</th>
            <th>Status</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {slides.map((slide, index) => (
            <tr
              key={slide.id}
              className={selected.has(slide.id) ? 'selected' : ''}
              onDoubleClick={() => onOpen(slide)}
            >
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(slide.id)}
                  aria-label={`Select ${slide.displayName}`}
                  onChange={(event) => onSelect(
                    slide.id,
                    index,
                    'shiftKey' in event.nativeEvent
                      && Boolean((event.nativeEvent as MouseEvent).shiftKey),
                  )}
                />
              </td>
              <td>
                <button type="button" onClick={() => onOpen(slide)}>
                  <span className="table-mini-thumb"><Thumbnail slide={slide} /></span>
                  {slide.displayName}
                </button>
              </td>
              <td>{slide.organSite || '—'}</td>
              <td>{slide.stain || '—'}</td>
              <td>{slide.diagnosis || '—'}</td>
              <td>{slide.caseId || '—'}</td>
              <td>{formatBytes(slide.sourceBytes)}</td>
              <td><Status slide={slide} /></td>
              <td>{new Date(slide.updatedAt).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SlideViews({
  view,
  slides,
  selected,
  onSelect,
  onOpen,
}: CommonProps & { view: LibraryViewMode }) {
  if (view === 'table') {
    return (
      <SlideTable
        slides={slides}
        selected={selected}
        onSelect={onSelect}
        onOpen={onOpen}
      />
    )
  }
  return (
    <div className={`library-slide-grid ${view === 'list' ? 'list-view' : ''}`}>
      {slides.map((slide, index) => (
        <SlideCard
          key={slide.id}
          slide={slide}
          index={index}
          selected={selected.has(slide.id)}
          onSelect={onSelect}
          onOpen={onOpen}
        />
      ))}
    </div>
  )
}
