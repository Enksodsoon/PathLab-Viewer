import type {
  AnnotationInput,
  AnnotationMutation,
  AnnotationMutationResult,
} from './types'

export function mutationTargetId(mutation: AnnotationMutation): string {
  return mutation.type === 'create' ? mutation.item.id : mutation.id
}

function mergeItem(item: AnnotationInput, update: Extract<AnnotationMutation, { type: 'update' }>) {
  return {
    ...structuredClone(item),
    ...(update.layerId === undefined ? {} : { layerId: update.layerId }),
    ...(update.geometry === undefined ? {} : { geometry: structuredClone(update.geometry) }),
    ...(update.style === undefined ? {} : { style: structuredClone(update.style) }),
    ...(update.metadata === undefined ? {} : { metadata: structuredClone(update.metadata) }),
  }
}

export function coalesceMutations(
  previous: AnnotationMutation,
  next: AnnotationMutation,
): AnnotationMutation[] {
  if (mutationTargetId(previous) !== mutationTargetId(next)) return [previous, next]
  if (previous.type === 'create') {
    if (next.type === 'update') {
      return [{ type: 'create', item: mergeItem(previous.item, next) }]
    }
    if (next.type === 'delete') return []
    if (next.type === 'create') throw new Error(`Duplicate create for ${previous.item.id}`)
    return [previous, next]
  }
  if (previous.type === 'update') {
    if (next.type === 'update') {
      return [{
        ...structuredClone(previous),
        ...(next.layerId === undefined ? {} : { layerId: next.layerId }),
        ...(next.geometry === undefined ? {} : { geometry: structuredClone(next.geometry) }),
        ...(next.style === undefined ? {} : { style: structuredClone(next.style) }),
        ...(next.metadata === undefined ? {} : { metadata: structuredClone(next.metadata) }),
        version: previous.version,
      }]
    }
    if (next.type === 'delete') {
      return [{ type: 'delete', id: previous.id, version: previous.version }]
    }
    return [previous, next]
  }
  if (previous.type === 'delete') {
    if (next.type === 'restore') return []
    if (next.type === 'delete') return [previous]
    return [previous, next]
  }
  if (next.type === 'delete') return []
  if (next.type === 'restore') return [previous]
  return [previous, next]
}

export function coalesceMutationSequence(
  mutations: readonly AnnotationMutation[],
): AnnotationMutation[] {
  const result: AnnotationMutation[] = []
  for (const mutation of mutations) {
    result.push(structuredClone(mutation))
    while (result.length >= 2) {
      const previous = result[result.length - 2]
      const next = result[result.length - 1]
      const coalesced = coalesceMutations(previous, next)
      if (
        coalesced.length === 2
        && sameMutation(coalesced[0], previous)
        && sameMutation(coalesced[1], next)
      ) {
        break
      }
      result.splice(
        result.length - 2,
        2,
        ...coalesced.map((entry) => structuredClone(entry)),
      )
    }
  }
  return result
}

export function rebaseMutation(
  mutation: AnnotationMutation,
  version: number,
): AnnotationMutation {
  if (mutation.type === 'create') return structuredClone(mutation)
  return { ...structuredClone(mutation), version }
}

export function rebaseForResults(
  mutations: readonly AnnotationMutation[],
  results: readonly AnnotationMutationResult[],
): AnnotationMutation[] {
  const versions = new Map(results.map((result) => [result.id, result.version]))
  return mutations.map((mutation) => {
    const version = versions.get(mutationTargetId(mutation))
    return version === undefined ? structuredClone(mutation) : rebaseMutation(mutation, version)
  })
}

export function sameMutation(left: AnnotationMutation, right: AnnotationMutation): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}
