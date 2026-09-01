import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams, useSearchParams } from 'react-router-dom'

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
const StudyPackAuthoringPage = lazy(() => import('./pages/StudyPackAuthoringPage').then((module) => ({ default: module.StudyPackAuthoringPage })))
const AssessmentAdminPage = lazy(() => import('./pages/AssessmentAdminPage').then((module) => ({ default: module.AssessmentAdminPage })))
const AssessmentBuilderPage = lazy(() => import('./pages/AssessmentBuilderPage').then((module) => ({ default: module.AssessmentBuilderPage })))
const AssessmentStudentPage = lazy(() => import('./pages/AssessmentStudentPage').then((module) => ({ default: module.AssessmentStudentPage })))
const AssessmentClassesPage = lazy(() => import('./pages/AssessmentClassesPage').then((module) => ({ default: module.AssessmentClassesPage })))
const AssessmentCourseFormPage = lazy(() => import('./pages/AssessmentCourseFormPage').then((module) => ({ default: module.AssessmentCourseFormPage })))
const AssessmentCourseDetailPage = lazy(() => import('./pages/AssessmentCourseDetailPage').then((module) => ({ default: module.AssessmentCourseDetailPage })))
const AssessmentCourseRosterPage = lazy(() => import('./pages/AssessmentCourseRosterPage').then((module) => ({ default: module.AssessmentCourseRosterPage })))
const AssessmentClassFormPage = lazy(() => import('./pages/AssessmentClassFormPage').then((module) => ({ default: module.AssessmentClassFormPage })))
const AssessmentClassDetailPage = lazy(() => import('./pages/AssessmentClassDetailPage').then((module) => ({ default: module.AssessmentClassDetailPage })))
const AssessmentShell = lazy(() => import('./pages/AssessmentShell').then((module) => ({ default: module.AssessmentShell })))

function LegacyAssessmentReportRedirect() {
  const { draftId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const next = new URLSearchParams(searchParams)
  next.set('tab', 'responses')
  return <Navigate replace to={`/admin/assessments/${encodeURIComponent(draftId)}?${next.toString()}`} />
}

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
    <Route path="/admin/study/packs/new" element={<Suspense fallback={<Loader label="Opening Study Pack authoring…" size="large" fullscreen />}><StudyPackAuthoringPage /></Suspense>} />
    <Route element={<Suspense fallback={<Loader label="Opening Assessment…" size="large" fullscreen />}><AssessmentShell /></Suspense>}>
      <Route path="/admin/assessments" element={<AssessmentAdminPage />} />
      <Route path="/admin/assessments/classes" element={<AssessmentClassesPage />} />
      <Route path="/admin/assessments/courses/new" element={<AssessmentCourseFormPage />} />
      <Route path="/admin/assessments/courses/:courseId" element={<AssessmentCourseDetailPage />} />
      <Route path="/admin/assessments/courses/:courseId/edit" element={<AssessmentCourseFormPage />} />
      <Route path="/admin/assessments/courses/:courseId/roster" element={<AssessmentCourseRosterPage />} />
      <Route path="/admin/assessments/courses/:courseId/classes/new" element={<AssessmentClassFormPage />} />
      <Route path="/admin/assessments/courses/:courseId/classes/:classId" element={<AssessmentClassDetailPage />} />
      <Route path="/admin/assessments/courses/:courseId/classes/:classId/edit" element={<AssessmentClassFormPage />} />
      <Route path="/admin/assessments/:draftId/report" element={<LegacyAssessmentReportRedirect />} />
      <Route path="/admin/assessments/:draftId" element={<AssessmentBuilderPage />} />
    </Route>
    <Route path="/assessment/:publicId" element={<Suspense fallback={<Loader label="Opening assessment…" size="large" fullscreen />}><AssessmentStudentPage /></Suspense>} />
    <Route path="/study" element={<Suspense fallback={<Loader label="Opening Study Mode…" size="large" fullscreen />}><StudyPage /></Suspense>} />
    <Route path="/s/:publicId" element={<Suspense fallback={<Loader label="Opening slide…" size="large" fullscreen />}><ViewerPage /></Suspense>} />
    <Route path="/f/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="folder" /></Suspense>} />
    <Route path="/c/:publicId" element={<Suspense fallback={<Loader label="Opening shared library…" size="large" fullscreen />}><SharedViewerPage targetType="collection" /></Suspense>} />
    <Route path="*" element={<Navigate to="/admin" replace />} />
  </Routes>
}
