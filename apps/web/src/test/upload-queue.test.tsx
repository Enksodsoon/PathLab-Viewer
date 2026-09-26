import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UploadCallbacks } from '../upload'
const api = vi.hoisted(() => ({ reserveUpload: vi.fn(), renewUploadReservation: vi.fn(), getPrivateSlide: vi.fn() }))
const transport = vi.hoisted(() => ({ startTusUpload: vi.fn() }))
vi.mock('../api', async (original) => ({ ...await original<typeof import('../api')>(), ...api }))
vi.mock('../upload', () => transport)
import { addUploadFiles, authorizeUploadQueue, cancelUploadItem, getUploadQueueSnapshot, renameUploadItem, resetUploadQueue, retryUploadItem, startUploadQueue, useUploadQueue } from '../uploadQueue'
const file = new File(['1234567890'], 'kidney.ome.tiff', {lastModified:1})
const reservation = { slide:{id:'private-one',state:'uploading'}, uploadUrl:'/uploads', uploadToken:'secret', expiresIn:60 }
let finish: () => void
let callbacks: UploadCallbacks
beforeEach(() => {
  resetUploadQueue(); api.reserveUpload.mockReset(); api.renewUploadReservation.mockReset(); api.getPrivateSlide.mockReset(); transport.startTusUpload.mockReset()
  api.reserveUpload.mockResolvedValue(reservation)
  api.renewUploadReservation.mockResolvedValue({...reservation,uploadToken:'fresh-token'})
  api.getPrivateSlide.mockResolvedValue({id:'private-one',state:'queued'})
  transport.startTusUpload.mockImplementation((_file: File, _url: string, _token: string, next: UploadCallbacks, _id: string, signal: AbortSignal) => {
    callbacks = next
    return new Promise((resolve,reject) => { finish=() => resolve({}); signal.addEventListener('abort',()=>reject(new DOMException('Paused','AbortError')),{once:true}) })
  })
  authorizeUploadQueue()
})
afterEach(() => { cleanup(); resetUploadQueue(); vi.restoreAllMocks(); vi.useRealTimers() })
describe('persistent sequential upload queue', () => {
  it('bounds default and edited labels while preserving a 255-character source filename and reservation identity', async () => {
    const filename = `${'a'.repeat(246)}.ome.tiff`
    const source = new File(['source'], filename, {lastModified: 42})
    expect(filename).toHaveLength(255)
    addUploadFiles([source])
    const item = getUploadQueueSnapshot().items[0]
    expect(item.displayName).toBe('a'.repeat(200))
    expect(item.file).toBe(source)
    expect(item.file.name).toBe(filename)
    renameUploadItem(item.id, 'b'.repeat(220))
    expect(getUploadQueueSnapshot().items[0].displayName).toBe('b'.repeat(200))
    renameUploadItem(item.id, ' ')
    const running = startUploadQueue()
    await Promise.resolve()
    expect(api.reserveUpload).toHaveBeenCalledWith(source, 'a'.repeat(200), null)
    expect(transport.startTusUpload.mock.calls[0][0]).toBe(source)
    expect(transport.startTusUpload.mock.calls[0][4]).toBe('private-one')
    finish(); await running
    expect(source.name).toBe(filename)
  })
  it('continues one transfer across consumer remount and polls actual processing before ready', async () => {
    const first=renderHook(useUploadQueue)
    act(()=>addUploadFiles([file]))
    const second=renderHook(useUploadQueue)
    expect(second.result.current.items[0].file).toBe(file)
    let running: Promise<void>
    await act(async()=> { running=startUploadQueue(); await Promise.resolve() })
    first.unmount(); second.unmount()
    expect(getUploadQueueSnapshot().running).toBe(true)
    const next=renderHook(useUploadQueue)
    expect(next.result.current.items[0].phase).toBe('uploading')
    vi.useFakeTimers()
    await act(async()=> { finish(); await running! })
    expect(next.result.current.items[0].phase).toBe('processing')
    expect(api.getPrivateSlide).toHaveBeenCalledWith('private-one')
    api.getPrivateSlide.mockResolvedValue({id:'private-one',state:'ready_private'})
    await act(async()=> { await vi.advanceTimersByTimeAsync(5000) })
    expect(getUploadQueueSnapshot().items[0].phase).toBe('ready')
  })
  it('retains a late reservation after cancellation and resumes the same identity', async () => {
    let reserved: (value: typeof reservation) => void = () => {}
    api.reserveUpload.mockImplementation(()=>new Promise((resolve)=>{reserved=resolve}))
    addUploadFiles([file]); const id=getUploadQueueSnapshot().items[0].id
    const running=startUploadQueue(); cancelUploadItem(id); reserved(reservation); await running
    expect(transport.startTusUpload).not.toHaveBeenCalled()
    expect(getUploadQueueSnapshot().items[0].reservation).toBe(reservation)
    retryUploadItem(id); await Promise.resolve()
    expect(api.reserveUpload).toHaveBeenCalledTimes(1)
    expect(api.renewUploadReservation).toHaveBeenCalledWith('private-one')
    expect(transport.startTusUpload.mock.calls[0][2]).toBe('fresh-token')
    expect(transport.startTusUpload.mock.calls[0][4]).toBe('private-one')
    finish(); await vi.waitFor(()=>expect(getUploadQueueSnapshot().running).toBe(false))
  })
  it('computes speed only from measured byte deltas and forgets data on session reset', async () => {
    let now=1000; vi.spyOn(performance,'now').mockImplementation(()=>now)
    addUploadFiles([file]); const running=startUploadQueue(); await Promise.resolve()
    callbacks.bytes!(3,10); expect(getUploadQueueSnapshot().items[0].bytesPerSecond).toBeNull()
    now=2000; callbacks.bytes!(7,10)
    expect(getUploadQueueSnapshot().items[0].bytesPerSecond).toBe(4)
    expect(getUploadQueueSnapshot().items[0].etaSeconds).toBe(.75)
    now=2100; callbacks.bytes!(7,10)
    expect(getUploadQueueSnapshot().items[0].bytesPerSecond).toBe(4)
    expect(getUploadQueueSnapshot().items[0].lastSampleAt).toBe(2000)
    window.dispatchEvent(new Event('pathlab-session-ended')); await running
    expect(getUploadQueueSnapshot()).toMatchObject({items:[],authorized:false,running:false})
  })
})
