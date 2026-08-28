export type AssessmentItemType =
  | 'multiple-choice'
  | 'checkboxes'
  | 'dropdown'
  | 'rating'
  | 'short-answer'
  | 'paragraph'
  | 'diagnostic-field'
  | 'information'
  | 'section-information'

export type AssessmentSchema = 'pathlab.assessment/1' | 'pathlab.assessment/2'

export interface AssessmentOption {
  id: string
  label: string
}

export interface AssessmentItem {
  id: string
  type: AssessmentItemType
  prompt: string
  points?: string
  required?: boolean
  options?: AssessmentOption[]
  answerKey?: Record<string, unknown>
  slideId?: string
  feedback?: { correct?: string; incorrect?: string }
  helpText?: string
  teacherNotes?: string
  manual?: boolean
  allowOther?: boolean
  shuffleOptions?: boolean
  rating?: {
    min: 1
    max: 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10
    style: 'numbers' | 'stars' | 'hearts' | 'thumbs-up'
  }
  validation?: {
    required?: boolean
    minimumLength?: number
    maximumLength?: number
    minimumValue?: number
    maximumValue?: number
    pattern?: string
    message?: string
  }
  media?: {
    kind: 'slide-thumbnail'
    slideId: string
    assetPath?: string
    alt?: string
  }
  education?: {
    objective?: string
    competency?: string
    difficulty?: 'introductory' | 'intermediate' | 'advanced'
    tags?: string[]
  }
  routing?: {
    rules?: Array<{
      when: {
        operator: 'equals' | 'contains' | 'answered' | 'not-answered' | 'greater-or-equal'
        optionId?: string
        value?: string | number
      }
      goToSectionId: string
    }>
    defaultSectionId?: string
  }
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

export interface AssessmentDocumentV1 {
  schema?: 'pathlab.assessment/1'
  title: string
  description?: string
  items: AssessmentItem[]
  settings: {
    mode?: 'practice' | 'formative' | 'quiz'
    shuffleQuestions?: boolean
  }
}

export interface AssessmentSection {
  id: string
  title: string
  description?: string
  slideId?: string
  viewport?: { x: number; y: number; width: number; height: number }
  items: AssessmentItem[]
}

export interface AssessmentDocumentV2 {
  schema: 'pathlab.assessment/2'
  title: string
  description?: string
  sections: AssessmentSection[]
  presentation: {
    preset?: 'compact' | 'standard' | 'focus'
    showProgress?: boolean
    showSectionTitles?: boolean
  }
  settings: {
    mode?: 'practice' | 'formative' | 'quiz'
    shuffleQuestions?: boolean
  }
  release?: {
    timing?: 'immediate' | 'manual'
    showScore?: boolean
    showAnswers?: boolean
    showAuthoredFeedback?: boolean
    showManualFeedback?: boolean
    showAnnotations?: boolean
  }
}

export type AssessmentDocument = AssessmentDocumentV1 | AssessmentDocumentV2

export function isAssessmentV2(document: AssessmentDocument): document is AssessmentDocumentV2 {
  return document.schema === 'pathlab.assessment/2'
}

export function assessmentItems(document: AssessmentDocument): AssessmentItem[] {
  return isAssessmentV2(document)
    ? document.sections.flatMap((section) => section.items)
    : document.items
}

export function replaceAssessmentItems(
  document: AssessmentDocument,
  items: AssessmentItem[],
): AssessmentDocument {
  if (!isAssessmentV2(document)) return { ...document, items }
  const sectionByItem = new Map(
    document.sections.flatMap((section) => section.items.map((item) => [item.id, section.id] as const)),
  )
  const fallbackSection = document.sections[0]?.id
  return {
    ...document,
    sections: document.sections.map((section) => ({
      ...section,
      items: items.filter((item) => (sectionByItem.get(item.id) ?? fallbackSection) === section.id),
    })),
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
