import type { KnowledgePack } from './types'

export const MAX_TUTOR_ASSET_BYTES = 500 * 1024 * 1024

export function retrieveGroundedClaimIds(
  pack: KnowledgePack,
  question: string,
  allowedClaimIds: string[],
  limit = 5,
): string[] {
  if (!question.trim() || question.length > 2_000) return []
  const query = tokens(question)
  if (!query.size) return []
  const allowed = new Set(allowedClaimIds)
  return pack.claims
    .filter((claim) => allowed.has(claim.id))
    .map((claim) => ({
      id: claim.id,
      score: intersection(query, tokens(`${claim.retrievalText} ${claim.text} ${claim.tags.join(' ')}`)),
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.id.localeCompare(right.id))
    .slice(0, Math.max(1, Math.min(5, limit)))
    .map((item) => item.id)
}

function tokens(value: string): Set<string> {
  return new Set(value.toLocaleLowerCase('en').match(/[a-z0-9]+/g)?.filter((item) => item.length >= 3) ?? [])
}

function intersection(left: Set<string>, right: Set<string>): number {
  let score = 0
  for (const item of left) if (right.has(item)) score += 1
  return score
}
