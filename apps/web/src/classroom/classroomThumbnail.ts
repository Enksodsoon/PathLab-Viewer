import type { ClassroomSlide } from './api'

export function classroomSlideThumbnail(slide: ClassroomSlide): string {
  const maximumDimension = Math.max(slide.width, slide.height)
  const maximumLevel = Math.ceil(Math.log2(maximumDimension))
  const previewLevel = Math.max(
    0,
    maximumLevel - Math.max(0, Math.ceil(Math.log2(maximumDimension / 256))),
  )
  const descriptorRoot = slide.tileSource.replace(/\.dzi(?:\?.*)?$/i, '')
  return `${descriptorRoot}_files/${previewLevel}/0_0.${slide.format}`
}
