import { Plus, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { ApiError, benchmarkComparisonSet, cancelComparisonRegistration, correctComparisonSet, getComparisonCandidates, getComparisonJobs, getComparisonSet, getSharedComparisonSet, promoteComparisonCandidate, registerComparisonSet, reregisterComparisonSet, updateComparisonSet } from '../api'
import { continuousAlignmentViewDelta, hasLocalEvidence, intersectSupport, mapComparisonBounds, mapContinuousComparisonPoint, mapLocalComparisonPoint, mapOverviewComparisonPoint, mapSupportBounds, normalizeRotation, overviewAlignmentViewDelta, type Support } from '../alignment'
import { adminSignInPath } from '../authReturnPath'
import { Brand } from '../components/Brand'
import { type ImageViewport, OpenSeadragonViewer, type ViewerHandle } from '../components/OpenSeadragonViewer'
import { Loader } from '../components/Loader'
import type { ComparisonMember, ComparisonRegistrationJob, ComparisonSet, RegistrationCandidateManifest } from '../types'

const MAX_PANES = 4
type AlignmentMode = 'independent' | 'matched' | 'approximate'
type ZoomMode = 'physical' | 'tissue'
type CorrectionState = {
  original: ComparisonSet
  originalPanes: string[]
  originalActivePane: number
  originalAlignmentMode: AlignmentMode
  originalLinked: boolean
  referenceId: string
  movingId: string
  points: Array<{ reference: [number, number]; moving: [number, number] }>
  preview: boolean
}


function pairRegistrations(source: ComparisonMember, target: ComparisonMember, primaryReferenceId: string) {
  const sourceRegistration = source.slideId === primaryReferenceId ? null : source.registration
  const targetRegistration = target.slideId === primaryReferenceId ? null : target.registration
  const coordinates = (registration: typeof sourceRegistration) => registration?.coordinateReferenceId ?? registration?.anchorSlideId ?? primaryReferenceId
  if (source.slideId === coordinates(targetRegistration)) return [null, targetRegistration] as const
  if (target.slideId === coordinates(sourceRegistration)) return [sourceRegistration, null] as const
  return coordinates(sourceRegistration) === coordinates(targetRegistration)
    ? [sourceRegistration, targetRegistration] as const
    : null
}

function matchedFocusBounds(source: ComparisonMember, targets: ComparisonMember[], primaryReferenceId: string): Exclude<Support, null> | null {
  const pairs = targets.map((target) => pairRegistrations(source, target, primaryReferenceId))
  if (!pairs.length || pairs.some((pair) => !pair)) return null
  const cells = pairs.flatMap((pair) => {
    const [sourceRegistration, targetRegistration] = pair!
    return sourceRegistration?.triangles?.map((triangle) => ({ points: triangle.moving, residual: triangle.maxResidualPixels ?? Number.POSITIVE_INFINITY }))
      ?? targetRegistration?.triangles?.map((triangle) => ({ points: triangle.reference, residual: triangle.maxResidualPixels ?? Number.POSITIVE_INFINITY }))
      ?? []
  })
  if (!cells?.length || !source.metadata) return null
  const area = (triangle: [[number, number], [number, number], [number, number]]) => Math.abs(
    (triangle[1][0] - triangle[0][0]) * (triangle[2][1] - triangle[0][1])
    - (triangle[1][1] - triangle[0][1]) * (triangle[2][0] - triangle[0][0]),
  )
  const sorted = [...cells].sort((left, right) => left.residual - right.residual || area(right.points) - area(left.points))
  const candidate = sorted.find(({ points }) => {
    const center: [number, number] = [
      points.reduce((sum, point) => sum + point[0], 0) / 3,
      points.reduce((sum, point) => sum + point[1], 0) / 3,
    ]
    return pairs.every((pair) => mapLocalComparisonPoint(center, pair![0], pair![1]))
  })
  if (!candidate) return null
  const triangle = candidate.points
  const centerX = triangle.reduce((sum, point) => sum + point[0], 0) / 3
  const centerY = triangle.reduce((sum, point) => sum + point[1], 0) / 3
  const extent = Math.max(160, Math.min(source.metadata.width, source.metadata.height) * 0.08)
  return [centerX - extent / 2, centerY - extent / 2, centerX + extent / 2, centerY + extent / 2]
}

function overviewFocusBounds(source: ComparisonMember, target: ComparisonMember, primaryReferenceId: string): Exclude<Support, null> | null {
  const pair = pairRegistrations(source, target, primaryReferenceId)
  if (!pair || !source.metadata || !target.metadata) return null
  const [sourceMap, targetMap] = pair
  const cells = sourceMap?.overviewTriangles?.map((triangle) => triangle.moving)
    ?? targetMap?.overviewTriangles?.map((triangle) => triangle.reference)
  if (cells?.length) {
    const area = (triangle: [[number, number], [number, number], [number, number]]) => Math.abs(
      (triangle[1][0] - triangle[0][0]) * (triangle[2][1] - triangle[0][1])
      - (triangle[1][1] - triangle[0][1]) * (triangle[2][0] - triangle[0][0]),
    )
    const triangle = [...cells].sort((left, right) => area(right) - area(left))[0]
    const centerX = triangle.reduce((sum, point) => sum + point[0], 0) / 3
    const centerY = triangle.reduce((sum, point) => sum + point[1], 0) / 3
    const extent = Math.max(320, Math.min(source.metadata.width, source.metadata.height) * 0.15)
    return [centerX - extent / 2, centerY - extent / 2, centerX + extent / 2, centerY + extent / 2]
  }
  if ([sourceMap, targetMap].some((registration) => registration && !registration.movingToReference)) return null
  const sourceBounds: Exclude<Support, null> = sourceMap?.movingSupport ?? [0, 0, source.metadata.width, source.metadata.height]
  const targetBounds: Exclude<Support, null> = targetMap?.movingSupport ?? [0, 0, target.metadata.width, target.metadata.height]
  const common = intersectSupport(
    sourceMap?.movingToReference ? mapSupportBounds(sourceBounds, sourceMap.movingToReference) : sourceBounds,
    targetMap?.movingToReference ? mapSupportBounds(targetBounds, targetMap.movingToReference) : targetBounds,
  )
  return common ? mapComparisonBounds(common, null, sourceMap?.movingToReference ?? null) : null
}

export function ComparisonPage() {
  const { comparisonId = '', publicId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const viewStorageKey = `pathlab-comparison-view:${publicId ?? 'admin'}:${comparisonId}`
  const preferenceStorageKey = `${viewStorageKey}:preferences`
  const [comparison, setComparison] = useState<ComparisonSet | null>(null)
  const [jobs, setJobs] = useState<ComparisonRegistrationJob[]>([])
  const [panes, setPanes] = useState<string[]>([])
  const [linked, setLinked] = useState(true)
  const [unlinkedPanes, setUnlinkedPanes] = useState<Set<string>>(() => new Set())
  const [alignmentMode, setAlignmentMode] = useState<AlignmentMode>('matched')
  const [zoomMode, setZoomMode] = useState<ZoomMode>('physical')
  const [trayOpen, setTrayOpen] = useState(true)
  const [activePane, setActivePane] = useState(0)
  const [maximizedPane, setMaximizedPane] = useState<number | null>(null)
  const [scaleBars, setScaleBars] = useState<Record<string, { microns: number; width: number }>>({})
  const [display, setDisplay] = useState<Record<string, { brightness: number; contrast: number; gamma: number }>>({})
  const [notice, setNotice] = useState('')
  const [registering, setRegistering] = useState(false)
  const [candidateManifest, setCandidateManifest] = useState<RegistrationCandidateManifest | null>(null)
  const [benchmarking, setBenchmarking] = useState(false)
  const [grouping, setGrouping] = useState<{ referenceId: string, anchors: Record<string, string> } | null>(null)
  const [correction, setCorrection] = useState<CorrectionState | null>(null)
  const [correctionBusy, setCorrectionBusy] = useState(false)
  const [correctionError, setCorrectionError] = useState('')
  const [suspendedPanes, setSuspendedPanes] = useState<Set<string>>(() => new Set())
  const handles = useRef(new Map<string, ViewerHandle>())
  const savedViewports = useRef(new Map<string, ImageViewport>())
  const openedSlides = useRef(new Set<string>())
  const initializedPanes = useRef('')
  const drivingPane = useRef<string | null>(null)
  const hasInitialField = useRef(false)
  const activeTransaction = useRef<string | null>(null)
  const restoreNavigationAfterCorrection = useRef(false)
  const alignmentPreferenceExplicit = useRef(false)
  useEffect(() => {
    let active = true
    const request = publicId ? getSharedComparisonSet(publicId, comparisonId) : getComparisonSet(comparisonId)
    void request.then((value) => {
      if (!active) return
      setComparison(value)
      setNotice('')
      let saved: string[] = []
      try { saved = JSON.parse(sessionStorage.getItem(viewStorageKey) ?? '[]') as string[] } catch { saved = [] }
      try {
        const preferences = JSON.parse(sessionStorage.getItem(preferenceStorageKey) ?? '{}') as { alignmentMode?: AlignmentMode, zoomMode?: ZoomMode, alignmentExplicit?: boolean }
        alignmentPreferenceExplicit.current = preferences.alignmentExplicit === true
        if (['matched', 'approximate', 'independent'].includes(preferences.alignmentMode ?? '') && (preferences.alignmentMode !== 'independent' || alignmentPreferenceExplicit.current)) {
          const restoredMode = preferences.alignmentMode as AlignmentMode
          setAlignmentMode(restoredMode)
          setLinked(restoredMode !== 'independent')
        }
        if (['physical', 'tissue'].includes(preferences.zoomMode ?? '')) setZoomMode(preferences.zoomMode as ZoomMode)
      } catch { /* Invalid saved preferences fall back to safe matched navigation. */ }
      const availableMembers = value.members.filter((member) => Boolean(member.tileSource))
      const available = new Set(availableMembers.map((member) => member.slideId))
      const restored = Array.isArray(saved) ? [...new Set(saved)].filter((slideId) => available.has(slideId)).slice(0, MAX_PANES) : []
      const initialPanes = restored.length ? restored : availableMembers.slice(0, 2).map((member) => member.slideId)
      setUnlinkedPanes(new Set(value.members
        .filter((member) => initialPanes.includes(member.slideId) && member.registration?.status === 'rejected')
        .map((member) => member.slideId)))
      setPanes(initialPanes)
    }).catch((caught) => {
      if (!active) return
      if (!publicId && caught instanceof ApiError && caught.status === 401) {
        void navigate(adminSignInPath(`${location.pathname}${location.search}${location.hash}`), { replace: true })
        return
      }
      setNotice('Comparison set is unavailable.')
    })
    return () => { active = false }
  }, [comparisonId, location.hash, location.pathname, location.search, navigate, preferenceStorageKey, publicId, viewStorageKey])
  useEffect(() => {
    if (!comparison || !panes.length) return
    try { sessionStorage.setItem(viewStorageKey, JSON.stringify(panes)) } catch { /* Storage may be disabled. Viewing remains available. */ }
  }, [comparison, panes, viewStorageKey])
  useEffect(() => {
    if (!comparison || correction) return
    try { sessionStorage.setItem(preferenceStorageKey, JSON.stringify({ alignmentMode, zoomMode, alignmentExplicit: alignmentPreferenceExplicit.current })) } catch { /* Storage may be disabled. Viewing remains available. */ }
  }, [alignmentMode, comparison, correction, preferenceStorageKey, zoomMode])
  useEffect(() => {
    if (publicId || !comparisonId) return
    let active = true
    void getComparisonJobs(comparisonId).then((value) => { if (active && Array.isArray(value)) setJobs(value) }).catch(() => undefined)
    return () => { active = false }
  }, [comparisonId, publicId])
  useEffect(() => {
    if (!comparison || !['queued', 'running'].includes(comparison.status)) return
    const timer = window.setInterval(() => {
      if (publicId) {
        void getSharedComparisonSet(publicId, comparison.id).then(setComparison).catch(() => undefined)
        return
      }
      void Promise.all([getComparisonSet(comparison.id), getComparisonJobs(comparison.id)])
        .then(([updated, updatedJobs]) => { setComparison(updated); if (Array.isArray(updatedJobs)) setJobs(updatedJobs) })
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [comparison, publicId])
  useEffect(() => {
    if (publicId || !comparisonId) return
    let active = true
    void getComparisonCandidates(comparisonId)
      .then((value) => {
        if (active && Array.isArray(value.candidates)) setCandidateManifest(value)
      })
      .catch(() => undefined)
    return () => { active = false }
  }, [comparisonId, publicId])
  const synchronize = useCallback((source: ComparisonMember, snapshot: ImageViewport, incomingTransaction?: string) => {
    if (!comparison || !linked || alignmentMode === 'independent') return
    if (unlinkedPanes.has(source.slideId)) return
    if (incomingTransaction) return
    drivingPane.current = source.slideId
    const transactionId = `${source.slideId}:${performance.now().toFixed(3)}`
    activeTransaction.current = transactionId
    const sourceIsLocalAnchor = panes.some((targetId) => comparison.members
      .find((member) => member.slideId === targetId)?.registration?.anchorSlideId === source.slideId)
    if (source.slideId !== comparison.referenceSlideId && !sourceIsLocalAnchor) {
      if (source.registration?.status === 'rejected' || !source.registration) {
        setSuspendedPanes(new Set(panes))
        setNotice(`Synchronization unavailable because ${source.displayName} has no correspondence map and remains independent.`)
        return
      }
    }
    const suspended: string[] = []
    const approximate: string[] = []
    const suspendedIds = new Set<string>()
    for (const targetId of panes) {
      if (targetId === source.slideId) continue
      if (unlinkedPanes.has(targetId)) continue
      const target = comparison.members.find((member) => member.slideId === targetId)
      if (!target) continue
      if (!openedSlides.current.has(targetId)) continue
      const pair = pairRegistrations(source, target, comparison.referenceSlideId)
      if (!pair) {
        suspended.push(target.displayName)
        suspendedIds.add(targetId)
        continue
      }
      const [sourceRegistration, targetRegistration] = pair
      const registrations = [sourceRegistration, targetRegistration].filter((item) => item !== null)
      const hasSafeComponentOverview = (registration: typeof sourceRegistration) => registration?.status === 'approximate'
        && registration.evidence?.componentOrderPreserved === true
        && (registration.overviewTriangles?.length ?? 0) > 0
      const usable = alignmentMode === 'approximate'
        ? registrations.every((registration) => registration?.status === 'ready' || registration?.status === 'approximate')
        : registrations.every((registration) => (registration?.status === 'ready' && hasLocalEvidence(registration))
          || hasSafeComponentOverview(registration))
      if (!usable) {
        suspended.push(target.displayName)
        suspendedIds.add(targetId)
        continue
      }
      const useOverview = alignmentMode === 'approximate'
        || registrations.some((registration) => hasSafeComponentOverview(registration))
      if (useOverview) approximate.push(target.displayName)
      const referencePoint = !useOverview
        ? mapContinuousComparisonPoint([snapshot.centerX, snapshot.centerY], sourceRegistration, null)
        : mapOverviewComparisonPoint([snapshot.centerX, snapshot.centerY], sourceRegistration, null)
      if (!referencePoint) {
        suspended.push(target.displayName)
        suspendedIds.add(targetId)
        continue
      }
      const targetPoint = !useOverview
        ? mapContinuousComparisonPoint(referencePoint, null, targetRegistration)
        : mapOverviewComparisonPoint(referencePoint, null, targetRegistration)
      const viewDelta = !useOverview
        ? continuousAlignmentViewDelta([snapshot.centerX, snapshot.centerY], sourceRegistration, targetRegistration)
        : overviewAlignmentViewDelta([snapshot.centerX, snapshot.centerY], sourceRegistration, targetRegistration)
      if (!targetPoint || !viewDelta) {
        suspended.push(target.displayName)
        suspendedIds.add(targetId)
        continue
      }
      const sourceMpp = source.metadata?.physicalSizeX
      const targetMpp = target.metadata?.physicalSizeX
      const zoomScale = zoomMode === 'physical' && sourceMpp && targetMpp
        ? targetMpp / sourceMpp
        : viewDelta.zoomScale
      const targetViewport = {
        centerX: targetPoint[0], centerY: targetPoint[1],
        imageZoom: snapshot.imageZoom * zoomScale,
        rotation: normalizeRotation(snapshot.rotation + viewDelta.rotation),
      }
      savedViewports.current.set(targetId, targetViewport)
      handles.current.get(targetId)?.setImageViewport(targetViewport, transactionId)
    }
    setSuspendedPanes(suspendedIds)
    setNotice(suspended.length
      ? `No verified correspondence is available at this field for ${suspended.join(', ')}. Those panes remain at their last verified position.`
      : approximate.length
        ? `Using approximate overview synchronization for ${[...new Set(approximate)].join(', ')}. Exact local correspondence is unavailable for these slides.`
        : '')
  }, [alignmentMode, comparison, linked, panes, unlinkedPanes, zoomMode])
  const alignOpenedPanes = useCallback(() => {
    if (!comparison || !linked) return
    const sourceId = panes.find((id) => id === drivingPane.current && openedSlides.current.has(id))
      ?? panes.find((id) => id === comparison.referenceSlideId && openedSlides.current.has(id))
      ?? panes.find((id) => {
        const member = comparison.members.find((candidate) => candidate.slideId === id)
        return openedSlides.current.has(id) && member?.registration?.status === 'ready'
      })
      ?? panes.find((id) => openedSlides.current.has(id) && panes.some((targetId) => comparison.members.find((member) => member.slideId === targetId)?.registration?.anchorSlideId === id))
      ?? panes.find((id) => openedSlides.current.has(id))
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
      : opened.find((id) => opened.some((otherId) => comparison.members
        .find((member) => member.slideId === otherId)?.registration?.anchorSlideId === id))
        ?? opened.find((id) => comparison.members.find((member) => member.slideId === id)?.registration?.status === 'ready')
    const anchor = comparison.members.find((member) => member.slideId === anchorId)
    const anchorHandle = anchorId ? handles.current.get(anchorId) : null
    if (anchor && anchorHandle && opened.length > 1) {
      const others = comparison.members.filter((member) => opened.includes(member.slideId) && member.slideId !== anchor.slideId)
      const other = others[0]
      const exactOthers = others.filter((target) => {
        const pair = pairRegistrations(anchor, target, comparison.referenceSlideId)
        const registrations = pair?.filter((item) => item !== null) ?? []
        return registrations.length > 0 && registrations.every((registration) => registration?.status === 'ready' && hasLocalEvidence(registration))
      })
      const matchedBounds = alignmentMode === 'matched' && exactOthers.length
        ? matchedFocusBounds(anchor, exactOthers, comparison.referenceSlideId)
        : null
      const anchorBounds = matchedBounds ?? (other ? overviewFocusBounds(anchor, other, comparison.referenceSlideId) : null)
      if (anchorBounds && (!hasInitialField.current || opened.length === panes.length)) {
        anchorHandle.fitImageBounds(anchorBounds)
        hasInitialField.current = true
        drivingPane.current = anchorId ?? null
        synchronize(anchor, anchorHandle.getImageViewport())
      }
    }
    window.requestAnimationFrame(alignOpenedPanes)
  }, [alignOpenedPanes, alignmentMode, comparison, linked, panes, synchronize])
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
    const otherMembers = comparison?.members.filter((member) => panes.includes(member.slideId) && member.slideId !== anchorId) ?? []
    const exactMembers = comparison && anchorMember ? otherMembers.filter((target) => {
      const pair = pairRegistrations(anchorMember, target, comparison.referenceSlideId)
      const registrations = pair?.filter((item) => item !== null) ?? []
      return registrations.length > 0 && registrations.every((registration) => registration?.status === 'ready' && hasLocalEvidence(registration))
    }) : []
    const bounds = comparison && anchorMember && otherMembers.length
      ? alignmentMode === 'matched' && exactMembers.length
        ? matchedFocusBounds(anchorMember, exactMembers, comparison.referenceSlideId)
        : overviewFocusBounds(anchorMember, otherMembers[0], comparison.referenceSlideId)
      : null
    if (bounds) anchor?.fitImageBounds(bounds)
    else anchor?.home()
    drivingPane.current = anchorId
    if (anchor && anchorMember) synchronize(anchorMember, anchor.getImageViewport())
  }, [alignmentMode, comparison, linked, panes, synchronize])
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (correction) return
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === '1' || event.key === '2' || event.key === '3' || event.key === '4') {
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
  }, [comparison, correction, resetView])
  const submitCorrection = async (previewOnly: boolean) => {
    if (!comparison || !correction) return
    setCorrectionBusy(true); setCorrectionError('')
    try {
      const result = await correctComparisonSet(comparison.id, correction.movingId, {
        version: correction.original.version, referenceSlideId: correction.referenceId,
        referencePoints: correction.points.map((point) => point.reference),
        movingPoints: correction.points.map((point) => point.moving), previewOnly,
      })
      setComparison(result); setLinked(true); setAlignmentMode('matched')
      hasInitialField.current = false; initializedPanes.current = ''; drivingPane.current = correction.referenceId
      if (previewOnly) setCorrection({ ...correction, preview: true })
      else {
        restoreNavigationAfterCorrection.current = true
        setPanes(correction.originalPanes)
        setActivePane(Math.min(correction.originalActivePane, correction.originalPanes.length - 1))
        setUnlinkedPanes((current) => { const next = new Set(current); next.delete(correction.movingId); return next })
        setSuspendedPanes((current) => { const next = new Set(current); next.delete(correction.movingId); return next })
        setCorrection(null)
        setNotice('Manual correction saved. Support is limited to the area between your landmarks.')
      }
    } catch (error) {
      setCorrectionError(error instanceof ApiError && error.status === 409
        ? 'This set changed. Cancel and reload before saving new landmarks.'
        : 'Correction rejected. Use at least three non-collinear corresponding points spread across the same tissue.')
    } finally { setCorrectionBusy(false) }
  }
  if (!comparison && !notice) return <Loader label="Opening comparison…" size="large" fullscreen />
  if (!comparison) return <main className="viewer-message"><h1>{notice}</h1></main>
  const paneCandidates = (current: string[]) => comparison.members
    .map((member, index) => ({
      member,
      index,
      localLinks: current.reduce((count, slideId) => {
        const existing = comparison.members.find((candidate) => candidate.slideId === slideId)
        const pair = existing ? pairRegistrations(existing, member, comparison.referenceSlideId) : null
        return count + (pair && pair.filter((registration) => registration !== null)
          .every((registration) => registration?.status === 'ready' && hasLocalEvidence(registration)) ? 1 : 0)
      }, 0),
      links: current.reduce((count, slideId) => {
        const existing = comparison.members.find((candidate) => candidate.slideId === slideId)
        return count + (existing && pairRegistrations(existing, member, comparison.referenceSlideId) ? 1 : 0)
      }, 0),
    }))
    .filter(({ member }) => !current.includes(member.slideId) && member.registration?.status !== 'rejected')
    .sort((left, right) => right.localLinks - left.localLinks || right.links - left.links || left.index - right.index)
    .map(({ member }) => member)
  const setLayout = (count: number) => { setActivePane(0); setMaximizedPane(null); setSuspendedPanes(new Set()); setNotice(''); setPanes((current) => {
    const next = [...current]
    for (const member of paneCandidates(current)) if (next.length < count) next.push(member.slideId)
    return next.slice(0, Math.min(count, comparison.members.length))
  }) }
  const selectPaneSlide = (paneIndex: number, slideId: string) => {
    hasInitialField.current = false
    initializedPanes.current = ''
    drivingPane.current = null
    const selected = comparison.members.find((member) => member.slideId === slideId)
    if (selected?.registration?.status === 'rejected') {
      setUnlinkedPanes((current) => new Set(current).add(slideId))
      setNotice(`${selected.displayName} has no reliable counterpart and is opened independently.`)
    } else if (selected?.registration?.status === 'approximate' && alignmentMode === 'matched') {
      setUnlinkedPanes((current) => new Set(current).add(slideId))
      setNotice(`${selected.displayName} has no verified component match and is opened independently. Choose Approximate overview to inspect the unverified proposal.`)
    } else if (selected?.registration?.status === 'approximate') {
      setLinked(true)
      setNotice(`${selected.displayName} uses an unverified approximate overview proposal.`)
    } else {
      setNotice('')
    }
    setActivePane(paneIndex)
    setPanes((current) => current.map((id, index) => index === paneIndex ? slideId : id))
  }
  const startCorrection = () => {
    const activeId = panes[Math.min(activePane, panes.length - 1)]
    const movingId = activeId !== comparison.referenceSlideId
      ? activeId
      : panes.find((slideId) => slideId !== comparison.referenceSlideId)
    if (!movingId) return
    const moving = comparison.members.find((member) => member.slideId === movingId)
    const configuredAnchor = comparison.alignmentConfig?.anchors?.[movingId]
    const candidateAnchor = moving?.registration?.anchorSlideId ?? configuredAnchor ?? comparison.referenceSlideId
    const referenceId = comparison.members.some((member) => member.slideId === candidateAnchor && member.slideId !== movingId)
      ? candidateAnchor
      : comparison.referenceSlideId
    setCorrection({
      original: comparison,
      originalPanes: [...panes],
      originalActivePane: activePane,
      originalAlignmentMode: alignmentMode,
      originalLinked: linked,
      referenceId,
      movingId,
      points: [],
      preview: false,
    })
    setPanes([referenceId, movingId])
    setActivePane(1)
    setCorrectionError('')
    setLinked(false)
    setAlignmentMode('independent')
    setNotice('')
    setMaximizedPane(null)
  }
  const cancelCorrection = () => {
    if (!correction) return
    setComparison(correction.original)
    restoreNavigationAfterCorrection.current = true
    setPanes(correction.originalPanes)
    setActivePane(Math.min(correction.originalActivePane, correction.originalPanes.length - 1))
    hasInitialField.current = false
    initializedPanes.current = ''
    drivingPane.current = correction.referenceId
    setCorrection(null)
    setCorrectionError('')
    setLinked(correction.originalLinked)
    setAlignmentMode(correction.originalAlignmentMode)
  }
  const hasMatchedMap = comparison.members.some((member) => member.registration?.status === 'ready' && hasLocalEvidence(member.registration))
  const hasApproximateMap = comparison.members.some((member) => (member.registration?.overviewTriangles?.length ?? 0) > 0)
  const hasPendingLandmarkValidation = comparison.members.some((member) => member.registration?.status === 'ready' && member.registration.evidence?.withheldCheck === 'pending-independent-landmarks')
  const registrationPending = ['queued', 'running'].includes(comparison.status)
  const currentJobsByMember = new Map<string, ComparisonRegistrationJob>()
  jobs
    .filter((job) => job.kind === 'align' && job.setVersion === comparison.version && job.memberId)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .forEach((job) => { if (job.memberId && !currentJobsByMember.has(job.memberId)) currentJobsByMember.set(job.memberId, job) })
  const registrationMembers = comparison.members.filter((member) => member.slideId !== comparison.referenceSlideId)
  const completedRegistrations = registrationMembers.filter((member) => member.registration || currentJobsByMember.get(member.slideId)?.status === 'succeeded').length
  const totalRegistrationProgress = registrationMembers.length
    ? Math.round(registrationMembers.reduce((total, member) => total + (member.registration ? 100 : currentJobsByMember.get(member.slideId)?.progress ?? 0), 0) / registrationMembers.length)
    : 100
  const anchorIds = new Set(comparison.members.flatMap((member) => member.registration?.anchorSlideId ? [member.registration.anchorSlideId] : []))
  return <div className="comparison-shell">
    <header className="comparison-header">
      <Brand variant="library" />
      <div className="comparison-heading"><strong>{comparison.name}</strong><span>{comparison.status} · {comparison.members.length} slides</span></div>
      <div className="comparison-view-controls" aria-label="Viewing controls">
        <label className="comparison-toolbar-field"><span>Layout</span><select disabled={!!correction || !!grouping} aria-label="Pane layout" value={panes.length} onChange={(event) => { setMaximizedPane(null); setLayout(Number(event.target.value)) }}><option value="1">1 pane</option><option value="2">2 panes</option><option value="3">3 panes</option><option value="4">4 panes</option></select></label>
        <label className="comparison-toolbar-field"><span>Alignment</span><select disabled={!!correction || !!grouping} aria-label="Alignment mode" value={alignmentMode} onChange={(event) => { const mode = event.target.value as AlignmentMode; alignmentPreferenceExplicit.current = true; hasInitialField.current = false; initializedPanes.current = ''; setAlignmentMode(mode); setLinked(mode !== 'independent'); setNotice(''); setSuspendedPanes(new Set()) }}><option value="matched">Best available</option><option value="approximate">Approximate overview</option><option value="independent">Independent</option></select></label>
        <label className="comparison-toolbar-field"><span>Zoom</span><select disabled={!!correction || !!grouping} aria-label="Linked zoom mode" value={zoomMode} onChange={(event) => setZoomMode(event.target.value as ZoomMode)}><option value="physical">Equal µm/pixel</option><option value="tissue">Fit corresponding tissue</option></select></label>
        <button type="button" className="comparison-link-control" disabled={!!correction || !!grouping} aria-label={linked ? 'Views linked' : 'Views independent'} aria-pressed={linked} onClick={() => { alignmentPreferenceExplicit.current = true; setLinked((value) => !value); if (linked) setAlignmentMode('independent'); else setAlignmentMode('matched') }}><span aria-hidden="true">{linked ? '●' : '○'}</span>{linked ? 'Linked' : 'Independent'}</button>
        <button type="button" onClick={resetView}><span aria-hidden="true">↻</span> Reset view</button>
        <button type="button" className="comparison-tray-toggle" aria-expanded={trayOpen} onClick={() => setTrayOpen((value) => !value)}>{trayOpen ? 'Hide slides' : 'Show slides'}</button>
      </div>
      {!publicId ? <details className="comparison-setup-menu"><summary>Setup</summary><div>
        <button type="button" disabled={registering || !!correction || !!grouping || registrationPending} onClick={() => { setRegistering(true); void reregisterComparisonSet(comparison.id).then(() => { setComparison((current) => current ? { ...current, status: 'queued', members: current.members.map((member) => ({ ...member, registration: null })) } : current); setNotice('Automatic alignment queued with the current anchors.') }).catch(() => setNotice('Automatic alignment could not be queued.')).finally(() => setRegistering(false)) }}>{registering ? 'Queuing…' : 'Run automatic alignment again'}</button>
        {['queued', 'running'].includes(comparison.status) ? <button type="button" disabled={registering} onClick={() => { setRegistering(true); void cancelComparisonRegistration(comparison.id).then(() => setNotice('Registration cancellation requested.')).catch(() => setNotice('Registration could not be cancelled.')).finally(() => setRegistering(false)) }}>Cancel registration</button> : null}
        <button type="button" aria-label="Groups" disabled={registering || !!correction || ['queued', 'running'].includes(comparison.status)} onClick={() => setGrouping({ referenceId: comparison.referenceSlideId, anchors: Object.fromEntries(comparison.members.filter((member) => member.slideId !== comparison.referenceSlideId).map((member) => [member.slideId, comparison.alignmentConfig?.anchors?.[member.slideId] ?? member.registration?.anchorSlideId ?? comparison.referenceSlideId])) })}>Reference groups</button>
        <button type="button" disabled={benchmarking || registrationPending} onClick={() => { const engines = Object.entries(candidateManifest?.engineAvailability ?? {}).filter(([, value]) => value.available).map(([engine]) => engine); setBenchmarking(true); void benchmarkComparisonSet(comparison.id, comparison.version, engines.length ? engines : ['native-v12']).then(() => { setNotice('Engine benchmark queued. Existing alignment remains active until you promote a candidate.') }).catch(() => setNotice('Engine benchmark could not be queued.')).finally(() => setBenchmarking(false)) }}>{benchmarking ? 'Queuing benchmark…' : 'Benchmark engines'}</button>
        <button type="button" disabled={registrationPending || !!correction || !!grouping || !panes.some((slideId) => slideId !== comparison.referenceSlideId)} onClick={startCorrection}>Correct alignment</button>
      </div></details> : null}
    </header>
    {registrationPending ? <section className="comparison-registration-progress" aria-label="Automatic alignment progress" aria-live="polite">
      <div><strong>Automatic alignment in progress</strong><span>{completedRegistrations} of {registrationMembers.length} slides complete · {totalRegistrationProgress}%</span></div>
      <progress max="100" value={totalRegistrationProgress}>{totalRegistrationProgress}%</progress>
      <ul>{registrationMembers.map((member) => {
        const job = currentJobsByMember.get(member.slideId)
        const complete = Boolean(member.registration) || job?.status === 'succeeded'
        const stage = complete ? 'Aligned' : job?.status === 'queued' ? 'Waiting for worker' : job?.stage?.replaceAll('-', ' ') || 'Preparing alignment'
        const counters = job && !complete
          ? [job.totalComponentPairs ? `${job.processedComponentPairs}/${job.totalComponentPairs} regions` : '', job.totalPatches ? `${job.processedPatches}/${job.totalPatches} patches` : ''].filter(Boolean).join(' · ')
          : ''
        return <li key={member.slideId} data-status={complete ? 'complete' : job?.status ?? 'queued'}><span>{complete ? '✓' : job?.status === 'running' || job?.status === 'leased' ? '●' : '○'}</span><b>{member.stain || member.displayName}</b><small>{stage}{counters ? ` · ${counters}` : ''}</small><em>{complete ? '100%' : `${job?.progress ?? 0}%`}</em></li>
      })}</ul>
      <p>You can view every slide now. Linked navigation becomes available for each slide as its map completes.</p>
    </section> : null}
    {!publicId && candidateManifest?.candidates?.length ? <details className="comparison-quality comparison-engine-candidates"><summary>Registration engine candidates</summary><p>Candidate maps are experimental until promoted. Fit residuals are engineering checks, not anatomical accuracy.</p><div>{candidateManifest.candidates.filter((candidate) => candidate.setVersion === comparison.version).map((candidate) => { const candidateSlideName = comparison.members.find((member) => member.slideId === candidate.slideId)?.displayName ?? candidate.slideId; return <article key={candidate.id}><strong>{candidateSlideName}</strong><span>{candidate.engine} · {candidate.status} · {candidate.validationState.replaceAll('_', ' ')}</span>{candidate.failureReason ? <small>{candidate.failureReason}</small> : null}<button type="button" aria-label={`Promote ${candidate.engine} for ${candidateSlideName}`} disabled={candidate.status !== 'ready' || candidate.validationState !== 'engineering_passed'} onClick={() => { setRegistering(true); void promoteComparisonCandidate(comparison.id, candidate.id, comparison.version).then((updated) => { setComparison(updated); setNotice(`${candidate.engine} candidate promoted for this slide.`) }).catch(() => setNotice('Candidate could not be promoted.')).finally(() => setRegistering(false)) }}>Promote candidate</button></article> })}</div></details> : null}
    {grouping ? <section className="comparison-groups" aria-label="Alignment groups"><strong>Reference and groups</strong><p>Choose the primary reference, then choose the serial-section anchor used for each other slide.</p><label>Primary reference<select aria-label="Primary reference" value={grouping.referenceId} onChange={(event) => setGrouping({ ...grouping, referenceId: event.target.value })}>{comparison.members.map((member) => <option key={member.slideId} value={member.slideId}>{member.stain} · {member.displayName}</option>)}</select></label>{comparison.members.filter((member) => member.slideId !== grouping.referenceId).map((member) => <label key={member.slideId}>{member.displayName}<select aria-label={`Anchor for ${member.displayName}`} value={grouping.anchors[member.slideId] ?? grouping.referenceId} onChange={(event) => setGrouping({ ...grouping, anchors: { ...grouping.anchors, [member.slideId]: event.target.value } })}>{comparison.members.filter((anchor) => anchor.slideId !== member.slideId).map((anchor) => <option key={anchor.slideId} value={anchor.slideId}>{anchor.stain} · {anchor.displayName}</option>)}</select></label>)}<button type="button" disabled={registering} onClick={() => { setRegistering(true); void updateComparisonSet(comparison.id, { version: comparison.version, referenceSlideId: grouping.referenceId, anchors: grouping.anchors }).then(async (updated) => { await registerComparisonSet(updated.id); setComparison({ ...updated, status: 'queued', members: updated.members.map((member) => ({ ...member, registration: null })) }); setGrouping(null); setNotice('Registration queued with the updated reference groups.') }).catch(() => setNotice('Reference groups could not be saved.')).finally(() => setRegistering(false)) }}>Save and register</button><button type="button" disabled={registering} onClick={() => setGrouping(null)}>Cancel</button></section> : null}
    {!correction && !grouping && !hasMatchedMap && !registrationPending ? <div className="comparison-notice" role="note" aria-label="Alignment unavailable"><strong>{hasApproximateMap ? 'Automatic alignment completed with overview maps.' : 'Automatic anatomical alignment could not establish a map for this set.'}</strong> {hasApproximateMap ? 'Overview alignment matches tissue-component shape, tilt, and size but may not place the same microscopic structure under both crosshairs.' : 'No accepted tissue correspondence was found. Linking panes cannot align these slides.'} {publicId ? 'Ask the set administrator to review the registration.' : 'Use Correct alignment to define and preview corresponding landmarks.'}</div> : null}
    {!correction && !grouping && hasMatchedMap && hasPendingLandmarkValidation && !registrationPending ? <details className="comparison-notice comparison-validation" aria-label="Alignment validation pending"><summary><strong>Local structural maps available</strong><span>Validation details</span></summary><p>Matched regions passed alternative-fragment and withheld patch checks, but anatomical error has not been measured against independent landmarks.</p></details> : null}
    {notice ? <div className="comparison-notice" role="status">{notice}</div> : null}
    {correction ? <section className="comparison-correction" aria-label="Landmark correction">
      <strong>{correction.preview ? 'Correction preview' : 'Mark corresponding tissue'}</strong>
      <p>Left pane is the reference. Pan each image independently until the same anatomical point is under both crosshairs, then record the pair. Use at least three points spread across the tissue.</p>
      <span>{correction.points.length} point pairs</span>
      <button type="button" disabled={correctionBusy || correction.preview || correction.points.length >= 20} onClick={() => {
        const reference = handles.current.get(correction.referenceId)?.getImageViewport(); const moving = handles.current.get(correction.movingId)?.getImageViewport()
        if (reference && moving) setCorrection({ ...correction, points: [...correction.points, { reference: [reference.centerX, reference.centerY], moving: [moving.centerX, moving.centerY] }] })
      }}>Record point pair</button>
      <button type="button" disabled={correctionBusy || !correction.points.length} onClick={() => { setComparison(correction.original); setCorrection({ ...correction, points: correction.points.slice(0, -1), preview: false }); setLinked(false); setAlignmentMode('independent') }}>Undo last pair</button>
      <button type="button" disabled={correctionBusy || correction.points.length < 3} onClick={() => void submitCorrection(true)}>Preview correction</button>
      <button type="button" disabled={correctionBusy || !correction.preview} onClick={() => void submitCorrection(false)}>Save correction</button>
      <button type="button" disabled={correctionBusy} onClick={cancelCorrection}>Cancel correction</button>
      {correction.preview ? <p>Preview only. Inspect corresponding anatomy and the fit residual in Alignment quality before saving.</p> : null}
      {correctionError ? <p role="alert">{correctionError}</p> : null}
    </section> : null}
    <div className="comparison-workstation" data-tray-open={trayOpen}><aside className="comparison-tray" aria-label="Case slides"><strong>Case slides <span>{comparison.members.length}</span></strong>{comparison.members.map((member) => <button type="button" key={member.slideId} disabled={!!correction || !member.tileSource} data-active={panes.includes(member.slideId)} data-current={panes[activePane] === member.slideId} aria-current={panes[activePane] === member.slideId ? 'true' : undefined} onClick={() => { const existing = panes.indexOf(member.slideId); if (existing >= 0) { setActivePane(existing); if (maximizedPane !== null) setMaximizedPane(existing); return } selectPaneSlide(Math.min(activePane, panes.length - 1), member.slideId) }}>{member.thumbnailUrl ? <img src={member.thumbnailUrl} alt="" loading="lazy" /> : <span className="comparison-thumbnail-pending" aria-hidden="true">WSI</span>}<span><b>{member.stain || 'Unspecified'}</b><small>{member.displayName}</small>{member.availabilityReason ? <small>{member.availabilityReason.replaceAll('_', ' ')}</small> : null}</span></button>)}</aside>
    <main className={`comparison-grid comparison-grid--${panes.length}`} data-maximized={maximizedPane === null ? undefined : maximizedPane}>
      {panes.map((slideId, paneIndex) => {
        if (maximizedPane !== null && maximizedPane !== paneIndex) return null
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
              ? `Local map via ${anchor.displayName}`
              : 'Local map available'
        const adjustments = display[slideId] ?? { brightness: 1, contrast: 1, gamma: 1 }
        const paneLinked = linked && !unlinkedPanes.has(slideId)
        const suspended = paneLinked && suspendedPanes.has(slideId)
        const evidence = member.registration?.evidence
        const residuals = member.registration?.controlPoints
          ?.map((point) => point.errorPixels)
          .filter((value) => Number.isFinite(value)) ?? []
        const medianResidual = residuals.length
          ? [...residuals].sort((left, right) => left - right)[Math.floor(residuals.length / 2)]
          : null
        return <section className="comparison-pane" data-active={paneIndex === activePane} data-hidden={maximizedPane !== null && maximizedPane !== paneIndex} key={`${paneIndex}-${slideId}`} onPointerDown={() => setActivePane(paneIndex)}>
          <header><span className="comparison-pane-number" aria-hidden="true">{paneIndex + 1}</span><select disabled={!!correction} aria-label={`Slide shown in pane ${paneIndex + 1}`} value={slideId} onChange={(event) => selectPaneSlide(paneIndex, event.target.value)}>{comparison.members.filter((candidate) => candidate.tileSource && (!panes.includes(candidate.slideId) || candidate.slideId === slideId)).map((candidate) => <option key={candidate.slideId} value={candidate.slideId}>{candidate.stain || 'Unspecified stain'} · {candidate.displayName}</option>)}</select><span aria-live="polite" className={suspended || !paneLinked ? 'alignment-unavailable' : member.registration?.status === 'approximate' ? 'alignment-approximate' : aligned ? 'alignment-ready' : 'alignment-unavailable'}>{suspended ? 'Unavailable' : !paneLinked ? 'Independent' : aligned ? alignmentLabel : member.registration?.status === 'approximate' ? 'Approximate sync' : member.registration?.status === 'ready' ? 'Overview sync' : 'Not aligned'}</span><button type="button" title={paneLinked ? 'Unlink this pane' : 'Link this pane'} disabled={!!correction} aria-label={`${paneLinked ? 'Unlink' : 'Link'} ${member.displayName} pane`} aria-pressed={paneLinked} onClick={() => {
            if (!paneLinked) {
              alignmentPreferenceExplicit.current = true
              setLinked(true)
              if (alignmentMode === 'independent') setAlignmentMode('matched')
            }
            setUnlinkedPanes((current) => { const next = new Set(current); if (paneLinked) next.add(slideId); else next.delete(slideId); return next })
          }}><span aria-hidden="true">{paneLinked ? 'On' : 'Off'}</span></button><button type="button" title={maximizedPane === paneIndex ? 'Restore all panes' : 'Maximize this pane'} disabled={!!correction} aria-label={`${maximizedPane === paneIndex ? 'Restore' : 'Maximize'} ${member.displayName} pane`} onClick={() => setMaximizedPane((current) => current === paneIndex ? null : paneIndex)}>{maximizedPane === paneIndex ? '↙' : '↗'}</button>{panes.length > 2 ? <button type="button" title="Close this pane" aria-label={`Close ${member.displayName} pane`} onClick={() => { setActivePane(0); setMaximizedPane(null); setPanes((current) => current.filter((_, index) => index !== paneIndex)) }}><X /></button> : null}</header>
          <OpenSeadragonViewer tileSource={member.tileSource!} displayAdjustments={adjustments} onReady={(handle) => handles.current.set(slideId, handle)} onDispose={() => { handles.current.delete(slideId); openedSlides.current.delete(slideId) }} onOpen={() => {
            openedSlides.current.add(slideId)
            const saved = savedViewports.current.get(slideId)
            if (saved) handles.current.get(slideId)?.setImageViewport(saved, 'restore-field')
            initializeOpenedPanes()
            window.requestAnimationFrame(alignOpenedPanes)
            if (restoreNavigationAfterCorrection.current && panes.every((id) => openedSlides.current.has(id))) {
              restoreNavigationAfterCorrection.current = false
              window.requestAnimationFrame(resetView)
            }
          }} micronsPerPixel={member.metadata?.physicalSizeX} onScaleChange={(microns, width) => setScaleBars((current) => ({ ...current, [slideId]: { microns, width } }))} onViewportChange={(snapshot, transactionId) => { savedViewports.current.set(slideId, snapshot); synchronize(member, snapshot, transactionId) }} networkProfile={{ initialJobLimit: 2, maximumJobLimit: Math.max(1, Math.floor(8 / panes.length)) }} />
          {(correction || (paneLinked && !suspended)) ? <div className="comparison-crosshair" aria-hidden="true" /> : null}
          {scaleBars[slideId] ? <div className="comparison-scale-bar" style={{ width: scaleBars[slideId].width }}><i /><span>{scaleBars[slideId].microns >= 1000 ? `${scaleBars[slideId].microns / 1000} mm` : `${scaleBars[slideId].microns} µm`}</span></div> : null}
          <details className="comparison-display"><summary>Display</summary><label>Brightness<input type="range" min="0.5" max="1.5" step="0.05" value={adjustments.brightness} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, brightness: Number(event.target.value) } }))} /></label><label>Contrast<input type="range" min="0.5" max="1.5" step="0.05" value={adjustments.contrast} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, contrast: Number(event.target.value) } }))} /></label><label>Gamma<input type="range" min="0.5" max="2" step="0.05" value={adjustments.gamma} onChange={(event) => setDisplay((current) => ({ ...current, [slideId]: { ...adjustments, gamma: Number(event.target.value) } }))} /></label><button type="button" onClick={() => setDisplay((current) => ({ ...current, [slideId]: { brightness: 1, contrast: 1, gamma: 1 } }))}>Reset display</button></details>
          <details className="comparison-quality"><summary>Alignment quality</summary>{member.slideId === comparison.referenceSlideId ? <p>Primary coordinate reference.</p> : <dl><div><dt>Mode</dt><dd>{member.registration?.status ?? 'unavailable'}</dd></div><div><dt>Evidence</dt><dd>{evidence?.featureMatchCount ?? evidence?.anatomicalMatchCount ?? 0} {member.registration?.provenance === 'manual' ? 'manual landmarks' : 'feature candidates'}</dd></div><div><dt>Map</dt><dd>{evidence?.triangleCount ?? member.registration?.triangles?.length ?? 0} accepted cells</dd></div>{member.registration?.overviewTriangles?.length ? <div><dt>Overview map</dt><dd>{member.registration.overviewTriangles.length} approximate cells</dd></div> : null}{evidence?.flowControlCount ? <div><dt>Local refinement</dt><dd>{evidence.flowControlCount} cycle-consistent controls</dd></div> : null}{evidence?.flowCycleP95 !== undefined ? <div><dt>Flow cycle p95</dt><dd>{evidence.flowCycleP95.toFixed(2)} px</dd></div> : null}{evidence?.verifiedPatchCount !== undefined ? <div><dt>Withheld patch check</dt><dd>{evidence.verifiedPatchCount} locally discriminative cells</dd></div> : null}{evidence?.supportExpansionCount ? <div><dt>Continuous support</dt><dd>{evidence.supportExpansionCount} edge-adjacent cells</dd></div> : null}{evidence?.patchNccMedian !== undefined && evidence.patchNccMedian >= 0 ? <div><dt>Patch NCC median</dt><dd>{evidence.patchNccMedian.toFixed(2)}</dd></div> : null}{evidence?.patchDiscriminationMedian !== undefined && evidence.patchDiscriminationMedian >= 0 ? <div><dt>Patch discrimination</dt><dd>{evidence.patchDiscriminationMedian.toFixed(2)}</dd></div> : null}{evidence?.structuralComponentPairsChecked !== undefined ? <div><dt>Fragment alternatives</dt><dd>{evidence.structuralComponentPairsChecked} checked · {evidence.acceptedStructuralComponents ?? 0} accepted · {evidence.ambiguousStructuralComponents ?? 0} ambiguous</dd></div> : null}{evidence?.layoutConsistencyMedian !== undefined ? <div><dt>Fragment layout</dt><dd>{evidence.layoutConsistencyMedian.toFixed(2)} consistency</dd></div> : null}{evidence?.opticalDensityKazeInliers !== undefined ? <div><dt>Stain-independent features</dt><dd>{evidence.opticalDensityKazeInliers} KAZE inliers · {(evidence.opticalDensityKazeSpreadMedian ?? 0).toFixed(2)} spread</dd></div> : null}<div><dt>Fit residual (not accuracy)</dt><dd>{medianResidual === null ? 'Not measured' : `${medianResidual.toFixed(1)} px`}</dd></div><div><dt>Provenance</dt><dd>{member.registration?.provenance ?? 'none'}</dd></div></dl>}{member.registration?.reason ? <p>{member.registration.reason}</p> : null}</details>
          {!member.metadata?.physicalSizeX ? <small className="comparison-relative-scale">Relative scale: physical pixel size unavailable</small> : null}
        </section>
      })}
    </main></div>
    {panes.length < Math.min(MAX_PANES, comparison.members.length) ? <button type="button" className="comparison-add-pane" disabled={!!correction} onClick={() => { const next = paneCandidates(panes)[0]; if (next) setPanes((current) => [...current, next.slideId]) }}><Plus /> Add pane</button> : null}
  </div>
}
