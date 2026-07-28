import {
  CaretDoubleLeft,
  CaretDoubleRight,
  Key,
  List as Menu,
  SignOut,
  UploadSimple as Upload,
} from '@phosphor-icons/react'
import type { Ref } from 'react'

import { Brand } from '../Brand'

interface AppRailProps {
  expanded: boolean
  isInert: boolean
  navigatorOpen: boolean
  navigatorButtonRef: Ref<HTMLButtonElement>
  onToggleExpanded: () => void
  onNavigator: () => void
  onUpload: () => void
  onSecurity: () => void
  onSignOut: () => void
}

export function AppRail({
  expanded,
  isInert,
  navigatorOpen,
  navigatorButtonRef,
  onToggleExpanded,
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
      <button
        type="button"
        className="library-rail-toggle"
        aria-label={expanded ? 'Collapse navigation rail' : 'Expand navigation rail'}
        aria-expanded={expanded}
        onClick={onToggleExpanded}
      >
        {expanded ? <CaretDoubleLeft aria-hidden="true" /> : <CaretDoubleRight aria-hidden="true" />}
        <span>{expanded ? 'Collapse' : 'Expand'}</span>
      </button>
      <nav className="library-rail-primary" aria-label="Library destinations">
        <button
          ref={navigatorButtonRef}
          type="button"
          className={navigatorOpen ? 'active mobile-navigator-toggle' : 'mobile-navigator-toggle'}
          aria-label="Slide library"
          aria-controls="library-navigator"
          aria-expanded={navigatorOpen}
          onClick={onNavigator}
        >
          <Menu aria-hidden="true" />
          <span>Slide library</span>
        </button>
        <button type="button" aria-label="Upload" onClick={onUpload}>
          <Upload aria-hidden="true" />
          <span>Upload</span>
        </button>
      </nav>
      <div className="library-rail-utilities" aria-label="Account actions">
        <button type="button" aria-label="Account" onClick={onSecurity}>
          <Key aria-hidden="true" />
          <span>Account</span>
        </button>
        <button type="button" aria-label="Sign out" onClick={onSignOut}>
          <SignOut aria-hidden="true" />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  )
}
