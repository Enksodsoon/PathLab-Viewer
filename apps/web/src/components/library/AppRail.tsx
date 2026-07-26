import {
  CircleDashed,
  Key,
  List as Menu,
  SignOut as LogOut,
  SquaresFour as Grid2X2,
  Trash as Trash2,
  UploadSimple as Upload,
  XCircle as CircleX,
} from '@phosphor-icons/react'
import type { Ref } from 'react'

import { Brand } from '../Brand'
import { ThemeControl } from '../../theme/ThemeControl'

interface AppRailProps {
  location: string
  isInert: boolean
  navigatorOpen: boolean
  navigatorButtonRef: Ref<HTMLButtonElement>
  onLocation: (location: string) => void
  onNavigator: () => void
  onUpload: () => void
  onSecurity: () => void
  onSignOut: () => void
}

export function AppRail({
  location,
  isInert,
  navigatorOpen,
  navigatorButtonRef,
  onLocation,
  onNavigator,
  onUpload,
  onSecurity,
  onSignOut,
}: AppRailProps) {
  return (
    <aside
      className="library-app-rail"
      aria-label="Product navigation"
      aria-hidden={isInert || undefined}
      data-canvas-region="icon-rail"
      inert={isInert || undefined}
    >
      <div className="library-rail-brand">
        <Brand variant="library" />
      </div>
      <nav className="library-rail-primary" aria-label="Library destinations">
        <button
          type="button"
          className={location === 'all' ? 'active' : ''}
          aria-current={location === 'all' ? 'page' : undefined}
          onClick={() => onLocation('all')}
        >
          <Grid2X2 aria-hidden="true" />
          <span>All slides</span>
        </button>
        <button
          ref={navigatorButtonRef}
          type="button"
          className="mobile-navigator-toggle"
          aria-label="Open library navigator"
          aria-controls="library-navigator"
          aria-expanded={navigatorOpen}
          onClick={onNavigator}
        >
          <Menu aria-hidden="true" />
          <span>Navigator</span>
        </button>
        <button type="button" onClick={onUpload}>
          <Upload aria-hidden="true" />
          <span>Upload</span>
        </button>
        <button
          type="button"
          className={location === 'processing' ? 'active' : ''}
          aria-current={location === 'processing' ? 'page' : undefined}
          onClick={() => onLocation('processing')}
        >
          <CircleDashed aria-hidden="true" />
          <span>Processing</span>
        </button>
        <button
          type="button"
          className={location === 'failed' ? 'active' : ''}
          aria-current={location === 'failed' ? 'page' : undefined}
          onClick={() => onLocation('failed')}
        >
          <CircleX aria-hidden="true" />
          <span>Failed</span>
        </button>
        <button
          type="button"
          className={location === 'trash' ? 'active' : ''}
          aria-current={location === 'trash' ? 'page' : undefined}
          onClick={() => onLocation('trash')}
        >
          <Trash2 aria-hidden="true" />
          <span>Trash</span>
        </button>
      </nav>
      <div className="library-rail-utilities">
        <ThemeControl compact className="library-theme-control" />
        <button type="button" className="account-action account-start" onClick={onSecurity}>
          <Key aria-hidden="true" />
          <span>Account</span>
        </button>
        <button type="button" className="account-action" onClick={onSignOut}>
          <LogOut aria-hidden="true" />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  )
}
