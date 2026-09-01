import { ArrowLeft, ArrowRight, CaretRight } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { ThemeControl } from '../../theme/ThemeControl'

export function AssessmentToolbar({
  title,
  actions,
  children,
}: {
  title: string
  actions?: ReactNode
  children?: ReactNode
}) {
  const navigate = useNavigate()
  return <header className="assessment-toolbar" aria-label="Teacher Studio command bar" data-canvas-region="command-bar">
    <div className="assessment-breadcrumb-row">
      <div className="assessment-history-controls" aria-label="Page history">
        <button type="button" aria-label="Back" onClick={() => navigate(-1)}><ArrowLeft /></button>
        <button type="button" aria-label="Forward" onClick={() => navigate(1)}><ArrowRight /></button>
      </div>
      <nav aria-label="Breadcrumb">
        <NavLink to="/admin">PathLab Viewer</NavLink>
        <CaretRight aria-hidden="true" />
        <span aria-current="page">{title}</span>
      </nav>
      <div className="assessment-toolbar-utilities">
        <ThemeControl compact className="assessment-theme-control" />
        {actions}
      </div>
    </div>
    {children ? <div className="assessment-command-row">{children}</div> : null}
  </header>
}

export function AssessmentWorkspaceNav() {
  return <nav className="assessment-workspace-nav" aria-label="Assessment workspace">
    <NavLink to="/admin/assessments/classes">Courses</NavLink>
    <NavLink end to="/admin/assessments">Assessments</NavLink>
  </nav>
}
