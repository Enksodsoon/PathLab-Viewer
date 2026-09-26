import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearLocalStudy } from '../study/localStore'
import { StudyPage } from '../pages/StudyPage'

const api = vi.hoisted(() => ({ getStudySession: vi.fn(), redeemStudyInvitation: vi.fn(), submitStudyTask: vi.fn() }))
vi.mock('../study/api', async (original) => ({ ...await original<typeof import('../study/api')>(), ...api }))
vi.mock('../theme/ThemeControl', () => ({ ThemeControl: () => null }))
vi.mock('../components/Brand', () => ({ Brand: () => null }))
vi.mock('../components/OpenSeadragonViewer', () => ({ OpenSeadragonViewer: () => <div /> }))
vi.mock('../study/localStore', () => ({ loadLocalStudy: async () => ({ records: [] }), appendLocalRecord: async () => [], clearLocalStudy: vi.fn(), verifyCachePersistence: vi.fn() }))
const session = {
  pseudonym: 'Learner', course: { id: 'course', title: 'Course', status: 'active', endsAt: null },
  pack: { schema: 'pathlab.study-pack/1', title: 'Pack', slides: [{ viewerSlideId: 'slide', tileSource: '/slide.dzi' }], tasks: [
    { id: 'one', type: 'multiple-choice', slideId: 'slide', prompt: 'First task', options: ['A', 'B'], hints: ['First hint'] },
    { id: 'two', type: 'multiple-choice', slideId: 'slide', prompt: 'Second task', options: ['A', 'B'], hints: [] },
  ] }, progress: [], ai: { eligible: false },
}
beforeEach(() => { api.getStudySession.mockResolvedValue(session); vi.stubGlobal('Worker', class { terminate() {} }) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('remains usable when language storage is denied', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Denied') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Denied') })
  render(<StudyPage />)
  expect(await screen.findByText('First task')).toBeTruthy()
})
it('jumps tasks on the same slide and clears the previous answer and hints', async () => {
  render(<StudyPage />)
  await screen.findByText('First task')
  fireEvent.click(screen.getByLabelText('A'))
  fireEvent.click(screen.getByText('Request faculty hint'))
  fireEvent.click(screen.getByRole('button', { name: /Task 2.*Pending/ }))
  expect(screen.getByText('Second task')).toBeTruthy()
  expect((screen.getByLabelText('A') as HTMLInputElement).checked).toBe(false)
  expect(screen.queryByText('First hint')).toBeNull()
  expect(screen.getByLabelText('3: Probable')).toBeTruthy()
})
it('accepts a pasted issued invitation without inventing a code format', async () => {
  api.getStudySession.mockRejectedValue(new Error('No session'))
  api.redeemStudyInvitation.mockResolvedValue(session)
  render(<StudyPage />)
  const issued = 'Ab_cd-0123456789issuedCODE'
  fireEvent.change(screen.getByLabelText('One-time invitation code'), { target: { value: issued } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Enter Study Mode' }))
  await screen.findByText('First task')
  expect(api.redeemStudyInvitation).toHaveBeenCalledWith(issued)
})
it('falls back from an unavailable local tutor and keeps navigation usable', async () => {
  vi.stubGlobal('Worker', class { constructor() { throw new Error('Workers disabled') } })
  const claim = { id: 'released', text: 'Reviewed explanation', source: { title: 'Source', url: 'https://example.org' } }
  api.submitStudyTask.mockResolvedValue({ status: 'completed', correct: true, attemptCount: 1, explanation: 'Faculty explanation', sources: [], claimIds: ['released'], claims: [claim] })
  render(<StudyPage />)
  await screen.findByText('First task')
  fireEvent.click(screen.getByLabelText('A'))
  fireEvent.click(screen.getByText('Check answer'))
  await screen.findByText('Ask reviewed pathology sources')
  fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'Why?' } })
  fireEvent.click(screen.getByText('Find grounded answer'))
  expect(await screen.findByText(/Local tutor unavailable/)).toBeTruthy()
  expect((screen.getByText('Next task').closest('button') as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: /Task 2.*Pending/ }))
  expect(screen.queryByText('Reviewed explanation')).toBeNull()
  expect(screen.queryByText('Faculty explanation')).toBeNull()
})

it('blocks clearing device data while an answer is awaiting acknowledgment', async () => {
  api.submitStudyTask.mockImplementationOnce(() => new Promise(() => {}))
  render(<StudyPage />)
  await screen.findByText('First task')
  fireEvent.click(screen.getByLabelText('A'))
  fireEvent.click(screen.getByText('Check answer'))
  const clear = screen.getByRole('button', { name: 'Clear this device' })
  expect(clear).toBeDisabled()
  fireEvent.click(clear)
  expect(clearLocalStudy).not.toHaveBeenCalled()
})
