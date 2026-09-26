import {
  ArrowRight,
  CaretDown,
  CaretRight,
  DotsSixVertical,
  FolderOpen,
  ImageSquare,
  LinkSimple,
  Plus,
  SpinnerGap,
  Stack,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'

import {
  createComparisonSet,
  getComparisonSet,
  getLibrarySlide,
  getStackSuggestions,
  listComparisonSets,
  reserveStackUpload,
  updateStackMembers,
} from '../../api'
import { startTusUpload } from '../../upload'
import type { ComparisonSet, LibrarySlide, StackSuggestion } from '../../types'

type UploadItem = {
  id: string
  file: File
  displayName: string
  stain: string
  progress: number
  status: 'queued' | 'uploading' | 'processing' | 'error'
}

interface SlideStackShelfProps {
  enabled: boolean
  slides: LibrarySlide[]
  onNotice?: (message: string) => void
}

const READY_STATES = new Set(['ready_private', 'published'])

function guessStain(filename: string) {
  const name = filename.toLowerCase()
  if (/\b(h[&+_-]?e|he)\b/.test(name)) return 'H&E'
  if (name.includes('trichrome')) return 'Trichrome'
  if (name.includes('silver')) return 'Silver'
  if (/\bpas\b/.test(name)) return 'PAS'
  if (name.includes('her2')) return 'HER2'
  const marker = name.match(/(?:^|[^a-z0-9])(cd\d+|panc?ytokeratin|ki-?67|p40|p53|ttf-?1|er|pr)(?=$|[^a-z0-9])/i)
  return marker?.[1]?.toUpperCase() ?? 'Other stain'
}

function cleanName(filename: string) {
  return filename.replace(/\.ome\.tiff?$/i, '').replaceAll('_', ' ')
}

function memberState(set: ComparisonSet, slideId: string) {
  if (slideId === set.referenceSlideId) return 'Reference'
  const member = set.members.find((value) => value.slideId === slideId)
  if (!member?.tileSource) return member?.availabilityReason?.replaceAll('_', ' ') ?? 'Processing'
  return member.registration?.status === 'ready' ? 'Aligned' : 'Waiting for alignment'
}

export function SlideStackShelf({ enabled, slides, onNotice }: SlideStackShelfProps) {
  const [sets, setSets] = useState<ComparisonSet[]>([])
  const [expandedId, setExpandedId] = useState('')
  const [expanded, setExpanded] = useState<ComparisonSet | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [mode, setMode] = useState<'new' | 'link' | null>(null)
  const [newReferenceId, setNewReferenceId] = useState('')
  const [newName, setNewName] = useState('')
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [suggestions, setSuggestions] = useState<StackSuggestion[]>([])
  const [query, setQuery] = useState('')
  const [selectedSlides, setSelectedSlides] = useState<Set<string>>(() => new Set())
  const [draggedId, setDraggedId] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const readySlides = useMemo(() => slides.filter((slide) => READY_STATES.has(slide.state)), [slides])
  const readyMembers = useMemo(
    () => expanded?.members.filter((member) => member.tileSource) ?? [],
    [expanded],
  )

  async function refresh(preferredId = expandedId) {
    const values = await listComparisonSets()
    setSets(values)
    const id = values.some((value) => value.id === preferredId) ? preferredId : ''
    if (id) {
      const value = await getComparisonSet(id)
      setExpanded(value)
      setExpandedId(id)
    } else if (expandedId) {
      setExpanded(null)
      setExpandedId('')
    }
  }

  useEffect(() => {
    if (!enabled) return
    let active = true
    void listComparisonSets().then((values) => active && setSets(values)).catch(() => {
      if (active) setMessage('Slide stacks could not be loaded.')
    })
    return () => { active = false }
  }, [enabled])

  useEffect(() => {
    if (mode !== 'link' || !expanded) return
    let active = true
    void getStackSuggestions(expanded.referenceSlideId, query).then((values) => {
      if (!active) return
      const members = new Set(expanded.members.map((member) => member.slideId))
      setSuggestions(values.filter((value) => !members.has(value.slideId)))
    }).catch(() => active && setMessage('Library slides could not be searched.'))
    return () => { active = false }
  }, [expanded, mode, query])

  if (!enabled) return null

  async function toggleStack(id: string) {
    if (expandedId === id) {
      setExpandedId(''); setExpanded(null); setMode(null); setUploads([])
      return
    }
    setExpandedId(id); setMode(null); setUploads([]); setMessage('')
    try { setExpanded(await getComparisonSet(id)) } catch { setMessage('This stack could not be opened.') }
  }

  function announce(value: string) {
    setMessage(value)
    onNotice?.(value)
  }

  async function createStack() {
    const reference = readySlides.find((slide) => slide.id === newReferenceId)
    if (!reference) return
    setBusy(true); setMessage('')
    try {
      const created = await createComparisonSet(
        newName.trim() || `${reference.caseId || reference.displayName} slide stack`,
        [reference.id], reference.id,
      )
      setMode(null); setNewReferenceId(''); setNewName(''); setUploads([])
      await refresh(created.id)
      announce('Stack created. Drop stained slides into it or add slides from the library.')
    } catch { setMessage('The stack could not be created.') } finally { setBusy(false) }
  }

  function queueFiles(files: File[]) {
    if (!expanded) return
    const accepted = files.filter((file) => /\.ome\.tiff?$/i.test(file.name))
    const room = Math.max(0, 12 - expanded.members.length - uploads.length)
    setUploads((current) => [...current, ...accepted.slice(0, room).map((file, index) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${index}`,
      file,
      displayName: cleanName(file.name),
      stain: guessStain(file.name),
      progress: 0,
      status: 'queued' as const,
    }))])
    if (!accepted.length) setMessage('Drop OME-TIFF files ending in .ome.tif or .ome.tiff.')
    else if (accepted.length > room) setMessage('A stack can contain up to 12 slides.')
  }

  function updateUpload(id: string, changes: Partial<UploadItem>) {
    setUploads((current) => current.map((item) => item.id === id ? { ...item, ...changes } : item))
  }

  async function uploadQueued() {
    if (!expanded) return
    setBusy(true); setMessage('')
    let current = expanded
    let failed = false
    for (const item of uploads.filter((value) => value.status === 'queued' || value.status === 'error')) {
      try {
        const reference = slides.find((slide) => slide.id === current.referenceSlideId)
          ?? await getLibrarySlide(current.referenceSlideId)
        const reservation = await reserveStackUpload(current.id, item.file, {
          version: current.version,
          displayName: item.displayName.trim() || cleanName(item.file.name),
          stain: item.stain.trim() || 'Other stain',
          anchorSlideId: current.referenceSlideId,
          folderId: reference?.folderId ?? null,
          caseId: reference?.caseId ?? '',
          organSite: reference?.organSite ?? '',
        })
        updateUpload(item.id, { status: 'uploading', progress: 0 })
        await startTusUpload(item.file, reservation.uploadUrl, reservation.uploadToken, {
          progress: (progress) => updateUpload(item.id, { progress }),
          success: () => updateUpload(item.id, { status: 'processing', progress: 100 }),
          error: () => updateUpload(item.id, { status: 'error' }),
        })
        current = await getComparisonSet(current.id)
        setExpanded(current)
      } catch {
        failed = true
        updateUpload(item.id, { status: 'error' })
        setMessage(`${item.file.name} needs attention. You can retry it.`)
        break
      }
    }
    await refresh(current.id)
    setBusy(false)
    if (!failed) announce('Slides attached. Processing and alignment continue automatically.')
  }

  async function updateMembers(payload: {
    add?: Array<{ slideId: string; anchorSlideId: string }>
    remove?: string[]
    referenceSlideId?: string
    order?: string[]
  }, success: string) {
    if (!expanded) return
    setBusy(true); setMessage('')
    try {
      const value = await updateStackMembers(expanded.id, {
        version: expanded.version,
        add: payload.add ?? [],
        ...payload,
      })
      setExpanded(value)
      await refresh(value.id)
      announce(success)
    } catch { setMessage('The stack changed or could not be updated. Refresh and try again.') } finally { setBusy(false) }
  }

  async function linkSelected() {
    if (!expanded || !selectedSlides.size) return
    await updateMembers({
      add: [...selectedSlides].map((slideId) => ({ slideId, anchorSlideId: expanded.referenceSlideId })),
    }, `${selectedSlides.size} slide${selectedSlides.size === 1 ? '' : 's'} added to the stack.`)
    setSelectedSlides(new Set()); setMode(null)
  }

  function moveBefore(targetId: string) {
    if (!expanded || !draggedId || draggedId === targetId) return
    const order = expanded.members.map((member) => member.slideId).filter((id) => id !== draggedId)
    order.splice(order.indexOf(targetId), 0, draggedId)
    setDraggedId('')
    void updateMembers({ order }, 'Slide order updated.')
  }

  function moveBy(slideId: string, direction: -1 | 1) {
    if (!expanded) return
    const order = expanded.members.map((member) => member.slideId)
    const index = order.indexOf(slideId)
    const destination = index + direction
    if (index < 0 || destination < 0 || destination >= order.length) return
    ;[order[index], order[destination]] = [order[destination], order[index]]
    void updateMembers({ order }, 'Slide order updated.')
  }

  return <section className="stack-shelf" id="slide-stacks" aria-labelledby="slide-stack-shelf-title">
    <div className="stack-shelf-heading">
      <div className="stack-shelf-title"><span className="stack-shelf-icon"><Stack weight="fill" /></span><div><h3 id="slide-stack-shelf-title">Slide stacks</h3><p>Keep serial sections and stains together.</p></div></div>
      <button type="button" className="stack-shelf-new" onClick={() => { setMode(mode === 'new' ? null : 'new'); setExpandedId(''); setExpanded(null) }}><Plus /> New stack</button>
    </div>

    {mode === 'new' ? <div className="stack-create-panel">
      <div><strong>Choose the first slide</strong><span>It becomes the starting reference. You can change this later.</span></div>
      <label>Stack name<input value={newName} placeholder="e.g. Breast biopsy · Block A" onChange={(event) => setNewName(event.target.value)} /></label>
      <label>First slide<select value={newReferenceId} onChange={(event) => setNewReferenceId(event.target.value)}><option value="">Choose a ready slide…</option>{readySlides.map((slide) => <option key={slide.id} value={slide.id}>{slide.stain || 'Unspecified'} · {slide.displayName}</option>)}</select></label>
      <div className="stack-create-actions"><button type="button" onClick={() => setMode(null)}>Cancel</button><button type="button" className="primary" disabled={busy || !newReferenceId} onClick={() => void createStack()}>{busy ? <SpinnerGap className="spin" /> : <Plus />} Create stack</button></div>
    </div> : null}

    {sets.length ? <div className="stack-shelf-row">{sets.map((set) => {
      const open = expandedId === set.id
      const previews = set.members.slice(0, 3)
      return <button type="button" className={`stack-shelf-card${open ? ' is-open' : ''}`} aria-expanded={open} aria-controls={`stack-${set.id}`} key={set.id} onClick={() => void toggleStack(set.id)}>
        <span className="stack-card-preview" aria-hidden="true">{previews.map((member, index) => member.thumbnailUrl ? <img key={member.slideId} src={member.thumbnailUrl} alt="" style={{ '--stack-index': index } as CSSProperties} /> : <span key={member.slideId} style={{ '--stack-index': index } as CSSProperties}><ImageSquare /></span>)}</span>
        <span className="stack-card-copy"><strong>{set.name}</strong><small>{set.members.length} slide{set.members.length === 1 ? '' : 's'} · {set.status}</small><span>{set.members.slice(0, 4).map((member) => member.stain || 'Unspecified').join(' · ')}</span></span>
        {open ? <CaretDown /> : <CaretRight />}
      </button>
    })}</div> : <button type="button" className="stack-shelf-empty" onClick={() => setMode('new')}><span className="stack-card-preview empty"><ImageSquare /></span><span><strong>Create your first slide stack</strong><small>Start with any H&E, IHC, or special stain.</small></span><ArrowRight /></button>}

    {expanded ? <div className="stack-expanded" id={`stack-${expanded.id}`}>
      <div className="stack-expanded-heading"><div><span>Open stack</span><h4>{expanded.name}</h4></div><a href={`/admin/comparisons/${expanded.id}`}>View side by side <ArrowRight /></a></div>
      <div className="stack-member-strip" aria-label="Slides in stack">{expanded.members.map((member, index) => <article
        className={`stack-member-card${draggedId === member.slideId ? ' is-dragging' : ''}`}
        key={member.slideId}
        draggable={!busy}
        tabIndex={0}
        aria-label={`${member.stain || 'Unspecified'} ${member.displayName}, position ${index + 1} of ${expanded.members.length}. Use Left and Right arrow keys to reorder.`}
        onDragStart={() => setDraggedId(member.slideId)}
        onDragEnd={() => setDraggedId('')}
        onDragOver={(event) => event.preventDefault()}
        onDrop={() => moveBefore(member.slideId)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowLeft') { event.preventDefault(); moveBy(member.slideId, -1) }
          if (event.key === 'ArrowRight') { event.preventDefault(); moveBy(member.slideId, 1) }
        }}
      >
        <span className="stack-member-grip" title="Drag to reorder"><DotsSixVertical /><em>{index + 1}</em></span>
        <div className="stack-member-image">{member.thumbnailUrl ? <img src={member.thumbnailUrl} alt="" /> : <ImageSquare />}</div>
        <div className="stack-member-copy"><strong>{member.stain || 'Unspecified'}</strong><span>{member.displayName}</span><small data-ready={memberState(expanded, member.slideId) === 'Aligned' || member.slideId === expanded.referenceSlideId}>{memberState(expanded, member.slideId)}</small></div>
      </article>)}</div>

      <div className="stack-quick-actions">
        <button type="button" className="stack-dropzone" disabled={busy || expanded.members.length + uploads.length >= 12} onClick={() => fileInput.current?.click()} onDragOver={(event) => { event.preventDefault(); event.currentTarget.dataset.drag = 'true' }} onDragLeave={(event) => { delete event.currentTarget.dataset.drag }} onDrop={(event) => { event.preventDefault(); delete event.currentTarget.dataset.drag; queueFiles(Array.from(event.dataTransfer.files)) }}><UploadSimple /><span><strong>Drop stained slides here</strong><small>or click to choose OME-TIFF files</small></span></button>
        <input ref={fileInput} className="visually-hidden" type="file" multiple accept=".ome.tif,.ome.tiff,image/tiff" onChange={(event) => queueFiles(Array.from(event.target.files ?? []))} />
        <button type="button" className="stack-library-button" disabled={busy || expanded.members.length >= 12} onClick={() => setMode(mode === 'link' ? null : 'link')}><FolderOpen /><span><strong>Add from library</strong><small>Link an existing slide</small></span></button>
      </div>

      {uploads.length ? <div className="stack-upload-queue"><div className="stack-subheading"><strong>Ready to add</strong><span>We identified stains from the filenames. Check them before uploading.</span></div>{uploads.map((item) => <div className="stack-upload-row" key={item.id}><span className="stack-file-icon"><ImageSquare /></span><label>Slide name<input value={item.displayName} disabled={item.status === 'uploading'} onChange={(event) => updateUpload(item.id, { displayName: event.target.value })} /></label><label>Stain or marker<input value={item.stain} disabled={item.status === 'uploading'} onChange={(event) => updateUpload(item.id, { stain: event.target.value })} /></label><span className="stack-upload-state">{item.status === 'uploading' ? `${Math.round(item.progress)}%` : item.status}</span><button type="button" aria-label={`Remove ${item.file.name}`} disabled={item.status === 'uploading'} onClick={() => setUploads((current) => current.filter((value) => value.id !== item.id))}><Trash /></button></div>)}<button type="button" className="primary stack-upload-submit" disabled={busy} onClick={() => void uploadQueued()}><UploadSimple /> Upload {uploads.length} slide{uploads.length === 1 ? '' : 's'}</button></div> : null}

      {mode === 'link' ? <div className="stack-library-picker"><div className="stack-subheading"><strong>Add from library</strong><span>Choose slides already stored in PathLab. Files are never duplicated.</span></div><label>Search<input type="search" value={query} placeholder="Case, stain, organ, or slide name" onChange={(event) => setQuery(event.target.value)} /></label><div className="stack-suggestion-grid">{suggestions.map((candidate) => <label key={candidate.slideId} className={selectedSlides.has(candidate.slideId) ? 'is-selected' : ''}><input type="checkbox" checked={selectedSlides.has(candidate.slideId)} onChange={(event) => setSelectedSlides((current) => { const next = new Set(current); if (event.target.checked) next.add(candidate.slideId); else next.delete(candidate.slideId); return next })} />{candidate.thumbnailUrl ? <img src={candidate.thumbnailUrl} alt="" /> : <span><ImageSquare /></span>}<b>{candidate.stain || 'Unspecified'}</b><small>{candidate.displayName}</small><em>{candidate.reasons.join(' · ')}</em></label>)}</div><div className="stack-create-actions"><button type="button" onClick={() => { setMode(null); setSelectedSlides(new Set()) }}>Cancel</button><button type="button" className="primary" disabled={busy || !selectedSlides.size || expanded.members.length + selectedSlides.size > 12} onClick={() => void linkSelected()}><LinkSimple /> Add {selectedSlides.size || ''} slide{selectedSlides.size === 1 ? '' : 's'}</button></div></div> : null}

      <details className="stack-advanced"><summary>Advanced alignment and removal</summary><p>Most stacks need no changes here. Choose another reference only when these sections belong to separate staining groups.</p><div>{expanded.members.map((member) => <article key={member.slideId}><span><b>{member.stain || 'Unspecified'}</b>{member.displayName}</span>{member.slideId !== expanded.referenceSlideId ? <><label>Align to<select value={member.anchorSlideId ?? expanded.referenceSlideId} disabled={busy} onChange={(event) => void updateMembers({ add: [{ slideId: member.slideId, anchorSlideId: event.target.value }] }, `Alignment reference updated for ${member.displayName}.`)}>{readyMembers.filter((anchor) => anchor.slideId !== member.slideId).map((anchor) => <option key={anchor.slideId} value={anchor.slideId}>{anchor.stain || 'Unspecified'} · {anchor.displayName}</option>)}</select></label><button type="button" disabled={busy} onClick={() => void updateMembers({ referenceSlideId: member.slideId }, `${member.displayName} is now the stack reference.`)}>Make reference</button><button type="button" className="danger-text" aria-label={`Remove ${member.displayName} from stack`} disabled={busy} onClick={() => void updateMembers({ remove: [member.slideId] }, `${member.displayName} was removed from the stack.`)}><Trash /> Remove</button></> : <span className="stack-reference-label">Stack reference</span>}</article>)}</div></details>
    </div> : null}
    {message ? <p className="stack-shelf-message" role="status">{message}</p> : null}
  </section>
}
