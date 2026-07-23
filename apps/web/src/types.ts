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
  tileSource?: string
}

export interface PublicSlide {
  publicId: string
  displayName: string
  state: 'published'
  tileSource: string
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
  counts: {
    all: number
    unfiled: number
    shared: number
    processing: number
    failed: number
    trash: number
  }
  folders: LibraryFolder[]
  collections: LibraryCollection[]
  savedViews: SavedView[]
}

export interface LibraryItemsPage {
  items: LibrarySlide[]
  nextCursor: string | null
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
  slides: SharedSlide[]
}

export interface SharePreviewItem {
  id: string
  displayName: string
  reason?: string
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
