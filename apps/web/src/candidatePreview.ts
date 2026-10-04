import type { ComparisonMember, ComparisonSet, RegistrationCandidate, RegistrationCandidateManifest, SlideRegistration } from './types'

function boundedMap(registration: SlideRegistration, moving: ComparisonMember, anchor: ComparisonMember): boolean {
  const matrix = registration.movingToReference
  if (!Array.isArray(matrix) || matrix.length !== 2 || matrix.some(row => !Array.isArray(row) || row.length !== 3 || row.some(value => !Number.isFinite(value)))) return false
  const determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
  if (!Number.isFinite(determinant) || determinant <= 1e-12) return false
  if ((registration.triangles && !Array.isArray(registration.triangles)) || (registration.overviewTriangles && !Array.isArray(registration.overviewTriangles))) return false
  const supported = [...(registration.triangles ?? []), ...(registration.overviewTriangles ?? [])]
  const signedArea = ([[ax, ay], [bx, by], [cx, cy]]: number[][]) => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
  const validCell = (points: number[][], member: ComparisonMember) => {
    const width = member.metadata?.width; const height = member.metadata?.height
    if (!width || !height || !Number.isFinite(width) || !Number.isFinite(height)
      || !Array.isArray(points) || points.length !== 3
      || points.some(point => !Array.isArray(point) || point.length !== 2 || point.some(value => !Number.isFinite(value))
        || point[0] < -1e-7 || point[1] < -1e-7 || point[0] > width + 1e-7 || point[1] > height + 1e-7)) return false
    const area = signedArea(points)
    return Number.isFinite(area) && Math.abs(area) > 1e-12
  }
  return supported.length > 0 && supported.every(cell => {
    if (!validCell(cell.moving, moving) || !validCell(cell.reference, anchor)) return false
    const orientation = signedArea(cell.reference) / signedArea(cell.moving)
    return Number.isFinite(orientation) && orientation > 1e-12
  })
}

/** Admission requires affirmative live pair proof, including independently fetched snapshots. */
export function candidatePairIsCurrent(candidate: RegistrationCandidate, comparison: ComparisonSet, manifest: RegistrationCandidateManifest | null): boolean {
  if (candidate.currentPair !== true || candidate.currentSettings !== true
    || manifest?.comparisonSetId !== comparison.id || manifest.setVersion !== comparison.version
    || candidate.setVersion !== comparison.version || !candidate.registration
    || ['stale', 'rejected', 'needs_refinement'].includes(candidate.status)) return false
  const moving = comparison.members.find(member => member.slideId === candidate.slideId)
  const anchor = comparison.members.find(member => member.slideId === candidate.anchorSlideId)
  const reference = candidate.registration.coordinateReferenceId
  return !!moving && !!anchor && moving.slideId !== anchor.slideId
    && (moving.anchorSlideId ?? comparison.referenceSlideId) === anchor.slideId
    && candidate.registration.anchorSlideId === anchor.slideId && reference === anchor.slideId
    && typeof moving.alignmentSourceVersion === 'string' && moving.alignmentSourceVersion.length > 0
    && typeof anchor.alignmentSourceVersion === 'string' && anchor.alignmentSourceVersion.length > 0
    && candidate.sourceSnapshotVersion === moving.alignmentSourceVersion
    && candidate.anchorSnapshotVersion === anchor.alignmentSourceVersion
    && ['ready', 'approximate'].includes(candidate.registration.status)
    && boundedMap(candidate.registration, moving, anchor)
}

export function candidatePreviewRegistration(candidate: RegistrationCandidate, comparison: ComparisonSet, manifest: RegistrationCandidateManifest | null): SlideRegistration | null {
  if (!candidatePairIsCurrent(candidate, comparison, manifest)) return null
  const registration = candidate.registration!
  // This projection is admitted against the live original sources/frame/calibration by the API.
  // Never recover a fallback from an unbound legacy registration or tile URL.
  const fallback = comparison.members.find(member => member.slideId === candidate.slideId)?.nativeOverviewFallback
  const moving = comparison.members.find(member => member.slideId === candidate.slideId)!
  const anchor = comparison.members.find(member => member.slideId === candidate.anchorSlideId)!
  const compatible = fallback?.status === 'approximate'
    && fallback.engine === 'native-overview-v6'
    && fallback.anchorSlideId === candidate.anchorSlideId
    && fallback.coordinateReferenceId === candidate.anchorSlideId
    && !!fallback.movingToReference && !!fallback.overviewTriangles?.length
    && boundedMap(fallback, moving, anchor)
  return { ...registration, retainedOverviewFallback: compatible ? fallback : undefined }
}
