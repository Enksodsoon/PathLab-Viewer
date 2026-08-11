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
    expect(overlay).toContain("setAttribute('d'")
    expect(overlay).toContain('if (!visibleAnnotations.length && !visiblePointer) return null')
    expect(teacher).toContain('if (!stateRef.current?.controller.participantId) return')
    expect(teacher).toContain("teachingTool === 'draw' ? <StudentDrawingOverlay")
  })

  it('keeps guide traffic opt-in and accepts intentionally coalesced movement', () => {
    const teacher = readFileSync(resolve('src/pages/ClassroomTeacherPage.tsx'), 'utf8')
    const student = readFileSync(resolve('src/pages/ClassroomStudentPage.tsx'), 'utf8')

    expect(teacher).toContain('const [guideMode, setGuideMode] = useState(false)')
    expect(teacher).toContain('if (!guideModeRef.current')
    expect(teacher).toContain('sequence(event, true)')
    expect(student).toContain('sequence(event, true)')
    expect(teacher).toContain('!coalescible && next !== streamSequence.current + 1')
    expect(student).toContain('!coalescible && next !== streamSequence.current + 1')
  })
})
