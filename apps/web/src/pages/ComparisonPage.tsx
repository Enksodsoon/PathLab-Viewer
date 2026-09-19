import { Plus, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getComparisonSet, getSharedComparisonSet, reregisterComparisonSet } from '../api'
import { alignmentViewDelta, hasLocalEvidence, intersectSupport, localAlignmentViewDelta, mapComparisonBounds, mapComparisonPoint, mapLocalComparisonPoint, mapSupportBounds, normalizeRotation, type Support } from '../alignment'
import { Brand } from '../components/Brand'
import { type ImageViewport, OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { Loader } from '../components/Loader'
import type { ComparisonMember, ComparisonSet } from '../types'

const MAX_PANES = 4
type AlignmentMode = 'independent' | 'matched' | 'approximate'
type ZoomMode = 'physical' | 'tissue'

function transform(member: ComparisonMember, referenceId: string) {
  return member.slideId === referenceId ? null : member.registration?.movingToReference ?? null
}

function localRegistration(member: ComparisonMember, referenceId: string) {
  return member.slideId === referenceId ? null : member.registration
}

function pairRegistrations(source: ComparisonMember, target: ComparisonMember, primaryReferenceId: string) {
  const sourceRegistration = source.slideId === primaryReferenceId ? null : source.registration
  const targetRegistration = target.slideId === primaryReferenceId ? null : target.registration
  if (source.slideId === targetRegistration?.anchorSlideId) return [null, targetRegistration] as const
  if (target.slideId === sourceRegistration?.anchorSlideId) return [sourceRegistration, null] as const
  if (sourceRegistration?.anchorSlideId && sourceRegistration.anchorSlideId === targetRegistration?.anchorSlideId) {
    return [sourceRegistration, targetRegistration] as const
  }
  const sourceCoordinates = source.slideId === primaryReferenceId
    ? primaryReferenceId
    : sourceRegistration?.coordinateReferenceId ?? primaryReferenceId
  const targetCoordinates = target.slideId === primaryReferenceId
    ? primaryReferenceId
    : targetRegistration?.coordinateReferenceId ?? primaryReferenceId
  return sourceCoordinates === primaryReferenceId && targetCoordinates === primaryReferenceId
    ? [sourceRegistration, targetRegistration] as const
    : null
}

function matchedFocusBounds(source: ComparisonMember, target: ComparisonMember, primaryReferenceId: string): Exclude<Support, null> | null {
  const pair = pairRegistrations(source, target, primaryReferenceId)
  if (!pair) return null
  const [sourceRegistration, targetRegistration] = pair
  const triangles = sourceRegistration?.triangles?.map((triangle) => triangle.moving)
    ?? targetRegistration?.triangles?.map((triangle) => triangle.reference)
  if (!triangles?.length) return null
  const area = (triangle: [[number, number], [number, number], [number, number]]) => Math.abs(
    (triangle[1][0] - triangle[0][0]) * (triangle[2][1] - triangle[0][1])
    - (triangle[1][1] - triangle[0][1]) * (triangle[2][0] - triangle[0][0]),
  )
  const triangle = [...triangles].sort((left, right) => area(right) - area(left))[0]
  const centerX = triangle.reduce((sum, point) => sum + point[0], 0) / 3
  const centerY = triangle.reduce((sum, point) => sum + point[1], 0) / 3
  const width = Math.max(...triangle.map((point) => point[0])) - Math.min(...triangle.map((point) => point[0]))
  const height = Math.max(...triangle.map((point) => point[1])) - Math.min(...triangle.map((point) => point[1]))
  return [centerX - width * 0.22, centerY - height * 0.22, centerX + width * 0.22, centerY + height * 0.22]
}

function commonReferenceBounds(comparison: ComparisonSet, slideIds: string[]): Exclude<Support, null> | null {
  const reference = comparison.members.find((member) => member.slideId === comparison.referenceSlideId)
  if (!reference?.metadata) return null
  let common: Exclude<Support, null> = [0, 0, reference.metadata.width, reference.metadata.height]
  let eligibleTargets = 0
  for (const slideId of slideIds) {
    if (slideId === comparison.referenceSlideId) continue
    const member = comparison.members.find((candidate) => candidate.slideId === slideId)
    const registration = member?.registration
    if (!member || registration?.status !== 'ready' || !registration.movingToReference) continue
    if (!registration.movingSupport && !member.metadata) continue
    const movingSupport: Exclude<Support, null> = registration.movingSupport
      ?? [0, 0, member.metadata!.width, member.metadata!.height]
    const mappedMoving = mapSupportBounds(movingSupport, registration.movingToReference)
    const referenceSupport: Exclude<Support, null> = registration.referenceSupport
      ?? [0, 0, reference.metadata.width, reference.metadata.height]
    const eligible = intersectSupport(mappedMoving, referenceSupport)
    if (!eligible) continue
    const next = intersectSupport(common, eligible)
    if (!next) return null
    common = next
    eligibleTargets += 1
  }
  return eligibleTargets ? common : null
}

export function ComparisonPage() {
  const { comparisonId = '', publicId } = useParams()
  const [comparison, setComparison] = useState<ComparisonSet | null>(null)
  const [panes, setPanes] = useState<string[]>([])
  const [linked, setLinked] = useState(true)
  const [unlinkedPanes, setUnlinkedPanes] = useState<Set<string>>(() => new Set())
  const [alignmentMode, setAlignmentMode] = useState<AlignmentMode>('matched')
  const [zoomMode, setZoomMode] = useState<ZoomMode>('physical')
  const [activePane, setActivePane] = useState(0)
  const [maximizedPane, setMaximizedPane] = useState<number | null>(null)
  const [scaleBars, setScaleBars] = useState<Record<string, { microns: number; width: number }>>({})
  const [display, setDisplay] = useState<Record<string, { brightness: number; contrast: number; gamma: number }>>({})
  const [notice, setNotice] = useState('')
  const [registering, setRegistering] = useState(false)
  const handles = useRef(new Map<string, ViewerHandle>())
  const openedSlides = useRef(new Set<string>())
  const initializedPanes = useRef('')
  const drivingPane = useRef<string | null>(null)
  const activeTransaction = useRef<string | null>(null)
  useEffect(() => {
    let active = true
    const request = publicId ? getSharedComparisonSet(publicId, comparisonId) : getComparisonSet(comparisonId)
    void request.then((value) => {
      if (!active) return
      setComparison(value)
      setPanes(value.members.slice(0, 2).map((member) => member.slideId))
    }).catch(() => { if (active) setNotice('Comparison set is unavailable.') })
    return () => { active = false }
  }, [comparisonId, publicId])
  useEffect(() => {
    if (!comparison || !['queued', 'running'].includes(comparison.status)) return
    const timer = window.setInterval(() => {
      const request = publicId ? getSharedComparisonSet(publicId, comparison.id) : getComparisonSet(comparison.id)
      void request.then(setComparison).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [comparison, publicId])
  const synchronize = useCallback((source: ComparisonMember, snapshot: ImageViewport, incomingTransaction?: string) => {
    if (!comparison || !linked || alignmentMode === 'independent') return
    if (unlinkedPanes.has(source.slideId)) return
    if (incomingTransaction && incomingTransaction === activeTransaction.current) return
    drivingPane.current = source.slideId
    const transactionId = `${source.slideId}:${performance.now().toFixed(3)}`
    activeTransaction.current = transactionId
    const sourceIsLocalAnchor = panes.some((targetId) => comparison.members
      .find((member) => member.slideId === targetId)?.registration?.anchorSlideId === source.slideId)
    if (source.slideId !== comparison.referenceSlideId && !sourceIsLocalAnchor) {
      if (source.registration?.status === 'rejected' || !source.registration) {
        setNotice(`Synchronization suspended because ${source.displayName} is not aligned.`)
        return
      }
      if (alignmentMode === 'matched' && !hasLocalEvidence(source.registration)) {
        setNotice(`Synchronization suspended because ${source.displayName} has only overview alignment.`)
        return
      }
    }
    const suspended: string[] = []
    for (const targetId of panes) {
      if (targetId === source.slideId) continue
      if (unlinkedPanes.has(targetId)) continue
      const target = comparison.members.find((member) => member.slideId === targetId)
      if (!target) continue
      if (!openedSlides.current.has(targetId)) continue
      const pair = pairRegistrations(source, target, comparison.referenceSlideId)
      if (!pair) {
        suspended.push(target.displayName)
        continue
      }
      const [sourceRegistration, targetRegistration] = pair
      const registrations = [sourceRegistration, targetRegistration].filter((item) => item !== null)
      const usable = registrations.every((registration) => registration?.status === 'ready'
        || (alignmentMode === 'approximate' && registration?.status === 'approximate'))
      if (!usable || (alignmentMode === 'matched' && registrations.some((registration) => !hasLocalEvidence(registration)))) {
        suspended.push(target.displayName)
        continue
      }
      const referencePoint = alignmentMode === 'matched'
        ? mapLocalComparisonPoint([snapshot.centerX, snapshot.centerY], sourceRegistration, null)
        : mapComparisonPoint([snapshot.centerX, snapshot.centerY], sourceRegistration?.movingToReference ?? null, null)
      if (!referencePoint) {
        suspended.push(target.displayName)
        continue
      }
      const targetPoint = alignmentMode === 'matched'
        ? mapLocalComparisonPoint(referencePoint, null, targetRegistration)
        : mapComparisonPoint(referencePoint, null, targetRegistration?.movingToReference ?? null)
      const viewDelta = alignmentMode === 'matched'
        ? localAlignmentViewDelta([snapshot.centerX, snapshot.centerY], sourceRegistration, targetRegistration)
        : alignmentViewDelta(transform(source, comparison.referenceSlideId), transform(target, comparison.referenceSlideId))
      if (!targetPoint || !viewDelta) {
        suspended.push(target.displayName)
        continue
      }
      const sourceMpp = source.metadata?.physicalSizeX
      const targetMpp = target.metadata?.physicalSizeX
      const zoomScale = zoomMode === 'physical' && sourceMpp && targetMpp
        ? targetMpp / sourceMpp
        : viewDelta.zoomScale
      handles.current.get(targetId)?.setImageViewport({
        centerX: targetPoint[0], centerY: targetPoint[1],
        imageZoom: snapshot.imageZoom * zoomScale,
        rotation: normalizeRotation(snapshot.rotation + viewDelta.rotation),
      }, transactionId)
    }
    setNotice(suspended.length ? `Synchronization suspended for ${suspended.join(', ')} because reliable correspondence is unavailable.` : '')
  }, [alignmentMode, comparison, linked, panes, unlinkedPanes, zoomMode])
  const alignOpenedPanes = useCallback(() => {
    if (!comparison || !linked) return
    const sourceId = panes.find((id) => id === comparison.referenceSlideId && openedSlides.current.has(id))
      ?? panes.find((id) => {
        const member = comparison.members.find((candidate) => candidate.slideId === id)
        return openedSlides.current.has(id) && member?.registration?.status === 'ready'
      })
    if (!sourceId) return
    const source = comparison.members.find((member) => member.slideId === sourceId)
    const handle = handles.current.get(sourceId)
    if (!source || !handle) return
    synchronize(source, handle.getImageViewport())
  }, [comparison, linked, panes, synchronize])
  const initializeOpenedPanes = useCallback(() => {
    if (!comparison || !linked) return
    const opened = panes.filter((id) => openedSlides.current.has(id))
    const key = opened.join('|')
    if (key === initializedPanes.current) return
    initializedPanes.current = key
    const anchorId = opened.includes(comparison.referenceSlideId)
      ? comparison.referenceSlideId
      : opened.find((id) => comparison.members.find((member) => member.slideId === id)?.registration?.status === 'ready')
    const anchor = comparison.members.find((member) => member.slideId === anchorId)
    const anchorHandle = anchorId ? handles.current.get(anchorId) : null
    if (anchor && anchorHandle && opened.length > 1) {
      const referenceBounds = commonReferenceBounds(comparison, opened)
      const anchorBounds = referenceBounds
        ? mapComparisonBounds(referenceBounds, null, transform(anchor, comparison.referenceSlideId))
        : null
      if (anchorBounds) anchorHandle.fitImageBounds(anchorBounds)
    }
    window.requestAnimationFrame(alignOpenedPanes)
  }, [alignOpenedPanes, comparison, linked, panes])
  useEffect(() => {
    if (!linked) return
    initializedPanes.current = ''
    const frame = window.requestAnimationFrame(initializeOpenedPanes)
    return () => window.cancelAnimationFrame(frame)
  }, [initializeOpenedPanes, linked])
  const resetView = useCallback(() => {
    if (!linked) {
      panes.forEach((slideId) => handles.current.get(slideId)?.home())
      return
    }
    const anchorId = panes.find((id) => id === comparison?.referenceSlideId && openedSlides.current.has(id))
      ?? panes.find((id) => openedSlides.current.has(id))
    if (!anchorId) return
    const anchor = handles.current.get(anchorId)
    const anchorMember = comparison?.members.find((member) => member.slideId === anchorId)
    const otherMember = comparison?.members.find((member) => panes.includes(member.slideId) && member.slideId !== anchorId)
    const referenceBounds = comparison
      ? commonReferenceBounds(comparison, panes.filter((id) => openedSlides.current.has(id)))
      : null
    const bounds = comparison && anchorMember && otherMember && alignmentMode === 'matched'
      ? matchedFocusBounds(anchorMember, otherMember, comparison.referenceSlideId)
      : comparison && anchorMember && referenceBounds
        ? mapComparisonBounds(referenceBounds, null, transform(anchorMember, comparison.referenceSlideId))
        : null
    if (bounds) anchor?.fitImageBounds(bounds)
    else anchor?.home()
    window.requestAnimationFrame(alignOpenedPanes)
  }, [alignOpenedPanes, alignmentMode, comparison, linked, panes])
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === '1' || event.key === '2' || event.key === '4') {
        const requested = Math.min(Number(event.key), comparison?.members.length ?? 1)
        setPanes((current) => {
          const next = [...current]
          for (const member of comparison?.members ?? []) if (next.length < requested && !next.includes(member.slideId)) next.push(member.slideId)
          return next.slice(0, requested)
        })
      }
      if (event.key.toLowerCase() === 'r') resetView()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [comparison, resetView])
  if (!comparison && !notice) return <Loader label="Opening comparison…" size="large" fullscreen />
  if (!comparison) return <main className="viewer-message"><h1>{notice}</h1></main>
  const setLayout = (count: number) => setPanes((current) => {
    const next = [...current]
    for (const member of comparison.members) if (next.length < count && !next.includes(member.slideId)) next.push(member.slideId)
    return next.slice(0, Math.min(count, comparison.members.length))
  })
  const anchorIds = new Set(comparison.members.flatMap((member) => member.registration?.anchorSlideId ? [member.registration.anchorSlideId] : []))
  return <div className="comparison-shell">
    <header className="comparison-header"><Brand variant="library" /><div className="comparison-heading"><strong>{comparison.name}</strong><span>{comparison.status} · {comparison.members.length} slides</span></div><label className="comparison-toolbar-field"><span>Layout</span><select aria-label="Pane layout" value={panes.length} onChange={(event) => { setMaximizedPane(null); setLayout(Number(event.target.value)) }}><option value="1">1 pane</option><option value="2">2 panes</option><option value="4">4 panes</option></select></label><label className="comparison-toolbar-field"><span>Alignment</span><select aria-label="Alignment mode" value={alignmentMode} onChange={(event) => { const mode = event.target.value as AlignmentMode; setAlignmentMode(mode); setLinked(mode !== 'independent') }}><option value="matched">Matched regions</option><option value="approximate">Approximate overview</option><option value="independent">Independent</option></select></label><label className="comparison-toolbar-field"><span>Zoom</span><select aria-label="Linked zoom mode" value={zoomMode} onChange={(event) => setZoomMode(event.target.value as ZoomMode)}><option value="physical">Equal µm/pixel</option><option value="tissue">Fit corresponding tissue</option></select></label><button type="button" aria-pressed={linked} onClick={() => { setLinked((value) => !value); if (linked) setAlignmentMode('independent'); else setAlignmentMode('matched') }}><span aria-hidden="true">{linked ? '⛓' : '⛓̸'}</span>{linked ? 'Views linked' : 'Views independent'}</button>{!publicId ? <button type="button" disabled={registering} onClick={() => { setRegistering(true); void reregisterComparisonSet(comparison.id).then(() => { setComparison((current) => current ? { ...current, status: 'queued' } : current); setNotice('Registration queued with the current anchors.') }).catch(() => setNotice('Registration could not be queued.')).finally(() => setRegistering(false)) }}>{registering ? 'Queuing…' : 'Re-register'}</button> : null}<button type="button" onClick={resetView}><span aria-hidden="true">↻</span> Reset</button></header>
    {notice ? <div className="comparison-notice" role="status">{notice}</div> : null}
    <div className="comparison-workstation"><aside className="comparison-tray" aria-label="Case slides"><strong>Case slides</strong>{comparison.members.map((member) => <button type="button" key={member.slideId} data-active={panes.includes(member.slideId)} onClick={() => setPanes((current) => current.map((id, index) => index === activePane ? member.slideId : id))}><img src={member.thumbnailUrl} alt="" loading="lazy" /><span><b>{member.stain || 'Unspecified'}</b><small>{member.displayName}</small></span></button>)}</aside>
    <main className={`comparison-grid comparison-grid--${panes.length}`} data-maximized={maximizedPane === null ? undefined : maximizedPane}>
      {panes.map((slideId, paneIndex) => {
        const member = comparison.members.find((candidate) => candidate.slideId === slideId)!
        const aligned = member.slideId === comparison.referenceSlideId
          || anchorIds.has(member.slideId)
          || (member.registration?.status === 'ready' && hasLocalEvidence(member.registration))
        const anchor = member.registration?.anchorSlideId
          ? comparison.members.find((candidate) => candidate.slideId === member.registration?.anchorSlideId)
          : null
        const alignmentLabel = member.slideId === comparison.referenceSlideId
          ? 'Primary reference'
          : anchorIds.has(member.slideId)
            ? 'Reference anchor'
            : anchor && anchor.slideId !== comparison.referenceSlideId
              ? `Locally aligned via ${anchor.displayName}`
              : 'Locally aligned'
        const adjustments = display[slideId] ?? { brightness: 1, contrast: 1, gamma: 1 }
        const paneLinked = linked && !unlinkedPanes.has(slideId)
        const evidence = member.registration?.evidence
        const residuals = member.registration?.controlPoints
          ?.map((point) => point.errorPixels)
          .filter((value) => Number.isFinite(value)) ?? []
        const medianResidual = residuals.length
          ? [...residuals].sort((left, right) => left - right)[Math.floor(residuals.length / 2)]
          : null
        return <section className="comparison-pane" data-active={paneIndex === activePane} data-hidden={maximizedPane !== null && maximizedPane !== paneIndex} key={`${paneIndex}-${slideId}`} onPointerDown={() => setActivePane(paneIndex)}>
          <header><select aria-label={`Slide shown in pane ${paneIndex + 1}`} value={slideId} onChange={(event) => setPanes((current) => current.map((id, index) => index === paneIndex ? event.target.value : id))}>{comparison.members.filter((candidate) => !panes.includes(candidate.slideId) || candidate.slideId === slideId).map((candidate) => <option key={candidate.slideId} value={candidate.slideId}>{candidate.stain || 'Unspecified stain'} · {candidate.displayName}</option>)}</select><span aria-live="polite" className={aligned ? 'alignment-ready' : 'alignment-unavailable'}>{aligned ? alignmentLabel : member.registration?.status === 'approximate' ? 'Approximate only' : member.registration?.status === 'ready' ? 'Overview only' : 'Not aligned'}</span><button type="button" aria-label={`${paneLinked ? 'Unlink' : 'Link'} ${member.displayName} pane`} aria-pressed={paneLinked} onClick={() => setUnlinkedPanes((current) => { const next = new Set(current); if (next.has(slideId)) next.delete(slideId); else next.add(slideId); return next })}><span aria-hidden="true">{paneLinked ? '⛓' : '⛓̸'}</span></button><button type="button" aria-label={`${maximizedPane === paneIndex ? 'Restore' : 'Maximize'} ${member.displayName} pane`} onClick={() => setMaximizedPane((current) => current === paneIndex ? null : paneIndex)}>{maximizedPane === paneIndex ? '↙' : '↗'}</button>{panes.length > 2 ? <button type="button" aria-label={`Close ${member.displayName} pane`} onClick={() => setPanes((current) => current.filter((_, index) => index !== paneIndex))}><X /></button> : null}</header>
          <OpenSeadragonViewer tileSource={member.tileSource} displayAdjustments={adjustments} onReady={(handle) => handles.current.set(slideId, handle)} onDispose={() => { handles.current.delete(slideId); openedSlides.current.delete(slideId) }} onOpen={() => {
            openedSlides.current.add(slideId)
            initializeOpenedPanes()
          }} micronsPerPixel={member.metadata?.physicalSizeX} onScaleChange={(microns, width) => setScaleBars((current) => ({ ...current, [slideId]: { microns, width } }))} onViewportChange={(snapshot, transactionId) => synchronize(member, snapshot, transactionId)} networkProfile={{ initialJobLimit: 2, maximumJobLimit: Math.max(1, Math.floor(8 / panes.length)) }} />
          <div className="comparison-crosshair" aria-hidden="true" />
          {scaleBars[slideId] ? <div className="comparison-scale-bar" style={{ width: scaleBars[slideId].width }}><i /><span>{scaleBars[slideId].microns >= 1000 ? `${scaleBars[slideId].microns / 1000} mm` : `${scaleBars[slideId].microns} µm`}</span></div> : null}
          <details className="comparison-display"><summary>Display</summary><label>Brightness<input type="range" min="0.5" max="1.5" step="0.05" value={adjustments.brightness} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, brightness: Number(event.target.value) } }))} /></label><label>Contrast<input type="range" min="0.5" max="1.5" step="0.05" value={adjustments.contrast} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, contrast: Number(event.target.value) } }))} /></label><label>Gamma<input type="range" min="0.5" max="2" step="0.05" value={adjustments.gamma} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, gamma: Number(event.target.value) } }))} /></label><button type="button" onClick={() => setDisplay((current) => ({ ...current, [slideId]: { brightness: 1, contrast: 1, gamma: 1 } }))}>Reset display</button></details>
          <details className="comparison-quality"><summary>Alignment quality</summary>{member.slideId === comparison.referenceSlideId ? <p>Primary coordinate reference.</p> : <dl><div><dt>Mode</dt><dd>{member.registration?.status ?? 'unavailable'}</dd></div><div><dt>Evidence</dt><dd>{evidence?.anatomicalMatchCount ?? 0} anatomical matches</dd></div><div><dt>Map</dt><dd>{evidence?.triangleCount ?? member.registration?.triangles?.length ?? 0} accepted cells</dd></div><div><dt>Median residual</dt><dd>{medianResidual === null ? 'Not measured' : `${medianResidual.toFixed(1)} px`}</dd></div><div><dt>Provenance</dt><dd>{member.registration?.provenance ?? 'none'}</dd></div></dl>}{member.registration?.reason ? <p>{member.registration.reason}</p> : null}</details>
          {!member.metadata?.physicalSizeX ? <small className="comparison-relative-scale">Relative scale: physical pixel size unavailable</small> : null}
        </section>
      })}
    </main></div>
    {panes.length < Math.min(MAX_PANES, comparison.members.length) ? <button type="button" className="comparison-add-pane" onClick={() => { const next = comparison.members.find((member) => !panes.includes(member.slideId)); if (next) setPanes((current) => [...current, next.slideId]) }}><Plus /> Add pane</button> : null}
  </div>
}
