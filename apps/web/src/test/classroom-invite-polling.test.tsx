import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '../api'
import { ClassroomInvitePage } from '../pages/ClassroomInvitePage'
import { ThemeProvider } from '../theme/ThemeProvider'

const api = vi.hoisted(() => ({ classroomInviteState: vi.fn(), classroomInvitePhase: vi.fn() }))
vi.mock('../classroom/api', async (original) => ({ ...await original<typeof import('../classroom/api')>(), ...api }))
vi.mock('../components/OpenSeadragonViewer', () => ({ OpenSeadragonViewer: () => <div data-testid="review-viewer" /> }))
const invite = { sessionId: 'session', publicId: 'one', phase: 'review', reviewExpiresAt: '2027-01-01', participant: { id: 'p', alias: 'MINT-12' }, csrfToken: 'csrf', slides: [{ id: 'slide', position: 0, displayName: 'Slide', assetVersion: 'v1', tileSource: '/tiles/slide.dzi', width: 100, height: 100, tileSize: 512, format: 'jpg', folderPath: [] }] }
beforeEach(() => {
  api.classroomInviteState.mockReset()
  api.classroomInvitePhase.mockReset()
  api.classroomInviteState.mockResolvedValue(invite)
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })))
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals() })
function NextInvite() { const navigate = useNavigate(); return <button onClick={() => navigate('/classroom/invite/two')}>Next invite</button> }
async function mount() {
  render(<MemoryRouter initialEntries={['/classroom/invite/one']}><ThemeProvider><NextInvite /><Routes>
    <Route path="/classroom/invite/:publicId" element={<ClassroomInvitePage />} />
  </Routes></ThemeProvider></MemoryRouter>)
  await screen.findByText('Post-class review')
}
it('retains review after transient polling error and clears only terminal denial', async () => {
  api.classroomInvitePhase.mockRejectedValueOnce(new Error('network')).mockRejectedValueOnce(new ApiError(410, 'expired'))
  await mount()
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
  expect(screen.getByTestId('review-viewer')).toBeVisible()
  expect(await screen.findByText(/Review status could not be refreshed/)).toBeVisible()
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
  expect(await screen.findByText('This classroom invitation is no longer available.')).toBeVisible()
  expect(screen.queryByTestId('review-viewer')).not.toBeInTheDocument()
})
it('serializes timer and visibility polling and ignores old invite responses', async () => {
  let resolveOld: ((value: { phase: string }) => void) | undefined
  api.classroomInvitePhase.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
  await mount()
  vi.useFakeTimers()
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); vi.advanceTimersByTime(15000) })
  expect(api.classroomInvitePhase).toHaveBeenCalledTimes(1)
  api.classroomInviteState.mockResolvedValue({ ...invite, publicId: 'two', phase: 'preview' })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Next invite' })) })
  expect(screen.getByText('Pre-class review')).toBeVisible()
  await act(async () => { resolveOld?.({ phase: 'live' }) })
  expect(screen.getByText('Pre-class review')).toBeVisible()
  expect(screen.queryByText('Class is live')).not.toBeInTheDocument()
})

it('ignores a late initial snapshot after invitation parameters change', async () => {
  let resolveOld: ((value: typeof invite) => void) | undefined
  api.classroomInviteState.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
    .mockResolvedValueOnce({ ...invite, publicId: 'two', phase: 'preview' })
  render(<MemoryRouter initialEntries={['/classroom/invite/one']}><ThemeProvider><NextInvite /><Routes>
    <Route path="/classroom/invite/:publicId" element={<ClassroomInvitePage />} />
  </Routes></ThemeProvider></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Next invite' }))
  expect(await screen.findByText('Pre-class review')).toBeVisible()
  await act(async () => { resolveOld?.(invite) })
  expect(screen.getByText('Pre-class review')).toBeVisible()
  expect(screen.queryByText('Post-class review')).not.toBeInTheDocument()
})
