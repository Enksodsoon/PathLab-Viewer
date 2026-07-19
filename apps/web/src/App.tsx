import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminPage } from './pages/AdminPage'

const ViewerPage = lazy(() => import('./pages/ViewerPage').then((module) => ({ default: module.ViewerPage })))

export function App() {
  return <Routes>
    <Route path="/admin" element={<AdminPage />} />
    <Route path="/admin/preview/:slideId" element={<Suspense fallback={<div className="center-state dark">Opening private preview…</div>}><ViewerPage /></Suspense>} />
    <Route path="/s/:publicId" element={<Suspense fallback={<div className="center-state dark">Opening slide…</div>}><ViewerPage /></Suspense>} />
    <Route path="*" element={<Navigate to="/admin" replace />} />
  </Routes>
}
