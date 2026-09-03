import assert from 'node:assert/strict'

import { FileUrlStorage } from '../../apps/web/node_modules/tus-js-client/lib/node/urlStorage.js'

const storage = new FileUrlStorage('unused-characterization-path')
const operationError = new Error('operation failed')
const releaseError = new Error('release failed')
const aggregate = await new Promise((resolve) => {
  storage._releaseAndCb(() => Promise.reject(releaseError), resolve)(operationError)
})

assert.equal(aggregate.name, 'MultiError')
assert.equal(aggregate.message, 'operation failed; release failed')
assert.deepEqual(aggregate.errors, [operationError, releaseError])
assert.match(aggregate.stack, /operation failed/)
assert.match(aggregate.stack, /release failed/)

const original = await new Promise((resolve) => {
  storage._releaseAndCb(() => Promise.resolve(), resolve)(operationError)
})
assert.equal(original, operationError)

console.log('tus-js-client patched error aggregation PASS')
