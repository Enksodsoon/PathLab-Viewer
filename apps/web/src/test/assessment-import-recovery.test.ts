import { expect, it } from 'vitest'
import { retainEditsAfterImport } from '../assessment/importRecovery'
import type { AssessmentDocumentV2 } from '../assessment/types'

const submitted: AssessmentDocumentV2 = { schema: 'pathlab.assessment/2', title: 'Old title', presentation: {}, settings: {},
  sections: [{ id: 'existing', title: 'Old section', items: [{ id: 'q1', type: 'short-answer', prompt: 'Old prompt' }] }] }
const imported = { id: 'imported', type: 'short-answer' as const, prompt: 'Imported prompt' }
const saved = { ...submitted, sections: [{ ...submitted.sections[0], items: [...submitted.sections[0].items, imported] }] }

it('retains section edits, added questions and ordering while incorporating server-created imports', () => {
  const current = { ...submitted, title: 'New title', sections: [
    { id: 'new-first', title: 'New first section', items: [{ id: 'local', type: 'short-answer' as const, prompt: 'Local question' }] },
    { ...submitted.sections[0], title: 'Edited section', items: [{ ...submitted.sections[0].items[0], prompt: 'Edited prompt' }] },
  ] }
  const merged = retainEditsAfterImport(current, submitted, saved)
  expect(merged).toEqual({ ...current, sections: [{ ...current.sections[0], items: [...current.sections[0].items, imported] }, current.sections[1]] })
})

it('does not restore locally removed questions while importing into an empty sectioned document', () => {
  const current = { ...submitted, title: 'New title', sections: [] }
  const merged = retainEditsAfterImport(current, submitted, saved)
  expect(merged).toEqual({ ...current, sections: [{ ...saved.sections[0], title: 'Imported questions', items: [imported] }] })
})

it('does not restore slide context from a section deleted while import was pending', () => {
  const submittedWithContext = { ...submitted, sections: [{ ...submitted.sections[0], slideId: 'removed-slide', description: 'Removed context', viewport: { x: 1, y: 2, width: 3, height: 4 } }] }
  const savedWithContext = { ...saved, sections: [{ ...submittedWithContext.sections[0], items: [...submitted.sections[0].items, imported] }] }
  const current = { ...submitted, sections: [] }
  expect(retainEditsAfterImport(current, submittedWithContext, savedWithContext)).toEqual({ ...current,
    sections: [{ id: 'existing', title: 'Imported questions', items: [imported] }] })
})
