import { useEffect, useRef, useState } from 'react'
import type { FormEvent, SyntheticEvent } from 'react'
import {
  ArrowRight,
  Eye,
  EyeOff,
  KeyRound,
  ShieldCheck,
  X,
} from 'lucide-react'

import { ApiError, changePassword, login, recoverPassword } from '../api'
import darkArtwork from '../assets/auth-histology-solace-dark.webp'
import lightArtwork from '../assets/auth-histology-solace-light.webp'
import { useTheme } from '../theme'
import { Brand } from './Brand'
import { ThemeControl } from './ThemeControl'

const MIN_NEW_PASSWORD_LENGTH = 12
const MAX_NEW_PASSWORD_LENGTH = 128
const RECOVERY_PASSWORD_REQUIREMENTS = '12–128 characters.'
const CHANGE_PASSWORD_REQUIREMENTS = '12–128 characters. Must differ from your current password.'

function hasValidNewPasswordLength(password: string) {
  const codePointLength = Array.from(password).length
  return codePointLength >= MIN_NEW_PASSWORD_LENGTH && codePointLength <= MAX_NEW_PASSWORD_LENGTH
}

function passwordChangeErrorMessage(caught: unknown) {
  if (!(caught instanceof ApiError)) return 'Unable to change the password. Try again.'
  if (caught.code === 'PASSWORD_REUSE') return 'Choose a password different from the current password.'
  if (caught.code === 'CURRENT_PASSWORD_INVALID') return 'Current password is incorrect.'
  if (caught.code === 'INVALID_PASSWORD') return 'New password must contain 12–128 characters.'
  return 'Unable to change the password. Try again.'
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
            <ThemeControl />
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
                  {message ? <p className="form-notice" role="status">{message}</p> : null}
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
                    {passwordVisible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </button>
                  <span className="auth-inline-label" aria-hidden="true">Password</span>
                </div>
              </div>
              {error ? <p className="form-error" role="alert">{error}</p> : null}
              <button className="button primary auth-submit" type="submit" disabled={busy}>
                <span>Enter workspace</span>
                <ArrowRight aria-hidden="true" />
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
                <KeyRound aria-hidden="true" />
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
                      {error ? <p className="form-error" role="alert">{error}</p> : null}
                      <div className="auth-actions">
                        <button className="button auth-secondary" type="button" onClick={returnToLogin} disabled={busy}>Back to sign in</button>
                        <button className="button primary" type="submit" disabled={busy}>Reset password</button>
                      </div>
                    </>
                  )}
              </div>
            </form>
            <footer className="auth-footnote">
              <ShieldCheck aria-hidden="true" />
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

interface AccountSecurityDialogProps {
  open: boolean
  onClose: () => void
  onChanged: () => void
  onAuthenticationRequired: () => void
}

export function AccountSecurityDialog({
  open,
  onClose,
  onChanged,
  onAuthenticationRequired,
}: AccountSecurityDialogProps) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const currentPasswordInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const element = dialog.current
    if (!element) return
    if (open) {
      if (!element.open) element.showModal()
      currentPasswordInput.current?.focus()
    } else if (element.open) {
      element.close()
    }
    return () => {
      if (element.open) element.close()
    }
  }, [open])

  function clearSecrets() {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmation('')
  }

  function close() {
    if (busyRef.current) return
    clearSecrets()
    setError('')
    dialog.current?.close()
    onClose()
  }

  function cancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault()
    close()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current) return
    setError('')
    if (!currentPassword) {
      setError('Enter your current password.')
      clearSecrets()
      return
    }
    if (!hasValidNewPasswordLength(newPassword)) {
      setError('New password must contain 12–128 characters.')
      clearSecrets()
      return
    }
    if (newPassword !== confirmation) {
      setError('New passwords do not match.')
      clearSecrets()
      return
    }
    busyRef.current = true
    setBusy(true)
    try {
      await changePassword(currentPassword, newPassword)
      onChanged()
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onAuthenticationRequired()
      } else {
        setError(passwordChangeErrorMessage(caught))
      }
    } finally {
      clearSecrets()
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog ref={dialog} className="security-dialog" aria-labelledby="security-title" onCancel={cancel}>
      <form
        className="security-form"
        onSubmit={submit}
      >
        <button className="dialog-close" type="button" aria-label="Close account security" onClick={close} disabled={busy}>
          <X size={18} />
        </button>
        <p className="eyebrow">Account security</p>
        <h2 id="security-title">Change password</h2>
        <label>
          Current password
          <input ref={currentPasswordInput} type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" />
        </label>
        <label>
          New password
          <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" aria-describedby="security-password-requirements" />
        </label>
        <p id="security-password-requirements" className="password-requirements">{CHANGE_PASSWORD_REQUIREMENTS}</p>
        <label>
          Confirm new password
          <input type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" />
        </label>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        <div className="auth-actions">
          <button className="button" type="button" onClick={close} disabled={busy}>Cancel</button>
          <button className="button primary" type="submit" disabled={busy}>Change password</button>
        </div>
      </form>
    </dialog>
  )
}
