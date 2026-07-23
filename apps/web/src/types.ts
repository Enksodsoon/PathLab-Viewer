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
  folderId?: string | null
  description?: string
  stain?: string
  organSite?: string
  tags?: string[]
  teachingNote?: string
  adminNotes?: string
  sortOrder?: number
  reservedBytes?: number
  derivativeBytes?: number
  derivativeFileCount?: number
  publication?: {
    individual: boolean
    folderGrantCount: number
    isPublic: boolean
  }
}

export interface PublicSlide {
  publicId: string
  displayName: string
  state: 'published'
  tileSource: string
  metadata: SlideMetadata | null
}

export interface LibraryFolder {
  id: string
  parentId: string | null
  name: string
  description: string
  sortOrder: number
  createdAt: string
  updatedAt: string
  share: {
    publicId: string
    isActive: boolean
    createdAt: string
  } | null
}

export interface StorageSummary {
  sourceBytes: number
  reservedBytes: number
  derivativeBytes: number
  derivativeFileCount: number
  accountedBytes: number
  capBytes: number
  availableBytes: number
}

export interface LibraryResponse {
  folders: LibraryFolder[]
  slides: AdminSlide[]
  storage: StorageSummary
}

export interface PublicFolderSlide {
  publicId: string
  displayName: string
  description: string
  stain: string
  organSite: string
  tags: string[]
  teachingNote: string
  metadata: SlideMetadata | null
  tileSource: string
  sortOrder: number
}

export interface PublicFolderManifest {
  folderPublicId: string
  name: string
  description: string
  shareStatus: 'active'
  slides: PublicFolderSlide[]
}
