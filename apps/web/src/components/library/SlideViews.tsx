import {
  Check,
  CircleAlert,
  CircleDashed,
  Clipboard,
  Edit3,
  ExternalLink,
  Eye,
  FolderInput,
  MoreVertical,
  RefreshCw,
  RotateCcw,
  Share2,
  Trash2,
  Undo2,
} from 'lucide-react'

import type { LibrarySlide } from '../../types'
import { ContextMenu } from './ContextMenu'
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

export type SlideAction =
  | 'edit'
  | 'move'
  | 'collection'
  | 'publish'
  | 'unpublish'
  | 'retry'
  | 'copy-public'
  | 'trash'
  | 'restore'
  | 'delete'

interface CommonProps {
  slides: LibrarySlide[]
  selected: Set<string>
  onSelect: (slideId: string, index: number, shift: boolean) => void
  onOpen: (slide: LibrarySlide) => void
  onAction: (slide: LibrarySlide, action: SlideAction) => void
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

function SlideActions({
  slide,
  onOpen,
  onAction,
}: {
  slide: LibrarySlide
  onOpen: CommonProps['onOpen']
  onAction: CommonProps['onAction']
}) {
  const ready = slide.state === 'ready_private'
  const published = slide.state === 'published'
  const failed = slide.state === 'failed'
  return (
    <ContextMenu
      label={`More actions for ${slide.displayName}`}
      buttonContent={<MoreVertical />}
    >
      {(close) => {
        const act = (action: SlideAction) => {
          close()
          onAction(slide, action)
        }
        return (
          <>
            <button type="button" role="menuitem" onClick={() => { close(); onOpen(slide) }}>
              <Eye /> Details
            </button>
            {(ready || published) ? (
              <a role="menuitem" href={`/admin/preview/${slide.id}`} onClick={close}>
                <Eye /> Preview
              </a>
            ) : null}
            {published ? (
              <>
                <a role="menuitem" href={`/s/${slide.publicId}`} target="_blank" rel="noreferrer" onClick={close}>
                  <ExternalLink /> Open public slide
                </a>
                <button type="button" role="menuitem" onClick={() => act('copy-public')}>
                  <Clipboard /> Copy public link
                </button>
                <button type="button" role="menuitem" onClick={() => act('unpublish')}>
                  <Undo2 /> Unpublish
                </button>
              </>
            ) : null}
            {!slide.trashedAt ? (
              <>
                <button type="button" role="menuitem" onClick={() => act('edit')}>
                  <Edit3 /> Edit details
                </button>
                <button type="button" role="menuitem" onClick={() => act('move')}>
                  <FolderInput /> Move
                </button>
                <button type="button" role="menuitem" onClick={() => act('collection')}>
                  <FolderInput /> Add to collection
                </button>
                {ready ? (
                  <button type="button" role="menuitem" onClick={() => act('publish')}>
                    <Share2 /> Publish
                  </button>
                ) : null}
                {failed ? (
                  <button type="button" role="menuitem" onClick={() => act('retry')}>
                    <RefreshCw /> Retry conversion
                  </button>
                ) : null}
                <button type="button" role="menuitem" className="danger" onClick={() => act('trash')}>
                  <Trash2 /> Move to Trash
                </button>
              </>
            ) : (
              <>
                <button type="button" role="menuitem" onClick={() => act('restore')}>
                  <RotateCcw /> Restore
                </button>
                <button type="button" role="menuitem" className="danger" onClick={() => act('delete')}>
                  <Trash2 /> Delete permanently
                </button>
              </>
            )}
          </>
        )
      }}
    </ContextMenu>
  )
}

function SlideCard({
  slide,
  index,
  selected,
  selectedIds,
  onSelect,
  onOpen,
  onAction,
}: {
  slide: LibrarySlide
  index: number
  selected: boolean
  selectedIds: Set<string>
  onSelect: CommonProps['onSelect']
  onOpen: CommonProps['onOpen']
  onAction: CommonProps['onAction']
}) {
  return (
    <article
      className={`library-slide-card ${selected ? 'selected' : ''}`}
      draggable
      onDragStart={(event) => {
        const ids = selected ? Array.from(selectedIds) : [slide.id]
        event.dataTransfer.setData('application/x-pathlab-slide-ids', ids.join(','))
      }}
      onDoubleClick={() => onOpen(slide)}
    >
      <div className="card-actions">
        <label>
          <input
            type="checkbox"
            checked={selected}
            aria-label={`Select ${slide.displayName}`}
            onChange={(event) => onSelect(
              slide.id,
              index,
              'shiftKey' in event.nativeEvent
                && Boolean((event.nativeEvent as MouseEvent).shiftKey),
            )}
          />
          <span><Check /></span>
        </label>
        <SlideActions slide={slide} onOpen={onOpen} onAction={onAction} />
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

function SlideTable(props: CommonProps) {
  const { slides, selected, onSelect, onOpen, onAction } = props
  return (
    <div className="library-table-wrap">
      <table className="library-table">
        <thead>
          <tr>
            <th><span className="visually-hidden">Select</span></th>
            <th>Name</th><th>Organ</th><th>Stain</th><th>Diagnosis</th>
            <th>Case</th><th>Size</th><th>Status</th><th>Updated</th>
            <th><span className="visually-hidden">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {slides.map((slide, index) => (
            <tr key={slide.id} className={selected.has(slide.id) ? 'selected' : ''}>
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
              <td>{slide.organSite || '—'}</td><td>{slide.stain || '—'}</td>
              <td>{slide.diagnosis || '—'}</td><td>{slide.caseId || '—'}</td>
              <td>{formatBytes(slide.sourceBytes)}</td><td><Status slide={slide} /></td>
              <td>{new Date(slide.updatedAt).toLocaleDateString()}</td>
              <td><SlideActions slide={slide} onOpen={onOpen} onAction={onAction} /></td>
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
    return <SlideTable {...{ slides, selected, onSelect, onOpen, onAction }} />
  }
  return (
    <div className={`library-slide-grid ${view === 'list' ? 'list-view' : ''}`}>
      {slides.map((slide, index) => (
        <SlideCard
          key={slide.id}
          slide={slide}
          index={index}
          selected={selected.has(slide.id)}
          selectedIds={selected}
          onSelect={onSelect}
          onOpen={onOpen}
          onAction={onAction}
        />
      ))}
    </div>
  )
}
