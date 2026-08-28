import { useEffect, useState } from 'react'

import { orderSectionRuns } from '../../assessment/learnerRuntime'
import { assessmentItems, type AssessmentDocument, type AssessmentItem } from '../../assessment/types'
import { AssessmentLearnerQuestion } from './AssessmentLearnerQuestion'

export function AssessmentLearnerPreview({ document, seed }: { document: AssessmentDocument; seed: string }) {
  const [items, setItems] = useState<AssessmentItem[]>(() => assessmentItems(document))
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      if (document.schema !== 'pathlab.assessment/2') {
        const ordered = await orderSectionRuns(document.items, seed, Boolean(document.settings.shuffleQuestions))
        if (!cancelled) setItems(ordered)
        return
      }
      const ordered = (await Promise.all(document.sections.map((section) => orderSectionRuns(
        section.items, seed, Boolean(document.settings.shuffleQuestions),
      )))).flat()
      if (!cancelled) setItems(ordered)
    }
    void load()
    return () => { cancelled = true }
  }, [document, seed])
  return <div className="assessment-learner-preview-renderer">
    {items.map((item, index) => <article key={item.id} className="assessment-preview-question"><div className="assessment-preview-meta"><span>{item.type === 'section-information' || item.type === 'information' ? 'Information' : `Question ${index + 1}`}</span><span>{item.type}</span></div><AssessmentLearnerQuestion item={item} value={{}} readOnly /></article>)}
  </div>
}
