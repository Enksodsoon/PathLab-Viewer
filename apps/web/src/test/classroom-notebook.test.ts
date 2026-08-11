import { describe, expect, it } from 'vitest'

import { notebookFile, notebookHtml } from '../classroom/notebook'

describe('classroom notebook export', () => {
  it('escapes note and slide text and has no external dependency', async () => {
    const html = await notebookHtml('Class <script>', [{
      id: 'one',
      sessionId: 'session',
      slideId: 'slide',
      slideName: '<img src=x onerror=alert(1)>',
      note: '<script>alert(1)</script>',
      createdAt: '2026-08-11T00:00:00Z',
    }])

    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img src=x')
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain("default-src 'none'")
    expect(html).not.toMatch(/<script|https?:\/\//)
  })

  it('exports a responsive offline field notebook with coordinates and drawing status', async () => {
    const entry = {
      id: 'one',
      sessionId: 'session',
      slideId: 'slide',
      slideName: 'Colon overview',
      note: 'Crypt architecture',
      createdAt: '2026-08-11T00:00:00Z',
      viewport: { x: 0.25, y: 0.75, zoom: 4 },
      hasDrawing: true,
    }
    const html = await notebookHtml('PathLab notebook', [entry])
    const file = await notebookFile('PathLab notebook', [entry])

    expect(html).toContain('Field 25%, 75% · zoom 4.00')
    expect(html).toContain('Private drawing included')
    expect(html).toContain('@media(max-width:560px)')
    expect(html).toContain('@media print')
    expect(file.name).toBe('pathlab-classroom-notebook.html')
    expect(file.type).toBe('text/html;charset=utf-8')
  })
})
