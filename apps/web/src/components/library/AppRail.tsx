import {
  Brain,
  CaretDoubleLeft,
  CaretDoubleRight,
  ChalkboardTeacher,
  HardDrives,
  Key,
  List,
  SignOut,
  UploadSimple,
} from '@phosphor-icons/react'
import type { Ref } from 'react'

import type { LibraryNavigation } from '../../types'
import { Brand } from '../Brand'

interface AppRailProps {
  expanded: boolean
  isInert: boolean
  navigatorOpen: boolean
  navigatorButtonRef: Ref<HTMLButtonElement>
  storage: LibraryNavigation['storage']
  onToggleExpanded: () => void
  onNavigator: () => void
  onUpload: () => void
  onClassroom?: () => void
  onStudy?: () => void
  onStorage: () => void
  storageActive: boolean
  onSecurity: () => void
  onSignOut: () => void
}

export function AppRail({
  expanded,
  isInert,
  navigatorOpen,
  navigatorButtonRef,
  storage,
  onToggleExpanded,
  onNavigator,
  onUpload,
  onClassroom,
  onStudy,
  onStorage,
  storageActive,
  onSecurity,
  onSignOut,
}: AppRailProps) {
  const capacity = storage.effectiveCapacityBytes
  const remainingPercent = capacity > 0
    ? Math.round((storage.usableBytes / capacity) * 100)
    : 0
  const storageLabel = capacity > 0
    ? `${formatBytes(storage.usableBytes)} available`
    : 'Storage unavailable'

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
          <List aria-hidden="true" />
          <span>Slide library</span>
        </button>
        <button type="button" aria-label="Upload" onClick={onUpload}>
          <UploadSimple aria-hidden="true" />
          <span>Upload</span>
        </button>
        {onClassroom && (
          <button type="button" aria-label="Classroom" onClick={onClassroom}>
            <ChalkboardTeacher aria-hidden="true" />
            <span>Classroom</span>
          </button>
        )}
        {onStudy && (
          <button type="button" aria-label="Study Coach" onClick={onStudy}>
            <Brain aria-hidden="true" />
            <span>Study Coach</span>
          </button>
        )}
      </nav>
      <div className="library-rail-utilities" aria-label="Account actions">
        <button
          type="button"
          className={`library-storage-meter ${storageActive ? 'active' : ''}`}
          aria-label={`Open storage, ${storageLabel}`}
          aria-current={storageActive ? 'page' : undefined}
          title={`${storageLabel}. Open managed storage.`}
          onClick={onStorage}
        >
          <HardDrives className="library-storage-icon" aria-hidden="true" />
          <div className="library-storage-copy">
            <span>Storage</span>
            <strong>{storageLabel}</strong>
          </div>
          <div
            className="library-storage-track"
            role="meter"
            aria-label="Usable storage remaining"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={remainingPercent}
            aria-valuetext={storageLabel}
          >
            <span style={{ width: `${remainingPercent}%` }} />
          </div>
        </button>
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

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
