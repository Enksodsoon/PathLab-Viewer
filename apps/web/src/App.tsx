import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { Loader } from './components/Loader'

const AdminPage = lazy(() => import('./pages/AdminPage').then((module) => ({ default: module.AdminPage })))
const ViewerPage = lazy(() => import('./pages/ViewerPage').then((module) => ({ default: module.ViewerPage })))
const SharedViewerPage = lazy(() => import('./pages/SharedViewerPage').then((module) => ({ default: module.SharedViewerPage })))

export function App() {
  return <Routes>
    <Route path="/admin" element={<Suspense fallback={<Loader label="Opening admin…" size="large" fullscreen />}><AdminPage /></Suspense>} />
    <Route path="/admin/preview/:slideId" element={<Suspense fallback={<Loader label="Opening private preview…" size="large" fullscreen />}><ViewerPage /></Suspense>} />
    <Route path="/s/:publicId" element={<Suspense fallback={<Loader label="Opening slide…" size="large" fullscreen />}><ViewerPage /></Suspense>} />
    <Route path="/f/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="folder" /></Suspense>} />
    <Route path="/c/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="collection" /></Suspense>} />
    <Route path="*" element={<Navigate to="/admin" replace />} />
  </Routes>
}
