import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { Loader } from './components/Loader'

const AdminPage = lazy(() => import('./pages/AdminPage').then((module) => ({ default: module.AdminPage })))
const ViewerPage = lazy(() => import('./pages/ViewerPage').then((module) => ({ default: module.ViewerPage })))
const SharedViewerPage = lazy(() => import('./pages/SharedViewerPage').then((module) => ({ default: module.SharedViewerPage })))
const DesktopConnectPage = lazy(() => import('./pages/DesktopConnectPage').then((module) => ({ default: module.DesktopConnectPage })))
const ClassroomTeacherPage = lazy(() => import('./pages/ClassroomTeacherPage').then((module) => ({ default: module.ClassroomTeacherPage })))
const ClassroomStudentPage = lazy(() => import('./pages/ClassroomStudentPage').then((module) => ({ default: module.ClassroomStudentPage })))
const ClassroomInvitePage = lazy(() => import('./pages/ClassroomInvitePage').then((module) => ({ default: module.ClassroomInvitePage })))
const StudyPage = lazy(() => import('./pages/StudyPage').then((module) => ({ default: module.StudyPage })))
const StudyAdminPage = lazy(() => import('./pages/StudyAdminPage').then((module) => ({ default: module.StudyAdminPage })))

export function App() {
  return <Routes>
    <Route path="/admin" element={<Suspense fallback={<Loader label="Opening admin…" size="large" fullscreen />}><AdminPage /></Suspense>} />
    <Route path="/admin/preview/:slideId" element={<Suspense fallback={<Loader label="Opening private preview…" size="large" fullscreen />}><ViewerPage /></Suspense>} />
    <Route path="/admin/connect" element={<Suspense fallback={<Loader label="Opening device pairing…" size="large" fullscreen />}><DesktopConnectPage /></Suspense>} />
    <Route path="/admin/classroom" element={<Suspense fallback={<Loader label="Opening classroom…" size="large" fullscreen />}><ClassroomTeacherPage /></Suspense>} />
    <Route path="/classroom" element={<Suspense fallback={<Loader label="Opening classroom…" size="large" fullscreen />}><ClassroomStudentPage /></Suspense>} />
    <Route path="/classroom/invite/:publicId" element={<Suspense fallback={<Loader label="Opening classroom review…" size="large" fullscreen />}><ClassroomInvitePage /></Suspense>} />
    <Route path="/classroom/:sessionId" element={<Suspense fallback={<Loader label="Opening classroom…" size="large" fullscreen />}><ClassroomStudentPage /></Suspense>} />
    <Route path="/admin/study" element={<Suspense fallback={<Loader label="Opening Study Coach…" size="large" fullscreen />}><StudyAdminPage /></Suspense>} />
    <Route path="/study" element={<Suspense fallback={<Loader label="Opening Study Mode…" size="large" fullscreen />}><StudyPage /></Suspense>} />
    <Route path="/s/:publicId" element={<Suspense fallback={<Loader label="Opening slide…" size="large" fullscreen />}><ViewerPage /></Suspense>} />
    <Route path="/f/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="folder" /></Suspense>} />
    <Route path="/c/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="collection" /></Suspense>} />
    <Route path="*" element={<Navigate to="/admin" replace />} />
  </Routes>
}
