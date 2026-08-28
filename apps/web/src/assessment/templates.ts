import type { AssessmentDocumentV2, AssessmentItem, AssessmentItemType } from './types'

export const ASSESSMENT_TEMPLATE_VERSION = 1

export interface AssessmentTemplate {
  id: string
  name: string
  description: string
  version: number
  document: AssessmentDocumentV2
}

const presentation: AssessmentDocumentV2['presentation'] = {
  preset: 'standard', showProgress: true, showSectionTitles: true,
}

function item(id: string, type: AssessmentItemType, prompt: string): AssessmentItem {
  if (type === 'multiple-choice' || type === 'dropdown') {
    return {
      id, type, prompt, points: '1', required: true,
      options: [{ id: `${id}-a`, label: 'Option 1' }, { id: `${id}-b`, label: 'Option 2' }],
      answerKey: { optionIds: [`${id}-a`] },
    }
  }
  if (type === 'rating') return { id, type, prompt, points: '1', required: true, rating: { min: 1, max: 5, style: 'stars' }, answerKey: {} }
  return { id, type, prompt, points: '1', required: true, answerKey: {}, manual: type === 'paragraph' }
}

function template(id: string, name: string, description: string, sections: AssessmentDocumentV2['sections']): AssessmentTemplate {
  return {
    id, name, description, version: ASSESSMENT_TEMPLATE_VERSION,
    document: {
      schema: 'pathlab.assessment/2', title: name, description, sections,
      presentation, settings: { mode: 'formative' },
      release: { timing: 'manual', showScore: true, showAnswers: false, showAuthoredFeedback: false, showManualFeedback: true },
    },
  }
}

export const assessmentTemplates: AssessmentTemplate[] = [
  template('diagnostic-checkpoint', 'Diagnostic checkpoint', 'A focused slide-linked knowledge and diagnosis check.', [
    { id: 'diagnostic-section', title: 'Observe and diagnose', items: [item('diagnostic-choice', 'multiple-choice', 'Which feature best supports your diagnosis?'), item('diagnostic-answer', 'diagnostic-field', 'Mark the diagnostic region and enter your diagnosis.')] },
  ]),
  template('slide-seminar', 'Slide seminar', 'A guided case discussion with observations before synthesis.', [
    { id: 'seminar-observe', title: 'Observe', items: [item('seminar-observation', 'paragraph', 'Describe the key morphologic findings.')] },
    { id: 'seminar-synthesise', title: 'Synthesize', items: [item('seminar-diagnosis', 'short-answer', 'State the most likely diagnosis.')] },
  ]),
  template('confidence-check', 'Confidence check', 'A compact answer and confidence pair.', [
    { id: 'confidence-section', title: 'Answer and reflect', items: [item('confidence-answer', 'dropdown', 'Select your diagnosis.'), item('confidence-rating', 'rating', 'How confident are you?')] },
  ]),
  template('branching-remediation', 'Branching remediation', 'A two-path formative check with targeted remediation.', [
    { id: 'branching-check', title: 'Checkpoint', items: [{ ...item('branching-choice', 'multiple-choice', 'Select the best interpretation.'), routing: { rules: [{ when: { operator: 'equals', optionId: 'branching-choice-b' }, goToSectionId: 'branching-review' }], defaultSectionId: 'branching-finish' } }] },
    { id: 'branching-review', title: 'Review', items: [{ id: 'branching-info', type: 'section-information', prompt: 'Review the teaching point, then try the final check.' }] },
    { id: 'branching-finish', title: 'Finish', items: [item('branching-final', 'short-answer', 'Summarize the distinguishing feature.')] },
  ]),
  template('exit-ticket', 'Exit ticket', 'A brief end-of-session knowledge and reflection check.', [
    { id: 'exit-section', title: 'Before you leave', items: [item('exit-answer', 'short-answer', 'Name one finding you can now recognize.'), item('exit-reflection', 'paragraph', 'What remains unclear?')] },
  ]),
]

export interface PasteParseResult {
  items: AssessmentItem[]
  errors: Array<{ line: number; message: string }>
}

export function parseAssessmentPaste(source: string): PasteParseResult {
  const items: AssessmentItem[] = []
  const errors: PasteParseResult['errors'] = []
  const lines = source.split(/\r?\n/)
  lines.forEach((raw, index) => {
    const value = raw.trim()
    if (!value) return
    const [kind, prompt, ...options] = value.split('|').map((part) => part.trim())
    const type = ({ mc: 'multiple-choice', dropdown: 'dropdown', rating: 'rating', short: 'short-answer', paragraph: 'paragraph' } as const)[kind.toLocaleLowerCase() as 'mc']
    if (!type) { errors.push({ line: index + 1, message: 'Use mc, dropdown, rating, short, or paragraph.' }); return }
    if (!prompt) { errors.push({ line: index + 1, message: 'Add a question prompt after the first |.' }); return }
    const id = `paste-${index + 1}`
    const created = item(id, type, prompt)
    if ((type === 'multiple-choice' || type === 'dropdown') && options.filter(Boolean).length < 2) {
      errors.push({ line: index + 1, message: 'Choice questions require at least two options.' })
      return
    }
    if (created.options) created.options = options.filter(Boolean).slice(0, 10).map((label, optionIndex) => ({ id: `${id}-${optionIndex + 1}`, label }))
    if (created.answerKey && created.options) created.answerKey.optionIds = [created.options[0].id]
    items.push(created)
  })
  return { items, errors }
}
