import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import * as assessmentApi from '../assessment/api'
import type { AssessmentDocument } from '../assessment/types'
import * as assessmentOutbox from '../assessment/outbox'
import { AssessmentStudentPage } from '../pages/AssessmentStudentPage'

vi.mock('../assessment/outbox', () => ({
  listAssessmentOutbox: vi.fn().mockResolvedValue([]),
  removeAssessmentOutbox: vi.fn().mockResolvedValue(undefined),
  enqueueAssessmentResponse: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../assessment/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../assessment/api')>(),
  getAssessmentMetadata: vi.fn().mockResolvedValue({
    publicId: 'practice-1',
    mode: 'practice',
    status: 'open',
    durationSeconds: 3600,
    manifest: { title: 'Lung pathology', items: [], settings: {} },
  }),
  getPracticeBundle: vi.fn().mockResolvedValue({
    publicId: 'practice-1',
    storage: 'browser-local',
    definition: {
      title: 'Lung pathology',
      settings: {},
      items: [{
        id: 'item-1',
        type: 'multiple-choice',
        prompt: 'Most likely diagnosis?',
        points: '1',
        required: true,
        options: [
          { id: 'a', label: 'Adenocarcinoma' },
          { id: 'b', label: 'Reactive change' },
        ],
        answerKey: { optionIds: ['a'] },
      }],
    },
  }),
  searchAssessmentRoster: vi.fn(),
  accessAssessment: vi.fn(),
  startAssessmentAttempt: vi.fn(),
  restoreAssessmentSession: vi.fn(),
  getAssessmentResult: vi.fn(),
}))

afterEach(cleanup)

it('retains the learner session when restoration fails because of connectivity', async () => {
  const key = 'pathlab-assessment-session:interrupted-1'
  sessionStorage.setItem(key, 'synthetic-csrf')
  vi.mocked(assessmentApi.getAssessmentMetadata).mockResolvedValueOnce({
    publicId: 'interrupted-1', mode: 'formative', status: 'open', durationSeconds: 3600,
    closesAt: null, assets: {}, manifest: { title: 'Interrupted assessment', items: [], settings: {} },
  })
  vi.mocked(assessmentApi.restoreAssessmentSession).mockRejectedValueOnce(new TypeError('Failed to fetch'))
  render(<MemoryRouter initialEntries={['/assessment/interrupted-1']}><Routes>
    <Route path="/assessment/:publicId" element={<AssessmentStudentPage />} />
  </Routes></MemoryRouter>)
  expect(await screen.findByText('Connection interrupted. Reconnect and reload to resume.')).toBeVisible()
  expect(sessionStorage.getItem(key)).toBe('synthetic-csrf')
  sessionStorage.removeItem(key)
})

it('does not launch a second restoration after admitting a learner', async () => {
  const manifest: AssessmentDocument = {
    title: 'Admission assessment', settings: {},
    items: [{ id: 'admission-question', type: 'multiple-choice', prompt: 'Choose an answer', points: '1', options: [{ id: 'a', label: 'Answer A' }] }],
  }
  const metadata = vi.mocked(assessmentApi.getAssessmentMetadata).mockResolvedValue({
    publicId: 'admission-1', mode: 'formative', status: 'open', durationSeconds: 3600,
    closesAt: null, assets: {}, manifest,
  })
  const previousCalls = metadata.mock.calls.length
  vi.mocked(assessmentApi.accessAssessment).mockResolvedValueOnce({ csrfToken: 'admission-csrf', kind: 'anonymous', publicId: 'admission-1' })
  let finishStart!: (value: Awaited<ReturnType<typeof assessmentApi.startAssessmentAttempt>>) => void
  let finishRestore!: (value: Awaited<ReturnType<typeof assessmentApi.restoreAssessmentSession>>) => void
  vi.mocked(assessmentApi.startAssessmentAttempt).mockReturnValueOnce(new Promise((resolve) => { finishStart = resolve }))
  const session: Awaited<ReturnType<typeof assessmentApi.restoreAssessmentSession>> = {
    kind: 'anonymous', publicId: 'admission-1', status: 'open', deviceGeneration: 1, manifest,
    attempt: { id: 'admission-attempt', ordinal: 1, status: 'active', startedAt: new Date().toISOString(), responses: [] },
  }
  const restored = vi.mocked(assessmentApi.restoreAssessmentSession).mockReturnValueOnce(new Promise((resolve) => { finishRestore = resolve }))
  const previousRestores = restored.mock.calls.length
  render(<MemoryRouter initialEntries={['/assessment/admission-1']}><Routes>
    <Route path="/assessment/:publicId" element={<AssessmentStudentPage />} />
  </Routes></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: 'Continue anonymously' }))
  expect(screen.getByRole('button', { name: 'Continue anonymously' })).toBeDisabled()
  expect(screen.queryByLabelText('Answer A')).not.toBeInTheDocument()
  await act(async () => { finishStart({ id: 'admission-attempt', ordinal: 1, status: 'active', startedAt: new Date().toISOString() }) })
  await waitFor(() => expect(restored.mock.calls.length - previousRestores).toBe(1))
  expect(screen.queryByLabelText('Answer A')).not.toBeInTheDocument()
  await act(async () => { finishRestore(session) })
  expect(await screen.findByLabelText('Answer A')).toBeVisible()
  expect(metadata.mock.calls.length - previousCalls).toBe(1)
  expect(restored.mock.calls.length - previousRestores).toBe(1)
  sessionStorage.removeItem('pathlab-assessment-session:admission-1')
  metadata.mockReset().mockResolvedValue({ publicId: 'practice-1', mode: 'practice', status: 'open', durationSeconds: 3600, closesAt: null, assets: {}, manifest })
})

it.each([true, false])('does not acknowledge a new answer from an older empty sync (offline=%s)', async (offline) => {
  const key = 'pathlab-assessment-session:sync-race'
  sessionStorage.setItem(key, 'sync-csrf')
  const manifest: AssessmentDocument = { title: 'Sync race', settings: {}, items: [{ id: 'sync-question', type: 'multiple-choice', prompt: 'Choose', points: '1', options: [{ id: 'a', label: 'Queued answer' }] }] }
  vi.mocked(assessmentApi.getAssessmentMetadata).mockResolvedValueOnce({ publicId: 'sync-race', mode: 'formative', status: 'open', durationSeconds: 3600, closesAt: null, assets: {}, manifest })
  vi.mocked(assessmentApi.restoreAssessmentSession).mockResolvedValueOnce({ kind: 'roster', publicId: 'sync-race', status: 'open', deviceGeneration: 1, manifest, attempt: { id: 'sync-attempt', ordinal: 1, status: 'active', startedAt: new Date().toISOString(), responses: [] } })
  let finishRead!: (entries: assessmentOutbox.AssessmentOutboxEntry[]) => void
  let finishWrite!: () => void
  vi.mocked(assessmentOutbox.listAssessmentOutbox).mockReset().mockResolvedValue([]).mockReturnValueOnce(new Promise((resolve) => { finishRead = resolve }))
  vi.mocked(assessmentOutbox.enqueueAssessmentResponse).mockReturnValueOnce(new Promise((resolve) => { finishWrite = resolve }))
  render(<MemoryRouter initialEntries={['/assessment/sync-race']}><Routes><Route path="/assessment/:publicId" element={<AssessmentStudentPage />} /></Routes></MemoryRouter>)
  const answer = await screen.findByLabelText('Queued answer')
  const connection = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(!offline)
  try {
    await userEvent.click(answer)
    await act(async () => { finishRead([]) })
    expect(screen.getByText(offline ? /Offline — queued/ : /Saving…/)).toBeVisible()
    await act(async () => { finishWrite() })
  } finally {
    connection.mockRestore()
    sessionStorage.removeItem(key)
  }
})

it('restores a submitted attempt as awaiting release instead of reopening the answer form', async () => {
  sessionStorage.setItem('pathlab-assessment-session:closed-1', 'synthetic-csrf')
  vi.mocked(assessmentApi.getAssessmentMetadata).mockResolvedValueOnce({
    publicId: 'closed-1', mode: 'formative', status: 'closed', durationSeconds: 3600,
    closesAt: null, assets: {}, manifest: { title: 'Closed assessment', items: [], settings: {} },
  })
  vi.mocked(assessmentApi.restoreAssessmentSession).mockResolvedValueOnce({
    kind: 'roster', publicId: 'closed-1', status: 'closed', deviceGeneration: 1,
    manifest: { title: 'Closed assessment', items: [], settings: {} },
    attempt: { id: 'attempt-1', ordinal: 1, status: 'submitted', startedAt: new Date().toISOString(), responses: [] },
  })
  vi.mocked(assessmentApi.getAssessmentResult).mockRejectedValueOnce(
    new assessmentApi.AssessmentHttpError(404, { code: 'ASSESSMENT_RESULT_NOT_RELEASED' }),
  )
  render(<MemoryRouter initialEntries={['/assessment/closed-1']}><Routes>
    <Route path="/assessment/:publicId" element={<AssessmentStudentPage />} />
  </Routes></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Assessment submitted' })).toBeVisible()
  expect(screen.getByText('Results will appear after your teacher releases them.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Submit assessment' })).not.toBeInTheDocument()
  sessionStorage.removeItem('pathlab-assessment-session:closed-1')
})

it('uses a one-question learner workspace with review and explicit submission', async () => {
  render(
    <MemoryRouter initialEntries={['/assessment/practice-1']}>
      <Routes>
        <Route path="/assessment/:publicId" element={<AssessmentStudentPage />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('heading', { name: 'Lung pathology' })).toBeVisible()
  expect(screen.getByText('Most likely diagnosis?')).toBeVisible()
  await userEvent.click(screen.getByLabelText('Adenocarcinoma'))
  expect(screen.getByRole('button', { name: 'Submit assessment' })).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: 'Mark for review' }))
  expect(screen.getByRole('button', { name: 'Marked for review' })).toHaveAttribute('aria-pressed', 'true')
})

it('requires a canonical roster selection found by name, ID, group, or subgroup', async () => {
  vi.mocked(assessmentApi.getAssessmentMetadata).mockResolvedValueOnce({
    publicId: 'quiz-1',
    mode: 'quiz',
    status: 'open',
    durationSeconds: 3600,
    closesAt: null,
    assets: {},
    manifest: { title: 'Roster quiz', items: [], settings: {} },
  })
  vi.mocked(assessmentApi.searchAssessmentRoster).mockResolvedValueOnce({
    items: [{
      identifier: 's001',
      displayName: 'Somchai Prasert',
      studentId: 's001',
      group: 'Year 3',
      subgroup: 'Blue',
    }],
  })
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/assessment/quiz-1']}>
      <Routes>
        <Route path="/assessment/:publicId" element={<AssessmentStudentPage />} />
      </Routes>
    </MemoryRouter>,
  )

  expect(await screen.findByRole('heading', { name: 'Roster quiz' })).toBeVisible()
  const begin = screen.getByRole('button', { name: 'Begin assessment' })
  expect(begin).toBeDisabled()
  await user.type(screen.getByLabelText('Access code'), 'quiz-code')
  await user.type(screen.getByRole('combobox', { name: 'Find your roster record' }), 'Blue')
  await waitFor(() => expect(assessmentApi.searchAssessmentRoster).toHaveBeenCalledWith('quiz-1', 'Blue', 'quiz-code'))
  await user.click(await screen.findByRole('button', { name: /Somchai Prasert/ }))
  expect(screen.getByText('s001 · Year 3 · Blue')).toBeVisible()
  expect(begin).toBeEnabled()
})
