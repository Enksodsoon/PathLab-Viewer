import { expect, it } from 'vitest'

import { scorePractice } from '../assessment/practiceScoring'
import type { AssessmentDocument } from '../assessment/types'

it('scores Practice locally with exact answers, geometry, and manual nulls', () => {
  const document: AssessmentDocument = {
    title: 'Practice', settings: {}, items: [
      { id: 'mcq', type: 'multiple-choice', prompt: 'Diagnosis?', points: '1', answerKey: { optionIds: ['a'] } },
      { id: 'text', type: 'short-answer', prompt: 'Name it', points: '1', answerKey: { variants: ['Adenocarcinoma'] } },
      { id: 'field', type: 'diagnostic-field', prompt: 'Mark it', points: '2', answerKey: { regions: [{ kind: 'point', x: .5, y: .5 }], diagnoses: ['Adenocarcinoma'] } },
      { id: 'manual', type: 'paragraph', prompt: 'Explain', points: '3', manual: true },
    ],
  }
  const score = scorePractice(document, {
    mcq: { optionId: 'a' }, text: { text: '  ADENOCARCINOMA ' },
    field: { selection: { kind: 'point', x: .51, y: .5 }, diagnosis: 'adenocarcinoma' },
    manual: { text: 'Irregular glands' },
  })
  expect(score).toEqual({ points: 4, maximumPoints: 7, breakdown: { mcq: 1, text: 1, field: 2, manual: null } })
})
