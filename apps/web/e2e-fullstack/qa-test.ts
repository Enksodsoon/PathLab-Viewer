import { test as base, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { fault } from './fixture-faults'
export { expect }
export type { Page } from '@playwright/test'

// Reachability evidence records controls actually encountered by each journey.
// A click alone is not a pass: the scenario's assertions remain the oracle.
export const test = base.extend<{ qaEvidence: void }>({
  qaEvidence: [async ({ browser, context }, use, testInfo) => {
    // Advance only completed synthetic assessments past the documented cooldown.
    // Open activities are never silently ended to make another test pass.
    fault('expire-assessment-cooldown')
    const errors: string[] = []
    const diagnostics: unknown[] = []
    const controls = new Map<string, unknown>()
    let contextNumber = 0
    const instrument = async (target: typeof context) => {
      const id = contextNumber++
      await target.exposeFunction('__qaControl', (record: { route: string; label: string; event: string }) => {
        if (controls.size < 10000) {
          const value = { context: id, ...record }
          controls.set(JSON.stringify(value), value)
        }
      })
      await target.addInitScript((contextId: number) => {
        const seen = new Set<string>()
        const record = (element: Element, event: string) => {
          const control = element.closest('button,input,select,textarea,a,summary,[role="button"],[role="menuitem"],[role="tab"]')
          if (!(control instanceof HTMLElement)) return
          const label = control.getAttribute('aria-label') || (control as HTMLInputElement).labels?.[0]?.textContent
            || (control.tagName === 'INPUT' ? control.getAttribute('type') : control.textContent) || ''
          const emit = (window as unknown as { __qaControl: (value: unknown) => Promise<void> }).__qaControl
          const value = { route: location.pathname, tag: control.tagName, label: label.trim().slice(0, 200), event, context: contextId,
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
      }, id)
      const observePage = (observed: Page) => {
        observed.on('pageerror', (error) => {
          errors.push(error.message)
          diagnostics.push({ at: Date.now(), context: id, event: 'pageerror', message: error.message, stack: error.stack, url: observed.url() })
        })
        observed.on('requestfailed', (request) => diagnostics.push({ at: Date.now(), context: id, event: 'requestfailed', url: request.url(), failure: request.failure() }))
        observed.on('framenavigated', (frame) => { if (frame === observed.mainFrame()) diagnostics.push({ at: Date.now(), context: id, event: 'navigation', url: frame.url() }) })
      }
      target.on('page', observePage)
      for (const observed of target.pages()) observePage(observed)
    }
    await instrument(context)

    // Existing journeys create isolated learner contexts through browser.newContext.
    // Instrument those contexts too so their controls and exceptions remain in the same receipt.
    const originalDescriptor = Object.getOwnPropertyDescriptor(browser, 'newContext')
    const originalNewContext = browser.newContext.bind(browser)
    const instrumentedNewContext = async (...args: Parameters<typeof browser.newContext>) => {
      const target = await originalNewContext(...args)
      await instrument(target)
      return target
    }
    Object.defineProperty(browser, 'newContext', { configurable: true, value: instrumentedNewContext })
    try {
      await use()
    } finally {
      if (originalDescriptor) Object.defineProperty(browser, 'newContext', originalDescriptor)
      else Reflect.deleteProperty(browser, 'newContext')
    }
    await testInfo.attach('navigation-diagnostics.json', { body: JSON.stringify(diagnostics), contentType: 'application/json' })
    await testInfo.attach('browser-version.json', { body: JSON.stringify({ version: browser.version(), project: testInfo.project.name }), contentType: 'application/json' })
    await testInfo.attach('reachable-controls.json', { body: JSON.stringify([...controls.values()]), contentType: 'application/json' })
    expect(errors, 'Unexpected application exceptions').toEqual([])
  }, { auto: true }],
})
