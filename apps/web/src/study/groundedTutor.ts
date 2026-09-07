import type { KnowledgePack } from './types'

export const MAX_TUTOR_ASSET_BYTES = 500 * 1024 * 1024

export type TutorModelManifest = {
  schema: 'pathlab.tutor-model/1'
  modelId: 'qwen3-0.6b-int4'
  artifactSha256: string
  artifactBytes: number
  runtime: 'webgpu-worker'
  output: 'claim-ids-only'
  status: 'not_evaluable' | 'experimental' | 'qualified'
}

export function validateTutorModelManifest(value: TutorModelManifest): TutorModelManifest {
  if (value.schema !== 'pathlab.tutor-model/1' || value.modelId !== 'qwen3-0.6b-int4'
    || !/^[a-f0-9]{64}$/.test(value.artifactSha256)
    || !Number.isSafeInteger(value.artifactBytes) || value.artifactBytes < 1
    || value.artifactBytes > MAX_TUTOR_ASSET_BYTES
    || value.runtime !== 'webgpu-worker' || value.output !== 'claim-ids-only'
    || !['not_evaluable', 'experimental', 'qualified'].includes(value.status)) {
    throw new Error('LOCAL_TUTOR_MANIFEST_INVALID')
  }
  return value
}

export function validateModelClaimOrder(
  candidate: unknown, retrievedClaimIds: string[], allowedClaimIds: string[],
): string[] {
  if (!Array.isArray(candidate) || candidate.length > 5
    || !candidate.every((item) => typeof item === 'string')) return []
  const available = new Set(retrievedClaimIds)
  const allowed = new Set(allowedClaimIds)
  const unique = new Set(candidate)
  if (unique.size !== candidate.length || candidate.some((id) => !available.has(id) || !allowed.has(id))) return []
  return candidate
}

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
