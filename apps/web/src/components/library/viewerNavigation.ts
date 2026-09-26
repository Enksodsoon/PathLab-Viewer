import type { LibrarySlide } from '../../types'

export interface LibraryViewerContext {
  returnTo: string
  slides: { id: string; displayName: string }[]
}
export function canPreview(slide: LibrarySlide) {
  return !slide.trashedAt && (slide.state === 'ready_private' || slide.state === 'published')
}
export function ignoresShortcut(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"]'))
}
export function isNestedControl(target: EventTarget | null, current: EventTarget | null) {
  return target instanceof Element && target !== current && Boolean(target.closest('button, a, input, label, select, textarea, [role="menu"]'))
}
export function readLibraryContext(value: unknown): LibraryViewerContext | null {
  if (!value || typeof value !== 'object' || !('library' in value)) return null
  const library = value.library as Partial<LibraryViewerContext> | null
  if (!library || typeof library.returnTo !== 'string' || !/^\/admin(?:\?|$)/.test(library.returnTo) || !Array.isArray(library.slides)) return null
  return { returnTo: library.returnTo, slides: library.slides.filter((item) => item && typeof item.id === 'string' && typeof item.displayName === 'string') }
}
