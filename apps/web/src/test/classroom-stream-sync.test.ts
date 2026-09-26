import { describe, expect, it } from 'vitest'

import {
  applyClassroomStreamEvent,
  createClassroomEphemeralBuffer,
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
  it('reconciles a teaching annotation mutation missed during disconnection', () => {
    const cursor = createClassroomStreamCursor(4)
    applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch', eventSequence: 10, stateVersion: 4,
    })
    // A teaching mutation commits version 5 while this client is disconnected.
    expect(applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch', eventSequence: 11, stateVersion: 5,
    })).toBe('resync')
    noteClassroomSnapshot(cursor, 5)
    expect(cursor.stateVersion).toBe(5)
  })

  it('holds contiguous versionless events after a gap but still accepts terminal authority', () => {
    const cursor = createClassroomStreamCursor(4)
    applyClassroomStreamEvent(cursor, 'stream-ready', {
      hubEpoch: 'epoch', eventSequence: 0, stateVersion: 4,
    })
    expect(applyClassroomStreamEvent(cursor, 'control', {
      hubEpoch: 'epoch', eventSequence: 2, stateVersion: 5,
    })).toBe('resync')
    expect(applyClassroomStreamEvent(cursor, 'pointer', {
      hubEpoch: 'epoch', eventSequence: 3,
    }, { coalescible: true })).toBe('resync')
    expect(applyClassroomStreamEvent(cursor, 'session-ended', {
      hubEpoch: 'epoch', eventSequence: 4, stateVersion: 5,
    }, { terminal: true })).toBe('apply')
    expect(cursor.needsSnapshot).toBeUndefined()
  })

  it('bounds ephemeral buffering by field and replays only latest arrival order', () => {
    const buffer = createClassroomEphemeralBuffer()
    const applied: string[] = []
    for (let sample = 0; sample < 1000; sample += 1) {
      buffer.hold('pointer', () => applied.push(`pointer-${sample}`))
      buffer.hold('presenter', () => applied.push(`presenter-${sample}`))
    }
    buffer.hold('pointer-removed', () => applied.push('pointer-removed'))
    expect(buffer.hold('control', () => applied.push('control'))).toBe(false)
    buffer.drain()
    expect(applied).toEqual(['presenter-999', 'pointer-removed'])
    buffer.hold('presenter', () => applied.push('obsolete-session'))
    buffer.clear()
    buffer.drain()
    expect(applied).toHaveLength(2)
  })

})
