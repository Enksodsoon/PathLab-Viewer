import { ArrowDown, ArrowUp, CaretDown, Copy, DotsSixVertical, ListMagnifyingGlass, MagnifyingGlass, Plus, Trash, X } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { listEligibleAssessmentSlides } from '../../assessment/api'
import { questionTypeGroups, questionTypeRegistry, questionTypesByType } from '../../assessment/questionTypes'
import type { AssessmentDocument, AssessmentItem, AssessmentItemType, DiagnosticSelection, EligibleAssessmentSlide } from '../../assessment/types'
import { AssessmentDiagnosticField } from '../AssessmentDiagnosticField'

interface CanvasProps {
  document: AssessmentDocument
  onDocumentChange: (update: (document: AssessmentDocument) => AssessmentDocument) => void
  onImport: () => void
}

type OutlineRequiredFilter = 'all' | 'required' | 'optional'
type AssessmentOption = NonNullable<AssessmentItem['options']>[number] | string

function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
}

function optionId(option: AssessmentOption, index: number) {
  return typeof option === 'string' ? `legacy-option-${index}` : option.id
}

function optionLabel(option: AssessmentOption) {
  return typeof option === 'string' ? option : option.label
}

export function AssessmentQuestionCanvas({ document, onDocumentChange, onImport }: CanvasProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(document.items[0] ? [document.items[0].id] : []))
  const [activeId, setActiveId] = useState(() => document.items[0]?.id ?? '')
  const [outlineOpen, setOutlineOpen] = useState(false)
  const [outlineSearch, setOutlineSearch] = useState('')
  const [outlineType, setOutlineType] = useState<'all' | AssessmentItemType>('all')
  const [outlineRequired, setOutlineRequired] = useState<OutlineRequiredFilter>('all')
  const [issuesOnly, setIssuesOnly] = useState(false)
  const [navigatorSearch, setNavigatorSearch] = useState('')
  const [insertAt, setInsertAt] = useState<number | null>(null)
  const [deleted, setDeleted] = useState<{ item: AssessmentItem; index: number } | null>(null)
  const [slides, setSlides] = useState<EligibleAssessmentSlide[]>([])
  const [draggedId, setDraggedId] = useState('')
  const initializedRef = useRef(document.items.length > 0)
  const outlineTriggerRef = useRef<HTMLButtonElement>(null)
  const outlineRef = useRef<HTMLDivElement>(null)
  const cardRefs = useRef(new Map<string, HTMLElement>())
  const promptRefs = useRef(new Map<string, HTMLTextAreaElement>())

  useEffect(() => {
    if (initializedRef.current || !document.items.length) return
    initializedRef.current = true
    setExpandedIds(new Set([document.items[0].id]))
    setActiveId(document.items[0].id)
  }, [document.items])

  useEffect(() => {
    if (!outlineOpen) return
    const dialog = outlineRef.current
    const focusable = dialog?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select') ?? []
    focusable[0]?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOutlineOpen(false)
        window.setTimeout(() => outlineTriggerRef.current?.focus())
      }
      if (event.key !== 'Tab' || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && globalThis.document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && globalThis.document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    globalThis.document.addEventListener('keydown', onKeyDown)
    return () => globalThis.document.removeEventListener('keydown', onKeyDown)
  }, [outlineOpen])

  const totalPoints = useMemo(() => document.items.reduce((total, item) => total + (questionTypesByType[item.type].supportsScoring ? Number(item.points || 0) || 0 : 0), 0), [document.items])
  const itemIndexById = useMemo(() => new Map(document.items.map((item, index) => [item.id, index])), [document.items])
  const navigatorItems = useMemo(() => {
    const query = navigatorSearch.trim().toLocaleLowerCase()
    if (!query) return document.items
    return document.items.filter((item) => item.prompt.toLocaleLowerCase().includes(query) || questionTypesByType[item.type].label.toLocaleLowerCase().includes(query))
  }, [document.items, navigatorSearch])
  const filteredOutline = useMemo(() => document.items.filter((item) => {
    const query = outlineSearch.trim().toLocaleLowerCase()
    const matchesSearch = !query || item.prompt.toLocaleLowerCase().includes(query) || questionTypesByType[item.type].label.toLocaleLowerCase().includes(query)
    const matchesType = outlineType === 'all' || item.type === outlineType
    const matchesRequired = outlineRequired === 'all' || (outlineRequired === 'required' ? item.required : !item.required)
    return matchesSearch && matchesType && matchesRequired && (!issuesOnly || questionTypesByType[item.type].validate(item).length > 0)
  }), [document.items, issuesOnly, outlineRequired, outlineSearch, outlineType])

  function updateItem(itemId: string, update: (item: AssessmentItem) => AssessmentItem) {
    onDocumentChange((current) => ({ ...current, items: current.items.map((item) => item.id === itemId ? update(item) : item) }))
  }

  function focusItem(itemId: string, focusPrompt = false) {
    setActiveId(itemId)
    setExpandedIds((current) => new Set(current).add(itemId))
    window.setTimeout(() => {
      const card = cardRefs.current.get(itemId)
      if (typeof card?.scrollIntoView === 'function') card.scrollIntoView({ behavior: 'auto', block: 'center' })
      ;(focusPrompt ? promptRefs.current.get(itemId) : cardRefs.current.get(itemId))?.focus()
    })
  }

  function insertItem(type: AssessmentItemType, index: number) {
    const item = questionTypesByType[type].create(newId)
    onDocumentChange((current) => {
      const items = [...current.items]
      items.splice(index, 0, item)
      return { ...current, items }
    })
    setInsertAt(null)
    focusItem(item.id, true)
  }

  function moveItem(sourceIndex: number, destinationIndex: number) {
    if (destinationIndex < 0 || destinationIndex >= document.items.length || sourceIndex === destinationIndex) return
    onDocumentChange((current) => {
      const items = [...current.items]
      const [item] = items.splice(sourceIndex, 1)
      items.splice(destinationIndex, 0, item)
      return { ...current, items }
    })
  }

  function duplicateItem(item: AssessmentItem, index: number) {
    const id = newId()
    const optionMap = new Map((item.options ?? []).map((option, optionIndex) => [optionId(option, optionIndex), newId()]))
    const answerIds = (item.answerKey?.optionIds as string[] | undefined)?.map((optionId) => optionMap.get(optionId) ?? optionId)
    const copy: AssessmentItem = {
      ...structuredClone(item), id,
      options: item.options?.map((option, optionIndex) => ({ id: optionMap.get(optionId(option, optionIndex))!, label: optionLabel(option) })),
      answerKey: { ...item.answerKey, ...(answerIds ? { optionIds: answerIds } : {}) },
    }
    onDocumentChange((current) => {
      const items = [...current.items]
      items.splice(index + 1, 0, copy)
      return { ...current, items }
    })
    focusItem(id, true)
  }

  function deleteItem(item: AssessmentItem, index: number) {
    setDeleted({ item: structuredClone(item), index })
    onDocumentChange((current) => ({ ...current, items: current.items.filter((candidate) => candidate.id !== item.id) }))
    setExpandedIds((current) => { const next = new Set(current); next.delete(item.id); return next })
    const nearest = document.items[index + 1] ?? document.items[index - 1]
    if (nearest) focusItem(nearest.id)
  }

  function undoDelete() {
    if (!deleted) return
    onDocumentChange((current) => {
      const items = [...current.items]
      items.splice(Math.min(deleted.index, items.length), 0, deleted.item)
      return { ...current, items }
    })
    focusItem(deleted.item.id)
    setDeleted(null)
  }

  function dropAt(targetIndex: number) {
    const sourceIndex = document.items.findIndex((item) => item.id === draggedId)
    if (sourceIndex >= 0) moveItem(sourceIndex, targetIndex)
    setDraggedId('')
  }

  return <main className="assessment-question-workspace">
    <header className="assessment-authoring-toolbar">
      <div className="assessment-authoring-totals"><strong>{document.items.length}</strong> {document.items.length === 1 ? 'question' : 'questions'}<span aria-hidden="true">·</span><strong>{totalPoints}</strong> {totalPoints === 1 ? 'point' : 'points'}</div>
      <div className="assessment-authoring-actions">
        <button ref={outlineTriggerRef} type="button" onClick={() => setOutlineOpen(true)}><ListMagnifyingGlass aria-hidden="true" /> Outline</button>
        <button type="button" onClick={() => setExpandedIds(new Set(document.items.map((item) => item.id)))}>Expand all</button>
        <button type="button" onClick={() => setExpandedIds(new Set())}>Collapse all</button>
        <button type="button" onClick={onImport}><Copy aria-hidden="true" /> Import</button>
        <button className="assessment-primary" type="button" onClick={() => setInsertAt(document.items.length)}><Plus aria-hidden="true" /> Add question</button>
      </div>
    </header>

    <div className="assessment-question-layout">
      <aside className="assessment-question-navigator" aria-label="Question navigator">
        <header><strong>Questions</strong><span>{document.items.length}</span></header>
        <label><MagnifyingGlass aria-hidden="true" /><input value={navigatorSearch} onChange={(event) => setNavigatorSearch(event.target.value)} placeholder="Find a question" /></label>
        <ol>
          {navigatorItems.map((item) => {
            const index = itemIndexById.get(item.id) ?? 0
            const issues = questionTypesByType[item.type].validate(item)
            return <li key={item.id}>
              <button type="button" className={activeId === item.id ? 'active' : ''} aria-current={activeId === item.id ? 'true' : undefined} aria-label={`Go to question ${index + 1}: ${item.prompt || 'Untitled question'}`} onClick={() => focusItem(item.id)}>
                <span>{index + 1}</span>
                <span><strong>{item.prompt || 'Untitled question'}</strong><small>{questionTypesByType[item.type].label}{item.required ? ' · Required' : ''}</small></span>
                {issues.length ? <i aria-label={`${issues.length} validation ${issues.length === 1 ? 'issue' : 'issues'}`}>{issues.length}</i> : null}
              </button>
            </li>
          })}
        </ol>
        {navigatorItems.length === 0 ? <p>No matching questions.</p> : null}
      </aside>

      <section className="assessment-question-canvas" aria-label="Questions">
      {document.items.length === 0 ? <div className="assessment-empty assessment-empty--canvas"><h2>Start with a question</h2><p>Choose a type and build the form in one continuous canvas.</p><button className="assessment-primary" type="button" onClick={() => setInsertAt(0)}><Plus /> Add question</button></div> : null}
      {document.items.map((item, index) => {
        const expanded = expandedIds.has(item.id)
        const issues = questionTypesByType[item.type].validate(item)
        return <div className="assessment-canvas-item" key={item.id} onDragOver={(event) => event.preventDefault()} onDrop={() => dropAt(index)}>
          <article
            ref={(node) => { if (node) cardRefs.current.set(item.id, node); else cardRefs.current.delete(item.id) }}
            role="group"
            aria-label={`Question ${index + 1}`}
            tabIndex={-1}
            className={`assessment-question-card${activeId === item.id ? ' assessment-question-card--focused' : ''}${expanded ? ' assessment-question-card--expanded' : ''}`}
            data-question-id={item.id}
            data-expanded={expanded}
            onFocus={() => setActiveId(item.id)}
          >
            <header className="assessment-question-card-header">
              <button
                className="assessment-question-drag"
                type="button"
                draggable
                aria-label={`Reorder question ${index + 1}`}
                onDragStart={() => setDraggedId(item.id)}
                onDragEnd={() => setDraggedId('')}
                onKeyDown={(event) => {
                  if (!event.altKey) return
                  if (event.key === 'ArrowUp') { event.preventDefault(); moveItem(index, index - 1) }
                  if (event.key === 'ArrowDown') { event.preventDefault(); moveItem(index, index + 1) }
                }}
              ><DotsSixVertical aria-hidden="true" /></button>
              <span className="assessment-question-number">{index + 1}</span>
              <button className="assessment-question-summary" type="button" aria-expanded={expanded} onClick={() => {
                setActiveId(item.id)
                setExpandedIds((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next })
              }}>
                <span className="assessment-question-summary-copy"><small>{questionTypesByType[item.type].label}</small><strong>{item.prompt || 'Untitled question'}</strong></span>
                <CaretDown aria-hidden="true" />
              </button>
              <span className="assessment-question-badges">
                {item.required ? <span>Required</span> : null}
                {questionTypesByType[item.type].supportsScoring ? <span>{item.points || 0} pt</span> : null}
                {issues.length ? <span className="assessment-validation-badge">{issues.length} issue{issues.length === 1 ? '' : 's'}</span> : null}
              </span>
              <details className="assessment-question-menu">
                <summary aria-label={`Question ${index + 1} actions`}>•••</summary>
                <div>
                  <button type="button" disabled={index === 0} onClick={() => moveItem(index, index - 1)}><ArrowUp /> Move up</button>
                  <button type="button" disabled={index === document.items.length - 1} onClick={() => moveItem(index, index + 1)}><ArrowDown /> Move down</button>
                  <button type="button" onClick={() => duplicateItem(item, index)}><Copy /> Duplicate</button>
                  <button type="button" className="assessment-danger-action" onClick={() => deleteItem(item, index)}><Trash /> Delete</button>
                </div>
              </details>
            </header>
            {expanded ? <QuestionEditor item={item} slides={slides} setSlides={setSlides} updateItem={updateItem} promptRef={(node) => { if (node) promptRefs.current.set(item.id, node); else promptRefs.current.delete(item.id) }} /> : null}
          </article>
          <InsertControl open={insertAt === index + 1} onOpen={() => setInsertAt(index + 1)} onClose={() => setInsertAt(null)} onSelect={(type) => insertItem(type, index + 1)} />
        </div>
      })}
      {document.items.length === 0 && insertAt === 0 ? <TypePicker onClose={() => setInsertAt(null)} onSelect={(type) => insertItem(type, 0)} /> : null}
      </section>
    </div>

    <button className="assessment-mobile-add" type="button" aria-label="Add question" onClick={() => setInsertAt(document.items.length)}><Plus aria-hidden="true" /></button>

    {deleted ? <div className="assessment-undo-toast" role="status"><span>Question deleted</span><button type="button" onClick={undoDelete}>Undo</button><button type="button" aria-label="Dismiss" onClick={() => setDeleted(null)}><X /></button></div> : null}

    {outlineOpen ? <div className="assessment-outline-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOutlineOpen(false) }}>
      <div ref={outlineRef} className="assessment-outline-drawer" role="dialog" aria-modal="true" aria-labelledby="assessment-outline-title">
        <header><div><span className="assessment-kicker">Form outline</span><h2 id="assessment-outline-title">Find a question</h2></div><button type="button" aria-label="Close outline" onClick={() => { setOutlineOpen(false); window.setTimeout(() => outlineTriggerRef.current?.focus()) }}><X /></button></header>
        <label className="assessment-outline-search"><MagnifyingGlass /><input autoFocus value={outlineSearch} onChange={(event) => setOutlineSearch(event.target.value)} placeholder="Search prompts or types" /></label>
        <div className="assessment-outline-filters">
          <select aria-label="Filter by question type" value={outlineType} onChange={(event) => setOutlineType(event.target.value as 'all' | AssessmentItemType)}><option value="all">All types</option>{questionTypeRegistry.map((definition) => <option key={definition.type} value={definition.type}>{definition.label}</option>)}</select>
          <select aria-label="Filter by required state" value={outlineRequired} onChange={(event) => setOutlineRequired(event.target.value as OutlineRequiredFilter)}><option value="all">Any requirement</option><option value="required">Required</option><option value="optional">Optional</option></select>
          <label><input type="checkbox" checked={issuesOnly} onChange={(event) => setIssuesOnly(event.target.checked)} /> Issues only</label>
        </div>
        <ol>{filteredOutline.map((item) => { const index = itemIndexById.get(item.id) ?? 0; return <li key={item.id}><button type="button" onClick={() => { setOutlineOpen(false); focusItem(item.id, true) }}><span>{index + 1}</span><span><strong>{item.prompt || 'Untitled question'}</strong><small>{questionTypesByType[item.type].label}</small></span></button></li> })}</ol>
        {filteredOutline.length === 0 ? <p className="assessment-outline-no-results">No matching questions.</p> : null}
      </div>
    </div> : null}
  </main>
}

function InsertControl({ open, onOpen, onClose, onSelect }: { open: boolean; onOpen: () => void; onClose: () => void; onSelect: (type: AssessmentItemType) => void }) {
  return <div className={`assessment-insert-control${open ? ' assessment-insert-control--open' : ''}`}>
    {!open ? <button type="button" aria-label="Insert question here" onClick={onOpen}><Plus aria-hidden="true" /><span>Insert</span></button> : <TypePicker onClose={onClose} onSelect={onSelect} />}
  </div>
}

function TypePicker({ onClose, onSelect }: { onClose: () => void; onSelect: (type: AssessmentItemType) => void }) {
  return <div className="assessment-type-picker" role="dialog" aria-label="Choose question type">
    <header><strong>Add item</strong><button type="button" aria-label="Close type picker" onClick={onClose}><X /></button></header>
    <div>{questionTypeGroups.map((group) => <section key={group}><h3>{group}</h3>{questionTypeRegistry.filter((definition) => definition.group === group).map((definition) => <button key={definition.type} type="button" aria-label={`Add ${definition.label.toLowerCase()}`} onClick={() => onSelect(definition.type)}><Plus aria-hidden="true" />{definition.label}</button>)}</section>)}</div>
  </div>
}

function QuestionEditor({ item, slides, setSlides, updateItem, promptRef }: { item: AssessmentItem; slides: EligibleAssessmentSlide[]; setSlides: (slides: EligibleAssessmentSlide[]) => void; updateItem: (itemId: string, update: (item: AssessmentItem) => AssessmentItem) => void; promptRef: (node: HTMLTextAreaElement | null) => void }) {
  const supportsScoring = questionTypesByType[item.type].supportsScoring
  return <div className="assessment-question-editor" data-testid="question-editor">
    <label className="assessment-question-prompt">Prompt<textarea ref={promptRef} value={item.prompt} onChange={(event) => updateItem(item.id, (current) => ({ ...current, prompt: event.target.value }))} /></label>
    {item.options?.map((option, optionIndex) => {
      const id = optionId(option, optionIndex)
      return <label key={id} className="assessment-option"><input type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={`key-${item.id}`} checked={((item.answerKey?.optionIds as string[] | undefined) ?? []).includes(id)} onChange={() => updateItem(item.id, (current) => { const selected = (current.answerKey?.optionIds as string[] | undefined) ?? []; const optionIds = current.type === 'checkboxes' ? (selected.includes(id) ? selected.filter((selectedId) => selectedId !== id) : [...selected, id]) : [id]; return { ...current, answerKey: { ...current.answerKey, optionIds } } })} /><input aria-label={`Option ${optionIndex + 1}`} value={optionLabel(option)} onChange={(event) => updateItem(item.id, (current) => ({ ...current, options: current.options?.map((candidate, candidateIndex) => candidateIndex === optionIndex ? { id, label: event.target.value } : typeof candidate === 'string' ? { id: optionId(candidate, candidateIndex), label: candidate } : candidate) }))} /></label>
    })}
    {item.options ? <div className="assessment-option-tools"><button type="button" onClick={() => updateItem(item.id, (current) => ({ ...current, options: [...(current.options ?? []), { id: newId(), label: `Option ${(current.options?.length ?? 0) + 1}` }] }))}>Add option</button><details><summary>Paste options</summary><label>One option per line<textarea onPaste={(event) => { event.preventDefault(); const optionLabels = event.clipboardData.getData('text').split(/\r?\n/).map((value) => value.trim()).filter(Boolean).slice(0, 10); updateItem(item.id, (current) => ({ ...current, options: optionLabels.map((label) => ({ id: newId(), label })), answerKey: { ...current.answerKey, optionIds: [] } })) }} /></label></details></div> : null}
    {item.type === 'diagnostic-field' ? <details className="assessment-progressive-section"><summary>Answer key & diagnostic regions</summary><div className="assessment-diagnostic"><p>Choose a privacy-passed static-DZI slide, then mark accepted points or rectangles.</p><button type="button" onClick={() => void listEligibleAssessmentSlides().then((result) => setSlides(result.items))}>Choose slide</button>{slides.length ? <select aria-label="Eligible slide" value={item.slideId ?? ''} onChange={(event) => updateItem(item.id, (current) => ({ ...current, slideId: event.target.value, answerKey: { ...current.answerKey, regions: [] } }))}><option value="">Select a slide</option>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select> : null}{item.slideId && slides.find((slide) => slide.id === item.slideId) ? <AssessmentDiagnosticField label="Accepted diagnostic regions" tileSource={slides.find((slide) => slide.id === item.slideId)!.tileSource} selections={(item.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []} multiple onCommit={(selection) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, regions: [...((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []), selection] } }))} onClear={() => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, regions: [] } }))} /> : null}<label>Accepted diagnoses<input value={((item.answerKey?.diagnoses as string[] | undefined) ?? []).join(', ')} onChange={(event) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, diagnoses: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label></div></details> : null}
    {item.type === 'short-answer' ? <details className="assessment-progressive-section"><summary>Answer key</summary><label>Accepted answers<input value={((item.answerKey?.variants as string[] | undefined) ?? []).join(', ')} onChange={(event) => updateItem(item.id, (current) => ({ ...current, answerKey: { ...current.answerKey, variants: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label></details> : null}
    {supportsScoring ? <details className="assessment-progressive-section"><summary>Feedback, validation & scoring</summary><label>Feedback<textarea value={item.feedback?.correct ?? ''} onChange={(event) => updateItem(item.id, (current) => ({ ...current, feedback: { ...current.feedback, correct: event.target.value } }))} /></label>{item.type === 'checkboxes' ? <label><input type="checkbox" checked={item.scoring?.partialCredit ?? false} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, partialCredit: event.target.checked } }))} /> Bounded partial credit</label> : null}{item.type === 'diagnostic-field' ? <div className="assessment-advanced-scoring"><label>Point tolerance<input type="number" min="0" max="1" step="0.01" value={item.scoring?.pointTolerance ?? 0.03} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, pointTolerance: Number(event.target.value), rectangleIou: current.scoring?.rectangleIou ?? 0.25 } }))} /></label><label>Rectangle IoU<input type="number" min="0" max="1" step="0.05" value={item.scoring?.rectangleIou ?? 0.25} onChange={(event) => updateItem(item.id, (current) => ({ ...current, scoring: { ...current.scoring, pointTolerance: current.scoring?.pointTolerance ?? 0.03, rectangleIou: Number(event.target.value) } }))} /></label></div> : null}</details> : null}
    {supportsScoring ? <footer className="assessment-question-footer"><label>Required <input type="checkbox" checked={item.required ?? false} onChange={(event) => updateItem(item.id, (current) => ({ ...current, required: event.target.checked }))} /></label><label>Points <input value={item.points ?? '0'} onChange={(event) => updateItem(item.id, (current) => ({ ...current, points: event.target.value }))} inputMode="decimal" /></label></footer> : null}
  </div>
}
