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
  manual?: boolean
  scoring?: {
    partialCredit?: boolean
    pointTolerance?: number
    rectangleIou?: number
  }
}

export type DiagnosticSelection =
  | { kind: 'point'; x: number; y: number }
  | { kind: 'rectangle'; x: number; y: number; width: number; height: number }

export interface EligibleAssessmentSlide {
  id: string
  publicId: string
  displayName: string
  tileSource: string
  thumbnail: string | null
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
  courseId?: string | null
  courseName?: string | null
  classId?: string | null
  className?: string | null
}

export interface AssessmentDraftList {
  items: AssessmentDraft[]
  total: number
}
