import {
  CaretDown as ChevronDown,
  CaretRight as ChevronRight,
  DotsThree as MoreHorizontal,
  Folder,
  FolderSimple as FolderInput,
  FolderOpen,
  PencilSimple as Edit3,
  Trash as Trash2,
} from '@phosphor-icons/react'
import { useMemo, useRef, useState } from 'react'

import type { LibraryFolder } from '../../types'
import { ContextMenu } from './ContextMenu'
import { canMoveFolder, FOLDER_DRAG_TYPE } from './folderDrag'

interface FolderTreeProps {
  roots: LibraryFolder[]
  children: Map<string, LibraryFolder[]>
  expanded: Set<string>
  selectedId: string | null
  onExpand: (folder: LibraryFolder) => void
  onSelect: (folder: LibraryFolder) => void
  onDropSlides: (folderId: string, slideIds: string[]) => void
  onDropFolder?: (folder: LibraryFolder, parentId: string | null) => void
  onAction: (folder: LibraryFolder, action: 'rename' | 'move' | 'trash') => void
}

interface FlatFolder {
  folder: LibraryFolder
  level: number
}

function flatten(
  folders: LibraryFolder[],
  children: Map<string, LibraryFolder[]>,
  expanded: Set<string>,
  level = 1,
  visited = new Set<string>(),
): FlatFolder[] {
  return folders.flatMap((folder) => {
    if (visited.has(folder.id)) return []
    visited.add(folder.id)
    return [
      { folder, level },
      ...(expanded.has(folder.id)
        ? flatten(children.get(folder.id) ?? [], children, expanded, level + 1, visited)
        : []),
    ]
  })
}

export function FolderTree({
  roots,
  children,
  expanded,
  selectedId,
  onExpand,
  onSelect,
  onDropSlides,
  onDropFolder,
  onAction,
}: FolderTreeProps) {
  const flattened = useMemo(
    () => flatten(roots, children, expanded),
    [children, expanded, roots],
  )
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const refs = useRef(new Map<string, HTMLDivElement>())
  const folders = new Map([...roots, ...[...children.values()].flat()].map((folder) => [folder.id, folder]))
  const [draggedId, setDraggedId] = useState<string | null>(null)

  function dropFolder(event: React.DragEvent, parentId: string | null) {
    const source = folders.get(event.dataTransfer.getData(FOLDER_DRAG_TYPE))
    if (!source) return false
    event.preventDefault()
    event.stopPropagation()
    if (canMoveFolder(source, parentId, folders)) onDropFolder?.(source, parentId)
    setDraggedId(null)
    return true
  }

  function focusAt(index: number) {
    const item = flattened[Math.max(0, Math.min(index, flattened.length - 1))]
    if (!item) return
    setFocusedId(item.folder.id)
    refs.current.get(item.folder.id)?.focus()
  }

  return (
    <div className="folder-tree" role="tree" aria-label="Folders">
      {onDropFolder && draggedId ? <div role="presentation" className="folder-tree-row" onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }} onDrop={(event) => dropFolder(event, null)}>Move to top level</div> : null}
      {flattened.map(({ folder, level }, index) => {
        const isExpanded = expanded.has(folder.id)
        const isSelected = selectedId === folder.id
        const subfolderCount = `${folder.childCount} ${
          folder.childCount === 1 ? 'subfolder' : 'subfolders'
        }`
        return (
          <div
            key={folder.id}
            ref={(node) => {
              if (node) refs.current.set(folder.id, node)
              else refs.current.delete(folder.id)
            }}
            role="treeitem"
            aria-label={folder.name}
            aria-level={level}
            aria-expanded={folder.hasChildren ? isExpanded : undefined}
            aria-selected={isSelected}
            tabIndex={focusedId === folder.id || (!focusedId && index === 0) ? 0 : -1}
            className={`folder-tree-row ${isSelected ? 'selected' : ''}`}
            style={{ paddingInlineStart: `${8 + (level - 1) * 16}px` }}
            draggable={Boolean(onDropFolder) && !folder.trashedAt}
            onDragStart={(event) => {
              if ((event.target as HTMLElement).closest('button')) { event.preventDefault(); return }
              event.dataTransfer.setData(FOLDER_DRAG_TYPE, folder.id)
              event.dataTransfer.effectAllowed = 'move'
              setDraggedId(folder.id)
            }}
            onDragEnd={() => setDraggedId(null)}
            onClick={() => onSelect(folder)}
            onFocus={() => setFocusedId(folder.id)}
            onDragOver={(event) => {
              if (event.dataTransfer.types.includes('application/x-pathlab-slide-ids') || (onDropFolder && event.dataTransfer.types.includes(FOLDER_DRAG_TYPE))) {
                event.preventDefault()
                event.dataTransfer.dropEffect = 'move'
              }
            }}
            onDrop={(event) => {
              event.preventDefault()
              if (dropFolder(event, folder.id)) return
              const ids = event.dataTransfer.getData('application/x-pathlab-slide-ids')
              if (ids) onDropSlides(folder.id, ids.split(',').filter(Boolean))
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                focusAt(index + 1)
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                focusAt(index - 1)
              } else if (event.key === 'ArrowRight' && folder.hasChildren) {
                event.preventDefault()
                if (!isExpanded) onExpand(folder)
                else focusAt(index + 1)
              } else if (event.key === 'ArrowLeft') {
                event.preventDefault()
                if (isExpanded) onExpand(folder)
                else {
                  let parentIndex = -1
                  for (let candidate = index - 1; candidate >= 0; candidate -= 1) {
                    if (flattened[candidate]?.level === level - 1) {
                      parentIndex = candidate
                      break
                    }
                  }
                  if (parentIndex >= 0) focusAt(parentIndex)
                }
              } else if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(folder)
              }
            }}
          >
            <button
              type="button"
              className="folder-disclosure"
              aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${folder.name}`}
              disabled={!folder.hasChildren}
              onClick={(event) => {
                event.stopPropagation()
                onExpand(folder)
              }}
            >
              {folder.hasChildren
                ? isExpanded ? <ChevronDown /> : <ChevronRight />
                : <span />}
            </button>
            {isExpanded ? <FolderOpen /> : <Folder />}
            <span className="folder-name">{folder.name}</span>
            <span
              className="navigator-count"
              aria-label={subfolderCount}
              title={subfolderCount}
            >
              {folder.childCount}
            </span>
            <div onClick={(event) => event.stopPropagation()}>
              <ContextMenu
                label={`More actions for ${folder.name}`}
                buttonClassName="navigator-more"
                buttonContent={<MoreHorizontal />}
              >
                {(close) => (
                  <>
                    <button type="button" role="menuitem" onClick={() => {
                      close()
                      onAction(folder, 'rename')
                    }}><Edit3 /> Rename</button>
                    <button type="button" role="menuitem" onClick={() => {
                      close()
                      onAction(folder, 'move')
                    }}><FolderInput /> Move</button>
                    <button type="button" role="menuitem" className="danger" onClick={() => {
                      close()
                      onAction(folder, 'trash')
                    }}><Trash2 /> Move to Trash</button>
                  </>
                )}
              </ContextMenu>
            </div>
          </div>
        )
      })}
    </div>
  )
}
