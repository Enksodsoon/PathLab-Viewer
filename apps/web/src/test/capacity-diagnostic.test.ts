import { describe, expect, it } from 'vitest'

import { conversionDecision } from '../../e2e-live/capacity-helpers'

describe('capacity conversion diagnostics', () => {
  it('preserves an allowlisted terminal conversion error code', () => {
    expect(conversionDecision({
      state: 'failed',
      errorCode: 'OME_DIMENSIONS_INVALID',
    }, false)).toEqual({
      kind: 'failed',
      errorCode: 'OME_DIMENSIONS_INVALID',
    })
  })

  it('uses a generic code when a terminal error code is unsafe', () => {
    expect(conversionDecision({
      state: 'failed',
      errorCode: 'private worker detail',
    }, false)).toEqual({
      kind: 'failed',
      errorCode: 'CONVERSION_FAILED',
    })
  })

  it('distinguishes a pending conversion from a timed-out conversion', () => {
    expect(conversionDecision({ state: 'processing' }, false)).toEqual({
      kind: 'pending',
    })
    expect(conversionDecision({ state: 'processing' }, true)).toEqual({
      kind: 'failed',
      errorCode: 'CONVERSION_TIMEOUT',
    })
  })
})
