import { test as base, expect } from '@playwright/test'
import { fault } from './fixture-faults'
export { expect }
export type { Page } from '@playwright/test'

// Reachability evidence records controls actually encountered by each journey.
// A click alone is not a pass: the scenario's assertions remain the oracle.
export const test = base.extend<{ qaEvidence: void }>({
  qaEvidence: [async ({ page, browser }, use, testInfo) => {
    // Advance only completed synthetic assessments past the documented cooldown.
    // Open activities are never silently ended to make another test pass.
    fault('expire-assessment-cooldown')
    const errors: string[] = []
    const diagnostics: unknown[] = []
    const controls = new Map<string, unknown>()
    page.on('pageerror', (error) => {
      errors.push(error.message)
      diagnostics.push({ at: Date.now(), event: 'pageerror', message: error.message, stack: error.stack })
    })
    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) {
        diagnostics.push({ at: Date.now(), event: 'console', level: message.type(), text: message.text() })
      }
    })
    page.on('requestfailed', (request) => diagnostics.push({ at: Date.now(), event: 'requestfailed', url: request.url(), failure: request.failure() }))
    page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) diagnostics.push({ at: Date.now(), event: 'navigation', url: frame.url() }) })
    await page.exposeFunction('__qaControl', (record: { route: string; label: string; event: string }) => {
      if (controls.size < 5000) controls.set(JSON.stringify(record), record)
    })
    await page.addInitScript(() => {
      const seen = new Set<string>()
      const record = (element: Element, event: string) => {
        const control = element.closest('button,input,select,textarea,a,summary,[role="button"],[role="menuitem"],[role="tab"]')
        if (!(control instanceof HTMLElement)) return
        const label = control.getAttribute('aria-label') || (control as HTMLInputElement).labels?.[0]?.textContent
          || (control.tagName === 'INPUT' ? control.getAttribute('type') : control.textContent) || ''
        const emit = (window as unknown as { __qaControl: (value: unknown) => Promise<void> }).__qaControl
        const value = { route: location.pathname, tag: control.tagName, label: label.trim().slice(0, 200), event,
          disabled: control.matches(':disabled'), expanded: control.getAttribute('aria-expanded') }
        const key = JSON.stringify(value)
        if (!seen.has(key) && seen.size < 5000) { seen.add(key); void emit(value) }
      }
      for (const event of ['click', 'change', 'focusin']) document.addEventListener(event, (value) => {
        if (value.target instanceof Element) record(value.target, event)
      }, true)
      document.addEventListener('DOMContentLoaded', () => {
        let scheduled = false
        const inventory = () => {
          scheduled = false
          for (const control of document.querySelectorAll('button,input,select,textarea,a,summary,[role="button"],[role="menuitem"],[role="tab"]')) {
            if (control instanceof HTMLElement && control.getClientRects().length) record(control, 'encountered')
          }
        }
        new MutationObserver(() => { if (!scheduled) { scheduled = true; setTimeout(inventory, 100) } }).observe(document.body, { subtree: true, childList: true })
        inventory()
      })
    })
    await use()
    await testInfo.attach('navigation-diagnostics.json', { body: JSON.stringify(diagnostics), contentType: 'application/json' })
    await testInfo.attach('browser-version.json', { body: JSON.stringify({ version: browser.version(), project: testInfo.project.name }), contentType: 'application/json' })
    await testInfo.attach('reachable-controls.json', { body: JSON.stringify([...controls.values()]), contentType: 'application/json' })
    expect(errors, 'Unexpected application exceptions').toEqual([])
  }, { auto: true }],
})
