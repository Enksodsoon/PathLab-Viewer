import { CaretRight as ChevronRight } from '@phosphor-icons/react'
import { memo } from 'react'

import type { LibraryFolder } from '../../types'
import type { LibraryViewMode } from './LibraryToolbar'

interface FolderViewsProps {
  folders: LibraryFolder[]
  view: LibraryViewMode
  onOpen: (folder: LibraryFolder) => void
}

function FolderArtwork({ compact = false }: { compact?: boolean }) {
  return (
    <span
      className={`folder-artwork${compact ? ' folder-artwork--compact' : ''}`}
      aria-hidden="true"
    >
      <span className="folder-artwork__back" />
      <span className="folder-artwork__papers">
        <span className="folder-artwork__paper folder-artwork__paper--1" />
        <span className="folder-artwork__paper folder-artwork__paper--2" />
        <span className="folder-artwork__paper folder-artwork__paper--3" />
      </span>
      <span className="folder-artwork__front" />
    </span>
  )
}

function countLabel(folder: LibraryFolder) {
  const slides = `${folder.itemCount} ${folder.itemCount === 1 ? 'slide' : 'slides'}`
  if (folder.childCount === 0) return slides
  return `${slides} · ${folder.childCount} ${folder.childCount === 1 ? 'subfolder' : 'subfolders'}`
}

export const FolderViews = memo(function FolderViews({
  folders,
  view,
  onOpen,
}: FolderViewsProps) {
  return (
    <section
      className="library-folder-section"
      aria-labelledby="folder-section-heading"
      data-view={view}
    >
      <div className="library-folder-heading">
        <h3 id="folder-section-heading">Folders</h3>
        <span>{folders.length}</span>
      </div>
      {view === 'table' ? (
        <div className="library-folder-table-wrap">
          <table className="library-folder-table" aria-label="Folders">
            <thead>
              <tr>
                <th>Name</th>
                <th>Slides</th>
                <th>Subfolders</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {folders.map((folder) => (
                <tr key={folder.id}>
                  <td>
                    <button
                      type="button"
                      aria-label={`Open folder ${folder.name}`}
                      onClick={() => onOpen(folder)}
                    >
                      <FolderArtwork compact />
                      <span>{folder.name}</span>
                    </button>
                  </td>
                  <td>{folder.itemCount}</td>
                  <td>{folder.childCount}</td>
                  <td>{new Date(folder.updatedAt).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={`library-folder-grid ${view === 'list' ? 'list-view' : ''}`}>
          {folders.map((folder) => (
            <button
              key={folder.id}
              type="button"
              className="library-folder-card"
              aria-label={`Open folder ${folder.name}`}
              onClick={() => onOpen(folder)}
            >
              <FolderArtwork />
              <span className="library-folder-copy">
                <strong>{folder.name}</strong>
                <span>{countLabel(folder)}</span>
              </span>
              <ChevronRight aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
    </section>
  )
})
