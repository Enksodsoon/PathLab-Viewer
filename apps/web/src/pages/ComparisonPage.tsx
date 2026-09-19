import { ArrowsClockwise, LinkBreak, LinkSimple, Plus, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { getComparisonSet, getSharedComparisonSet } from '../api'
import { mapComparisonPoint, withinSupport } from '../alignment'
import { Brand } from '../components/Brand'
import { type ImageViewport, OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { Loader } from '../components/Loader'
import type { ComparisonMember, ComparisonSet } from '../types'

const MAX_PANES = 4

function transform(member: ComparisonMember, referenceId: string) {
  return member.slideId === referenceId ? null : member.registration?.movingToReference ?? null
}

export function ComparisonPage() {
  const { comparisonId = '', publicId } = useParams()
  const [comparison, setComparison] = useState<ComparisonSet | null>(null)
  const [panes, setPanes] = useState<string[]>([])
  const [linked, setLinked] = useState(true)
  const [notice, setNotice] = useState('')
  const handles = useRef(new Map<string, ViewerHandle>())
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
      if (target.slideId !== comparison.referenceSlideId && target.registration?.status !== 'ready') {
        suspended.push(target.displayName)
        continue
      }
      if (!withinSupport(referencePoint, target.registration?.referenceSupport ?? null)) {
        suspended.push(target.displayName)
        continue
      }
      const [centerX, centerY] = mapComparisonPoint(referencePoint, null, transform(target, comparison.referenceSlideId))
      const sourceMpp = source.metadata?.physicalSizeX
      const targetMpp = target.metadata?.physicalSizeX
      handles.current.get(targetId)?.setImageViewport({
        centerX, centerY,
        imageZoom: sourceMpp && targetMpp ? snapshot.imageZoom * targetMpp / sourceMpp : snapshot.imageZoom,
        rotation: snapshot.rotation,
      })
    }
    setNotice(suspended.length ? `Synchronization suspended for ${suspended.join(', ')} because reliable correspondence is unavailable.` : '')
  }, [comparison, linked, panes])
  if (!comparison && !notice) return <Loader label="Opening comparison…" size="large" fullscreen />
  if (!comparison) return <main className="viewer-message"><h1>{notice}</h1></main>
  return <div className="comparison-shell">
    <header className="comparison-header"><Brand variant="library" /><div className="comparison-heading"><strong>{comparison.name}</strong><span>{comparison.status} · {comparison.members.length} slides</span></div><button type="button" aria-pressed={linked} onClick={() => setLinked((value) => !value)}>{linked ? <LinkSimple /> : <LinkBreak />}{linked ? 'Views linked' : 'Views independent'}</button><button type="button" onClick={() => panes.forEach((slideId) => handles.current.get(slideId)?.home())}><ArrowsClockwise /> Reset</button></header>
    {notice ? <div className="comparison-notice" role="status">{notice}</div> : null}
    <main className={`comparison-grid comparison-grid--${panes.length}`}>
      {panes.map((slideId, paneIndex) => {
        const member = comparison.members.find((candidate) => candidate.slideId === slideId)!
        const aligned = member.slideId === comparison.referenceSlideId || member.registration?.status === 'ready'
        return <section className="comparison-pane" key={`${paneIndex}-${slideId}`}>
          <header><select aria-label={`Slide shown in pane ${paneIndex + 1}`} value={slideId} onChange={(event) => setPanes((current) => current.map((id, index) => index === paneIndex ? event.target.value : id))}>{comparison.members.filter((candidate) => !panes.includes(candidate.slideId) || candidate.slideId === slideId).map((candidate) => <option key={candidate.slideId} value={candidate.slideId}>{candidate.stain || 'Unspecified stain'} · {candidate.displayName}</option>)}</select><span aria-live="polite" className={aligned ? 'alignment-ready' : 'alignment-unavailable'}>{aligned ? (member.slideId === comparison.referenceSlideId ? 'Reference' : 'Aligned') : 'Not aligned'}</span>{panes.length > 2 ? <button type="button" aria-label={`Close ${member.displayName} pane`} onClick={() => setPanes((current) => current.filter((_, index) => index !== paneIndex))}><X /></button> : null}</header>
          <OpenSeadragonViewer tileSource={member.tileSource} onReady={(handle) => handles.current.set(slideId, handle)} micronsPerPixel={member.metadata?.physicalSizeX} onViewportChange={(snapshot) => synchronize(member, snapshot)} networkProfile={{ initialJobLimit: 2, maximumJobLimit: panes.length > 2 ? 2 : 4 }} />
          {!member.metadata?.physicalSizeX ? <small className="comparison-relative-scale">Relative scale: physical pixel size unavailable</small> : null}
        </section>
      })}
    </main>
    {panes.length < Math.min(MAX_PANES, comparison.members.length) ? <button type="button" className="comparison-add-pane" onClick={() => { const next = comparison.members.find((member) => !panes.includes(member.slideId)); if (next) setPanes((current) => [...current, next.slideId]) }}><Plus /> Add pane</button> : null}
  </div>
}
