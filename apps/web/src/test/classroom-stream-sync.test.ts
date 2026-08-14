import { describe, expect, it } from 'vitest'

import {
  applyClassroomStreamEvent,
  createClassroomStreamCursor,
  noteClassroomSnapshot,
} from '../classroom/streamSync'

describe('classroom stream snapshot and gap reconciliation', () => {
  it('accepts a matching stream-ready without taking another snapshot', () => {
    const cursor = createClassroomStreamCursor(17)

    expect(applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 4, stateVersion: 17,
    })).toBe('apply')
    expect(cursor).toEqual({ hubEpoch: 'epoch-a', eventSequence: 4, stateVersion: 17 })
  })

  it('resynchronizes only version, epoch, or critical sequence gaps', () => {
    const cursor = createClassroomStreamCursor(17)
    expect(applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 4, stateVersion: 18,
    })).toBe('resync')
    noteClassroomSnapshot(cursor, 18)

    expect(applyClassroomStreamEvent(cursor, 'control', {
      hubEpoch: 'epoch-a', eventSequence: 5, stateVersion: 19,
    })).toBe('resync')
    noteClassroomSnapshot(cursor, 19)
    expect(applyClassroomStreamEvent(cursor, 'control', {
      hubEpoch: 'epoch-a', eventSequence: 5, stateVersion: 19,
    })).toBe('ignore')
    expect(applyClassroomStreamEvent(cursor, 'question-removed', {
      hubEpoch: 'epoch-a', eventSequence: 7, stateVersion: 20,
    })).toBe('resync')

    noteClassroomSnapshot(cursor, 20)
    expect(applyClassroomStreamEvent(cursor, 'presenter', {
      hubEpoch: 'epoch-a', eventSequence: 11,
    }, { coalescible: true })).toBe('apply')
    expect(applyClassroomStreamEvent(cursor, 'control', {
      hubEpoch: 'epoch-b', eventSequence: 1, stateVersion: 21,
    })).toBe('resync')
  })

  it('accepts a sequenced terminal event as authoritative without a dead snapshot request', () => {
    const cursor = createClassroomStreamCursor(20)
    expect(applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch-a', eventSequence: 8, stateVersion: 20,
    })).toBe('apply')

    expect(applyClassroomStreamEvent(cursor, 'session-ended', {
      hubEpoch: 'epoch-a', eventSequence: 11, stateVersion: 21,
    }, { terminal: true })).toBe('apply')
    expect(cursor).toEqual({ hubEpoch: 'epoch-a', eventSequence: 11, stateVersion: 21 })
  })
})
