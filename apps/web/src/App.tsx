import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminPage } from './pages/AdminPage'

const ViewerPage = lazy(() => import('./pages/ViewerPage').then((module) => ({ default: module.ViewerPage })))
const SharedViewerPage = lazy(() => import('./pages/SharedViewerPage').then((module) => ({ default: module.SharedViewerPage })))

export function App() {
  return <Routes>
    <Route path="/admin" element={<AdminPage />} />
    <Route path="/admin/preview/:slideId" element={<Suspense fallback={<div className="center-state dark">Opening private preview…</div>}><ViewerPage /></Suspense>} />
    <Route path="/s/:publicId" element={<Suspense fallback={<div className="center-state dark">Opening slide…</div>}><ViewerPage /></Suspense>} />
    <Route path="/f/:publicId" element={<Suspense fallback={<div className="center-state dark">Opening shared library…</div>}><SharedViewerPage targetType="folder" /></Suspense>} />
    <Route path="/c/:publicId" element={<Suspense fallback={<div className="center-state dark">Opening shared library…</div>}><SharedViewerPage targetType="collection" /></Suspense>} />
    <Route path="*" element={<Navigate to="/admin" replace />} />
  </Routes>
}
