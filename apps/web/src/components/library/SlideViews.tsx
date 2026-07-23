import {
  Check,
  CircleAlert,
  CircleDashed,
  Edit3,
  Eye,
  FolderInput,
  MoreVertical,
  RotateCcw,
  Share2,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'

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
  onAction: (
    slide: LibrarySlide,
    action: 'edit' | 'move' | 'collection' | 'publish' | 'trash' | 'restore' | 'delete',
  ) => void
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
  onAction,
}: {
  slide: LibrarySlide
  index: number
  selected: boolean
  onSelect: CommonProps['onSelect']
  onOpen: CommonProps['onOpen']
  onAction: CommonProps['onAction']
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  function action(name: Parameters<CommonProps['onAction']>[1]) {
    setMenuOpen(false)
    onAction(slide, name)
  }

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
        <button
          type="button"
          aria-label={`More actions for ${slide.displayName}`}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          onClick={() => setMenuOpen((current) => !current)}
        >
          <MoreVertical />
        </button>
        {menuOpen ? (
          <div className="library-menu card-action-menu" role="menu">
            <button type="button" role="menuitem" onClick={() => onOpen(slide)}>
              <Eye /> Details
            </button>
            <a role="menuitem" href={`/admin/preview/${slide.id}`}>
              <Eye /> Preview
            </a>
            <button type="button" role="menuitem" onClick={() => action('edit')}>
              <Edit3 /> Edit details
            </button>
            {slide.trashedAt ? (
              <>
                <button type="button" role="menuitem" onClick={() => action('restore')}>
                  <RotateCcw /> Restore
                </button>
                <button type="button" role="menuitem" className="danger" onClick={() => action('delete')}>
                  <Trash2 /> Delete permanently
                </button>
              </>
            ) : (
              <>
                <button type="button" role="menuitem" onClick={() => action('move')}>
                  <FolderInput /> Move
                </button>
                <button type="button" role="menuitem" onClick={() => action('collection')}>
                  <FolderInput /> Add to collection
                </button>
                {slide.state === 'ready_private' ? (
                  <button type="button" role="menuitem" onClick={() => action('publish')}>
                    <Share2 /> Publish
                  </button>
                ) : null}
                <button type="button" role="menuitem" className="danger" onClick={() => action('trash')}>
                  <Trash2 /> Move to Trash
                </button>
              </>
            )}
          </div>
        ) : null}
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
  onAction,
}: CommonProps & { view: LibraryViewMode }) {
  if (view === 'table') {
    return (
      <SlideTable
        slides={slides}
        selected={selected}
        onSelect={onSelect}
        onOpen={onOpen}
        onAction={onAction}
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
          onAction={onAction}
        />
      ))}
    </div>
  )
}
