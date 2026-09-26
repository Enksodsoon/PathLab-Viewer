import { describe, expect, it, vi } from 'vitest'

import { notebookFile, notebookHtml } from '../classroom/notebook'

describe('classroom notebook export', () => {
  it('converts captured images one at a time in note order', async () => {
    let active = 0
    let peak = 0
    class Reader {
      result = 'data:image/png;base64,cGl4ZWw='
      onload?: () => void
      readAsDataURL() {
        peak = Math.max(peak, ++active)
        setTimeout(() => { active -= 1; this.onload?.() }, 0)
      }
    }
    vi.stubGlobal('FileReader', Reader)
    try {
      const html = await notebookHtml('Notebook', [0, 1, 2].map((index) => ({
        id: String(index), sessionId: 'session', slideId: 'slide', slideName: `Slide ${index}`,
        note: '', createdAt: '', image: new Blob(['image']),
      })))
      expect(peak).toBe(1)
      expect(html.indexOf('Slide 0')).toBeLessThan(html.indexOf('Slide 1'))
    } finally { vi.unstubAllGlobals() }
  })
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
