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
