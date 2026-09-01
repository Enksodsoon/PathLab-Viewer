import {
  CaretDoubleLeft,
  CaretDoubleRight,
  ChalkboardTeacher,
  Brain,
  ClipboardText,
  HardDrives,
  Key,
  List as Menu,
  SignOut,
  UploadSimple as Upload,
} from '@phosphor-icons/react'
import type { Ref } from 'react'

export interface ProductRailStorage {
  usableBytes: number
  effectiveCapacityBytes: number
}

export interface PathLabProductRailProps {
  productName: 'Viewer' | 'Forge'
  expanded: boolean
  isInert?: boolean
  navigatorOpen: boolean
  navigatorButtonRef?: Ref<HTMLButtonElement>
  storage: ProductRailStorage
  onToggleExpanded: () => void
  onNavigator: () => void
  onUpload: () => void
  onClassroom?: () => void
  onStudy?: () => void
  onAssessment?: () => void
  onStorage?: () => void
  storageActive?: boolean
  onSecurity: () => void
  onSignOut: () => void
  uploadLabel?: string
  classroomLabel?: string
  studyLabel?: string
  assessmentLabel?: string
  accountLabel?: string
  signOutLabel?: string
}

export function PathLabProductRail({
  productName,
  expanded,
  isInert = false,
  navigatorOpen,
  navigatorButtonRef,
  storage,
  onToggleExpanded,
  onNavigator,
  onUpload,
  onClassroom,
  onStudy,
  onAssessment,
  onStorage,
  storageActive = false,
  onSecurity,
  onSignOut,
  uploadLabel = 'Upload',
  classroomLabel = 'Classroom',
  studyLabel = 'Study Coach',
  assessmentLabel = 'Assessment',
  accountLabel = 'Account',
  signOutLabel = 'Sign out',
}: PathLabProductRailProps) {
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
        <PathLabBrand productName={productName} />
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
        <button type="button" aria-label={uploadLabel} onClick={onUpload}>
          <Upload aria-hidden="true" />
          <span>{uploadLabel}</span>
        </button>
        {onClassroom ? (
          <button type="button" aria-label={classroomLabel} onClick={onClassroom}>
            <ChalkboardTeacher aria-hidden="true" />
            <span>{classroomLabel}</span>
          </button>
        ) : null}
        {onStudy ? (
          <button type="button" aria-label={studyLabel} onClick={onStudy}>
            <Brain aria-hidden="true" />
            <span>{studyLabel}</span>
          </button>
        ) : null}
        {onAssessment ? (
          <button type="button" aria-label={assessmentLabel} onClick={onAssessment}>
            <ClipboardText aria-hidden="true" />
            <span>{assessmentLabel}</span>
          </button>
        ) : null}
      </nav>
      <div className="library-rail-utilities" aria-label="Account actions">
        {onStorage ? (
          <button
            type="button"
            className={`library-storage-meter ${storageActive ? 'active' : ''}`}
            aria-label={`Open storage, ${storageLabel}`}
            aria-current={storageActive ? 'page' : undefined}
            title={`${storageLabel}. Open managed storage.`}
            onClick={onStorage}
          >
            <StorageMeter storageLabel={storageLabel} remainingPercent={remainingPercent} />
          </button>
        ) : (
          <section
            className="library-storage-meter"
            aria-label={`Storage, ${storageLabel}`}
            title={`${storageLabel}. Safe capacity after active conversion reservations.`}
          >
            <StorageMeter storageLabel={storageLabel} remainingPercent={remainingPercent} />
          </section>
        )}
        <button type="button" aria-label={accountLabel} onClick={onSecurity}>
          <Key aria-hidden="true" />
          <span>{accountLabel}</span>
        </button>
        <button type="button" aria-label={signOutLabel} onClick={onSignOut}>
          <SignOut aria-hidden="true" />
          <span>{signOutLabel}</span>
        </button>
      </div>
    </aside>
  )
}

function StorageMeter({
  storageLabel,
  remainingPercent,
}: {
  storageLabel: string
  remainingPercent: number
}) {
  return (
    <>
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
    </>
  )
}

function PathLabBrand({ productName }: { productName: string }) {
  return (
    <div className="brand brand-library" aria-label={`PathLab ${productName}`}>
      <span className="brand-mark brand-mark-layers">
        <svg aria-hidden="true" color="currentColor" fill="none" viewBox="0 0 32 32">
          <path d="M4.5 10.1 16 4.4l11.5 5.7L16 15.8 4.5 10.1Z" fill="currentColor" opacity=".34" />
          <path d="m4.5 15.9 11.5 5.7 11.5-5.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
          <path d="m4.5 21.7 11.5 5.7 11.5-5.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" />
        </svg>
      </span>
      <span>PathLab</span>
      <span className="brand-product">{productName}</span>
    </div>
  )
}

function formatBytes(bytes: number) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}
