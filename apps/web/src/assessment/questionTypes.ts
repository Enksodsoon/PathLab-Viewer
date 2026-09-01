import type { AssessmentItem, AssessmentItemType } from './types'

export type QuestionTypeGroup = 'Choice' | 'Text' | 'Pathology' | 'Structure'

export interface QuestionTypeDefinition {
  type: AssessmentItemType
  label: string
  group: QuestionTypeGroup
  supportsScoring: boolean
  create: (newId: () => string) => AssessmentItem
  validate: (item: AssessmentItem) => string[]
}

const promptIssue = (item: AssessmentItem) => String(item.prompt ?? '').trim() ? [] : ['Missing prompt']
type AssessmentOption = NonNullable<AssessmentItem['options']>[number] | string
const optionLabel = (option: AssessmentOption) => typeof option === 'string' ? option : String(option?.label ?? '')
const choiceIssues = (item: AssessmentItem) => [
  ...promptIssue(item),
  ...((item.options?.filter((option) => optionLabel(option).trim()).length ?? 0) >= 2 ? [] : ['Add at least two options']),
]

function baseItem(type: AssessmentItemType, newId: () => string): AssessmentItem {
  const informational = type === 'information' || type === 'section-information'
  return {
    id: newId(),
    type,
    prompt: informational ? 'Information' : 'Untitled question',
    ...(informational ? {} : { points: '1', required: false, answerKey: {} }),
  }
}

export const questionTypeRegistry: QuestionTypeDefinition[] = [
  {
    type: 'multiple-choice', label: 'Multiple choice', group: 'Choice', supportsScoring: true,
    create: (newId) => ({ ...baseItem('multiple-choice', newId), options: [{ id: newId(), label: 'Option 1' }, { id: newId(), label: 'Option 2' }] }),
    validate: choiceIssues,
  },
  {
    type: 'checkboxes', label: 'Checkboxes', group: 'Choice', supportsScoring: true,
    create: (newId) => ({ ...baseItem('checkboxes', newId), options: [{ id: newId(), label: 'Option 1' }, { id: newId(), label: 'Option 2' }] }),
    validate: choiceIssues,
  },
  {
    type: 'dropdown', label: 'Multiple choice', group: 'Choice', supportsScoring: true,
    create: (newId) => ({ ...baseItem('dropdown', newId), options: [{ id: newId(), label: 'Option 1' }, { id: newId(), label: 'Option 2' }] }),
    validate: choiceIssues,
  },
  {
    type: 'rating', label: 'Rating', group: 'Choice', supportsScoring: true,
    create: (newId) => ({ ...baseItem('rating', newId), rating: { min: 1, max: 5, style: 'stars' } }),
    validate: promptIssue,
  },
  { type: 'short-answer', label: 'Text response', group: 'Text', supportsScoring: true, create: (newId) => baseItem('short-answer', newId), validate: promptIssue },
  { type: 'paragraph', label: 'Text response', group: 'Text', supportsScoring: true, create: (newId) => ({ ...baseItem('paragraph', newId), manual: true }), validate: promptIssue },
  { type: 'diagnostic-field', label: 'Diagnostic field', group: 'Pathology', supportsScoring: true, create: (newId) => baseItem('diagnostic-field', newId), validate: promptIssue },
  { type: 'information', label: 'Description', group: 'Structure', supportsScoring: false, create: (newId) => baseItem('information', newId), validate: promptIssue },
  { type: 'section-information', label: 'Description', group: 'Structure', supportsScoring: false, create: (newId) => baseItem('section-information', newId), validate: promptIssue },
]

export const questionTypesByType = Object.fromEntries(questionTypeRegistry.map((definition) => [definition.type, definition])) as Record<AssessmentItemType, QuestionTypeDefinition>

// Keep legacy types readable in existing drafts, while presenting one clear
// authoring choice for equivalent response models.
export const authorableQuestionTypeRegistry = questionTypeRegistry.filter((definition) =>
  !['dropdown', 'paragraph', 'information'].includes(definition.type),
)

export const questionTypeGroups = ['Choice', 'Text', 'Pathology', 'Structure'] as const
