import { ArrowRight, Plus, Stack } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { createComparisonSet, getSlideStacks } from '../../api'
import type { LibrarySlide, LibrarySlideDetails, SlideStackSummary } from '../../types'

interface SlideStackSectionProps {
  slide: LibrarySlide | LibrarySlideDetails
  enabled: boolean
}

export function SlideStackSection({ slide, enabled }: SlideStackSectionProps) {
  const [stacks, setStacks] = useState<SlideStackSummary[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function refresh() {
    setStacks(await getSlideStacks(slide.id))
  }

  useEffect(() => {
    if (!enabled) return
    let active = true
    void getSlideStacks(slide.id).then((values) => active && setStacks(values)).catch(() => {
      if (active) setMessage('Slide stacks could not be loaded.')
    })
    return () => { active = false }
  }, [enabled, slide.id])

  if (!enabled) return null

  async function createStack() {
    setBusy(true); setMessage('')
    try {
      await createComparisonSet(`${slide.caseId || slide.displayName} slide stack`, [slide.id], slide.id)
      await refresh()
      setMessage('Stack created. Open the Slide stacks shelf to add stains.')
    } catch { setMessage('The stack could not be created.') } finally { setBusy(false) }
  }

  return <section className="slide-stack-section stack-details-summary" aria-label="Slide stacks">
    <div className="slide-stack-heading"><div><h4>Slide stacks</h4><p>Serial sections and stains linked to this slide.</p></div><span className="stack-details-icon"><Stack weight="fill" /></span></div>
    {stacks.length ? <div className="stack-details-list">{stacks.map((stack) => <article key={stack.id}>
      <div><strong>{stack.name}</strong><span>{stack.memberCount} slide{stack.memberCount === 1 ? '' : 's'} · {stack.role === 'reference' ? 'This slide is the reference' : 'Linked slide'}</span><small>{stack.stains.join(' · ') || 'Stains not specified'} · {stack.status}</small></div>
      <a href={`/admin/comparisons/${stack.id}`}>Open <ArrowRight /></a>
    </article>)}</div> : <button type="button" className="primary" disabled={busy || !['ready_private', 'published'].includes(slide.state)} onClick={() => void createStack()}><Plus /> Start a stack with this slide</button>}
    {stacks.length ? <a className="stack-details-manage" href="/admin#slide-stacks">Manage in Slide stacks <ArrowRight /></a> : null}
    {message ? <p className="slide-stack-message" role="status">{message}</p> : null}
  </section>
}