import { useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { X } from 'lucide-react'

import { ApiError, changePassword, login, recoverPassword } from '../api'
import { Brand } from './Brand'

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

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
      onSuccess()
    } catch {
      setError('Sign-in failed. Check your credentials.')
    } finally {
      setPassword('')
      setBusy(false)
    }
  }

  async function submitRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setMessage('')
    if (newPassword !== confirmation) {
      setError('New passwords do not match.')
      setRecoveryCode('')
      setNewPassword('')
      setConfirmation('')
      return
    }
    setBusy(true)
    try {
      await recoverPassword(username, recoveryCode, newPassword)
      setMode('login')
      setMessage('Password reset. Sign in with your new password.')
    } catch (caught) {
      setError(caught instanceof ApiError && caught.code === 'INVALID_PASSWORD'
        ? 'Use a password between 12 and 128 characters.'
        : 'Invalid or expired recovery code.')
    } finally {
      setRecoveryCode('')
      setNewPassword('')
      setConfirmation('')
      setBusy(false)
    }
  }

  function returnToLogin() {
    setMode('login')
    setError('')
    setMessage('')
    setRecoveryCode('')
    setNewPassword('')
    setConfirmation('')
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={mode === 'login' ? submitLogin : submitRecovery}>
        <Brand />
        <div>
          <p className="eyebrow">Administrator access</p>
          <h1>{mode === 'login' ? 'Manage whole-slide images' : 'Recover your account'}</h1>
        </div>
        {message ? <p className="form-notice" role="status">{message}</p> : null}
        <label>
          Username
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        {mode === 'login' ? (
          <>
            <label>
              Password
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
            </label>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button className="button primary" type="submit" disabled={busy}>Sign in</button>
            <button
              className="auth-link"
              type="button"
              onClick={() => {
                setMode('recover')
                setPassword('')
                setError('')
                setMessage('')
              }}
            >
              Forgot password?
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
              <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" />
            </label>
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
    </main>
  )
}

interface AccountSecurityDialogProps {
  open: boolean
  onClose: () => void
  onChanged: () => void
}

export function AccountSecurityDialog({ open, onClose, onChanged }: AccountSecurityDialogProps) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const currentPasswordInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) currentPasswordInput.current?.focus()
  }, [open])

  if (!open) return null

  function clearSecrets() {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmation('')
  }

  function close() {
    clearSecrets()
    setError('')
    onClose()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === 'Escape' && !busy) close()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (newPassword !== confirmation) {
      setError('New passwords do not match.')
      clearSecrets()
      return
    }
    setBusy(true)
    try {
      await changePassword(currentPassword, newPassword)
      onChanged()
    } catch (caught) {
      setError(caught instanceof ApiError && caught.code === 'PASSWORD_REUSE'
        ? 'Choose a password different from the current password.'
        : 'Password change failed. Check the current password and requirements.')
    } finally {
      clearSecrets()
      setBusy(false)
    }
  }

  return (
    <div className="dialog-backdrop">
      <form
        className="security-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="security-title"
        onSubmit={submit}
        onKeyDown={handleKeyDown}
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
          <input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" />
        </label>
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
    </div>
  )
}
