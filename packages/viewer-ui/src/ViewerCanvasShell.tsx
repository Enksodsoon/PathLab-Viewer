import type { ReactNode } from 'react'

export interface ViewerCanvasShellProps {
  rail: ReactNode
  navigator: ReactNode
  stage: ReactNode
  inspector: ReactNode
  queue: ReactNode
  railExpanded?: boolean
  navigatorOpen?: boolean
  inspectorOpen?: boolean
}

export function ViewerCanvasShell({
  rail,
  navigator,
  stage,
  inspector,
  queue,
  railExpanded = false,
  navigatorOpen = true,
  inspectorOpen = true,
}: ViewerCanvasShellProps) {
  return (
    <div className={`pathlab-canvas-shell${railExpanded ? ' rail-expanded' : ''}`}>
      {rail}
      <div
        id="library-navigator"
        className="pathlab-local-navigator"
        hidden={!navigatorOpen}
      >
        {navigator}
      </div>
      <main className="pathlab-viewer-stage">{stage}</main>
      <aside className="pathlab-viewer-inspector" hidden={!inspectorOpen}>
        {inspector}
      </aside>
      <footer className="pathlab-queue-dock">{queue}</footer>
    </div>
  )
}
