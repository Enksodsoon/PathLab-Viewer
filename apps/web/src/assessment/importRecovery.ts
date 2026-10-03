import { assessmentItems, isAssessmentV2, type AssessmentDocument } from './types'

/** Preserve newer local edits while adding the server-created imported items. */
export function retainEditsAfterImport(current: AssessmentDocument, submitted: AssessmentDocument, saved: AssessmentDocument): AssessmentDocument {
  const existing = new Set([...assessmentItems(submitted), ...assessmentItems(current)].map(item => item.id))
  const added = assessmentItems(saved).filter(item => !existing.has(item.id))
  if (!isAssessmentV2(current)) return { ...current, items: [...current.items, ...added] }
  if (current.sections.length) {
    return { ...current, sections: current.sections.map((section, index) => index === 0
      ? { ...section, items: [...section.items, ...added] } : section) }
  }
  // Keep imported items without restoring context from a locally deleted section.
  const section = isAssessmentV2(saved) ? saved.sections[0] : undefined
  return { ...current, sections: section ? [{ id: section.id, title: 'Imported questions', items: added }] : [] }
}
