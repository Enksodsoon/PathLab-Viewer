import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'

import { ApiError, getLibraryNavigation, logout } from '../api'
import { AccountSecurityDialog } from '../components/AccountSecurityDialog'
import { Loader } from '../components/Loader'
import { AppRail } from '../components/library/AppRail'
import { getStoredRailExpanded, persistRailExpanded } from '../components/library/libraryShellPreferences'
import type { LibraryNavigation } from '../types'
import '../library.css'
import './assessment.css'

const AuthPanel = lazy(() => import('../components/AuthPanel').then((module) => ({ default: module.AuthPanel })))

const EMPTY_NAVIGATION: LibraryNavigation = {
  capabilities: { classroom: false, study: false, assessment: false },
  counts: { all: 0, unfiled: 0, shared: 0, processing: 0, failed: 0, trash: 0 },
  folders: [],
  collections: [],
  savedViews: [],
  storage: { usedBytes: 0, usableBytes: 0, effectiveCapacityBytes: 0 },
}

export function AssessmentShell() {
  const navigate = useNavigate()
  const navigatorButtonRef = useRef<HTMLButtonElement>(null)
  const [navigation, setNavigation] = useState(EMPTY_NAVIGATION)
  const [authorized, setAuthorized] = useState<boolean | null>(null)
  const [authRevision, setAuthRevision] = useState(0)
  const [railExpanded, setRailExpanded] = useState(getStoredRailExpanded)
  const [securityOpen, setSecurityOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    void getLibraryNavigation().then((value) => {
      if (cancelled) return
      setNavigation(value)
      setAuthorized(true)
    }).catch((caught) => {
      if (cancelled) return
      if (caught instanceof ApiError && caught.status === 401) setAuthorized(false)
      else {
        setError('PathLab navigation could not load. Teacher Studio remains available with limited navigation.')
        setAuthorized(true)
      }
    })
    return () => { cancelled = true }
  }, [authRevision])

  async function signOut() {
    if (signingOut) return
    setSigningOut(true)
    try {
      await logout()
      setAuthorized(false)
      setNavigation(EMPTY_NAVIGATION)
    } catch {
      setError('Sign-out failed. Try again.')
    } finally {
      setSigningOut(false)
    }
  }

  if (signingOut) return <Loader label="Signing out…" size="large" fullscreen />
  if (authorized === false) return <Suspense fallback={<Loader label="Opening secure sign in…" size="large" fullscreen />}><AuthPanel notice="" onSuccess={() => { setAuthorized(null); setAuthRevision((current) => current + 1) }} /></Suspense>
  if (authorized === null) return <Loader label="Loading Teacher Studio…" size="large" fullscreen />

  return <div className={`library-shell assessment-app-shell ${railExpanded ? 'rail-expanded' : ''}`} data-layout="canvas-focus">
    <AppRail
      expanded={railExpanded}
      isInert={false}
      navigatorOpen={false}
      navigatorButtonRef={navigatorButtonRef}
      storage={navigation.storage}
      activeDestination="assessment"
      onToggleExpanded={() => setRailExpanded((current) => { persistRailExpanded(!current); return !current })}
      onNavigator={() => navigate('/admin')}
      onUpload={() => navigate('/admin?action=upload')}
      onStudy={navigation.capabilities?.study ? () => navigate('/admin/study') : undefined}
      onAssessment={() => navigate('/admin/assessments')}
      onStorage={() => navigate('/admin?location=storage')}
      storageActive={false}
      onSecurity={() => setSecurityOpen(true)}
      onSignOut={() => void signOut()}
    />
    <main className="library-main assessment-workspace" data-canvas-region="content">
      {error ? <p className="assessment-shell-error" role="alert">{error}</p> : null}
      <Outlet />
    </main>
    <AccountSecurityDialog
      open={securityOpen}
      onClose={() => setSecurityOpen(false)}
      onChanged={() => setSecurityOpen(false)}
      onAuthenticationRequired={() => { setSecurityOpen(false); setAuthorized(false) }}
    />
  </div>
}
