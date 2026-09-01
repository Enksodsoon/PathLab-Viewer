export type AssessmentItemType =
  | 'multiple-choice'
  | 'checkboxes'
  | 'short-answer'
  | 'paragraph'
  | 'diagnostic-field'
  | 'information'

export interface AssessmentItem {
  id: string
  type: AssessmentItemType
  prompt: string
  points?: string
  required?: boolean
  options?: Array<{ id: string; label: string }>
  answerKey?: Record<string, unknown>
  slideId?: string
  feedback?: { correct?: string; incorrect?: string }
}

export interface AssessmentDocument {
  title: string
  items: AssessmentItem[]
  settings: {
    mode?: 'practice' | 'formative' | 'quiz'
    shuffleQuestions?: boolean
  }
}

export interface AssessmentDraft {
  id: string
  title: string
  status: 'draft' | 'archived'
  revision: number
  document: AssessmentDocument
}

export interface AssessmentDraftList {
  items: AssessmentDraft[]
  total: number
}
