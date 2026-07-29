import { CheckCircle, Desktop, ShieldCheck } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ApiError, approveDesktopPairing } from '../api'
import './DesktopConnectPage.css'

export function DesktopConnectPage() {
  const [params] = useSearchParams()
  const code = (params.get('code') ?? '').toUpperCase()
  const [state, setState] = useState<'ready' | 'working' | 'approved' | 'signin' | 'error'>(
    /^[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(code) ? 'ready' : 'error',
  )

  const approve = async () => {
    setState('working')
    try {
      await approveDesktopPairing(code)
      setState('approved')
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setState('signin')
      } else {
        setState('error')
      }
    }
  }

  return <main className="desktop-connect-page">
    <section className="desktop-connect-card" aria-labelledby="desktop-connect-title">
      <span className="desktop-connect-mark" aria-hidden="true"><Desktop /></span>
      <p className="desktop-connect-eyebrow">PathLab Viewer</p>
      <h1 id="desktop-connect-title">Connect PathLab Forge</h1>
      <p className="desktop-connect-copy">
        Approve this local desktop to prepare private slide uploads and synchronize annotations.
        Viewer remains authoritative for library state and permissions.
      </p>
      <div className="desktop-connect-code">
        <span>Verification code</span>
        <strong>{code || 'Invalid code'}</strong>
      </div>
      <div className="desktop-connect-scopes">
        <ShieldCheck aria-hidden="true" />
        <span>Private ingest · private slide preview · annotation sync</span>
      </div>
      {state === 'approved'
        ? <div className="desktop-connect-success" role="status">
          <CheckCircle aria-hidden="true" />
          <span><strong>Forge connected</strong>You can return to the desktop app.</span>
        </div>
        : null}
      {state === 'signin'
        ? <div className="desktop-connect-message" role="alert">
          Sign in to Viewer, then reopen this verification link.
        </div>
        : null}
      {state === 'error'
        ? <div className="desktop-connect-message" role="alert">
          This pairing code is invalid, expired, or already used.
        </div>
        : null}
      {state !== 'approved'
        ? <button
          className="desktop-connect-approve"
          type="button"
          disabled={state === 'working' || !code}
          onClick={() => void approve()}
        >
          {state === 'working' ? 'Approving…' : 'Approve this Forge device'}
        </button>
        : null}
      <Link className="desktop-connect-back" to="/admin">Back to slide library</Link>
    </section>
  </main>
}
