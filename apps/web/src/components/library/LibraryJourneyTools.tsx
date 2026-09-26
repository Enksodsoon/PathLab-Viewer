import { useEffect, useRef, useState } from 'react'
import { getPrivateSlide } from '../../api'
import type { AdminSlide, LibrarySlide } from '../../types'
import { OpenSeadragonViewer } from '../OpenSeadragonViewer'
import { Loader } from '../Loader'
import { LibraryDialog } from './LibraryDialog'
import { canPreview, ignoresShortcut } from './viewerNavigation'
import './viewerJourney.css'

export interface LibraryCommand { id: string; label: string; run: () => void }
interface Props {
  slides: LibrarySlide[]
  selected: Set<string>
  quickLook: LibrarySlide | null
  onQuickLook: (slide: LibrarySlide | null) => void
  onPreview: (slide: LibrarySlide) => void
  commands?: LibraryCommand[]
}
export function LibraryJourneyTools({ slides, selected, quickLook, onQuickLook, onPreview, commands = [] }: Props) {
  const [commandOpen, setCommandOpen] = useState(false)
  const [query, setQuery] = useState('')
  const searchInput = useRef<HTMLInputElement>(null)
  useEffect(() => { if (commandOpen) searchInput.current?.focus() }, [commandOpen])
  const [preview, setPreview] = useState<AdminSlide | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const selectedSlide = slides.find((slide) => selected.has(slide.id) && canPreview(slide))
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (ignoresShortcut(event.target) || event.defaultPrevented) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        if (document.querySelector('dialog[open]') && !commandOpen) return
        event.preventDefault(); setQuery(''); setCommandOpen((open) => !open)
      } else if (event.key === ' ' && !event.ctrlKey && !event.metaKey && !event.altKey && (quickLook || selectedSlide)) {
        if (event.target instanceof Element && event.target.closest('button, a, [role="menu"]')) return
        if (document.querySelector('dialog[open]') && !quickLook) return
        event.preventDefault(); onQuickLook(quickLook ? null : selectedSlide!)
      }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [commandOpen, onQuickLook, quickLook, selectedSlide])
  useEffect(() => {
    let active = true
    setPreview(null); setFailed(false)
    if (quickLook) void getPrivateSlide(quickLook.id).then((slide) => { if (active) setPreview(slide) }).catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [quickLook, attempt])
  const needle = query.trim().toLocaleLowerCase()
  const results = [
    ...slides.filter(canPreview).map((slide) => ({ id: `slide-${slide.id}`, label: slide.displayName, detail: [slide.organSite, slide.stain, slide.caseId].filter(Boolean).join(' · '), run: () => onPreview(slide) })),
    ...commands.map((command) => ({ ...command, detail: 'Library action' })),
  ].filter((command) => `${command.label} ${command.detail}`.toLocaleLowerCase().includes(needle))
  return <>
    <div className="library-journey-tools">
      <button type="button" onClick={() => { setQuery(''); setCommandOpen(true) }}>Search commands <kbd>Ctrl / ⌘ K</kbd></button>
      <button type="button" disabled={!selectedSlide} onClick={() => selectedSlide && onQuickLook(selectedSlide)}>Quick look <kbd>Space</kbd></button>
    </div>
    <LibraryDialog open={commandOpen} title="Search library commands" onClose={() => setCommandOpen(false)}>
      <label htmlFor="library-command-query">Slide name, organ, stain, case, or action</label>
      <input ref={searchInput} id="library-command-query" className="library-command-search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && results[0]) { event.preventDefault(); setCommandOpen(false); results[0].run() } }} autoFocus />
      <div className="library-command-results">{results.map((command) => <button type="button" key={command.id} onClick={() => { setCommandOpen(false); command.run() }}>{command.label}<small>{command.detail || 'Open private viewer'}</small></button>)}</div>
      {!results.length ? <p role="status">No matching commands in this library view.</p> : null}
    </LibraryDialog>
    <LibraryDialog open={Boolean(quickLook)} title={quickLook ? `Quick look: ${quickLook.displayName}` : 'Quick look'} wide onClose={() => onQuickLook(null)}>
      {quickLook ? <>
        <p className="library-quicklook-metadata">{[quickLook.organSite, quickLook.stain, quickLook.diagnosis].filter(Boolean).join(' · ') || 'Whole-slide image'}</p>
        <div className="library-quicklook-stage">
          {failed ? <div role="alert"><p>Preview could not load. Your session may have expired or the slide may be unavailable.</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry preview</button></div> : preview ? <OpenSeadragonViewer key={preview.id} tileSource={preview.tileSource ?? ''} onReady={() => {}} posterUrl={preview.thumbnailUrl} micronsPerPixel={preview.metadata?.physicalSizeX} /> : <Loader label="Opening preview…" />}
        </div>
        <button type="button" className="button primary library-quicklook-open" onClick={() => { onQuickLook(null); onPreview(quickLook) }}>Open viewer</button>
      </> : null}
    </LibraryDialog>
  </>
}
