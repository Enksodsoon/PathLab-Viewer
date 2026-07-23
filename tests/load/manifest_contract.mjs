const PUBLIC_ID = /^[A-Za-z0-9_-]+$/
const DZI_PATH = /^[A-Za-z0-9_-]+\.dzi$/
const TILE_PATH = /^slide_files\/\d+\/\d+_\d+\.(?:jpg|jpeg)$/i
const SLIDE_KEYS = ['commonTiles', 'dziPath', 'publicId', 'randomTiles']

function invalid() {
  throw new Error('Invalid viewer load manifest')
}

function validatePaths(paths, limit) {
  if (!Array.isArray(paths) || paths.length === 0 || paths.length > limit) {
    invalid()
  }
  for (const path of paths) {
    if (typeof path !== 'string' || !TILE_PATH.test(path)) {
      invalid()
    }
  }
}

export function validateManifest(manifest) {
  if (
    manifest === null ||
    typeof manifest !== 'object' ||
    Array.isArray(manifest) ||
    Object.keys(manifest).length !== 1 ||
    !Array.isArray(manifest.slides) ||
    manifest.slides.length === 0
  ) {
    invalid()
  }
  for (const slide of manifest.slides) {
    if (slide === null || typeof slide !== 'object' || Array.isArray(slide)) {
      invalid()
    }
    const keys = Object.keys(slide).sort()
    if (keys.length !== SLIDE_KEYS.length || keys.some((key, index) => key !== SLIDE_KEYS[index])) {
      invalid()
    }
    if (typeof slide.publicId !== 'string' || !PUBLIC_ID.test(slide.publicId)) {
      invalid()
    }
    if (typeof slide.dziPath !== 'string' || !DZI_PATH.test(slide.dziPath)) {
      invalid()
    }
    validatePaths(slide.commonTiles, 12)
    validatePaths(slide.randomTiles, 256)
  }
  return manifest.slides
}
