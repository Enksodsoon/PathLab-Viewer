import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StudyAdminPage } from '../pages/StudyAdminPage'
import { StudyPackAuthoringPage } from '../pages/StudyPackAuthoringPage'
import { ThemeProvider } from '../theme/ThemeProvider'

const api = vi.hoisted(() => ({ listStudyAuthoringSlides: vi.fn(), listStudyPacks: vi.fn(), listStudyCourses: vi.fn(), downloadStudyInvitations: vi.fn(), downloadStudyProgress: vi.fn() }))
const draft = vi.hoisted(() => ({ loadStudyPackDraft: vi.fn(), saveStudyPackDraft: vi.fn() }))
vi.mock('../study/api', async (original) => ({ ...await original<typeof import('../study/api')>(), ...api }))
vi.mock('../study/authoringStore', async (original) => ({ ...await original<typeof import('../study/authoringStore')>(), ...draft }))
const course = { id: 'one', packId: 'pack', title: 'Synthetic course', status: 'preparation', retentionDays: 30, learnerLimit: 2, invitations: 2, redeemed: 1, readiness: { ready: 0, fallback: 0 }, aiMode: 'deterministic', aiActions: {} }
beforeEach(() => {
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  api.listStudyAuthoringSlides.mockResolvedValue([{ id: 'slide', displayName: 'Synthetic slide', sha256: 'a'.repeat(64) }])
  api.listStudyPacks.mockResolvedValue([])
  api.listStudyCourses.mockResolvedValue([course])
  draft.loadStudyPackDraft.mockResolvedValue(null)
  draft.saveStudyPackDraft.mockResolvedValue(undefined)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals() })
function mount(page: ReactNode) { render(<MemoryRouter><ThemeProvider>{page}</ThemeProvider></MemoryRouter>) }
it.each(['id', 'prompt'])('rejects trimmed blank %s in the shared Add task handler', async (field) => {
  mount(<StudyPackAuthoringPage />)
  await screen.findByText('Drafts stay on this device until publication.')
  fireEvent.change(screen.getByRole('textbox', { name: 'Task ID' }), { target: { value: field === 'id' ? '   ' : 'task-one' } })
  fireEvent.change(screen.getByRole('textbox', { name: 'Prompt' }), { target: { value: field === 'prompt' ? '   ' : 'Valid prompt' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Task ID and prompt are required.')
  expect(screen.getByRole('textbox', { name: 'Task ID' })).toHaveValue(field === 'id' ? '   ' : 'task-one')
  expect(screen.queryByText('Task added. Preview again after every edit.')).not.toBeInTheDocument()
})
it('accepts a nonblank task and trims its stored ID and prompt', async () => {
  mount(<StudyPackAuthoringPage />)
  await screen.findByText('Drafts stay on this device until publication.')
  fireEvent.change(screen.getByRole('textbox', { name: 'Task ID' }), { target: { value: ' task-one ' } })
  fireEvent.change(screen.getByRole('textbox', { name: 'Prompt' }), { target: { value: ' Valid prompt ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add task' }))
  expect(screen.getByText('Valid prompt')).toBeVisible()
  await waitFor(() => expect(draft.saveStudyPackDraft).toHaveBeenCalledWith(expect.objectContaining({ tasks: [expect.objectContaining({ id: 'task-one', prompt: 'Valid prompt' })] })))
})
it('disables exhausted invitation controls with a valid zero range and remaining capacity', async () => {
  mount(<StudyAdminPage />)
  await screen.findByText('Synthetic course')
  const count = screen.getByRole('spinbutton', { name: 'New codes' })
  expect(count).toBeDisabled()
  expect(count).toHaveAttribute('min', '0')
  expect(count).toHaveAttribute('max', '0')
  expect(count).toHaveValue(0)
  expect(screen.getByText('0 invitation slots remaining.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Export one-time codes' })).toBeDisabled()
  expect(api.downloadStudyInvitations).not.toHaveBeenCalled()
})
it('reports progress download failure while keeping the admin course visible', async () => {
  api.downloadStudyProgress.mockRejectedValueOnce(new Error('Progress download denied'))
  mount(<StudyAdminPage />)
  await screen.findByText('Synthetic course')
  fireEvent.click(screen.getByRole('button', { name: 'Export pseudonymous progress' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Progress download denied')
  expect(screen.getByText('Synthetic course')).toBeVisible()
})
it('downloads authenticated CSV as a file and rejects a failed response without navigating', async () => {
  const original = await vi.importActual<typeof import('../study/api')>('../study/api')
  const fetch = vi.fn().mockResolvedValueOnce(new Response('pseudonym,task_id\r\n', { status: 200 })).mockResolvedValueOnce(new Response('', { status: 403 }))
  vi.stubGlobal('fetch', fetch)
  const create = vi.fn(() => 'blob:synthetic')
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { expect(this.download).toBe('study-progress-course-one.csv'); expect(this.href).toBe('blob:synthetic') })
  const path = window.location.href
  await original.downloadStudyProgress('course-one')
  expect(fetch).toHaveBeenCalledWith('/api/v1/admin/study/courses/course-one/progress.csv', expect.objectContaining({ credentials: 'same-origin' }))
  expect(click).toHaveBeenCalledOnce()
  expect(create).toHaveBeenCalledOnce()
  expect(revoke).toHaveBeenCalledWith('blob:synthetic')
  await expect(original.downloadStudyProgress('course-one')).rejects.toMatchObject({ status: 403 })
  expect(click).toHaveBeenCalledOnce()
  expect(window.location.href).toBe(path)
})
