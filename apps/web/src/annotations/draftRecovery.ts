import type { AnnotationDraft } from './drafts'
import type { AnnotationStore } from './store'
import type { AnnotationInput, AnnotationRecord } from './types'

function sameAnnotationInput(
  record: AnnotationRecord,
  input: AnnotationInput,
): boolean {
  return record.layerId === input.layerId
    && JSON.stringify(record.geometry) === JSON.stringify(input.geometry)
    && JSON.stringify(record.style) === JSON.stringify(input.style)
    && JSON.stringify(record.metadata) === JSON.stringify(input.metadata)
}

export function replayDraft(store: AnnotationStore, draft: AnnotationDraft) {
  for (const mutation of draft.mutations) {
    if (mutation.type === 'create') {
      const committed = store.getState().annotations.get(mutation.item.id)
      if (!committed) {
        store.create(mutation.item)
      } else if (committed.deletedAt) {
        throw new Error(
          `Recovered annotation ${mutation.item.id} conflicts with a deleted server record`,
        )
      } else if (!sameAnnotationInput(committed, mutation.item)) {
        store.update(committed.id, {
          layerId: mutation.item.layerId,
          geometry: mutation.item.geometry,
          style: mutation.item.style,
          metadata: mutation.item.metadata,
        })
      }
    } else if (mutation.type === 'update') {
      store.update(mutation.id, {
        ...(mutation.layerId === undefined ? {} : { layerId: mutation.layerId }),
        ...(mutation.geometry === undefined ? {} : { geometry: mutation.geometry }),
        ...(mutation.style === undefined ? {} : { style: mutation.style }),
        ...(mutation.metadata === undefined ? {} : { metadata: mutation.metadata }),
      })
    } else if (mutation.type === 'delete') store.delete([mutation.id])
    else store.restore([mutation.id])
  }
}
