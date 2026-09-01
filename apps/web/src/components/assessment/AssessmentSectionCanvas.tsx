import { ArrowDown, ArrowUp, ArrowsInLineVertical, ArrowsOutLineVertical, CaretDown, CaretLeft, CaretRight, ChatCircleDots, CheckCircle, Copy, DotsSixVertical, Eye, Image, MagnifyingGlass, Plus, Trash, X } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'

import { authorableQuestionTypeRegistry, questionTypesByType } from '../../assessment/questionTypes'
import { assessmentQuestionMedia, type AssessmentDocumentV2, type AssessmentItem, type AssessmentItemType, type AssessmentSection, type EligibleAssessmentSlide } from '../../assessment/types'
import { QuestionEditor } from './AssessmentQuestionCanvas'
import { AutoGrowTextarea } from './AutoGrowTextarea'

interface SectionCanvasProps {
  document: AssessmentDocumentV2
  draftId?: string
  mediaScopeLabel?: string
  onDocumentChange: (update: (document: AssessmentDocumentV2) => AssessmentDocumentV2) => void
  onImport: () => void
  onPreview: () => void
  onCreateTemplate?: (name: string) => Promise<AssessmentTemplateSummary>
  onListTemplates?: () => Promise<AssessmentTemplateSummary[]>
}

export interface AssessmentTemplateSummary {
  id: string
  name: string
  document: AssessmentDocumentV2
}

type DraggedQuestion = { sectionId: string; itemId: string }
const QUESTION_DRAG_TYPE = 'application/x-pathlab-assessment-question'

function readDraggedQuestion(dataTransfer: DataTransfer, fallback: DraggedQuestion | null) {
  const encoded = dataTransfer.getData(QUESTION_DRAG_TYPE)
  if (!encoded) return fallback
  try {
    const parsed = JSON.parse(encoded) as Partial<DraggedQuestion>
    return typeof parsed.sectionId === 'string' && typeof parsed.itemId === 'string'
      ? { sectionId: parsed.sectionId, itemId: parsed.itemId }
      : fallback
  } catch {
    return fallback
  }
}

function newId(prefix = 'assessment') {
  return globalThis.crypto?.randomUUID?.() ?? `${prefix}-${Date.now()}-${Math.random()}`
}

function cloneSection(section: AssessmentSection): AssessmentSection {
  const itemIds = new Map(section.items.map((item) => [item.id, newId('item')]))
  return {
    ...structuredClone(section),
    id: newId('section'),
    title: `${section.title} copy`,
    items: section.items.map((item) => {
      const options = (item.options ?? []).map((option) => ({ ...option, id: newId('option') }))
      const optionIds = new Map((item.options ?? []).map((option, index) => [option.id, options[index].id]))
      const keyIds = (item.answerKey?.optionIds as string[] | undefined)?.map((id) => optionIds.get(id) ?? id)
      return {
        ...structuredClone(item),
        id: itemIds.get(item.id)!,
        options,
        answerKey: { ...item.answerKey, ...(keyIds ? { optionIds: keyIds } : {}) },
        routing: undefined,
      }
    }),
  }
}

function answerMediaCount(item: AssessmentItem) {
  return (item.options ?? []).reduce((total, option) => total + (option.media ? 1 : 0) + (option.mediaItems?.length ?? 0), 0)
}

function hasFeedback(item: AssessmentItem) {
  return Boolean(item.feedback?.correct?.trim() || item.feedback?.incorrect?.trim())
}

export function AssessmentSectionCanvas({ document, draftId = '', mediaScopeLabel = 'this lesson', onDocumentChange, onImport, onPreview, onCreateTemplate, onListTemplates }: SectionCanvasProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [collapsedQuestions, setCollapsedQuestions] = useState<Set<string>>(new Set())
  const [navigatorCollapsed, setNavigatorCollapsed] = useState(false)
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState(document.sections[0]?.items[0]?.id ?? '')
  const [deleted, setDeleted] = useState<{ section: AssessmentSection; index: number } | null>(null)
  const [slides, setSlides] = useState<EligibleAssessmentSlide[]>([])
  const [draggedSection, setDraggedSection] = useState('')
  const [draggedItem, setDraggedItem] = useState<DraggedQuestion | null>(null)
  const [dropTarget, setDropTarget] = useState('')
  const [message, setMessage] = useState('')
  const [starterOpen, setStarterOpen] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateStatus, setTemplateStatus] = useState('')
  const [templateBusy, setTemplateBusy] = useState(false)
  const [templates, setTemplates] = useState<AssessmentTemplateSummary[]>([])
  const [templatesLoading, setTemplatesLoading] = useState(false)
  const [mediaRequest, setMediaRequest] = useState<{ itemId: string; nonce: number }>({ itemId: '', nonce: 0 })
  const query = search.trim().toLocaleLowerCase()
  const numbering = useMemo(() => {
    const result = new Map<string, number>()
    let number = 0
    for (const section of document.sections) {
      for (const item of section.items) {
        if (item.type !== 'section-information') number += 1
        result.set(item.id, number)
      }
    }
    return result
  }, [document.sections])
  const itemCount = [...numbering.values()].at(-1) ?? 0
  const issueCount = document.sections.reduce((total, section) => total + section.items.reduce(
    (sectionTotal, item) => sectionTotal + questionTypesByType[item.type].validate(item).length,
    0,
  ), 0)

  function updateSections(update: (sections: AssessmentSection[]) => AssessmentSection[]) {
    onDocumentChange((current) => ({ ...current, sections: update(current.sections) }))
  }

  function updateSection(sectionId: string, update: (section: AssessmentSection) => AssessmentSection) {
    updateSections((sections) => sections.map((section) => section.id === sectionId ? update(section) : section))
  }

  function updateItem(itemId: string, update: (item: AssessmentItem) => AssessmentItem) {
    updateSections((sections) => sections.map((section) => ({
      ...section,
      items: section.items.map((item) => item.id === itemId ? update(item) : item),
    })))
  }

  function moveSection(index: number, direction: -1 | 1) {
    const destination = index + direction
    if (destination < 0 || destination >= document.sections.length) return
    updateSections((sections) => {
      const next = [...sections]
      const [section] = next.splice(index, 1)
      next.splice(destination, 0, section)
      return next
    })
    setMessage(`Moved section ${index + 1} to position ${destination + 1}.`)
  }

  function moveItem(sectionId: string, itemIndex: number, direction: -1 | 1) {
    updateSection(sectionId, (section) => {
      const destination = itemIndex + direction
      if (destination < 0 || destination >= section.items.length) return section
      const items = [...section.items]
      const [item] = items.splice(itemIndex, 1)
      items.splice(destination, 0, item)
      return { ...section, items }
    })
  }

  function startItemDrag(dataTransfer: DataTransfer, source: DraggedQuestion) {
    setDraggedSection('')
    setDraggedItem(source)
    dataTransfer.effectAllowed = 'move'
    dataTransfer.setData(QUESTION_DRAG_TYPE, JSON.stringify(source))
    dataTransfer.setData('text/item', source.itemId)
  }

  function dropItem(sectionId: string, destinationIndex: number, source = draggedItem) {
    if (!source) return
    onDocumentChange((current) => {
      const sourceSection = current.sections.find((section) => section.id === source.sectionId)
      const sourceIndex = sourceSection?.items.findIndex((item) => item.id === source.itemId) ?? -1
      const moving = sourceIndex >= 0 ? sourceSection?.items[sourceIndex] : undefined
      if (!moving || !current.sections.some((section) => section.id === sectionId)) return current
      const stripped = current.sections.map((section) => ({
        ...section,
        items: section.items.filter((item) => item.id !== source.itemId),
      }))
      return {
        ...current,
        sections: stripped.map((section) => {
          if (section.id !== sectionId) return section
          const nextItems = [...section.items]
          nextItems.splice(Math.max(0, Math.min(destinationIndex, nextItems.length)), 0, moving)
          return { ...section, items: nextItems }
        }),
      }
    })
    setMessage('Question order updated.')
    setDraggedItem(null)
    setDropTarget('')
  }

  function dropSection(destinationIndex: number, sourceId = draggedSection) {
    const sourceIndex = document.sections.findIndex((section) => section.id === sourceId)
    if (sourceIndex < 0 || sourceIndex === destinationIndex) {
      setDraggedSection('')
      setDropTarget('')
      return
    }
    updateSections((sections) => {
      const next = [...sections]
      const [moving] = next.splice(sourceIndex, 1)
      next.splice(destinationIndex, 0, moving)
      return next
    })
    setMessage(`Moved section ${sourceIndex + 1} to position ${destinationIndex + 1}.`)
    setDraggedSection('')
    setDropTarget('')
  }

  function addSection() {
    const id = newId('section')
    updateSections((sections) => [...sections, { id, title: `Section ${sections.length + 1}`, description: '', items: [] }])
    setCollapsed((current) => { const next = new Set(current); next.delete(id); return next })
  }

  function addItem(sectionId: string, type: AssessmentItemType) {
    const item = questionTypesByType[type].create(() => newId('item'))
    updateSection(sectionId, (section) => ({ ...section, items: [...section.items, item] }))
    setSelectedId(item.id)
  }

  function deleteSection(section: AssessmentSection, index: number) {
    setDeleted({ section: structuredClone(section), index })
    updateSections((sections) => sections.filter((candidate) => candidate.id !== section.id))
  }

  function undoDelete() {
    if (!deleted) return
    updateSections((sections) => {
      const next = [...sections]
      next.splice(Math.min(deleted.index, next.length), 0, deleted.section)
      return next
    })
    setDeleted(null)
  }

  async function createTemplate() {
    const name = templateName.trim()
    if (!name || !onCreateTemplate) return
    setTemplateBusy(true)
    setTemplateStatus('')
    try {
      const created = await onCreateTemplate(name)
      setTemplateName('')
      setTemplates((current) => [created, ...current.filter((template) => template.id !== created.id)])
      setTemplateStatus(`${created.name} is ready to use.`)
    } catch {
      setTemplateStatus('The template could not be created. Try again.')
    } finally {
      setTemplateBusy(false)
    }
  }

  async function openTemplateHub() {
    const nextOpen = !starterOpen
    setStarterOpen(nextOpen)
    if (!nextOpen || !onListTemplates) return
    setTemplatesLoading(true)
    try {
      setTemplates(await onListTemplates())
    } catch {
      setTemplateStatus('Your templates could not be loaded. Try again.')
    } finally {
      setTemplatesLoading(false)
    }
  }

  return <main className="assessment-question-workspace assessment-section-workspace">
    <header className="assessment-authoring-toolbar">
      <div><h2>Questions</h2><p>{document.sections.length} sections · {itemCount} questions · {issueCount ? `${issueCount} issues` : 'Ready to review'}</p></div>
      <div className="assessment-authoring-actions">
        <button className="assessment-icon-action" type="button" aria-label="Assignment preview" title="Assignment preview" onClick={onPreview}><Eye aria-hidden="true" /></button>
        <button className="assessment-icon-action" type="button" aria-label="Expand all sections" title="Expand all sections" onClick={() => setCollapsed(new Set())}><ArrowsOutLineVertical aria-hidden="true" /></button>
        <button className="assessment-icon-action" type="button" aria-label="Collapse all sections" title="Collapse all sections" onClick={() => setCollapsed(new Set(document.sections.map((section) => section.id)))}><ArrowsInLineVertical aria-hidden="true" /></button>
        <button type="button" aria-expanded={starterOpen} onClick={() => void openTemplateHub()}>Templates & import</button>
        <button className="assessment-primary" type="button" onClick={addSection}><Plus aria-hidden="true" /> Add section</button>
      </div>
    </header>
    {starterOpen ? <section className="assessment-starter-panel" aria-label="Templates and assessment import">
      <header className="assessment-starter-header"><div><h3>Templates & import</h3><p>Reuse this assessment or bring in questions from another one.</p></div><button className="assessment-icon-action" type="button" aria-label="Close templates and import" onClick={() => setStarterOpen(false)}><X aria-hidden="true" /></button></header>
      <div className="assessment-reuse-actions">
        <article className="assessment-reuse-action assessment-reuse-action--create"><span className="assessment-reuse-icon"><Copy aria-hidden="true" /></span><div className="assessment-reuse-copy"><h4>Create template</h4><p>Save the current sections, questions, scoring, and media for later.</p></div><div className="assessment-template-create"><label><span className="visually-hidden">Template name</span><input aria-label="Template name" placeholder="Template name" value={templateName} onChange={(event) => { setTemplateName(event.target.value); setTemplateStatus('') }} /></label><button className="assessment-primary" type="button" disabled={!templateName.trim() || templateBusy || !onCreateTemplate} onClick={() => void createTemplate()}>{templateBusy ? 'Saving…' : 'Save template'}</button></div></article>
        <article className="assessment-reuse-action"><span className="assessment-reuse-icon"><ArrowDown aria-hidden="true" /></span><div className="assessment-reuse-copy"><h4>Import assessment</h4><p>Review another assessment and choose only the questions you need.</p></div><button className="assessment-secondary-action" type="button" onClick={() => { setStarterOpen(false); onImport() }}>Choose assessment</button></article>
      </div>
      {templateStatus ? <p className="assessment-template-status" role="status">{templateStatus}</p> : null}
      <section className="assessment-template-library" aria-label="Your templates"><header><div><h3>Your templates</h3><p>Templates you create will appear here.</p></div><span>{templates.length}</span></header>{templatesLoading ? <div className="assessment-template-empty" role="status">Loading templates…</div> : templates.length ? <div className="assessment-template-grid">{templates.map((template) => { const questionCount = template.document.sections.reduce((total, section) => total + section.items.filter((item) => item.type !== 'section-information').length, 0); return <button key={template.id} type="button" onClick={() => { onDocumentChange((current) => ({ ...structuredClone(template.document), title: current.title })); setStarterOpen(false) }}><Copy aria-hidden="true" /><span><strong>{template.name}</strong><small>{template.document.sections.length} sections · {questionCount} questions</small></span><b>Use template</b></button> })}</div> : <div className="assessment-template-empty"><Copy aria-hidden="true" /><div><strong>No templates yet</strong><span>Create one from this assessment and it will be ready here.</span></div></div>}</section>
    </section> : null}
    <div className={`assessment-question-layout${navigatorCollapsed ? ' is-navigator-collapsed' : ''}`}>
      <aside className={`assessment-question-navigator assessment-section-navigator${navigatorCollapsed ? ' is-collapsed' : ''}`} aria-label="Question navigator">
        {navigatorCollapsed ? <button className="assessment-navigator-expand" type="button" aria-label="Expand question navigator" title={`Expand question navigator (${itemCount} questions)`} onClick={() => setNavigatorCollapsed(false)}><CaretRight aria-hidden="true" /><span>Question navigator</span></button> : <>
        <header><div><h3>Question navigator</h3><p>{document.sections.length} sections · {itemCount} questions</p></div><button className="assessment-navigator-collapse" type="button" aria-label="Collapse question navigator" title="Collapse question navigator" onClick={() => setNavigatorCollapsed(true)}><CaretLeft aria-hidden="true" /></button></header>
        <label className="assessment-navigator-search"><MagnifyingGlass aria-hidden="true" /><input placeholder="Search sections and questions" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <ol
          className="assessment-section-outline"
          tabIndex={0}
          onWheel={(event) => {
            const outline = event.currentTarget
            const maximum = outline.scrollHeight - outline.clientHeight
            if (maximum <= 0 || event.deltaY === 0) return
            const next = Math.max(0, Math.min(maximum, outline.scrollTop + event.deltaY))
            if (next === outline.scrollTop) return
            event.preventDefault()
            outline.scrollTop = next
          }}
          onKeyDown={(event) => {
            if (event.key !== 'PageDown' && event.key !== 'PageUp') return
            event.preventDefault()
            event.currentTarget.scrollBy({
              top: (event.key === 'PageDown' ? 1 : -1) * event.currentTarget.clientHeight * 0.8,
              behavior: 'smooth',
            })
          }}
        >
          {document.sections.map((section, sectionIndex) => {
            const visible = !query || section.title.toLocaleLowerCase().includes(query) || section.items.some((item) => item.prompt.toLocaleLowerCase().includes(query))
            if (!visible) return null
            return <li key={section.id} draggable={!query} className={`${draggedSection === section.id ? 'is-dragging' : ''}${dropTarget === `section:${section.id}` ? ' is-drop-target' : ''}`} onDragStart={(event) => { if ((event.target as HTMLElement).closest('ol')) return; setDraggedSection(section.id); setDraggedItem(null); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/section', section.id) }} onDragEnd={() => { setDraggedSection(''); setDropTarget('') }} onDragEnter={() => setDropTarget(`section:${section.id}`)} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }} onDrop={(event) => { event.preventDefault(); event.stopPropagation(); const question = readDraggedQuestion(event.dataTransfer, draggedItem); if (question) dropItem(section.id, section.items.length, question); else dropSection(sectionIndex, event.dataTransfer.getData('text/section') || draggedSection) }} onMouseEnter={() => { if (draggedSection || draggedItem) setDropTarget(`section:${section.id}`) }} onMouseUp={() => { if (draggedItem) dropItem(section.id, section.items.length); else if (draggedSection) dropSection(sectionIndex) }}>
              <button type="button" className="assessment-section-outline-title" onClick={() => globalThis.document.getElementById(section.id)?.scrollIntoView({ block: 'start' })} onMouseDown={(event) => { if (event.button !== 0 || !(event.target as HTMLElement).closest('.assessment-outline-drag')) return; setDraggedSection(section.id); setDraggedItem(null) }}>
                <DotsSixVertical className="assessment-outline-drag" aria-hidden="true" /><span className="assessment-outline-number">{sectionIndex + 1}</span><span className="assessment-outline-copy"><strong>{section.title || 'Untitled section'}</strong><small>Section · {section.items.length} items</small></span>
              </button>
              <ol>{section.items.filter((item) => !query || item.prompt.toLocaleLowerCase().includes(query)).map((item, itemIndex) => { const mediaCount = assessmentQuestionMedia(item).length + answerMediaCount(item); return <li key={item.id} draggable={!query} className={`${draggedItem?.itemId === item.id ? 'is-dragging' : ''}${dropTarget === `item:${item.id}` ? ' is-drop-target' : ''}`} onDragStart={(event) => { event.stopPropagation(); startItemDrag(event.dataTransfer, { sectionId: section.id, itemId: item.id }) }} onDragEnd={() => { setDraggedItem(null); setDropTarget('') }} onDragEnter={(event) => { event.stopPropagation(); setDropTarget(`item:${item.id}`) }} onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move' }} onDrop={(event) => { event.preventDefault(); event.stopPropagation(); dropItem(section.id, itemIndex, readDraggedQuestion(event.dataTransfer, draggedItem)) }} onMouseEnter={(event) => { event.stopPropagation(); if (draggedItem) setDropTarget(`item:${item.id}`) }} onMouseUp={(event) => { event.stopPropagation(); if (draggedItem) dropItem(section.id, itemIndex) }}><button type="button" aria-current={selectedId === item.id ? 'true' : undefined} className={selectedId === item.id ? 'active' : ''} onClick={() => { setSelectedId(item.id); setCollapsed((current) => { const next = new Set(current); next.delete(section.id); return next }); globalThis.setTimeout(() => globalThis.document.querySelector(`[data-question-id="${item.id}"]`)?.scrollIntoView({ block: 'start' }), 0) }} onMouseDown={(event) => { if (event.button !== 0 || !(event.target as HTMLElement).closest('.assessment-outline-drag')) return; setDraggedSection(''); setDraggedItem({ sectionId: section.id, itemId: item.id }) }}><DotsSixVertical className="assessment-outline-drag" aria-hidden="true" /><span className="assessment-outline-number">{item.type === 'section-information' ? 'i' : numbering.get(item.id)}</span><span className="assessment-outline-copy"><strong>{item.prompt || 'Untitled question'}</strong><small>{questionTypesByType[item.type].label}</small></span><span className="assessment-outline-status" aria-label="Question status">{item.required ? <CheckCircle aria-label="Required" /> : null}{Number(item.points ?? 0) > 0 ? <b aria-label={`${item.points} points`}>{item.points}</b> : null}{hasFeedback(item) ? <ChatCircleDots aria-label="Feedback added" /> : null}{mediaCount ? <span aria-label={`${mediaCount} media items`}><Image aria-hidden="true" /><i>{mediaCount}</i></span> : null}</span></button></li> })}</ol>
            </li>
          })}
        </ol>
        </>}
      </aside>
      <section className="assessment-question-canvas assessment-section-canvas" aria-label="Sections">
        {document.sections.map((section, sectionIndex) => {
          const sectionCollapsed = collapsed.has(section.id)
          return <article
            id={section.id}
            key={section.id}
            className={`assessment-section-card${draggedSection === section.id ? ' is-dragging' : ''}`}
            draggable
            onDragStart={(event) => { if ((event.target as HTMLElement).closest('[data-question-id]')) return; setDraggedSection(section.id); event.dataTransfer.setData('text/section', section.id) }}
            onDragEnd={() => setDraggedSection('')}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              const question = readDraggedQuestion(event.dataTransfer, draggedItem)
              if (question) { dropItem(section.id, section.items.length, question); return }
              const sourceId = event.dataTransfer.getData('text/section') || draggedSection
              dropSection(sectionIndex, sourceId)
            }}
          >
            <header className="assessment-section-header">
              <button className="assessment-question-drag" type="button" aria-label={`Reorder section ${sectionIndex + 1}`} title="Drag or use Alt + arrow keys" onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveSection(sectionIndex, -1); if (event.key === 'ArrowDown') moveSection(sectionIndex, 1) }}><DotsSixVertical aria-hidden="true" /></button>
              <span className="assessment-section-number"><span className="visually-hidden">Section </span>{sectionIndex + 1}</span>
              <label className="assessment-section-title-fields"><span className="assessment-section-kicker">Section {sectionIndex + 1}</span><input aria-label={`Section ${sectionIndex + 1} title`} value={section.title} maxLength={200} onChange={(event) => updateSection(section.id, (current) => ({ ...current, title: event.target.value }))} /></label>
              <div className="assessment-section-actions">
                <span className="assessment-section-count">{section.items.length} item{section.items.length === 1 ? '' : 's'}</span>
                <button type="button" aria-label={`${sectionCollapsed ? 'Expand' : 'Collapse'} section ${sectionIndex + 1}`} onClick={() => setCollapsed((current) => { const next = new Set(current); if (next.has(section.id)) next.delete(section.id); else next.add(section.id); return next })}><CaretDown aria-hidden="true" /></button>
                <button type="button" aria-label={`Duplicate section ${sectionIndex + 1}`} onClick={() => updateSections((sections) => { const next = [...sections]; next.splice(sectionIndex + 1, 0, cloneSection(section)); return next })}><Copy aria-hidden="true" /></button>
                <button type="button" aria-label={`Delete section ${sectionIndex + 1}`} disabled={document.sections.length === 1} onClick={() => deleteSection(section, sectionIndex)}><Trash aria-hidden="true" /></button>
              </div>
            </header>
            {!sectionCollapsed ? <>
              <label className="assessment-section-description">Description<AutoGrowTextarea maxLength={2000} value={section.description ?? ''} onChange={(event) => updateSection(section.id, (current) => ({ ...current, description: event.target.value }))} /></label>
              <div className="assessment-section-items">
                {section.items.map((item, itemIndex) => { const questionCollapsed = collapsedQuestions.has(item.id); const questionMediaCount = assessmentQuestionMedia(item).length; return <article
                  key={item.id}
                  data-question-id={item.id}
                  className={`assessment-question-card assessment-question-card--${questionCollapsed ? 'collapsed' : 'expanded'}${selectedId === item.id ? ' assessment-question-card--focused' : ''}`}
                  draggable
                  onDragStart={(event) => { event.stopPropagation(); startItemDrag(event.dataTransfer, { sectionId: section.id, itemId: item.id }) }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => { event.preventDefault(); event.stopPropagation(); dropItem(section.id, itemIndex, readDraggedQuestion(event.dataTransfer, draggedItem)) }}
                  onFocus={() => setSelectedId(item.id)}
                >
                  <header className="assessment-question-card-header">
                    <button className="assessment-question-drag" type="button" aria-label={`Reorder question ${numbering.get(item.id)}`} onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveItem(section.id, itemIndex, -1); if (event.key === 'ArrowDown') moveItem(section.id, itemIndex, 1) }}><DotsSixVertical /></button>
                    <span className="assessment-question-number">{numbering.get(item.id)}</span>
                    <span className="assessment-question-summary-copy"><small>{questionTypesByType[item.type].label}</small><strong>{item.prompt || 'Untitled question'}</strong></span>
                    <span className="assessment-question-quick-settings"><button type="button" className={`assessment-header-media${questionMediaCount ? ' is-active' : ''}`} aria-label={`${questionMediaCount ? 'Edit' : 'Add'} media for question ${numbering.get(item.id)}`} title={`${questionMediaCount ? 'Edit' : 'Add'} question media`} onClick={() => { setCollapsedQuestions((current) => { const next = new Set(current); next.delete(item.id); return next }); setMediaRequest({ itemId: item.id, nonce: Date.now() }) }}><Image aria-hidden="true" />{questionMediaCount ? <b>{questionMediaCount}</b> : null}</button>{questionTypesByType[item.type].supportsScoring ? <><label className={item.required ? 'is-required' : ''}><input aria-label={`Required question ${numbering.get(item.id)}`} type="checkbox" checked={item.required ?? false} onChange={(event) => updateItem(item.id, (current) => ({ ...current, required: event.target.checked }))} /><span>Required</span></label><label className={Number(item.points ?? 0) > 0 ? 'has-points' : ''}><span>Points</span><input aria-label={`Points for question ${numbering.get(item.id)}`} value={item.points ?? '0'} onChange={(event) => updateItem(item.id, (current) => ({ ...current, points: event.target.value }))} inputMode="decimal" /></label></> : null}</span>
                    <details className="assessment-question-menu"><summary aria-label={`Question ${numbering.get(item.id)} actions`}>•••</summary><div>
                      <button type="button" disabled={itemIndex === 0} onClick={() => moveItem(section.id, itemIndex, -1)}><ArrowUp /> Move up</button>
                      <button type="button" disabled={itemIndex === section.items.length - 1} onClick={() => moveItem(section.id, itemIndex, 1)}><ArrowDown /> Move down</button>
                      <button type="button" onClick={() => updateSection(section.id, (current) => ({ ...current, items: current.items.filter((candidate) => candidate.id !== item.id) }))}><Trash /> Delete</button>
                    </div></details>
                    <button type="button" className="assessment-question-collapse" aria-label={`${questionCollapsed ? 'Expand' : 'Collapse'} question ${numbering.get(item.id)}`} aria-expanded={!questionCollapsed} onClick={() => setCollapsedQuestions((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })}><CaretDown aria-hidden="true" /></button>
                  </header>
                  {!questionCollapsed ? <QuestionEditor item={item} slides={slides} setSlides={setSlides} updateItem={updateItem} promptRef={() => undefined} routingTargets={document.sections.filter((candidate) => candidate.id !== section.id)} draftId={draftId} mediaScopeLabel={mediaScopeLabel} mediaDialogRequest={mediaRequest.itemId === item.id ? mediaRequest.nonce : 0} /> : null}
                </article> })}
              </div>
              <div className="assessment-section-add-question"><span className="assessment-section-add-question-label"><Plus aria-hidden="true" /> Add question</span><label><span className="visually-hidden">Question type</span><select aria-label={`Question type for section ${sectionIndex + 1}`} defaultValue="multiple-choice">{authorableQuestionTypeRegistry.map((type) => <option key={type.type} value={type.type}>{type.label}</option>)}</select></label><button type="button" aria-label={`Add selected question to section ${sectionIndex + 1}`} title="Add question" onClick={(event) => { const select = event.currentTarget.previousElementSibling?.querySelector('select') as HTMLSelectElement | null; addItem(section.id, (select?.value ?? 'multiple-choice') as AssessmentItemType) }}><Plus aria-hidden="true" /></button></div>
            </> : null}
          </article>
        })}
        {document.sections.length === 0 ? <div className="assessment-empty"><h2>Add the first section</h2><button className="assessment-primary" type="button" onClick={addSection}><Plus /> Add section</button></div> : null}
      </section>
    </div>
    <p className="visually-hidden" aria-live="polite">{message}</p>
    {deleted ? <div className="assessment-undo-toast" role="status"><span>Section deleted</span><button type="button" onClick={undoDelete}>Undo</button><button type="button" aria-label="Dismiss" onClick={() => setDeleted(null)}><X /></button></div> : null}
  </main>
}
