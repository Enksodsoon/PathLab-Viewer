import {
  CircleDashed,
  CircleX,
  Clock3,
  FolderInput,
  Grid2X2,
  Edit3,
  MoreHorizontal,
  Plus,
  Share2,
  Trash2,
} from 'lucide-react'

import type { LibraryFolder, LibraryNavigation } from '../../types'
import { ContextMenu } from './ContextMenu'
import { FolderTree } from './FolderTree'

interface LibraryNavigatorProps {
  navigation: LibraryNavigation
  location: string
  folderChildren: Map<string, LibraryFolder[]>
  expandedFolders: Set<string>
  onExpandFolder: (folder: LibraryFolder) => void
  onLocation: (location: string) => void
  onNewFolder: () => void
  onNewCollection: () => void
  onNewSavedView: () => void
  onDropSlides: (folderId: string, slideIds: string[]) => void
  onFolderAction: (
    folder: LibraryFolder,
    action: 'rename' | 'move' | 'trash',
  ) => void
  onCollectionAction: (id: string, action: 'rename' | 'delete') => void
  onSavedViewAction: (id: string, action: 'rename' | 'delete') => void
}

const SPECIAL = [
  ['all', 'All slides', Grid2X2, 'all'],
  ['unfiled', 'Unfiled', FolderInput, 'unfiled'],
  ['shared', 'Shared', Share2, 'shared'],
  ['processing', 'Processing', CircleDashed, 'processing'],
  ['failed', 'Failed', CircleX, 'failed'],
  ['trash', 'Trash', Trash2, 'trash'],
] as const

function SectionTitle({
  children,
  label,
  onAdd,
}: {
  children: string
  label: string
  onAdd: () => void
}) {
  return (
    <div className="navigator-section-title">
      <span>{children}</span>
      <button type="button" aria-label={label} onClick={onAdd}><Plus /></button>
    </div>
  )
}

export function LibraryNavigator({
  navigation,
  location,
  folderChildren,
  expandedFolders,
  onExpandFolder,
  onLocation,
  onNewFolder,
  onNewCollection,
  onNewSavedView,
  onDropSlides,
  onFolderAction,
  onCollectionAction,
  onSavedViewAction,
}: LibraryNavigatorProps) {
  const selectedFolderId = location.startsWith('folder:')
    ? location.slice('folder:'.length)
    : null

  return (
    <aside className="library-navigator" aria-label="Library navigator">
      <h1>Slides library</h1>
      <nav className="navigator-special">
        {SPECIAL.map(([id, label, Icon, countKey]) => (
          <button
            key={id}
            type="button"
            className={location === id ? 'active' : ''}
            onClick={() => onLocation(id)}
          >
            <Icon />
            <span>{label}</span>
            <strong>{navigation.counts[countKey]}</strong>
          </button>
        ))}
      </nav>

      <SectionTitle label="New folder" onAdd={onNewFolder}>Folders</SectionTitle>
      <FolderTree
        roots={navigation.folders}
        children={folderChildren}
        expanded={expandedFolders}
        selectedId={selectedFolderId}
        onExpand={onExpandFolder}
        onSelect={(folder) => onLocation(`folder:${folder.id}`)}
        onDropSlides={onDropSlides}
        onAction={onFolderAction}
      />

      <SectionTitle label="New collection" onAdd={onNewCollection}>Collections</SectionTitle>
      <nav className="navigator-list">
        {navigation.collections.map((collection) => (
          <div className="navigator-list-row" key={collection.id}>
            <button
              type="button"
              className={location === `collection:${collection.id}` ? 'active' : ''}
              onClick={() => onLocation(`collection:${collection.id}`)}
            >
              <Grid2X2 /><span>{collection.name}</span><strong>{collection.itemCount}</strong>
            </button>
            <ContextMenu
              label={`More actions for ${collection.name}`}
              buttonClassName="navigator-more"
              buttonContent={<MoreHorizontal />}
            >
              {(close) => (<>
                <button type="button" role="menuitem" onClick={() => {
                  close(); onCollectionAction(collection.id, 'rename')
                }}><Edit3 /> Rename</button>
                <button type="button" role="menuitem" className="danger" onClick={() => {
                  close(); onCollectionAction(collection.id, 'delete')
                }}><Trash2 /> Delete collection</button>
              </>)}
            </ContextMenu>
          </div>
        ))}
      </nav>

      <SectionTitle label="New saved view" onAdd={onNewSavedView}>Saved views</SectionTitle>
      <nav className="navigator-list">
        {navigation.savedViews.map((view) => (
          <div className="navigator-list-row" key={view.id}>
            <button
              type="button"
              className={location === `saved:${view.id}` ? 'active' : ''}
              onClick={() => onLocation(`saved:${view.id}`)}
            >
              <Clock3 /><span>{view.name}</span>
            </button>
            <ContextMenu
              label={`More actions for ${view.name}`}
              buttonClassName="navigator-more"
              buttonContent={<MoreHorizontal />}
            >
              {(close) => (<>
                <button type="button" role="menuitem" onClick={() => {
                  close(); onSavedViewAction(view.id, 'rename')
                }}><Edit3 /> Rename</button>
                <button type="button" role="menuitem" className="danger" onClick={() => {
                  close(); onSavedViewAction(view.id, 'delete')
                }}><Trash2 /> Delete saved view</button>
              </>)}
            </ContextMenu>
          </div>
        ))}
      </nav>
    </aside>
  )
}
