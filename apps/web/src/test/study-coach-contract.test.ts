import { describe, expect, it } from 'vitest'

import { studyActionCopy, studyReasonCopy } from '../study/copy'
import { reasonForAction } from '../study/traceSim'
import type { LocalStudyRecord, StudyAction, StudyReason } from '../study/types'

const actions: StudyAction[] = [
  'continue', 'offer_hint', 'ask_confidence', 'ask_source_check', 'retrieve', 'pause',
]
const reasons: StudyReason[] = [
  'CONTINUE_PRACTICE', 'HINT_SUPPORT', 'CHECK_CONFIDENCE', 'VERIFY_SOURCE',
  'REVIEW_PREVIOUS', 'TAKE_BREAK', 'MODEL_SUGGESTION',
]

function record(features: LocalStudyRecord['features']): LocalStudyRecord {
  return { taskId: 'task-1', completedAt: 1, completed: true, features }
}

describe('Study Coach bounded local policy', () => {
  it('has non-empty English and Thai copy for every action and reason', () => {
    for (const action of actions) {
      expect(studyActionCopy('en', action)).not.toBe('')
      expect(studyActionCopy('th', action)).not.toBe('')
    }
    for (const reason of reasons) {
      expect(studyReasonCopy('en', reason)).not.toBe('')
      expect(studyReasonCopy('th', reason)).not.toBe('')
    }
  })

  it('uses the generic reason unless a local deterministic predicate is true', () => {
    const neutral = record([1, 0.1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    expect(reasonForAction('offer_hint', [neutral])).toBe('MODEL_SUGGESTION')
    expect(reasonForAction('pause', [neutral])).toBe('MODEL_SUGGESTION')
    expect(reasonForAction('retrieve', [neutral])).toBe('MODEL_SUGGESTION')

    expect(reasonForAction('offer_hint', [record([0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0])])).toBe('HINT_SUPPORT')
    expect(reasonForAction('pause', [record([0, 0.8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])])).toBe('TAKE_BREAK')
    expect(reasonForAction('retrieve', [record([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])])).toBe('REVIEW_PREVIOUS')
  })

  it('never exposes model probabilities in learner copy', () => {
    for (const locale of ['en', 'th'] as const) {
      const copy = reasons.map((reason) => studyReasonCopy(locale, reason)).join(' ')
      expect(copy).not.toMatch(/probab|logit|percent|%/i)
    }
  })
})
