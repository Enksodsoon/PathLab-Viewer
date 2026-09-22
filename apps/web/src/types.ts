export type SlideState =
  | 'uploading'
  | 'queued'
  | 'validating'
  | 'converting'
  | 'ready_private'
  | 'published'
  | 'failed'
  | 'deleting'

export interface SlideMetadata {
  width: number
  height: number
  bitsPerSample?: number
  physicalSizeX?: number | null
  physicalSizeY?: number | null
  physicalSizeUnit?: string | null
}

export interface AdminSlide {
  id: string
  publicId: string
  displayName: string
  filename: string
  sourceBytes: number
  state: SlideState
  errorCode: string | null
  errorMessage: string | null
  metadata: SlideMetadata | null
  createdAt: string
  folderId?: string | null
  tileSource?: string
  renderMode?: 'static_dzi' | 'ome_dynamic'
  thumbnailUrl?: string | null
  annotationsEnabled?: boolean
  annotationVersion?: number
}

export interface PublicSlide {
  publicId: string
  displayName: string
  state: 'published'
  tileSource: string
  thumbnailUrl?: string | null
  metadata: SlideMetadata | null
}

export interface LibrarySlide {
  id: string
  publicId: string
  displayName: string
  description: string
  folderId: string | null
  caseId: string
  organSite: string
  stain: string
  diagnosis: string
  course: string
  tags: string[]
  teachingNote: string
  sourceBytes: number
  derivativeBytes: number
  state: SlideState
  errorCode: string | null
  createdAt: string
  updatedAt: string
  trashedAt: string | null
  thumbnailUrl: string | null
  stackCount?: number
}

export interface LibrarySlideDetails extends LibrarySlide {
  filename: string
  adminNotes: string
  metadata: SlideMetadata | null
}

export interface LibraryFolder {
  id: string
  parentId: string | null
  name: string
  description: string
  sortOrder: number
  itemCount: number
  childCount: number
  hasChildren: boolean
  trashedAt: string | null
  updatedAt: string
}

export interface LibraryCollection {
  id: string
  name: string
  description: string
  sortOrder: number
  itemCount: number
  updatedAt: string
}

export interface SavedView {
  id: string
  name: string
  definition: {
    version: 1
    filters: Record<string, string | string[]>
  }
  sort: string
  updatedAt: string
}

export interface LibraryNavigation {
  capabilities?: {
    classroom: boolean
    study?: boolean
    assessment?: boolean
    alignment?: boolean
  }
  counts: {
    all: number
    unfiled: number
    shared: number
    processing: number
    failed: number
    trash: number
  }
  folders: LibraryFolder[]
  folderPath?: LibraryFolder[]
  collections: LibraryCollection[]
  savedViews: SavedView[]
  storage: {
    usedBytes: number
    usableBytes: number
    effectiveCapacityBytes: number
  }
}

export interface LibraryItemsPage {
  items: LibrarySlide[]
  nextCursor: string | null
  total: number
}

export interface StorageSummary {
  managedBytes: number
  usableBytes: number
  effectiveCapacityBytes: number
  applicationCapBytes: number
  physicalTotalBytes: number
  physicalUsedBytes: number
  physicalFreeBytes: number
  libraryBytes: number
  processingBytes: number
  trashBytes: number
  deletingBytes: number
  libraryCount: number
  processingCount: number
  trashCount: number
  deletingCount: number
}

export interface StorageItem {
  id: string
  displayName: string
  originalFilename: string
  state: SlideState
  sourceBytes: number
  derivativeBytes: number
  reservedBytes: number
  accountedBytes: number
  updatedAt: string
  trashedAt: string | null
  canTrash: boolean
  canRestore: boolean
  canDelete: boolean
}

export interface StorageInventory {
  summary: StorageSummary
  items: StorageItem[]
  offset: number
  limit: number
  total: number
}

export interface LibraryFacetValue {
  value: string
  count: number
}

export interface LibraryFacets {
  organ: LibraryFacetValue[]
  stain: LibraryFacetValue[]
  diagnosis: LibraryFacetValue[]
  course: LibraryFacetValue[]
}

export interface SlideStatusItem {
  id: string
  state: SlideState
  errorCode: string | null
}

export interface SharedSlide {
  position: number
  folderPath: string[]
  displayName: string
  organSite: string
  stain: string
  diagnosis: string
  tags: string[]
  teachingNote: string
  thumbnailUrl: string
  tileSource: string
  scale: number | null
}

export interface SharedManifest {
  publicId: string
  targetType: 'folder' | 'collection'
  name: string
  description: string
  expiresAt: string | null
  folders: string[][]
  slides: SharedSlide[]
}

export interface SlideRegistration {
  status: 'ready' | 'approximate' | 'rejected' | 'needs_refinement' | 'stale'
  provenance: 'automatic' | 'automatic-candidate' | 'manual'
  engine?: string
  engineVersion?: string
  anchorSlideId?: string
  coordinateReferenceId?: string
  movingToReference?: number[][]
  referenceSupport?: [number, number, number, number] | null
  movingSupport?: [number, number, number, number] | null
  confidence?: number
  controlPoints?: Array<{
    moving: [number, number]
    reference: [number, number]
    errorPixels: number
  }>
  triangles?: Array<{
    moving: [[number, number], [number, number], [number, number]]
    reference: [[number, number], [number, number], [number, number]]
    maxResidualPixels?: number
    provenance?: 'structural-feature' | 'structural-flow-patch' | 'structural-flow-neighbor' | 'manual-landmark' | 'approximate-intensity-shape' | 'approximate-structural-flow'
  }>
  overviewTriangles?: Array<{
    moving: [[number, number], [number, number], [number, number]]
    reference: [[number, number], [number, number], [number, number]]
    provenance?: 'approximate-intensity-shape' | 'approximate-structural-flow'
  }>
  supportPolygons?: {
    moving: Array<[[number, number], [number, number], [number, number]]>
    reference: Array<[[number, number], [number, number], [number, number]]>
  }
  evidence?: {
    stackAcceptedAt?: string
    previewPublishedAt?: string
    source?: string
    mode?: 'matched-regions' | 'outline-proposal'
    anatomicalMatchCount?: number
    featureMatchCount?: number
    triangleCount?: number
    overviewTriangleCount?: number
    flowControlCount?: number
    flowCycleP95?: number
    verifiedPatchCount?: number
    supportExpansionCount?: number
    patchNccMedian?: number
    patchDiscriminationMedian?: number
    structuralComponentPairsChecked?: number
    acceptedStructuralComponents?: number
    ambiguousStructuralComponents?: number
    layoutConsistencyMedian?: number
    opticalDensityKazeInliers?: number
    opticalDensityKazeSpreadMedian?: number
    componentOrderPreserved?: boolean
    availabilityReason?: string
    withheldCheck?: string
  }
  reason?: string
}

export interface ComparisonMember {
  slideId: string
  displayName: string
  stain: string
  tileSource: string | null
  thumbnailUrl: string | null
  metadata: SlideMetadata | null
  registration: SlideRegistration | null
  state?: SlideState
  availabilityReason?: string | null
  errorCode?: string | null
  anchorSlideId?: string | null
}

export interface ComparisonSet {
  id: string
  name: string
  referenceSlideId: string
  status: 'draft' | 'queued' | 'running' | 'ready' | 'partial' | 'failed' | 'cancelled'
  version: number
  alignmentConfig?: {
    anchors?: Record<string, string>
    enginePolicy?: 'benchmark' | 'selected'
    benchmarkEngines?: string[]
    selectedEngines?: Record<string, string>
  }
  members: ComparisonMember[]
}

export interface ComparisonRegistrationJob {
  phase?: 'preview' | 'refinement' | 'fallback'
  resultStatus?: SlideRegistration['status']
  runtimeSeconds?: number
  queueSeconds?: number
  id: string
  kind: 'align' | 'align_benchmark'
  engine?: string | null
  memberId: string | null
  setVersion: number | null
  status: 'queued' | 'leased' | 'running' | 'retry_wait' | 'succeeded' | 'failed' | 'cancelled'
  stage: string
  progress: number
  processedPatches: number
  processedComponentPairs: number
  totalComponentPairs: number
  totalPatches: number
  failureCode: string | null
  createdAt: string
  updatedAt?: string
  heartbeatAt?: string | null
}

export interface RegistrationCandidate {
  id: string
  slideId: string
  setVersion: number
  anchorSlideId: string
  engine: string
  engineVersion: string
  settingsDigest: string
  currentSettings: boolean
  status: 'ready' | 'approximate' | 'rejected' | 'needs_refinement' | 'stale'
  validationState: 'engineering_passed' | 'landmark_passed' | 'rejected'
  registration: SlideRegistration | null
  evidence: Record<string, unknown>
  artifactSha256: string | null
  failureReason: string | null
  createdAt: string
}

export interface RegistrationCandidateManifest {
  comparisonSetId: string
  setVersion: number
  engineAvailability: Record<string, { available: boolean, reason: string | null, buildVersion: string }>
  candidates: RegistrationCandidate[]
}

export interface SharedComparisonSummary {
  id: string
  name: string
  status: ComparisonSet['status']
}

export interface SlideStackSummary {
  id: string
  name: string
  status: ComparisonSet['status']
  version: number
  referenceSlideId: string
  role: 'reference' | 'member'
  memberCount: number
  stains: string[]
}

export interface StackSuggestion {
  slideId: string
  displayName: string
  stain: string
  caseId: string
  organSite: string
  folderId: string | null
  thumbnailUrl: string | null
  reasons: string[]
}

export interface SharePreviewItem {
  id: string
  displayName: string
  reason?: string
  privacyReviewRequired?: boolean
  folderPath?: string[]
}

export interface SharePreview {
  targetType: 'folder' | 'collection'
  targetId: string
  name: string
  description: string
  included: SharePreviewItem[]
  excluded: SharePreviewItem[]
}

export interface LibraryShare {
  id: string
  publicId: string
  targetType: 'folder' | 'collection'
  targetId: string
  state: 'active' | 'expired' | 'revoked'
  includeDescendants: boolean
  autoIncludeNew: boolean
  expiresAt: string | null
  includedCount: number
  updatedAt: string
}
