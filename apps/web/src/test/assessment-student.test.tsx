import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

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
