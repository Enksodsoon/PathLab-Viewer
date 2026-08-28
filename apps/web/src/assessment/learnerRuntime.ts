import type { AssessmentDocument, AssessmentDocumentV2, AssessmentItem } from './types'

export type LearnerResponses = Record<string, Record<string, unknown>>

function conditionMatches(condition: Record<string, unknown>, response?: Record<string, unknown>) {
  if (condition.operator === 'answered') return Boolean(response && Object.keys(response).length)
  if (condition.operator === 'not-answered') return !response || !Object.keys(response).length
  if (!response) return false
  const expected = condition.optionId ?? condition.value
  if (condition.operator === 'equals') return response.optionId === expected || response.value === expected
  if (condition.operator === 'contains') return Array.isArray(response.optionIds) && response.optionIds.includes(expected)
  if (condition.operator === 'greater-or-equal') return Number(response.value) >= Number(condition.value)
  return false
}

export function reachableSectionIds(document: AssessmentDocumentV2, responses: LearnerResponses) {
  if (!document.sections.length) return []
  const byId = new Map(document.sections.map((section, index) => [section.id, { section, index }]))
  const reachable: string[] = []
  const visited = new Set<string>()
  let current = document.sections[0].id
  while (byId.has(current) && !visited.has(current)) {
    visited.add(current)
    reachable.push(current)
    const entry = byId.get(current)!
    let destination: string | undefined
    for (const item of entry.section.items) {
      const routing = item.routing
      if (!routing) continue
      const matching = routing.rules?.find((rule) => conditionMatches(rule.when, responses[item.id]))
      if (matching) { destination = matching.goToSectionId; break }
      destination = routing.defaultSectionId ?? destination
    }
    if (destination) { current = destination; continue }
    current = document.sections[entry.index + 1]?.id ?? ''
  }
  return reachable
}

export function reachableItems(document: AssessmentDocument, responses: LearnerResponses): AssessmentItem[] {
  if (document.schema !== 'pathlab.assessment/2') return document.items
  const reachable = new Set(reachableSectionIds(document, responses))
  return document.sections.filter((section) => reachable.has(section.id)).flatMap((section) => section.items)
}

export function pruneUnreachableResponses(document: AssessmentDocument, responses: LearnerResponses) {
  const reachable = new Set(reachableItems(document, responses).map((item) => item.id))
  return Object.fromEntries(Object.entries(responses).filter(([itemId]) => reachable.has(itemId)))
}

async function digest(seed: string, itemId: string) {
  const encoded = new TextEncoder().encode(`${seed}:${itemId}`)
  const value = await globalThis.crypto.subtle.digest('SHA-256', encoded)
  return [...new Uint8Array(value)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

export async function deterministicOrder(items: AssessmentItem[], seed: string) {
  const keyed = await Promise.all(items.map(async (item) => ({ item, digest: await digest(seed, item.id) })))
  return keyed.sort((left, right) => left.digest.localeCompare(right.digest) || left.item.id.localeCompare(right.item.id)).map(({ item }) => item)
}

export async function orderSectionRuns(items: AssessmentItem[], seed: string, shuffle: boolean) {
  if (!shuffle) return items
  const result: AssessmentItem[] = []
  let run: AssessmentItem[] = []
  const flush = async () => { result.push(...await deterministicOrder(run, seed)); run = [] }
  for (const item of items) {
    if (item.type === 'section-information' || item.type === 'information') {
      await flush()
      result.push(item)
    } else run.push(item)
  }
  await flush()
  return result
}
