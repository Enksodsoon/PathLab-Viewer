import {
  BookOpen,
  KeyRound,
  Layers3,
  LogOut,
  Share2,
  Trash2,
  Upload,
} from 'lucide-react'

interface AppRailProps {
  location: string
  onLocation: (location: string) => void
  onUpload: () => void
  onSecurity: () => void
  onSignOut: () => void
}

export function AppRail({
  location,
  onLocation,
  onUpload,
  onSecurity,
  onSignOut,
}: AppRailProps) {
  const destination = location === 'trash'
    ? 'trash'
    : location === 'shared'
      ? 'shared'
      : 'library'

  return (
    <aside className="library-app-rail" aria-label="Product navigation">
      <div className="library-brand" aria-label="PathLab Viewer">
        <Layers3 aria-hidden="true" />
        <span>PathLab Viewer</span>
      </div>
      <nav>
        <button
          type="button"
          className={destination === 'library' ? 'active' : ''}
          aria-current={destination === 'library' ? 'page' : undefined}
          onClick={() => onLocation('all')}
        >
          <BookOpen />
          <span>Library</span>
        </button>
        <button type="button" onClick={onUpload}>
          <Upload />
          <span>Uploads</span>
        </button>
        <button
          type="button"
          className={destination === 'shared' ? 'active' : ''}
          aria-current={destination === 'shared' ? 'page' : undefined}
          onClick={() => onLocation('shared')}
        >
          <Share2 />
          <span>Shared</span>
        </button>
        <button
          type="button"
          className={destination === 'trash' ? 'active' : ''}
          aria-current={destination === 'trash' ? 'page' : undefined}
          onClick={() => onLocation('trash')}
        >
          <Trash2 />
          <span>Trash</span>
        </button>
        <button type="button" className="account-action account-start" onClick={onSecurity}>
          <KeyRound />
          <span>Account</span>
        </button>
        <button type="button" className="account-action" onClick={onSignOut}>
          <LogOut />
          <span>Sign out</span>
        </button>
      </nav>
    </aside>
  )
}
