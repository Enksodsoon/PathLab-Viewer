import assert from 'node:assert/strict'
import test from 'node:test'

import { validateManifest } from './manifest_contract.mjs'

const valid = {
  slides: [
    {
      publicId: 'public-1',
      dziPath: 'slide.dzi',
      commonTiles: ['slide_files/13/1_1.jpeg'],
      randomTiles: ['slide_files/11/0_0.jpeg'],
    },
  ],
}

test('accepts bounded public-only manifest', () => {
  assert.deepEqual(validateManifest(valid), valid.slides)
})

test('rejects missing groups and unsafe paths', () => {
  assert.throws(() => validateManifest({ slides: [] }), /manifest/i)
  assert.throws(
    () =>
      validateManifest({
        slides: [{ ...valid.slides[0], randomTiles: ['../private.jpeg'] }],
      }),
    /manifest/i,
  )
  assert.throws(
    () =>
      validateManifest({
        slides: [{ ...valid.slides[0], displayName: 'private' }],
      }),
    /manifest/i,
  )
})
