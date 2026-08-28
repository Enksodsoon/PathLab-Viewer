import { assessmentItems, type AssessmentDocument, type AssessmentItem, type DiagnosticSelection } from './types'

function normalized(value: unknown) {
  return String(value ?? '').normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}

function regionMatches(selection: DiagnosticSelection, accepted: DiagnosticSelection, item: AssessmentItem) {
  const pointTolerance = item.scoring?.pointTolerance ?? 0.03
  const rectangleIou = item.scoring?.rectangleIou ?? 0.25
  const center = selection.kind === 'point'
    ? selection
    : { kind: 'point' as const, x: selection.x + selection.width / 2, y: selection.y + selection.height / 2 }
  if (accepted.kind === 'point') {
    return Math.hypot(center.x - accepted.x, center.y - accepted.y) <= pointTolerance
  }
  if (
    center.x >= accepted.x && center.x <= accepted.x + accepted.width
    && center.y >= accepted.y && center.y <= accepted.y + accepted.height
  ) return true
  if (selection.kind === 'point') return false
  const left = Math.max(selection.x, accepted.x)
  const top = Math.max(selection.y, accepted.y)
  const right = Math.min(selection.x + selection.width, accepted.x + accepted.width)
  const bottom = Math.min(selection.y + selection.height, accepted.y + accepted.height)
  const intersection = Math.max(0, right - left) * Math.max(0, bottom - top)
  const union = selection.width * selection.height + accepted.width * accepted.height - intersection
  return union > 0 && intersection / union >= rectangleIou
}

export function scorePractice(
  document: AssessmentDocument,
  responses: Record<string, Record<string, unknown>>,
) {
  let points = 0
  let maximumPoints = 0
  const breakdown: Record<string, number | null> = {}
  for (const item of assessmentItems(document)) {
    if (item.type === 'information') continue
    const maximum = Number(item.points ?? 0)
    maximumPoints += maximum
    const response = responses[item.id] ?? {}
    const key = item.answerKey ?? {}
    let fraction: number | null = 0
    if (item.type === 'multiple-choice') {
      fraction = (key.optionIds as string[] | undefined)?.includes(String(response.optionId)) ? 1 : 0
    } else if (item.type === 'checkboxes') {
      const selected = new Set((response.optionIds as string[] | undefined) ?? [])
      const correct = new Set((key.optionIds as string[] | undefined) ?? [])
      if (!item.scoring?.partialCredit) {
        fraction = selected.size === correct.size && [...selected].every((id) => correct.has(id)) ? 1 : 0
      } else {
        const incorrect = new Set((item.options ?? []).map((option) => option.id).filter((id) => !correct.has(id)))
        const positive = [...selected].filter((id) => correct.has(id)).length / Math.max(1, correct.size)
        const penalty = [...selected].filter((id) => incorrect.has(id)).length / Math.max(1, incorrect.size)
        fraction = Math.max(0, Math.min(1, positive - penalty))
      }
    } else if (item.type === 'short-answer' && !item.manual) {
      fraction = ((key.variants as string[] | undefined) ?? []).map(normalized)
        .includes(normalized(response.text)) ? 1 : 0
    } else if (item.type === 'paragraph' || item.manual) {
      fraction = null
    } else if (item.type === 'diagnostic-field') {
      const regions = (key.regions as DiagnosticSelection[] | undefined) ?? []
      const diagnoses = ((key.diagnoses as string[] | undefined) ?? []).map(normalized)
      const selection = response.selection as DiagnosticSelection | undefined
      const regionScore = regions.length > 0
        ? Number(Boolean(selection && regions.some((accepted) => regionMatches(selection, accepted, item))))
        : null
      const diagnosisScore = diagnoses.length > 0
        ? Number(diagnoses.includes(normalized(response.diagnosis)))
        : null
      fraction = regionScore !== null && diagnosisScore !== null
        ? (regionScore + diagnosisScore) / 2
        : regionScore ?? diagnosisScore ?? 0
    }
    const earned = fraction === null
      ? null
      : Math.floor(maximum * fraction * 1000 + 0.5 + Number.EPSILON) / 1000
    breakdown[item.id] = earned
    if (earned !== null) points += earned
  }
  return { points, maximumPoints, breakdown }
}
