import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { FolderTree } from '../components/library/FolderTree'
import { canMoveFolder, FOLDER_DRAG_TYPE } from '../components/library/folderDrag'
import type { LibraryFolder } from '../types'

const folder = (id: string, parentId: string | null = null): LibraryFolder => ({ id, parentId, name: id, description: '', sortOrder: 0, itemCount: 0, childCount: 0, hasChildren: false, trashedAt: null, updatedAt: '' })
const a = { ...folder('A'), hasChildren: true, childCount: 1 }
const b = folder('B')
const child = folder('Child', 'A')
afterEach(cleanup)
function setup() {
  const onDropFolder = vi.fn(); const onDropSlides = vi.fn(); const onAction = vi.fn()
  render(<FolderTree roots={[a, b]} children={new Map([['A', [child]]])} expanded={new Set(['A'])} selectedId={null} onExpand={vi.fn()} onSelect={vi.fn()} onDropFolder={onDropFolder} onDropSlides={onDropSlides} onAction={onAction} />)
  const data = new Map<string, string>()
  const transfer = { setData: (key: string, value: string) => data.set(key, value), getData: (key: string) => data.get(key) ?? '', types: [FOLDER_DRAG_TYPE], effectAllowed: '', dropEffect: '' }
  return { transfer, onDropFolder, onDropSlides, onAction }
}
it('drags a folder to a sibling, rejects descendants, and moves a child to top level', () => {
  const { transfer, onDropFolder } = setup()
  fireEvent.dragStart(screen.getByRole('treeitem', {name: 'A'}), {dataTransfer: transfer})
  expect(transfer.getData(FOLDER_DRAG_TYPE)).toBe('A')
  fireEvent.drop(screen.getByRole('treeitem', {name: 'Child'}), {dataTransfer: transfer})
  expect(onDropFolder).not.toHaveBeenCalled()
  fireEvent.drop(screen.getByRole('treeitem', {name: 'B'}), {dataTransfer: transfer})
  expect(onDropFolder).toHaveBeenCalledWith(a, 'B')
  fireEvent.dragStart(screen.getByRole('treeitem', {name: 'Child'}), {dataTransfer: transfer})
  fireEvent.drop(screen.getByText('Move to top level'), {dataTransfer: transfer})
  expect(onDropFolder).toHaveBeenLastCalledWith(child, null)
})
it('preserves slide drop and accessible Move action', () => {
  const { transfer, onDropSlides, onAction } = setup()
  transfer.setData('application/x-pathlab-slide-ids', 'slide-a,slide-b')
  fireEvent.drop(screen.getByRole('treeitem', {name: 'B'}), {dataTransfer: transfer})
  expect(onDropSlides).toHaveBeenCalledWith('B', ['slide-a', 'slide-b'])
  fireEvent.click(screen.getByRole('button', {name: 'More actions for A'}))
  fireEvent.click(screen.getByRole('menuitem', {name: 'Move'}))
  expect(onAction).toHaveBeenCalledWith(a, 'move')
})
it('blocks self, unchanged parent, trash and cyclic destinations', () => {
  const folders = new Map([a, b, child, {...folder('Trash'), trashedAt: 'today'}].map((item) => [item.id, item]))
  expect(canMoveFolder(a, 'A', folders)).toBe(false)
  expect(canMoveFolder(a, null, folders)).toBe(false)
  expect(canMoveFolder(a, 'Child', folders)).toBe(false)
  expect(canMoveFolder(a, 'Trash', folders)).toBe(false)
  expect(canMoveFolder(child, 'B', folders)).toBe(true)
})
