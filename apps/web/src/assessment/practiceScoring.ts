import { reachableItems } from './learnerRuntime'
import { type AssessmentDocument, type AssessmentItem, type DiagnosticSelection } from './types'

function normalized(value: unknown) {
  return String(value ?? '').normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}

export function matchedAnswerKeywords(response: unknown, keywords: string[]) {
  const text = normalized(response)
  return keywords.filter((keyword) => {
    const candidate = normalized(keyword)
    return candidate.length > 0 && text.includes(candidate)
  })
}

function selectionBounds(selection: DiagnosticSelection) {
  if (selection.kind === 'point') return { x: selection.x, y: selection.y, width: 0, height: 0 }
  if (selection.kind === 'rectangle') return selection
  const xs = selection.points.map((point) => point.x)
  const ys = selection.points.map((point) => point.y)
  const x = Math.min(...xs)
  const y = Math.min(...ys)
  return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y }
}

function regionMatches(selection: DiagnosticSelection, accepted: DiagnosticSelection, item: AssessmentItem) {
  const pointTolerance = item.scoring?.pointTolerance ?? 0.03
  const rectangleIou = item.scoring?.rectangleIou ?? 0.25
  const selectionBox = selectionBounds(selection)
  const center = selection.kind === 'point'
    ? selection
    : { kind: 'point' as const, x: selectionBox.x + selectionBox.width / 2, y: selectionBox.y + selectionBox.height / 2 }
  if (accepted.kind === 'point') {
    return Math.hypot(center.x - accepted.x, center.y - accepted.y) <= pointTolerance
  }
  const acceptedBox = selectionBounds(accepted)
  if (
    center.x >= acceptedBox.x && center.x <= acceptedBox.x + acceptedBox.width
    && center.y >= acceptedBox.y && center.y <= acceptedBox.y + acceptedBox.height
  ) return true
  if (selection.kind === 'point') return false
  const left = Math.max(selectionBox.x, acceptedBox.x)
  const top = Math.max(selectionBox.y, acceptedBox.y)
  const right = Math.min(selectionBox.x + selectionBox.width, acceptedBox.x + acceptedBox.width)
  const bottom = Math.min(selectionBox.y + selectionBox.height, acceptedBox.y + acceptedBox.height)
  const intersection = Math.max(0, right - left) * Math.max(0, bottom - top)
  const union = selectionBox.width * selectionBox.height + acceptedBox.width * acceptedBox.height - intersection
  return union > 0 && intersection / union >= rectangleIou
}

export function scorePractice(
  document: AssessmentDocument,
  responses: Record<string, Record<string, unknown>>,
) {
  let points = 0
  let maximumPoints = 0
  const breakdown: Record<string, number | null> = {}
  for (const item of reachableItems(document, responses)) {
    if (item.type === 'information' || item.type === 'section-information') continue
    const maximum = Number(item.points ?? 0)
    maximumPoints += maximum
    const response = responses[item.id] ?? {}
    const key = item.answerKey ?? {}
    let fraction: number | null = 0
    if (item.type === 'multiple-choice' || item.type === 'dropdown') {
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
    } else if ((item.type === 'short-answer' || item.type === 'paragraph') && !item.manual) {
      const variants = ((key.variants as string[] | undefined) ?? []).map(normalized).filter(Boolean)
      const keywords = ((key.keywords as string[] | undefined) ?? []).map((keyword) => keyword.trim()).filter(Boolean)
      if (variants.includes(normalized(response.text))) {
        fraction = 1
      } else if (keywords.length) {
        const matches = matchedAnswerKeywords(response.text, keywords).length
        fraction = item.scoring?.partialCredit ? matches / keywords.length : Number(matches === keywords.length)
      } else {
        fraction = null
      }
    } else if (item.type === 'rating') {
      const rating = Number(response.value)
      const expected = key.value
      fraction = expected === undefined
        ? Number(Number.isInteger(rating) && rating >= 1 && rating <= (item.rating?.max ?? 0))
        : Number(rating === Number(expected))
    } else if (item.manual) {
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
