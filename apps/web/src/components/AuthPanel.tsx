import {
  ArrowRight,
  Eye,
  EyeSlash,
  Key,
  ShieldCheck,
} from '@phosphor-icons/react'
import { Brand, ThemeControl, useTheme } from '@enksodsoon/pathlab-ui'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, login, recoverPassword } from '../api'
import darkArtwork from '../assets/auth-histology-solace-dark.webp'
import lightArtwork from '../assets/auth-histology-solace-light.webp'
import { Loader } from './Loader'
import { StatusMessage } from './StatusMessage'

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
  const { resolvedTheme } = useTheme()
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
  const formHeadingRef = useRef<HTMLHeadingElement>(null)
  const previousMode = useRef(mode)

  useEffect(() => {
    if (previousMode.current === mode) return
    previousMode.current = mode
    formHeadingRef.current?.focus()
  }, [mode])

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
    <main className={`auth-shell${mode === 'recover' ? ' recovery-mode' : ''}`}>
      <div className="auth-layout">
        <section className="auth-form-panel" aria-labelledby="auth-form-title">
          <header className="auth-panel-header">
            <Brand variant="library" />
            <ThemeControl compact />
          </header>
          <div className="auth-form-wrap">
            <form
              className="login-card auth-solace-card"
              aria-labelledby="auth-form-title"
              onSubmit={mode === 'login' ? submitLogin : submitRecovery}
            >
              <div className="auth-form-content" key={mode}>
                <header className="auth-form-heading">
                  <h2 id="auth-form-title" ref={formHeadingRef} tabIndex={-1}>
                    {mode === 'login' ? 'Administrator sign in' : 'Recover administrator access'}
                  </h2>
                  <p>
                    {mode === 'login'
                      ? 'Continue to your secure slide library.'
                      : 'Use a server-issued recovery code to restore access.'}
                  </p>
                </header>
                {message ? <StatusMessage tone="info">{message}</StatusMessage> : null}
                <div className="auth-field">
                  <label htmlFor="auth-username">Username</label>
                  <div className="auth-input">
                    <input
                      id="auth-username"
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      autoComplete="username"
                    />
                    <span className="auth-inline-label" aria-hidden="true">Username</span>
                  </div>
                </div>
                {mode === 'login' ? (
                  <>
                    <div className="auth-field">
                      <label htmlFor="auth-password">Password</label>
                      <div className="auth-input">
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
                        <span className="auth-inline-label" aria-hidden="true">Password</span>
                      </div>
                    </div>
                    {error ? <StatusMessage tone="error">{error}</StatusMessage> : null}
                    <button className="button primary auth-submit" type="submit" disabled={busy}>
                      {busy ? (
                        <Loader label="Signing in…" size="small" inline />
                      ) : (
                        <>
                          <span>Enter workspace</span>
                          <ArrowRight aria-hidden="true" color="currentColor" />
                        </>
                      )}
                    </button>
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
                    <div className="auth-field">
                      <label htmlFor="recovery-code">Recovery code</label>
                      <div className="auth-input">
                        <input id="recovery-code" value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} autoComplete="one-time-code" />
                        <span className="auth-inline-label" aria-hidden="true">Recovery code</span>
                      </div>
                    </div>
                    <div className="auth-field">
                      <label htmlFor="recovery-new-password">New password</label>
                      <div className="auth-input">
                        <input id="recovery-new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" aria-describedby="recovery-password-requirements" />
                        <span className="auth-inline-label" aria-hidden="true">New password</span>
                      </div>
                    </div>
                    <p id="recovery-password-requirements" className="password-requirements">{RECOVERY_PASSWORD_REQUIREMENTS}</p>
                    <div className="auth-field">
                      <label htmlFor="recovery-confirm-password">Confirm new password</label>
                      <div className="auth-input">
                        <input id="recovery-confirm-password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" />
                        <span className="auth-inline-label" aria-hidden="true">Confirm password</span>
                      </div>
                    </div>
                    {error ? <StatusMessage tone="error">{error}</StatusMessage> : null}
                    <div className="auth-actions">
                      <button className="button auth-secondary" type="button" onClick={returnToLogin} disabled={busy}>Back to sign in</button>
                      <button className="button primary" type="submit" disabled={busy}>
                        {busy
                          ? <Loader label="Resetting password…" size="small" inline />
                          : 'Reset password'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </form>
            <footer className="auth-footnote">
              <ShieldCheck aria-hidden="true" color="currentColor" />
              <span>Private by design. Built for whole-slide imaging.</span>
            </footer>
          </div>
        </section>

        <section className="auth-visual" aria-labelledby="auth-visual-title">
          <img
            alt=""
            aria-hidden="true"
            className="auth-visual-image"
            data-auth-artwork-theme={resolvedTheme}
            decoding="async"
            fetchPriority="high"
            src={resolvedTheme === 'dark' ? darkArtwork : lightArtwork}
          />
          <div className="auth-visual-grain" aria-hidden="true" />
          <div className="auth-visual-content">
            <h1 id="auth-visual-title">
              See the whole
              <br />
              picture.
            </h1>
            <p className="auth-visual-caption">Built for detail. Designed for focus.</p>
          </div>
        </section>
      </div>
    </main>
  )
}
