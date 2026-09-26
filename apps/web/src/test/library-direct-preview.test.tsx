import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SlideViews } from '../components/library/SlideViews'
import type { LibrarySlide } from '../types'

const slide: LibrarySlide = { id:'a', publicId:'public-a', displayName:'Kidney A', description:'', folderId:null, caseId:'', organSite:'Kidney', stain:'H&E', diagnosis:'', course:'', tags:[], teachingNote:'', sourceBytes:1024, derivativeBytes:0, state:'ready_private', errorCode:null, createdAt:'2026-09-01T00:00:00Z', updatedAt:'2026-09-01T00:00:00Z', trashedAt:null, thumbnailUrl:null }
afterEach(cleanup)
describe('direct library activation', () => {
  it.each(['grid', 'table'] as const)('opens %s viewer with double click or Enter while nested selection stays selection', (view) => {
    const onPreview=vi.fn(); const onOpen=vi.fn(); const onQuickLook=vi.fn()
    const { container }=render(<MemoryRouter><SlideViews view={view} slides={[slide]} selected={new Set()} onSelect={vi.fn()} onOpen={onOpen} onAction={vi.fn()} onPreview={onPreview} onQuickLook={onQuickLook} /></MemoryRouter>)
    const card=container.querySelector(view === 'table' ? 'tbody tr' : 'article')!
    fireEvent.doubleClick(screen.getByRole('checkbox'))
    expect(onPreview).not.toHaveBeenCalled(); expect(onOpen).not.toHaveBeenCalled()
    fireEvent.doubleClick(card); expect(onPreview).toHaveBeenCalledWith(slide)
    fireEvent.keyDown(card, {key:'Enter'}); expect(onPreview).toHaveBeenCalledTimes(2)
    fireEvent.keyDown(card, {key:' '}); expect(onQuickLook).toHaveBeenCalledWith(slide)
    fireEvent.keyDown(screen.getByRole('checkbox'), {key:'Enter'}); expect(onPreview).toHaveBeenCalledTimes(2)
    fireEvent.keyDown(container.querySelector('.card-preview, td:nth-child(2) button')!, {key:'Enter'}); expect(onPreview).toHaveBeenCalledTimes(3)
  })
  it('never previews failed or trashed items', () => {
    const onPreview=vi.fn(); const onOpen=vi.fn()
    const { container }=render(<MemoryRouter><SlideViews view="grid" slides={[{...slide,trashedAt:'2026-09-02'}]} selected={new Set()} onSelect={vi.fn()} onOpen={onOpen} onAction={vi.fn()} onPreview={onPreview} /></MemoryRouter>)
    fireEvent.doubleClick(container.querySelector('article')!)
    expect(onPreview).not.toHaveBeenCalled(); expect(onOpen).toHaveBeenCalled()
    expect(screen.queryByRole('button', {name:'Open viewer'})).not.toBeInTheDocument()
  })
})
