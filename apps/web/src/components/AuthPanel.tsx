import { useGSAP } from '@gsap/react'
import {
  ArrowRight,
  Eye,
  EyeSlash,
  Key,
  LockKey,
  ShieldCheck,
  UserCircle,
} from '@phosphor-icons/react'
import gsap from 'gsap'
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, login, recoverPassword } from '../api'
import { ThemeControl } from '../theme/ThemeControl'
import { Brand } from './Brand'

const MIN_NEW_PASSWORD_LENGTH = 12
const MAX_NEW_PASSWORD_LENGTH = 128
const RECOVERY_PASSWORD_REQUIREMENTS = '12–128 characters.'

function hasValidNewPasswordLength(password: string) {
  const codePointLength = Array.from(password).length
  return codePointLength >= MIN_NEW_PASSWORD_LENGTH && codePointLength <= MAX_NEW_PASSWORD_LENGTH
}

interface AuthPanelProps {
  onSuccess: () => void
  notice?: string
}

export function AuthPanel({ onSuccess, notice = '' }: AuthPanelProps) {
  const [mode, setMode] = useState<'login' | 'recover'>('login')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [message, setMessage] = useState(notice)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [passwordVisible, setPasswordVisible] = useState(false)
  const busyRef = useRef(false)
  const page = useRef<HTMLElement>(null)

  useGSAP(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined

    const timeline = gsap.timeline({
      defaults: { duration: 0.82, ease: 'expo.out' },
    })
    timeline
      .from('[data-auth-entrance="brand"]', {
        autoAlpha: 0,
        filter: 'blur(8px)',
        y: 18,
        clearProps: 'opacity,visibility,filter,transform',
      })
      .from('[data-auth-entrance="story"]', {
        autoAlpha: 0,
        clipPath: 'inset(0 0 28% 0)',
        y: 32,
        clearProps: 'opacity,visibility,clipPath,transform',
      }, '-=0.58')
      .from('[data-auth-entrance="form"]', {
        autoAlpha: 0,
        filter: 'blur(7px)',
        x: 28,
        clearProps: 'opacity,visibility,filter,transform',
      }, '-=0.64')

    return () => timeline.kill()
  }, { scope: page })

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      await login(username, password)
      onSuccess()
    } catch {
      setError('Sign-in failed. Check your credentials.')
    } finally {
      setPassword('')
      busyRef.current = false
      setBusy(false)
    }
  }

  async function submitRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current) return
    setError('')
    setMessage('')
    if (!hasValidNewPasswordLength(newPassword)) {
      setError('New password must contain 12–128 characters.')
      setRecoveryCode('')
      setNewPassword('')
      setConfirmation('')
      return
    }
    if (newPassword !== confirmation) {
      setError('New passwords do not match.')
      setRecoveryCode('')
      setNewPassword('')
      setConfirmation('')
      return
    }
    busyRef.current = true
    setBusy(true)
    try {
      await recoverPassword(username, recoveryCode, newPassword)
      setMode('login')
      setMessage('Password reset. Sign in with your new password.')
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 429) {
        setError('Too many attempts. Try again later.')
      } else {
        setError(caught instanceof ApiError && caught.code === 'INVALID_PASSWORD'
          ? 'Use a password between 12 and 128 characters.'
          : 'Invalid or expired recovery code.')
      }
    } finally {
      setRecoveryCode('')
      setNewPassword('')
      setConfirmation('')
      busyRef.current = false
      setBusy(false)
    }
  }

  function returnToLogin() {
    if (busyRef.current) return
    setMode('login')
    setError('')
    setMessage('')
    setRecoveryCode('')
    setNewPassword('')
    setConfirmation('')
  }

  return (
    <main ref={page} className={`login-page${mode === 'recover' ? ' recovery-mode' : ''}`}>
      <section className="auth-story" aria-labelledby="auth-story-title">
        <div className="auth-story-header" data-auth-entrance="brand">
          <Brand variant="library" />
          <ThemeControl compact className="auth-theme-control" />
        </div>
        <div className="auth-story-copy" data-auth-entrance="story">
          <h1 id="auth-story-title">
            <span data-auth-line>See the</span>
            <span data-auth-line>whole picture.</span>
          </h1>
          <p>A focused workspace for reviewing, organizing, and sharing whole-slide images.</p>
        </div>
      </section>

      <section className="auth-panel" data-auth-entrance="form">
        <form
          className="login-card"
          aria-labelledby="auth-form-title"
          onSubmit={mode === 'login' ? submitLogin : submitRecovery}
        >
          <header className="auth-form-heading">
            <h2 id="auth-form-title">
              {mode === 'login' ? 'Administrator sign in' : 'Recover administrator access'}
            </h2>
            <p>
              {mode === 'login'
                ? 'Continue to your secure slide library.'
                : 'Use a server-issued recovery code to restore access.'}
            </p>
          </header>
          {message ? <p className="form-notice" role="status">{message}</p> : null}
          <div className="auth-field">
            <label htmlFor="auth-username">Username</label>
            <div className="auth-input">
              <UserCircle aria-hidden="true" color="currentColor" />
              <input
                id="auth-username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
              />
            </div>
          </div>
          {mode === 'login' ? (
            <>
              <div className="auth-field">
                <label htmlFor="auth-password">Password</label>
                <div className="auth-input">
                  <LockKey aria-hidden="true" color="currentColor" />
                  <input
                    id="auth-password"
                    type={passwordVisible ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete="current-password"
                  />
                  <button
                    className="password-visibility"
                    type="button"
                    aria-label={passwordVisible ? 'Hide password' : 'Show password'}
                    onClick={() => setPasswordVisible((visible) => !visible)}
                  >
                    {passwordVisible
                      ? <EyeSlash aria-hidden="true" color="currentColor" />
                      : <Eye aria-hidden="true" color="currentColor" />}
                  </button>
                </div>
              </div>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
              <button className="button primary auth-submit" type="submit" disabled={busy}>
                <span>Enter workspace</span>
                <ArrowRight aria-hidden="true" color="currentColor" />
              </button>
              <div className="auth-separator"><span>or</span></div>
              <button
                className="auth-link"
                type="button"
                onClick={() => {
                  if (busyRef.current) return
                  setMode('recover')
                  setPassword('')
                  setPasswordVisible(false)
                  setError('')
                  setMessage('')
                }}
                disabled={busy}
              >
                <Key aria-hidden="true" color="currentColor" />
                <span>Recover administrator access</span>
              </button>
            </>
          ) : (
            <>
              <p className="recovery-help">Generate a 15-minute code on the PathLab server, then enter it below.</p>
              <code className="recovery-command">docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin</code>
              <label>
                Recovery code
                <input value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} autoComplete="one-time-code" />
              </label>
              <label>
                New password
                <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" aria-describedby="recovery-password-requirements" />
              </label>
              <p id="recovery-password-requirements" className="password-requirements">{RECOVERY_PASSWORD_REQUIREMENTS}</p>
              <label>
                Confirm new password
                <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" />
              </label>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
              <div className="auth-actions">
                <button className="button" type="button" onClick={returnToLogin} disabled={busy}>Back to sign in</button>
                <button className="button primary" type="submit" disabled={busy}>Reset password</button>
              </div>
            </>
          )}
        </form>
        <footer className="auth-footnote">
          <ShieldCheck aria-hidden="true" color="currentColor" />
          <span>Private by design. Built for whole-slide imaging.</span>
        </footer>
      </section>
    </main>
  )
}
