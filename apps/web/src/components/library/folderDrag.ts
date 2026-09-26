import type { LibraryFolder } from '../../types'

export const FOLDER_DRAG_TYPE = 'application/x-pathlab-folder-id'

// Loaded folders are an early UI guard; the protected API validates the complete tree.
export function canMoveFolder(source: LibraryFolder, targetId: string | null, folders: Map<string, LibraryFolder>) {
  if (source.trashedAt || source.id === targetId || source.parentId === targetId) return false
  const visited = new Set<string>()
  let current = targetId
  while (current) {
    if (current === source.id || visited.has(current)) return false
    visited.add(current)
    const target = folders.get(current)
    if (target?.trashedAt) return false
    current = target?.parentId ?? null
  }
  return true
}
