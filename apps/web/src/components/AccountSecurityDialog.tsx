import { X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, SyntheticEvent } from 'react'

import { ApiError, changePassword } from '../api'
import { Loader } from './Loader'
import { StatusMessage } from './StatusMessage'

const MIN_NEW_PASSWORD_LENGTH = 12
const MAX_NEW_PASSWORD_LENGTH = 128
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
      <form className="security-form" onSubmit={submit}>
        <button className="dialog-close" type="button" aria-label="Close account security" onClick={close} disabled={busy}>
          <X aria-hidden="true" color="currentColor" size={18} />
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
        {error ? <StatusMessage tone="error">{error}</StatusMessage> : null}
        <div className="auth-actions">
          <button className="button" type="button" onClick={close} disabled={busy}>Cancel</button>
          <button className="button primary" type="submit" disabled={busy}>
            {busy
              ? <Loader label="Changing password…" size="small" inline />
              : 'Change password'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
