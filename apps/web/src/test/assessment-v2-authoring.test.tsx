import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import type { AssessmentDocumentV2 } from '../assessment/types'
import { AssessmentSectionCanvas } from '../components/assessment/AssessmentSectionCanvas'

const fixture: AssessmentDocumentV2 = {
  schema: 'pathlab.assessment/2',
  title: 'Thoracic pathology',
  description: 'A sectioned diagnostic assessment.',
  presentation: { preset: 'standard', showProgress: true, showSectionTitles: true },
  settings: { mode: 'formative' },
  sections: [
    {
      id: 'section-a',
      title: 'Invasive tumours',
      description: 'Review the slide before answering.',
      items: [
        {
          id: 'question-a',
          type: 'multiple-choice',
          prompt: 'Which diagnosis best fits the glands?',
          required: true,
          points: '1',
          options: [
            { id: 'option-a', label: 'Adenocarcinoma' },
            { id: 'option-b', label: 'Reactive atypia' },
          ],
          answerKey: { optionIds: ['option-a'] },
        },
      ],
    },
  ],
}

function Harness() {
  const [document, setDocument] = useState(fixture)
  return <AssessmentSectionCanvas
    document={document}
    onDocumentChange={(update) => setDocument((current) => update(current))}
    onImport={vi.fn()}
    onPreview={vi.fn()}
  />
}

afterEach(cleanup)

it('authors, reorders, duplicates, deletes, and restores true sections', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  expect(screen.getByRole('heading', { name: 'Questions' })).toBeVisible()
  expect(screen.getByText('1 sections · 1 questions · Ready to review')).toBeVisible()
  expect(screen.getAllByText('Required').find((element) => element.classList.contains('assessment-required-badge'))).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Add section' }))
  expect(screen.getByRole('textbox', { name: 'Section 2 title' })).toHaveValue('Section 2')
  await user.clear(screen.getByRole('textbox', { name: 'Section 2 title' }))
  await user.type(screen.getByRole('textbox', { name: 'Section 2 title' }), 'Clinical correlation')

  await user.click(screen.getByRole('button', { name: 'Duplicate section 1' }))
  expect(screen.getByDisplayValue('Invasive tumours copy')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Delete section 2' }))
  expect(screen.queryByDisplayValue('Invasive tumours copy')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Undo' }))
  expect(screen.getByDisplayValue('Invasive tumours copy')).toBeVisible()

  const reorder = screen.getByRole('button', { name: 'Reorder section 1' })
  reorder.focus()
  fireEvent.keyDown(reorder, { key: 'ArrowDown', altKey: true })
  expect(screen.getByRole('textbox', { name: 'Section 1 title' })).toHaveValue('Invasive tumours copy')
})

it('provides complete stable choice editing and section search', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  const navigator = screen.getByRole('complementary', { name: 'Question navigator' })
  await user.type(within(navigator).getByPlaceholderText('Search sections and questions'), 'glands')
  expect(within(navigator).getByText('Which diagnosis best fits the glands?')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Duplicate option 1' }))
  expect(screen.getByDisplayValue('Adenocarcinoma copy')).toBeVisible()
  expect(screen.getAllByRole('radio')).toHaveLength(3)
  await user.click(screen.getByRole('button', { name: 'Delete option 1' }))
  expect(screen.queryByDisplayValue('Adenocarcinoma')).not.toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: 'Allow Other' }))
  await user.click(screen.getByRole('checkbox', { name: 'Shuffle choices' }))
  expect(screen.getByRole('checkbox', { name: 'Allow Other' })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: 'Shuffle choices' })).toBeChecked()
})

it('adds dropdown and rating items with the approved rating controls', async () => {
  const user = userEvent.setup()
  render(<Harness />)

  await user.selectOptions(screen.getByRole('combobox', { name: 'Question type for section 1' }), 'rating')
  await user.click(screen.getByRole('button', { name: 'Add' }))
  expect(screen.getByRole('combobox', { name: 'Style' })).toHaveValue('stars')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Maximum' }), '10')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Style' }), 'hearts')
  expect(screen.getAllByText('♥')).toHaveLength(10)
})
