import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { acceptedCells, selectComplexitySamples, sourceSnapshot } from './alignment-browser-latency-inputs.mjs'

const cell = { moving: [[0, 0], [10, 0], [0, 10]], reference: [[1, 2], [11, 2], [1, 12]] }
const receipt = (digest, count, status = 'approximate') => ({ digest, recipe: 'native-overview-v6', outcome: 'ok', registration: {
  status, overviewTriangles: Array.from({ length: count }, () => cell), triangles: [],
} })

test('only accepted status with finite supported cells can enter measurement', () => {
  assert.equal(acceptedCells({ ...receipt('a', 1), outcome: 'rejected' }), null)
  assert.equal(acceptedCells(receipt('a', 0)), null)
  assert.equal(acceptedCells(receipt('a', 1, 'ready')), null)
  assert.equal(acceptedCells(receipt('a', 1, 'needs_refinement')), null)
  assert.equal(acceptedCells({ ...receipt('a', 1), registration: { status: 'approximate', overviewTriangles: [{ ...cell, moving: [[NaN, 0], [1, 0], [0, 1]] }] } }), null)
  assert.equal(acceptedCells(receipt('a', 1)).length, 1)
})

test('complexity sampling is deterministic and independent of claimed quality', () => {
  const rows = [receipt('middle', 5), receipt('large', 10), receipt('small', 1), receipt('rejected', 100, 'rejected')]
    .map(value => ({ receipt: { ...value, confidence: value.digest === 'middle' ? 1 : 0 } }))
  assert.deepEqual([...selectComplexitySamples(rows)].sort(), ['large', 'small'])
  assert.deepEqual([...selectComplexitySamples([...rows].reverse())].sort(), ['large', 'small'])
  assert.equal(selectComplexitySamples([{ receipt: receipt('empty', 0) }]).size, 0)
})

test('source binding changes with registered bytes or geometry and rejects the byte cap', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'pathlab-latency-input-'))
  const image = path.join(directory, 'thumbnail.jpg')
  try {
    // Conformance bytes only; the browser additionally requires decoded original pixels.
    await fs.writeFile(image, Buffer.from([1, 2, 3]))
    const first = await sourceSnapshot({ path: directory, size: [2, 3] })
    assert.match(first.digest, /^[a-f0-9]{64}$/)
    assert.notEqual((await sourceSnapshot({ path: directory, size: [3, 3] })).digest, first.digest)
    await fs.writeFile(image, Buffer.from([1, 2, 4]))
    assert.notEqual((await sourceSnapshot({ path: directory, size: [2, 3] })).digest, first.digest)
    await assert.rejects(sourceSnapshot({ path: directory, size: [2, 3] }, 2), /bounded thumbnail scope/)
  } finally {
    await fs.unlink(image)
    await fs.rmdir(directory)
  }
})

test('source traversal rejects file-count and depth ceilings before reading source images', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'pathlab-latency-bounds-'))
  const files = []
  const directories = []
  try {
    for (let index = 0; index < 257; index++) {
      const file = path.join(directory, `entry-${index}.bin`)
      await fs.writeFile(file, Buffer.from([index % 256]))
      files.push(file)
    }
    await assert.rejects(sourceSnapshot({ path: directory, size: [2, 3] }), /file count exceeds/)
    for (const file of files.splice(0)) await fs.unlink(file)
    let parent = directory
    for (let index = 0; index < 9; index++) {
      parent = path.join(parent, 'nested')
      await fs.mkdir(parent)
      directories.push(parent)
    }
    await assert.rejects(sourceSnapshot({ path: directory, size: [2, 3] }), /directory depth\/count exceeds/)
  } finally {
    for (const file of files) await fs.unlink(file)
    for (const nested of directories.reverse()) await fs.rmdir(nested)
    await fs.rmdir(directory)
  }
})
