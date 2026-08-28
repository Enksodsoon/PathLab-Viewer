import { getFolderChildren, getLibraryNavigation } from '../api'
import type { AdminSlide, LibraryFolder, LibraryNavigation } from '../types'

export interface ClassFolderOption {
  folder: LibraryFolder
  depth: number
  slides: AdminSlide[]
}

export async function loadAllLibraryFolders(): Promise<{ folders: LibraryFolder[]; navigation: LibraryNavigation }> {
  const navigation = await getLibraryNavigation()
  const folders = [...navigation.folders]
  const seen = new Set(folders.map((folder) => folder.id))
  const queue = folders.filter((folder) => folder.hasChildren)
  const concurrency = 8
  while (queue.length) {
    const parents = queue.splice(0, concurrency)
    const childGroups = await Promise.all(parents.map((folder) => getFolderChildren(folder.id)))
    for (const children of childGroups) {
      for (const child of children) {
        if (seen.has(child.id)) continue
        seen.add(child.id)
        folders.push(child)
        if (child.hasChildren) queue.push(child)
      }
    }
  }
  return { folders, navigation }
}

export function classFolderOptions(folders: LibraryFolder[], slides: AdminSlide[]): ClassFolderOption[] {
  const children = new Map<string | null, LibraryFolder[]>()
  folders.forEach((folder) => {
    const siblings = children.get(folder.parentId) ?? []
    siblings.push(folder)
    children.set(folder.parentId, siblings)
  })
  const slidesByFolder = new Map<string, AdminSlide[]>()
  slides.forEach((slide) => {
    if (!slide.folderId) return
    const items = slidesByFolder.get(slide.folderId) ?? []
    items.push(slide)
    slidesByFolder.set(slide.folderId, items)
  })
  const slideMemo = new Map<string, AdminSlide[]>()
  const collecting = new Set<string>()
  const collectSlides = (folder: LibraryFolder): AdminSlide[] => {
    const cached = slideMemo.get(folder.id)
    if (cached) return cached
    if (collecting.has(folder.id)) return []
    collecting.add(folder.id)
    const items = [...(slidesByFolder.get(folder.id) ?? []), ...(children.get(folder.id) ?? []).flatMap(collectSlides)]
    collecting.delete(folder.id)
    slideMemo.set(folder.id, items)
    return items
  }
  const options: ClassFolderOption[] = []
  const visited = new Set<string>()
  const append = (folder: LibraryFolder, depth: number) => {
    if (visited.has(folder.id)) return
    visited.add(folder.id)
    options.push({ folder, depth, slides: collectSlides(folder) })
    ;(children.get(folder.id) ?? []).forEach((child) => append(child, depth + 1))
  }
  ;(children.get(null) ?? []).forEach((folder) => append(folder, 0))
  folders.forEach((folder) => { if (!visited.has(folder.id)) append(folder, 0) })
  return options
}
