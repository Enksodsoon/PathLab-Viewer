import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import { deterministicOrder, orderSectionRuns, pruneUnreachableResponses, reachableSectionIds } from '../assessment/learnerRuntime'
import type { AssessmentDocumentV2, AssessmentItem } from '../assessment/types'
import { AssessmentLearnerQuestion } from '../components/assessment/AssessmentLearnerQuestion'

afterEach(cleanup)

const items = ['q-a', 'q-b', 'q-c', 'q-d'].map((id) => ({ id, type: 'short-answer' as const, prompt: id, points: '1' }))

it('matches the backend SHA-256 order and preserves information boundaries', async () => {
  expect((await deterministicOrder(items, 'seed-42')).map((item) => item.id)).toEqual(['q-b', 'q-d', 'q-c', 'q-a'])
  const information: AssessmentItem = { id: 'info', type: 'section-information', prompt: 'Read this' }
  const ordered = await orderSectionRuns([items[0], items[1], information, items[2], items[3]], 'seed-42', true)
  expect(ordered[2]).toBe(information)
  expect(new Set(ordered.slice(0, 2).map((item) => item.id))).toEqual(new Set(['q-a', 'q-b']))
})

it('recalculates section routing and removes unreachable response state', () => {
  const document: AssessmentDocumentV2 = {
    schema: 'pathlab.assessment/2', title: 'Branching', presentation: {}, settings: {},
    sections: [
      { id: 'start', title: 'Start', items: [{ id: 'route', type: 'multiple-choice', prompt: 'Route', options: [{ id: 'yes', label: 'Yes' }, { id: 'no', label: 'No' }], answerKey: { optionIds: ['yes'] }, routing: { rules: [{ when: { operator: 'equals', optionId: 'yes' }, goToSectionId: 'finish' }], defaultSectionId: 'remediation' } }] },
      { id: 'remediation', title: 'Review', items: [{ id: 'review-answer', type: 'short-answer', prompt: 'Review' }] },
      { id: 'finish', title: 'Finish', items: [{ id: 'final-answer', type: 'short-answer', prompt: 'Finish' }] },
    ],
  }
  const responses = { route: { optionId: 'yes' }, 'review-answer': { text: 'stale' }, 'final-answer': { text: 'kept' } }
  expect(reachableSectionIds(document, responses)).toEqual(['start', 'finish'])
  expect(pruneUnreachableResponses(document, responses)).toEqual({ route: { optionId: 'yes' }, 'final-answer': { text: 'kept' } })
})

it('renders dropdown, Other, and every approved rating style accessibly', async () => {
  const user = userEvent.setup()
  const changed = vi.fn()
  const { rerender } = render(<AssessmentLearnerQuestion item={{ id: 'drop', type: 'dropdown', prompt: 'Diagnosis', options: [{ id: 'a', label: 'Adenocarcinoma' }, { id: 'b', label: 'Other' }] }} value={{}} onChange={changed} />)
  await user.selectOptions(screen.getByRole('combobox', { name: 'Answer' }), 'a')
  expect(changed).toHaveBeenCalledWith({ optionId: 'a' })
  for (const style of ['numbers', 'stars', 'hearts', 'thumbs-up'] as const) {
    rerender(<AssessmentLearnerQuestion item={{ id: 'rating', type: 'rating', prompt: 'Confidence', rating: { min: 1, max: 3, style } }} value={{}} onChange={changed} />)
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    await user.click(screen.getByRole('radio', { name: 'Rating 3' }))
    expect(changed).toHaveBeenLastCalledWith({ value: 3 })
  }
})
