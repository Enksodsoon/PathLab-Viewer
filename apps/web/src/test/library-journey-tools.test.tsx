import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LibraryJourneyTools } from '../components/library/LibraryJourneyTools'
import type { LibrarySlide } from '../types'

vi.mock('../components/OpenSeadragonViewer', () => ({ OpenSeadragonViewer: () => <div>Deep zoom</div> }))
afterEach(cleanup)
const ready = { id:'ready', displayName:'Kidney biopsy', state:'ready_private', trashedAt:null, organSite:'Kidney', stain:'H&E', caseId:'Case 2' } as LibrarySlide

describe('authorized library commands', () => {
  it('searches supplied previewable slides and actual supplied actions only', () => {
    const preview=vi.fn(); const upload=vi.fn()
    render(<LibraryJourneyTools slides={[ready, {...ready, id:'failed', displayName:'Failed biopsy', state:'failed'}, {...ready, id:'trash', displayName:'Trashed biopsy', trashedAt:'2026-09-01'}]} selected={new Set()} quickLook={null} onQuickLook={vi.fn()} onPreview={preview} commands={[{id:'upload',label:'Upload slide',run:upload}]} />)
    fireEvent.click(screen.getByRole('button', {name:/Search commands/}))
    const dialog=screen.getByRole('dialog')
    expect(within(dialog).queryByRole('button', {name:/Failed biopsy/})).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', {name:/Trashed biopsy/})).not.toBeInTheDocument()
    const search=screen.getByLabelText('Slide name, organ, stain, case, or action')
    expect(search).toHaveFocus()
    fireEvent.change(search,{target:{value:'Case 2'}})
    fireEvent.keyDown(search,{key:'Enter'})
    expect(preview).toHaveBeenCalledWith(ready)
    fireEvent.click(screen.getByRole('button', {name:/Search commands/}))
    fireEvent.change(search,{target:{value:'Upload'}})
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:/Upload slide/}))
    expect(upload).toHaveBeenCalledOnce()
  })
  it('ignores shortcuts inside editable controls and supports a touch quick look button', () => {
    const peek=vi.fn()
    render(<><input aria-label="Elsewhere" /><LibraryJourneyTools slides={[ready]} selected={new Set(['ready'])} quickLook={null} onQuickLook={peek} onPreview={vi.fn()} /></>)
    fireEvent.keyDown(screen.getByLabelText('Elsewhere'),{key:'k',ctrlKey:true})
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('button',{name:/Search commands/}),{key:' '})
    expect(peek).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button',{name:/Quick look/}))
    expect(peek).toHaveBeenCalledWith(ready)
    fireEvent.keyDown(window,{key:'k',metaKey:true})
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
