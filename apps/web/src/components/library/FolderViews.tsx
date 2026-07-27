import { CaretRight as ChevronRight, Folder } from '@phosphor-icons/react'
import { memo } from 'react'

import type { LibraryFolder } from '../../types'

interface FolderViewsProps {
  folders: LibraryFolder[]
  onOpen: (folder: LibraryFolder) => void
}

function countLabel(folder: LibraryFolder) {
  const slides = `${folder.itemCount} ${folder.itemCount === 1 ? 'slide' : 'slides'}`
  if (folder.childCount === 0) return slides
  return `${slides} · ${folder.childCount} ${folder.childCount === 1 ? 'subfolder' : 'subfolders'}`
}

export const FolderViews = memo(function FolderViews({
  folders,
  onOpen,
}: FolderViewsProps) {
  return (
    <section className="library-folder-section" aria-labelledby="folder-section-heading">
      <div className="library-folder-heading">
        <h3 id="folder-section-heading">Folders</h3>
        <span>{folders.length}</span>
      </div>
      <div className="library-folder-grid">
        {folders.map((folder) => (
          <button
            key={folder.id}
            type="button"
            className="library-folder-card"
            aria-label={`Open folder ${folder.name}`}
            onClick={() => onOpen(folder)}
          >
            <span className="library-folder-icon" aria-hidden="true">
              <Folder />
            </span>
            <span className="library-folder-copy">
              <strong>{folder.name}</strong>
              <span>{countLabel(folder)}</span>
            </span>
            <ChevronRight aria-hidden="true" />
          </button>
        ))}
      </div>
    </section>
  )
})
