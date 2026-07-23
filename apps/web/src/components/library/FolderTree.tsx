import {
  ChevronDown,
  ChevronRight,
  Edit3,
  Folder,
  FolderInput,
  FolderOpen,
  MoreHorizontal,
  Trash2,
} from 'lucide-react'
import { useMemo, useRef, useState } from 'react'

import type { LibraryFolder } from '../../types'
import { ContextMenu } from './ContextMenu'

interface FolderTreeProps {
  roots: LibraryFolder[]
  children: Map<string, LibraryFolder[]>
  expanded: Set<string>
  selectedId: string | null
  onExpand: (folder: LibraryFolder) => void
  onSelect: (folder: LibraryFolder) => void
  onDropSlides: (folderId: string, slideIds: string[]) => void
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
): FlatFolder[] {
  return folders.flatMap((folder) => [
    { folder, level },
    ...(expanded.has(folder.id)
      ? flatten(children.get(folder.id) ?? [], children, expanded, level + 1)
      : []),
  ])
}

export function FolderTree({
  roots,
  children,
  expanded,
  selectedId,
  onExpand,
  onSelect,
  onDropSlides,
  onAction,
}: FolderTreeProps) {
  const flattened = useMemo(
    () => flatten(roots, children, expanded),
    [children, expanded, roots],
  )
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const refs = useRef(new Map<string, HTMLDivElement>())

  function focusAt(index: number) {
    const item = flattened[Math.max(0, Math.min(index, flattened.length - 1))]
    if (!item) return
    setFocusedId(item.folder.id)
    refs.current.get(item.folder.id)?.focus()
  }

  return (
    <div className="folder-tree" role="tree" aria-label="Folders">
      {flattened.map(({ folder, level }, index) => {
        const isExpanded = expanded.has(folder.id)
        const isSelected = selectedId === folder.id
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
            draggable
            onClick={() => onSelect(folder)}
            onFocus={() => setFocusedId(folder.id)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
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
            <span className="navigator-count">{folder.itemCount}</span>
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
