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
})
