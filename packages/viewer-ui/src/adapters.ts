export interface SlideSource {
  id: string
  displayName: string
  tileSource: string
  thumbnailUrl?: string
  width?: number
  height?: number
  physicalSizeX?: number
  physicalSizeY?: number
  physicalSizeUnit?: string
}

export interface SlideSourceAdapter {
  list(): Promise<SlideSource[]>
  open(slideId: string): Promise<SlideSource>
}

export interface LibraryCommandAdapter {
  search(query: string): Promise<void>
  sort(key: string, direction: 'asc' | 'desc'): Promise<void>
  openDestination(destination: 'all' | 'unfiled' | 'shared' | 'processing' | 'failed' | 'trash'): Promise<void>
  upload(): Promise<void>
  share(selection: string[]): Promise<void>
  moveToTrash(selection: string[]): Promise<void>
  restore(selection: string[]): Promise<void>
}

export interface ViewerCommandAdapter {
  zoomIn(): void
  zoomOut(): void
  home(): void
  setFullScreen(active: boolean): Promise<void> | void
  previousSlide(): Promise<void> | void
  nextSlide(): Promise<void> | void
}

export interface AnnotationDocument<TItem = unknown, TLayer = unknown> {
  slideId: string
  version: number
  items: TItem[]
  layers: TLayer[]
}

export interface AnnotationAdapter<TItem = unknown, TLayer = unknown> {
  load(slideId: string): Promise<AnnotationDocument<TItem, TLayer>>
  apply(
    slideId: string,
    baseVersion: number,
    operations: unknown[],
  ): Promise<AnnotationDocument<TItem, TLayer>>
  export(slideId: string, format: string): Promise<Blob | string>
  import(slideId: string, input: Blob | string): Promise<AnnotationDocument<TItem, TLayer>>
  history(slideId: string): Promise<unknown[]>
}

export type PathLabTheme = 'light' | 'dark' | 'system'

export interface ThemeAdapter {
  get(): PathLabTheme
  set(theme: PathLabTheme): void
  subscribe(listener: (theme: PathLabTheme) => void): () => void
}

export interface AccountState {
  connected: boolean
  displayName: string
  scopes: string[]
}

export interface AccountAdapter {
  status(): Promise<AccountState>
  connect(): Promise<AccountState>
  disconnect(): Promise<void>
}

export interface ViewerCapabilities {
  annotations: boolean
  libraryWrites: boolean
  sharing: boolean
  trash: boolean
  upload: boolean
  privatePreview: boolean
}

export interface CapabilityAdapter {
  capabilities(): Promise<ViewerCapabilities>
}

export interface ViewerUiAdapters<
  TAnnotationItem = unknown,
  TAnnotationLayer = unknown,
> {
  slides: SlideSourceAdapter
  library: LibraryCommandAdapter
  viewer: ViewerCommandAdapter
  annotations: AnnotationAdapter<TAnnotationItem, TAnnotationLayer>
  theme: ThemeAdapter
  account: AccountAdapter
  capabilities: CapabilityAdapter
}
