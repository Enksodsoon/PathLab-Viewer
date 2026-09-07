import { expect, it } from 'vitest'

import { ASSESSMENT_TEMPLATE_VERSION, assessmentTemplates, parseAssessmentPaste } from '../assessment/templates'

it('ships five versioned v2 templates with stable sections', () => {
  expect(assessmentTemplates).toHaveLength(5)
  expect(new Set(assessmentTemplates.map((template) => template.id)).size).toBe(5)
  for (const template of assessmentTemplates) {
    expect(template.version).toBe(ASSESSMENT_TEMPLATE_VERSION)
    expect(template.document.schema).toBe('pathlab.assessment/2')
    expect(template.document.sections.length).toBeGreaterThan(0)
  }
})

it('parses local paste input with line-level errors and bounded options', () => {
  const result = parseAssessmentPaste([
    'mc | Best diagnosis? | Adenocarcinoma | Reactive atypia',
    'rating | How confident are you?',
    'unknown | This should fail',
    'dropdown | Needs options | Only one',
  ].join('\n'))

  expect(result.items.map((item) => item.type)).toEqual(['multiple-choice', 'rating'])
  expect(result.items[0].options?.map((option) => option.label)).toEqual(['Adenocarcinoma', 'Reactive atypia'])
  expect(result.errors).toEqual([
    { line: 3, message: 'Use mc, rating, or text.' },
    { line: 4, message: 'Choice questions require at least two options.' },
  ])
})
