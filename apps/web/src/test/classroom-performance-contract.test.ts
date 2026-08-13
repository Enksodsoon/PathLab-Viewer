import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('classroom disabled-mode resource contract', () => {
  it('keeps classroom pages lazy and absent from the main entrypoint', () => {
    const app = readFileSync(resolve('src/App.tsx'), 'utf8')
    const entrypoint = readFileSync(resolve('src/main.tsx'), 'utf8')

    expect(app).toContain("lazy(() => import('./pages/ClassroomTeacherPage')")
    expect(app).toContain("lazy(() => import('./pages/ClassroomStudentPage')")
    expect(entrypoint).not.toMatch(/classroom/i)
  })

  it('does not define any screenshot or notebook upload endpoint', () => {
    const classroomApi = readFileSync(resolve('src/classroom/api.ts'), 'utf8')
    const notebook = readFileSync(resolve('src/classroom/notebook.ts'), 'utf8')

    expect(classroomApi).not.toMatch(/screenshot|notebook|capture/i)
    expect(notebook).not.toMatch(/fetch\(|XMLHttpRequest|sendBeacon/)
  })

  it('keeps live teaching projection outside the React animation loop', () => {
    const overlay = readFileSync(resolve('src/classroom/ClassroomTeachingOverlays.tsx'), 'utf8')
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')

    expect(overlay).not.toContain('useState')
    expect(overlay).toContain("setAttribute('transform'")
    expect(overlay).toContain('data-teaching-annotations')
    expect(overlay).not.toContain('annotation.points.map(project)')
    expect(overlay).toContain('useImperativeHandle')
    expect(overlay).toContain("setAttribute('visibility', 'visible')")
    expect(teacher).toContain('if (!stateRef.current?.controller.participantId) return')
    expect(teacher).toContain("teachingTool === 'draw' ? <StudentDrawingOverlay")
    expect(teacher).toContain("setMouseNavEnabled(teachingTool !== 'draw')")
    expect(teacher).toContain("if (!viewer || classroom?.phase !== 'live') return")
  })

  it('keeps guide traffic opt-in and accepts intentionally coalesced movement', () => {
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')
    const student = readFileSync(resolve('src/pages/ClassroomStudentPage.tsx'), 'utf8')

    expect(teacher).toContain('const [guideMode, setGuideMode] = useState(false)')
    expect(teacher).toContain('if (adminAuthFailed.current || !guideModeRef.current')
    expect(teacher).toContain('sequence(event, true)')
    expect(student).toContain('sequence(event, true)')
    expect(teacher).toContain('!coalescible && next !== streamSequence.current + 1')
    expect(student).toContain('!coalescible && next !== streamSequence.current + 1')
  })

  it('keeps the teacher workspace bounded and uses one lightweight arrow tool', () => {
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')
    const styles = readFileSync(resolve('src/classroom/classroom.css'), 'utf8')

    expect(teacher).not.toContain("name: 'laser'")
    expect(teacher).toContain("['green', 'red'] as const")
    expect(teacher).not.toContain('/300')
    expect(teacher).not.toContain('/200')
    expect(styles).toContain('.classroom-participant-list')
    expect(styles).toContain('overflow-y: auto')
    expect(styles).toContain('max-height: min(30vh, 260px)')
  })

  it('fails closed on expired teacher auth without continuing live traffic', () => {
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')
    const styles = readFileSync(resolve('src/classroom/classroom.css'), 'utf8')

    expect(teacher).toContain('const adminAuthFailed = useRef(false)')
    expect(teacher).toContain('adminAuthFailed.current = true')
    expect(teacher).toContain("navigate('/admin', { replace: true })")
    expect(teacher).toContain('if (adminAuthFailed.current || !guideModeRef.current')
    expect(teacher).toContain('classroom-local-pointer')
    expect(teacher).toContain('viewer.container.append(localPointer)')
    expect(teacher).not.toContain('viewer.updateOverlay(localPointer')
    expect(teacher).toContain('window.requestAnimationFrame')
    expect(teacher).toContain('pointerBoundsObserver.observe(viewer.canvas)')
    expect(teacher).toContain("if (teachingToolRef.current !== 'pointer')")
    expect(teacher).toContain("if (teachingTool === 'pointer') teachingOverlayRef.current?.setPointer(null)")
    expect(teacher).not.toContain('sender.push(readPresenterViewport')
    expect(styles).not.toContain('.classroom-local-pointer {\n  position: absolute;\n  top: 0;\n  left: 0;\n  z-index: 7;\n  width: 40px;\n  height: 48px;\n  pointer-events: none;\n  opacity: 0;\n  filter:')
    expect(teacher).toContain('pending questions`')
  })

  it('projects presenter movement directly without a React render per event', () => {
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')
    const student = readFileSync(resolve('src/pages/ClassroomStudentPage.tsx'), 'utf8')
    const teacherHandler = teacher.match(/events\.addEventListener\('presenter',[\s\S]*?events\.addEventListener\('pointer'/)?.[0] ?? ''
    const studentHandler = student.match(/source\.addEventListener\('presenter',[\s\S]*?source\.addEventListener\('control'/)?.[0] ?? ''

    expect(teacherHandler).toContain('presenterRef.current = nextPresenter')
    expect(studentHandler).toContain('presenterRef.current = nextPresenter')
    expect(teacherHandler).toContain('applyPresenterViewport(target, slide, nextPresenter.viewport)')
    expect(studentHandler).toContain('applyPresenterViewport(target, slide, nextPresenter.viewport)')
    expect(teacherHandler).not.toContain('setState(')
    expect(studentHandler).not.toContain('setState(')
    expect(teacher).not.toContain('setState((current) => current ? {\n        ...current,\n        teacherPointer:')
    expect(student).not.toContain('setState((current) => current ? {\n          ...current,\n          teacherPointer:')
  })
})
