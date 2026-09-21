import {
  ArrowClockwise,
  ArrowDown,
  ArrowUp,
  LinkSimple,
  Plus,
  SlidersHorizontal,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'

import {
  createComparisonSet,
  getComparisonSet,
  getSlideStacks,
  getStackSuggestions,
  reserveStackUpload,
  updateStackMembers,
} from '../../api'
import { startTusUpload } from '../../upload'
import type {
  ComparisonSet,
  LibrarySlide,
  LibrarySlideDetails,
  SlideStackSummary,
  StackSuggestion,
} from '../../types'

type Mode = 'upload' | 'link' | 'manage' | null
type UploadItem = {
  id: string
  file: File
  displayName: string
  stain: string
  anchorSlideId: string
  progress: number
  status: 'queued' | 'uploading' | 'processing' | 'error'
  error: string
}

interface SlideStackSectionProps {
  slide: LibrarySlide | LibrarySlideDetails
  enabled: boolean
}

export function SlideStackSection({ slide, enabled }: SlideStackSectionProps) {
  const [stacks, setStacks] = useState<SlideStackSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [stack, setStack] = useState<ComparisonSet | null>(null)
  const [mode, setMode] = useState<Mode>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [suggestions, setSuggestions] = useState<StackSuggestion[]>([])
  const [suggestionQuery, setSuggestionQuery] = useState('')
  const [selectedSlides, setSelectedSlides] = useState<Set<string>>(() => new Set())
  const [linkAnchor, setLinkAnchor] = useState('')

  async function refreshStacks(preferredId?: string) {
    const values = await getSlideStacks(slide.id)
    setStacks(values)
    const nextId = preferredId ?? selectedId ?? values[0]?.id ?? ''
    const validId = values.some((value) => value.id === nextId) ? nextId : values[0]?.id ?? ''
    setSelectedId(validId)
    if (validId) {
      const value = await getComparisonSet(validId)
      setStack(value)
      setLinkAnchor((current) => current && value.members.some((member) => member.slideId === current)
        ? current
        : value.referenceSlideId)
    } else {
      setStack(null)
    }
  }

  useEffect(() => {
    if (!enabled) return
    let active = true
    void getSlideStacks(slide.id).then(async (values) => {
      if (!active) return
      setStacks(values)
      const first = values[0]?.id ?? ''
      setSelectedId(first)
      if (first) setStack(await getComparisonSet(first))
    }).catch(() => active && setMessage('Slide stacks could not be loaded.'))
    return () => { active = false }
  }, [enabled, slide.id])

  useEffect(() => {
    if (mode !== 'link') return
    let active = true
    void getStackSuggestions(slide.id, suggestionQuery).then((values) => {
      if (!active) return
      const members = new Set(stack?.members.map((member) => member.slideId) ?? [])
      setSuggestions(values.filter((value) => !members.has(value.slideId)))
    }).catch(() => active && setMessage('Slide suggestions could not be loaded.'))
    return () => { active = false }
  }, [mode, slide.id, stack?.id, stack?.members, suggestionQuery])

  const awaitingUpdates = Boolean(stack && (
    ['queued', 'running'].includes(stack.status)
    || stack.members.some((member) => !member.tileSource)
  ))
  useEffect(() => {
    if (!enabled || !selectedId || !awaitingUpdates) return
    let active = true
    const timer = window.setInterval(() => {
      void getComparisonSet(selectedId).then((value) => {
        if (active) setStack(value)
      }).catch(() => undefined)
    }, 5000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [awaitingUpdates, enabled, selectedId])

  const readyAnchors = useMemo(
    () => stack?.members.filter((member) => member.tileSource) ?? [],
    [stack],
  )
  if (!enabled) return null

  async function createStack() {
    setBusy(true); setMessage('')
    try {
      const created = await createComparisonSet(
        `${slide.caseId || slide.displayName} slide stack`, [slide.id], slide.id,
      )
      await refreshStacks(created.id)
      setMessage('Slide stack created. Add uploaded or existing stained slides.')
    } catch {
      setMessage('Slide stack could not be created.')
    } finally { setBusy(false) }
  }

  async function chooseStack(id: string) {
    setSelectedId(id); setMode(null); setMessage('')
    setStack(await getComparisonSet(id))
  }

  function addUploadFiles(files: File[]) {
    if (!stack) return
    const remaining = Math.max(0, 12 - stack.members.length - uploads.length)
    setUploads((current) => [...current, ...files.slice(0, remaining).map((file, index) => ({
      id: `${file.name}-${file.size}-${Date.now()}-${index}`,
      file,
      displayName: file.name.replace(/\.ome\.tiff?$/i, ''),
      stain: '',
      anchorSlideId: stack.referenceSlideId,
      progress: 0,
      status: 'queued' as const,
      error: '',
    }))])
  }

  function updateUpload(id: string, changes: Partial<UploadItem>) {
    setUploads((current) => current.map((item) => item.id === id ? { ...item, ...changes } : item))
  }

  async function uploadAll() {
    if (!stack || uploads.some((item) => !item.stain.trim())) {
      setMessage('Enter the stain or marker for every upload.')
      return
    }
    setBusy(true); setMessage('')
    let current = stack
    for (const item of uploads.filter((value) => value.status === 'queued' || value.status === 'error')) {
      try {
        const reservation = await reserveStackUpload(current.id, item.file, {
          version: current.version,
          displayName: item.displayName,
          stain: item.stain,
          anchorSlideId: item.anchorSlideId,
          folderId: slide.folderId,
          caseId: slide.caseId,
          organSite: slide.organSite,
        })
        updateUpload(item.id, { status: 'uploading', progress: 0, error: '' })
        await startTusUpload(item.file, reservation.uploadUrl, reservation.uploadToken, {
          progress: (progress) => updateUpload(item.id, { progress }),
          success: () => updateUpload(item.id, { status: 'processing', progress: 100 }),
          error: (error) => updateUpload(item.id, { status: 'error', error }),
        })
        current = await getComparisonSet(current.id)
        setStack(current)
      } catch {
        updateUpload(item.id, { status: 'error', error: 'Upload paused. Retry this file.' })
        setMessage('One or more uploads need attention.')
        break
      }
    }
    await refreshStacks(current.id)
    setBusy(false)
  }

  async function linkSlides() {
    if (!stack || !selectedSlides.size) return
    setBusy(true); setMessage('')
    try {
      const updated = await updateStackMembers(stack.id, {
        version: stack.version,
        add: [...selectedSlides].map((slideId) => ({ slideId, anchorSlideId: linkAnchor })),
      })
      setStack(updated); setSelectedSlides(new Set()); setMode(null)
      await refreshStacks(updated.id)
      setMessage('Slides linked. Alignment was queued for ready members.')
    } catch {
      setMessage('Slides could not be linked. Refresh the stack and try again.')
    } finally { setBusy(false) }
  }

  async function updateOrganization(payload: {
    add?: Array<{ slideId: string; anchorSlideId: string }>
    remove?: string[]
    referenceSlideId?: string
    order?: string[]
  }, successMessage: string) {
    if (!stack) return
    setBusy(true); setMessage('')
    try {
      const updated = await updateStackMembers(stack.id, {
        version: stack.version,
        add: payload.add ?? [],
        ...payload,
      })
      setStack(updated)
      await refreshStacks(updated.id)
      setMessage(successMessage)
    } catch {
      setMessage('The stack changed elsewhere or could not be updated. Refresh and try again.')
    } finally { setBusy(false) }
  }

  function moveMember(slideId: string, direction: -1 | 1) {
    if (!stack) return
    const order = stack.members.map((member) => member.slideId)
    const index = order.indexOf(slideId)
    const destination = index + direction
    if (index < 0 || destination < 0 || destination >= order.length) return
    ;[order[index], order[destination]] = [order[destination], order[index]]
    void updateOrganization({ order }, 'Slide order updated.')
  }

  return <section className="slide-stack-section" aria-label="Slide stack">
    <div className="slide-stack-heading">
      <div><h4>Slide stack</h4><p>Link serial sections and synchronized stains.</p></div>
      <button type="button" aria-label="Refresh slide stack" onClick={() => void refreshStacks()}><ArrowClockwise /></button>
    </div>
    {!stacks.length ? <button type="button" className="primary" disabled={busy || !['ready_private', 'published'].includes(slide.state)} onClick={() => void createStack()}><Plus /> Create stack</button> : <>
      <div className="slide-stack-picker"><label>Stack<select aria-label="Slide stack" value={selectedId} onChange={(event) => void chooseStack(event.target.value)}>{stacks.map((value) => <option key={value.id} value={value.id}>{value.name} · {value.memberCount} slides</option>)}</select></label><button type="button" disabled={busy} onClick={() => void createStack()}><Plus /> New stack</button></div>
      {stack ? <>
        <div className="slide-stack-members">{stack.members.map((member) => <article key={member.slideId} data-state={member.availabilityReason ?? member.registration?.status ?? 'ready'}><span><b>{member.stain || 'Unspecified'}</b> {member.displayName}<small>{member.slideId === stack.referenceSlideId ? 'Reference' : member.availabilityReason?.replaceAll('_', ' ') ?? member.registration?.status ?? 'Waiting for alignment'}</small></span>{mode === 'manage' ? <div className="slide-stack-member-tools"><button type="button" aria-label={`Move ${member.displayName} up`} disabled={busy || stack.members[0].slideId === member.slideId} onClick={() => moveMember(member.slideId, -1)}><ArrowUp /></button><button type="button" aria-label={`Move ${member.displayName} down`} disabled={busy || stack.members.at(-1)?.slideId === member.slideId} onClick={() => moveMember(member.slideId, 1)}><ArrowDown /></button><button type="button" disabled={busy || member.slideId === stack.referenceSlideId || !member.tileSource} onClick={() => void updateOrganization({ referenceSlideId: member.slideId }, `${member.displayName} is now the reference slide.`)}>Make reference</button><button type="button" className="danger" aria-label={`Remove ${member.displayName} from stack`} disabled={busy || member.slideId === stack.referenceSlideId || stack.members.length <= 1} title={member.slideId === stack.referenceSlideId ? 'Choose another reference before removing this slide.' : undefined} onClick={() => void updateOrganization({ remove: [member.slideId] }, `${member.displayName} was removed from this stack.`)}><Trash /></button>{member.slideId !== stack.referenceSlideId ? <label>Align to<select aria-label={`Alignment anchor for ${member.displayName}`} value={member.anchorSlideId ?? stack.referenceSlideId} disabled={busy} onChange={(event) => void updateOrganization({ add: [{ slideId: member.slideId, anchorSlideId: event.target.value }] }, `Alignment anchor updated for ${member.displayName}.`)}>{readyAnchors.filter((anchor) => anchor.slideId !== member.slideId).map((anchor) => <option key={anchor.slideId} value={anchor.slideId}>{anchor.stain || 'Unspecified'} · {anchor.displayName}</option>)}</select></label> : null}</div> : null}</article>)}</div>
        <a className="slide-stack-open" href={`/admin/comparisons/${stack.id}`}>Open stack</a>
        <div className="slide-stack-actions"><button type="button" disabled={busy || stack.members.length >= 12} onClick={() => setMode(mode === 'upload' ? null : 'upload')}><UploadSimple /> Add stained slides</button><button type="button" disabled={busy || stack.members.length >= 12} onClick={() => setMode(mode === 'link' ? null : 'link')}><LinkSimple /> Link existing slides</button><button type="button" disabled={busy} onClick={() => setMode(mode === 'manage' ? null : 'manage')}><SlidersHorizontal /> Organize</button></div>
      </> : null}
    </>}
    {mode === 'upload' && stack ? <div className="slide-stack-workflow">
      <label className="slide-stack-file">Choose OME-TIFF files<input type="file" multiple accept=".ome.tif,.ome.tiff,image/tiff" onChange={(event) => addUploadFiles(Array.from(event.target.files ?? []))} /></label>
      {uploads.map((item) => <article key={item.id}><strong>{item.file.name}</strong><label>Display name<input value={item.displayName} disabled={item.status === 'uploading'} onChange={(event) => updateUpload(item.id, { displayName: event.target.value })} /></label><label>Stain or marker<input value={item.stain} disabled={item.status === 'uploading'} placeholder="e.g. HER2, CD3, PAS" onChange={(event) => updateUpload(item.id, { stain: event.target.value })} /></label><label>Align to<select value={item.anchorSlideId} disabled={item.status === 'uploading'} onChange={(event) => updateUpload(item.id, { anchorSlideId: event.target.value })}>{readyAnchors.map((member) => <option key={member.slideId} value={member.slideId}>{member.stain || 'Unspecified'} · {member.displayName}</option>)}</select></label><span>{item.status === 'uploading' ? `Uploading ${Math.round(item.progress)}%` : item.status}{item.error ? ` · ${item.error}` : ''}</span></article>)}
      <button type="button" className="primary" disabled={busy || !uploads.length} onClick={() => void uploadAll()}>{busy ? 'Uploading…' : 'Upload and attach'}</button>
    </div> : null}
    {mode === 'link' && stack ? <div className="slide-stack-workflow">
      <label>Find slides<input type="search" value={suggestionQuery} placeholder="Name, case, organ, or stain" onChange={(event) => setSuggestionQuery(event.target.value)} /></label>
      <label>Align selected slides to<select value={linkAnchor} onChange={(event) => setLinkAnchor(event.target.value)}>{readyAnchors.map((member) => <option key={member.slideId} value={member.slideId}>{member.stain || 'Unspecified'} · {member.displayName}</option>)}</select></label>
      <div className="slide-stack-suggestions">{suggestions.map((candidate) => <label key={candidate.slideId}><input type="checkbox" checked={selectedSlides.has(candidate.slideId)} onChange={(event) => setSelectedSlides((current) => { const next = new Set(current); if (event.target.checked) next.add(candidate.slideId); else next.delete(candidate.slideId); return next })} />{candidate.thumbnailUrl ? <img src={candidate.thumbnailUrl} alt="" /> : null}<span><b>{candidate.stain || 'Unspecified'} · {candidate.displayName}</b><small>{candidate.caseId || 'No case ID'} · {candidate.reasons.join(', ')}</small></span></label>)}</div>
      <button type="button" className="primary" disabled={busy || !selectedSlides.size || stack.members.length + selectedSlides.size > 12} onClick={() => void linkSlides()}>{busy ? 'Linking…' : `Link ${selectedSlides.size || ''} slides`}</button>
    </div> : null}
    {message ? <p className="slide-stack-message" role="status">{message}</p> : null}
  </section>
}
