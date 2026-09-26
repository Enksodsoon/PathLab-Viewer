import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const queue=vi.hoisted(()=>({snapshot:{authorized:true,running:false,notice:'',items:[] as unknown[]}}))
vi.mock('../uploadQueue',()=>({useUploadQueue:()=>queue.snapshot,cancelUploadItem:vi.fn(),removeUploadItem:vi.fn(),retryUploadItem:vi.fn(),startUploadQueue:vi.fn()}))
import { UploadDock } from '../components/library/UploadDock'
const item={id:'upload',file:new File(['slide'],'slide.ome.tiff'),displayName:'Kidney',phase:'processing',processingState:'converting',progress:100,error:'',uploadedBytes:5,bytesPerSecond:null,etaSeconds:null,reservation:{slide:{id:'private'}}}
beforeEach(()=>{ queue.snapshot={authorized:true,running:false,notice:'',items:[item]} })
afterEach(cleanup)
it('opens only API-confirmed ready slides and minimizes without cancelling transfer',()=>{
  const {rerender}=render(<MemoryRouter><UploadDock /></MemoryRouter>)
  expect(screen.getByText(/Processing: converting/)).toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'Open viewer'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Minimize uploads'}))
  expect(screen.queryByText('Kidney')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Expand uploads'}))
  queue.snapshot.items=[{...item,phase:'ready'}];rerender(<MemoryRouter><UploadDock /></MemoryRouter>)
  expect(screen.getByRole('link',{name:'Open viewer'})).toHaveAttribute('href','/admin/preview/private')
})
it('does not reveal queued source metadata after session reset',()=>{
  queue.snapshot.authorized=false
  render(<MemoryRouter><UploadDock /></MemoryRouter>)
  expect(screen.queryByLabelText('Background uploads')).not.toBeInTheDocument()
})
