import { FolderPlus } from 'lucide-react'

import type { LibraryFolder } from '../types'

interface Props {
  folders: LibraryFolder[]
  selected: string
  counts: Record<'all' | 'unfiled' | 'shared' | 'processing' | 'failed', number>
  onSelect: (id: string) => void
  onCreate: (parentId: string | null) => void
}

export function LibrarySidebar({ folders, selected, counts, onSelect, onCreate }: Props) {
  const children = (parentId: string | null, depth = 0): React.ReactNode =>
    folders.filter((folder) => folder.parentId === parentId).map((folder) => (
      <div key={folder.id}>
        <button
          type="button"
          className={selected === folder.id ? 'library-nav active' : 'library-nav'}
          style={{ paddingLeft: 14 + depth * 16 }}
          onClick={() => onSelect(folder.id)}
        >
          <span>{folder.name}</span>
        </button>
        {children(folder.id, depth + 1)}
      </div>
    ))
  return <aside className="library-sidebar" aria-label="Slide library">
    {(['all', 'unfiled', 'shared', 'processing', 'failed'] as const).map((id) => (
      <button
        type="button"
        key={id}
        className={selected === id ? 'library-nav active' : 'library-nav'}
        onClick={() => onSelect(id)}
      >
        <span>{id === 'all' ? 'All slides' : id[0].toUpperCase() + id.slice(1)}</span>
        <small>{counts[id]}</small>
      </button>
    ))}
    <div className="sidebar-heading">
      <strong>Folders</strong>
      <button type="button" aria-label="Create folder" onClick={() => onCreate(null)}>
        <FolderPlus size={16} />
      </button>
    </div>
    {children(null)}
  </aside>
}
