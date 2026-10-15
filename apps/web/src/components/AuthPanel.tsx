import {
  ArrowRight,
  Eye,
  EyeSlash,
  Key,
} from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, login, recoverPassword } from '../api'
import darkDesktopArtwork from '../assets/auth-login-dark-desktop-v2.png'
import darkMobileArtwork from '../assets/auth-login-dark-mobile-v2.png'
import darkTabletLandscapeArtwork from '../assets/auth-login-dark-tablet-landscape-v2.png'
import darkTabletPortraitArtwork from '../assets/auth-login-dark-tablet-portrait-v2.png'
import lightDesktopArtwork from '../assets/auth-login-light-desktop-v2.png'
import lightMobileArtwork from '../assets/auth-login-light-mobile-v2.png'
import lightTabletLandscapeArtwork from '../assets/auth-login-light-tablet-landscape-v2.png'
import lightTabletPortraitArtwork from '../assets/auth-login-light-tablet-portrait-v2.png'
import { ThemeControl } from '../theme/ThemeControl'
import { useTheme } from '../theme/ThemeProvider'
import { Brand } from './Brand'
import { Loader } from './Loader'
import { StatusMessage } from './StatusMessage'

const MIN_NEW_PASSWORD_LENGTH = 12
const MAX_NEW_PASSWORD_LENGTH = 128
const RECOVERY_PASSWORD_REQUIREMENTS = '12–128 characters.'
const artworkByTheme = {
  dark: {
    desktop: darkDesktopArtwork,
    mobile: darkMobileArtwork,
    tabletLandscape: darkTabletLandscapeArtwork,
    tabletPortrait: darkTabletPortraitArtwork,
  },
  light: {
    desktop: lightDesktopArtwork,
    mobile: lightMobileArtwork,
    tabletLandscape: lightTabletLandscapeArtwork,
    tabletPortrait: lightTabletPortraitArtwork,
  },
}

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
  const artwork = artworkByTheme[resolvedTheme]
  const [mode, setMode] = useState<'login' | 'recover'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [message, setMessage] = useState(notice)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [focusModality, setFocusModality] = useState<'keyboard' | 'pointer'>('keyboard')
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
    <main
      className={`auth-shell${mode === 'recover' ? ' recovery-mode' : ''}`}
      data-focus-modality={focusModality}
      onPointerDownCapture={() => setFocusModality('pointer')}
      onKeyDownCapture={(event) => {
        if (event.key === 'Tab') setFocusModality('keyboard')
      }}
    >
      <picture className="auth-visual" aria-hidden="true">
        <source media="(max-width: 767px) and (orientation: portrait)" srcSet={artwork.mobile} />
        <source media="(max-width: 1439px) and (orientation: portrait)" srcSet={artwork.tabletPortrait} />
        <source media="(max-width: 1439px)" srcSet={artwork.tabletLandscape} />
        <img
          alt=""
          className="auth-visual-image"
          data-auth-artwork-theme={resolvedTheme}
          decoding="async"
          fetchPriority="high"
          onError={(event) => { event.currentTarget.style.visibility = 'hidden' }}
          onLoad={(event) => { event.currentTarget.style.visibility = 'visible' }}
          src={artwork.desktop}
        />
      </picture>
      <div className="auth-layout">
        <header className="auth-panel-header">
          <Brand variant="library" />
          <ThemeControl compact />
        </header>
        <section className="auth-form-panel" aria-labelledby="auth-form-title">
          <div className="auth-form-wrap">
            <div className="auth-visual-content">
              <h1 id="auth-visual-title">A closer perspective.</h1>
              <p className="auth-visual-caption">Slide library, reimagined</p>
            </div>
            <form
              className="login-card auth-solace-card"
              aria-labelledby="auth-form-title"
              onSubmit={mode === 'login' ? submitLogin : submitRecovery}
            >
              <div className="auth-form-content" key={mode}>
                <header className="auth-form-heading">
                  <h2 id="auth-form-title" ref={formHeadingRef} tabIndex={-1}>
                    {mode === 'login' ? 'Welcome back' : 'Recover administrator access'}
                  </h2>
                  <p>
                    {mode === 'login'
                      ? 'Sign in to continue to your slides'
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
                      placeholder="admin"
                    />
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
                          placeholder="••••••••"
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
                    {error ? <StatusMessage tone="error">{error}</StatusMessage> : null}
                    <button className="button primary auth-submit" type="submit" aria-label={busy ? 'Signing in…' : 'Enter workspace'} disabled={busy}>
                      {busy ? (
                        <Loader label="Signing in…" size="small" inline />
                      ) : (
                        <ArrowRight aria-hidden="true" color="currentColor" />
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
                      <span>Forgot password?</span>
                    </button>
                  </>
                ) : (
                  <>
                    <p className="recovery-help">Ask your PathLab administrator for a 15-minute recovery code, then enter it below.</p>
                    <details className="recovery-operator-details">
                      <summary>PathLab administrator instructions</summary>
                      <code className="recovery-command">docker compose -f deploy/compose.yaml exec api pathlab-admin issue-recovery-code --username admin</code>
                    </details>
                    <div className="auth-field">
                      <label htmlFor="recovery-code">Recovery code</label>
                      <div className="auth-input">
                        <input id="recovery-code" value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} autoComplete="one-time-code" />
                      </div>
                    </div>
                    <div className="auth-field">
                      <label htmlFor="recovery-new-password">New password</label>
                      <div className="auth-input">
                        <input id="recovery-new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" aria-describedby="recovery-password-requirements" />
                      </div>
                    </div>
                    <p id="recovery-password-requirements" className="password-requirements">{RECOVERY_PASSWORD_REQUIREMENTS}</p>
                    <div className="auth-field">
                      <label htmlFor="recovery-confirm-password">Confirm new password</label>
                      <div className="auth-input">
                        <input id="recovery-confirm-password" type="password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" />
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
          </div>
        </section>
      </div>
    </main>
  )
}
