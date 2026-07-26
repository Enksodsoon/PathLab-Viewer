import { describe, expect, it } from 'vitest'

import {
  conversionDecision,
  publicAvailabilityDecision,
} from '../../e2e-live/capacity-helpers'

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

describe('capacity publication diagnostics', () => {
  it('preserves a sanitized public metadata HTTP failure', () => {
    expect(publicAvailabilityDecision({
      metadataBody: { detail: { code: 'SLIDE_NOT_FOUND' } },
      metadataStatus: 404,
    })).toEqual({
      kind: 'failed',
      errorCode: 'SLIDE_NOT_FOUND',
      httpStatus: 404,
    })
  })

  it('distinguishes incomplete metadata, poster, and descriptor failures', () => {
    expect(publicAvailabilityDecision({
      metadataBody: {},
      metadataStatus: 200,
    })).toEqual({
      kind: 'failed',
      errorCode: 'PUBLIC_METADATA_INCOMPLETE',
      httpStatus: 0,
    })
    expect(publicAvailabilityDecision({
      metadataBody: {
        thumbnailUrl: '/tiles/public/version/thumbnail.jpg',
        tileSource: '/tiles/public/version/slide.dzi',
      },
      metadataStatus: 200,
      posterStatus: 404,
      descriptorStatus: 200,
    })).toEqual({
      kind: 'failed',
      errorCode: 'PUBLIC_POSTER_UNAVAILABLE',
      httpStatus: 404,
    })
    expect(publicAvailabilityDecision({
      metadataBody: {
        thumbnailUrl: '/tiles/public/version/thumbnail.jpg',
        tileSource: '/tiles/public/version/slide.dzi',
      },
      metadataStatus: 200,
      posterStatus: 200,
      descriptorStatus: 503,
    })).toEqual({
      kind: 'failed',
      errorCode: 'PUBLIC_DESCRIPTOR_UNAVAILABLE',
      httpStatus: 503,
    })
  })
})
