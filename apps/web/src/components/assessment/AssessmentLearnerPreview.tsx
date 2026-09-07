import { ArrowLeft, ArrowRight, BookmarkSimple, CheckCircle } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'

import { reachableItems } from '../../assessment/learnerRuntime'
import { questionTypesByType } from '../../assessment/questionTypes'
import { type AssessmentDocument, type AssessmentItem } from '../../assessment/types'
import { AssessmentLearnerQuestion } from './AssessmentLearnerQuestion'

type ResponseMap = Record<string, Record<string, unknown>>

const isInformation = (item: AssessmentItem) => item.type === 'section-information' || item.type === 'information'

function isAnswered(item: AssessmentItem, responses: ResponseMap) {
  const value = responses[item.id] ?? {}
  if (isInformation(item)) return true
  if (item.type === 'multiple-choice' || item.type === 'dropdown') return Boolean(value.optionId || value.other)
  if (item.type === 'checkboxes') return Array.isArray(value.optionIds) && value.optionIds.length > 0
  if (item.type === 'rating') return Number(value.value) >= 1
  if (item.type === 'diagnostic-field') return Boolean(value.selection || value.diagnosis)
  return Boolean(String(value.text ?? '').trim())
}

export function AssessmentLearnerPreview({ document, seed, assets = {} }: { document: AssessmentDocument; seed: string; assets?: Record<string, string> }) {
  const [responses, setResponses] = useState<ResponseMap>({})
  const [current, setCurrent] = useState(0)
  const [marked, setMarked] = useState<Set<string>>(new Set())
  const items = useMemo(() => reachableItems(document, responses), [document, responses])
  const itemIndexById = useMemo(() => new Map(items.map((item, index) => [item.id, index])), [items])
  const questionItems = useMemo(() => items.filter((item) => !isInformation(item)), [items])
  const item = items[current]

  useEffect(() => {
    setResponses({})
    setCurrent(0)
    setMarked(new Set())
  }, [document, seed])

  useEffect(() => {
    setCurrent((index) => Math.min(index, Math.max(items.length - 1, 0)))
  }, [items.length])

  const sections = useMemo(() => {
    if (document.schema !== 'pathlab.assessment/2') return [{ id: 'assessment', title: 'Questions', description: document.description, items }]
    const reachableIds = new Set(items.map((candidate) => candidate.id))
    return document.sections.map((section) => ({
      id: section.id,
      title: section.title,
      description: section.description,
      items: section.items.filter((candidate) => reachableIds.has(candidate.id)),
    })).filter((section) => section.items.length)
  }, [document, items])

  if (!item) return <div className="assessment-preview-empty"><h3>No questions to preview</h3><p>Add a question to see the learner experience.</p></div>

  const activeSection = sections.find((section) => section.items.some((candidate) => candidate.id === item.id)) ?? sections[0]
  const activeSectionIndex = Math.max(0, sections.findIndex((section) => section.id === activeSection?.id))
  const questionNumber = isInformation(item) ? 0 : questionItems.findIndex((candidate) => candidate.id === item.id) + 1
  const progressLabel = isInformation(item) ? `Section ${activeSectionIndex + 1} of ${sections.length}` : `Question ${questionNumber} of ${questionItems.length}`
  const progressValue = ((current + 1) / items.length) * 100
  const value = responses[item.id] ?? {}

  const goTo = (index: number) => setCurrent(Math.min(Math.max(index, 0), items.length - 1))
  const toggleMarked = () => setMarked((currentMarked) => {
    const next = new Set(currentMarked)
    if (next.has(item.id)) next.delete(item.id)
    else next.add(item.id)
    return next
  })

  return <div className="assessment-learner-preview-shell" data-preset={document.schema === 'pathlab.assessment/2' ? document.presentation.preset ?? 'standard' : 'standard'}>
    <aside className="assessment-preview-outline" aria-label="Preview question navigator">
      <div className="assessment-preview-section-context">
        <span>Section {activeSectionIndex + 1}</span>
        <strong>{activeSection?.title}</strong>
        {activeSection?.description ? <p>{activeSection.description}</p> : null}
      </div>
      <nav>
        {sections.map((section, sectionIndex) => <section key={section.id} aria-label={`Section ${sectionIndex + 1}: ${section.title}`}>
          <header><span>{sectionIndex + 1}</span><strong>{section.title}</strong></header>
          <div>{section.items.map((candidate) => {
            const candidateIndex = itemIndexById.get(candidate.id) ?? 0
            const candidateQuestionNumber = isInformation(candidate) ? 0 : questionItems.findIndex((question) => question.id === candidate.id) + 1
            return <button key={candidate.id} type="button" aria-current={candidate.id === item.id ? 'step' : undefined} onClick={() => goTo(candidateIndex)}>
              <span>{isInformation(candidate) ? 'i' : candidateQuestionNumber}</span>
              <span><strong>{isInformation(candidate) ? 'Section information' : `Question ${candidateQuestionNumber}`}</strong><small>{questionTypesByType[candidate.type].label}</small></span>
              {isAnswered(candidate, responses) && !isInformation(candidate) ? <CheckCircle aria-label="Answered" /> : null}
            </button>
          })}</div>
        </section>)}
      </nav>
    </aside>
    <section className="assessment-preview-workspace">
      <header className="assessment-preview-progress">
        <strong>{progressLabel}</strong>
        <span role="progressbar" aria-label="Preview progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressValue)}><i style={{ width: `${progressValue}%` }} /></span>
        <small>{questionTypesByType[item.type].label}</small>
      </header>
      <div className="assessment-preview-question-stage">
        <AssessmentLearnerQuestion item={item} value={value} assets={assets} dropdownPresentation="choices" onChange={(response) => setResponses((currentResponses) => ({ ...currentResponses, [item.id]: response }))} />
      </div>
      <footer className="assessment-preview-actions">
        <button type="button" disabled={current === 0} onClick={() => goTo(current - 1)}><ArrowLeft aria-hidden="true" />Back</button>
        {!isInformation(item) ? <button className="assessment-preview-mark" type="button" aria-pressed={marked.has(item.id)} onClick={toggleMarked}><BookmarkSimple aria-hidden="true" />{marked.has(item.id) ? 'Marked' : 'Mark for review'}</button> : <span />}
        <button className="assessment-primary" type="button" onClick={() => goTo(current === items.length - 1 ? 0 : current + 1)}>{current === items.length - 1 ? 'Restart preview' : 'Continue'}<ArrowRight aria-hidden="true" /></button>
      </footer>
    </section>
  </div>
}
