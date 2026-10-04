import { expect, test } from '@playwright/test'
import { fault } from './fixture-faults'

test('fault helper accepts a leading-hyphen share identifier as data', () => {
  // Reach the disposable database lookup; a missing synthetic share cannot mutate it.
  expect(() => fault('expire-share', '-synthetic-missing-share'))
    .toThrow(/Synthetic share not found/)
})
