import { ArrowsClockwise, LinkBreak, LinkSimple, Plus, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getComparisonSet, getSharedComparisonSet } from '../api'
import { alignmentViewDelta, intersectSupport, mapComparisonBounds, mapComparisonPoint, mapSupportBounds, normalizeRotation, withinSupport, type Support } from '../alignment'
import { Brand } from '../components/Brand'
import { type ImageViewport, OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { Loader } from '../components/Loader'
import type { ComparisonMember, ComparisonSet } from '../types'

const MAX_PANES = 4

function transform(member: ComparisonMember, referenceId: string) {
  return member.slideId === referenceId ? null : member.registration?.movingToReference ?? null
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
  const [notice, setNotice] = useState('')
  const handles = useRef(new Map<string, ViewerHandle>())
  const openedSlides = useRef(new Set<string>())
  const initializedPanes = useRef('')
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
  const synchronize = useCallback((source: ComparisonMember, snapshot: ImageViewport) => {
    if (!comparison || !linked) return
    if (source.slideId !== comparison.referenceSlideId && source.registration?.status !== 'ready') {
      setNotice(`Synchronization suspended because ${source.displayName} is not aligned.`)
      return
    }
    if (!withinSupport([snapshot.centerX, snapshot.centerY], source.registration?.movingSupport ?? null)) {
      setNotice(`Alignment suspended outside supported tissue on ${source.displayName}.`)
      return
    }
    const referencePoint = mapComparisonPoint(
      [snapshot.centerX, snapshot.centerY],
      transform(source, comparison.referenceSlideId),
      null,
    )
    const suspended: string[] = []
    for (const targetId of panes) {
      if (targetId === source.slideId) continue
      const target = comparison.members.find((member) => member.slideId === targetId)
      if (!target) continue
      if (!openedSlides.current.has(targetId)) continue
      if (target.slideId !== comparison.referenceSlideId && target.registration?.status !== 'ready') {
        suspended.push(target.displayName)
        continue
      }
      if (!withinSupport(referencePoint, target.registration?.referenceSupport ?? null)) {
        suspended.push(target.displayName)
        continue
      }
      const [centerX, centerY] = mapComparisonPoint(referencePoint, null, transform(target, comparison.referenceSlideId))
      const viewDelta = alignmentViewDelta(
        transform(source, comparison.referenceSlideId),
        transform(target, comparison.referenceSlideId),
      )
      handles.current.get(targetId)?.setImageViewport({
        centerX, centerY,
        imageZoom: snapshot.imageZoom * viewDelta.zoomScale,
        rotation: normalizeRotation(snapshot.rotation + viewDelta.rotation),
      })
    }
    setNotice(suspended.length ? `Synchronization suspended for ${suspended.join(', ')} because reliable correspondence is unavailable.` : '')
  }, [comparison, linked, panes])
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
    const referenceBounds = comparison
      ? commonReferenceBounds(comparison, panes.filter((id) => openedSlides.current.has(id)))
      : null
    const bounds = comparison && anchorMember && referenceBounds
      ? mapComparisonBounds(referenceBounds, null, transform(anchorMember, comparison.referenceSlideId))
      : null
    if (bounds) anchor?.fitImageBounds(bounds)
    else anchor?.home()
    window.requestAnimationFrame(alignOpenedPanes)
  }, [alignOpenedPanes, comparison, linked, panes])
  if (!comparison && !notice) return <Loader label="Opening comparison…" size="large" fullscreen />
  if (!comparison) return <main className="viewer-message"><h1>{notice}</h1></main>
  const anchorIds = new Set(comparison.members.flatMap((member) => member.registration?.anchorSlideId ? [member.registration.anchorSlideId] : []))
  return <div className="comparison-shell">
    <header className="comparison-header"><Brand variant="library" /><div className="comparison-heading"><strong>{comparison.name}</strong><span>{comparison.status} · {comparison.members.length} slides</span></div><button type="button" aria-pressed={linked} onClick={() => setLinked((value) => !value)}>{linked ? <LinkSimple /> : <LinkBreak />}{linked ? 'Views linked' : 'Views independent'}</button><button type="button" onClick={resetView}><ArrowsClockwise /> Reset</button></header>
    {notice ? <div className="comparison-notice" role="status">{notice}</div> : null}
    <main className={`comparison-grid comparison-grid--${panes.length}`}>
      {panes.map((slideId, paneIndex) => {
        const member = comparison.members.find((candidate) => candidate.slideId === slideId)!
        const aligned = member.slideId === comparison.referenceSlideId || member.registration?.status === 'ready'
        const anchor = member.registration?.anchorSlideId
          ? comparison.members.find((candidate) => candidate.slideId === member.registration?.anchorSlideId)
          : null
        const alignmentLabel = member.slideId === comparison.referenceSlideId
          ? 'Primary reference'
          : anchorIds.has(member.slideId)
            ? 'Reference anchor'
            : anchor && anchor.slideId !== comparison.referenceSlideId
              ? `Aligned via ${anchor.displayName}`
              : 'Aligned'
        return <section className="comparison-pane" key={`${paneIndex}-${slideId}`}>
          <header><select aria-label={`Slide shown in pane ${paneIndex + 1}`} value={slideId} onChange={(event) => setPanes((current) => current.map((id, index) => index === paneIndex ? event.target.value : id))}>{comparison.members.filter((candidate) => !panes.includes(candidate.slideId) || candidate.slideId === slideId).map((candidate) => <option key={candidate.slideId} value={candidate.slideId}>{candidate.stain || 'Unspecified stain'} · {candidate.displayName}</option>)}</select><span aria-live="polite" className={aligned ? 'alignment-ready' : 'alignment-unavailable'}>{aligned ? alignmentLabel : 'Not aligned'}</span>{panes.length > 2 ? <button type="button" aria-label={`Close ${member.displayName} pane`} onClick={() => setPanes((current) => current.filter((_, index) => index !== paneIndex))}><X /></button> : null}</header>
          <OpenSeadragonViewer tileSource={member.tileSource} onReady={(handle) => handles.current.set(slideId, handle)} onOpen={() => {
            openedSlides.current.add(slideId)
            initializeOpenedPanes()
          }} micronsPerPixel={member.metadata?.physicalSizeX} onViewportChange={(snapshot) => synchronize(member, snapshot)} networkProfile={{ initialJobLimit: 2, maximumJobLimit: panes.length > 2 ? 2 : 4 }} />
          {!member.metadata?.physicalSizeX ? <small className="comparison-relative-scale">Relative scale: physical pixel size unavailable</small> : null}
        </section>
      })}
    </main>
    {panes.length < Math.min(MAX_PANES, comparison.members.length) ? <button type="button" className="comparison-add-pane" onClick={() => { const next = comparison.members.find((member) => !panes.includes(member.slideId)); if (next) setPanes((current) => [...current, next.slideId]) }}><Plus /> Add pane</button> : null}
  </div>
}
