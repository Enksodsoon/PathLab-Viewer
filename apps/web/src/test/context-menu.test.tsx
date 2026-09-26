import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ContextMenu } from '../components/library/ContextMenu'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('keeps a menu open when focusing an item would otherwise scroll the page', async () => {
  const focus = HTMLElement.prototype.focus
  vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function (this: HTMLElement, options) {
    focus.call(this, options)
    if (!options?.preventScroll) queueMicrotask(() => window.dispatchEvent(new Event('scroll')))
  })
  render(<ContextMenu label="Actions" buttonContent="Open">
    {() => <button role="menuitem">Preview</button>}
  </ContextMenu>)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Actions' })) })
  expect(screen.getByRole('menuitem', { name: 'Preview' })).toHaveFocus()
  await act(async () => { fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' }) })
  expect(screen.getByRole('menuitem', { name: 'Preview' })).toHaveFocus()
  fireEvent.scroll(window)
  expect(screen.getByRole('menu')).toBeVisible()
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
  expect(screen.queryByRole('menu')).not.toBeInTheDocument()
})
