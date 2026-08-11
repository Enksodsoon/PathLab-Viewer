import { describe, expect, it } from 'vitest'

import { notebookHtml } from '../classroom/notebook'

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
})
