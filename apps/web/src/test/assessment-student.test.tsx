import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import * as assessmentApi from '../assessment/api'
import { AssessmentStudentPage } from '../pages/AssessmentStudentPage'

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
}))

afterEach(cleanup)

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
