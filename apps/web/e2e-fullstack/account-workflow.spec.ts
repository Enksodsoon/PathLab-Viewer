import { expect, test } from './qa-test'
import { signIn } from '../e2e-live/capacity-helpers'
import { execFileSync } from 'node:child_process'
import { fault } from './fixture-faults'

test('synthetic account validates, changes password, signs out and signs back in', async ({ page }) => {
  const username = process.env.PATHLAB_E2E_USERNAME!
  const original = process.env.PATHLAB_E2E_PASSWORD!
  const replacement = `${original}-QA`
  await signIn(page, username, original)
  await page.getByRole('button', { name: 'Account', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Change password', exact: true })
  const submit = dialog.getByRole('button', { name: 'Change password', exact: true })
  await submit.click()
  await expect(dialog.getByText('Enter your current password.', { exact: true })).toBeVisible()
  await dialog.getByLabel('Current password', { exact: true }).fill(original)
  await dialog.getByLabel('New password', { exact: true }).fill('short')
  await submit.click()
  await expect(dialog.getByText('New password must contain 12–128 characters.', { exact: true })).toBeVisible()
  await dialog.getByLabel('Current password', { exact: true }).fill(original)
  await dialog.getByLabel('New password', { exact: true }).fill(replacement)
  await dialog.getByLabel('Confirm new password', { exact: true }).fill(`${replacement}-mismatch`)
  await submit.click()
  await expect(dialog.getByText('New passwords do not match.', { exact: true })).toBeVisible()
  async function change(current: string, next: string) {
    await dialog.getByLabel('Current password', { exact: true }).fill(current)
    await dialog.getByLabel('New password', { exact: true }).fill(next)
    await dialog.getByLabel('Confirm new password', { exact: true }).fill(next)
    await submit.click()
    await expect(page.getByText('Password changed. Sign in again.', { exact: true })).toBeVisible()
  }
  await change(original, replacement)
  try {
    await signIn(page, username, replacement)
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
    await signIn(page, username, replacement)
  } finally {
    await page.getByRole('button', { name: 'Account', exact: true }).click()
    await change(replacement, original)
  }
  await signIn(page, username, original)
  fault('expire-session', username)
  await page.reload()
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible()
  const code = execFileSync(process.env.PATHLAB_E2E_PYTHON!, ['-c',
    'from wsi_viewer.cli import main; main()', 'issue-recovery-code', '--username', username],
  { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
  await page.getByRole('button', { name: 'Recover administrator access', exact: true }).click()
  await page.getByLabel('Username', { exact: true }).fill(username)
  await page.getByLabel('Recovery code', { exact: true }).fill(code)
  await page.getByLabel('New password', { exact: true }).fill(original)
  await page.getByLabel('Confirm new password', { exact: true }).fill(original)
  await page.getByRole('button', { name: /Reset password/ }).click()
  await signIn(page, username, original)
})
