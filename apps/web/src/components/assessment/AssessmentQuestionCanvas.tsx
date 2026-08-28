import { ArrowDown, ArrowUp, ArrowsInLineVertical, ArrowsOutLineVertical, CaretDown, Copy, DotsSixVertical, Eye, MagnifyingGlass, Plus, Trash, X } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { listEligibleAssessmentSlides } from '../../assessment/api'
import { questionTypeGroups, questionTypeRegistry, questionTypesByType } from '../../assessment/questionTypes'
import { assessmentItems, replaceAssessmentItems, type AssessmentDocument, type AssessmentItem, type AssessmentItemType, type AssessmentSection, type DiagnosticSelection, type EligibleAssessmentSlide } from '../../assessment/types'
import { AssessmentDiagnosticField } from '../AssessmentDiagnosticField'

interface CanvasProps {
  document: AssessmentDocument
  onDocumentChange: (update: (document: AssessmentDocument) => AssessmentDocument) => void
  onImport: () => void
  onPreview: () => void
}

type NavigatorRequiredFilter = 'all' | 'required' | 'optional'
type AssessmentOption = NonNullable<AssessmentItem['options']>[number] | string
type DragVisual = { itemId: string; x: number; y: number; width: number }

function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
}

function optionId(option: AssessmentOption, index: number) {
  return typeof option === 'string' ? `legacy-option-${index}` : option.id
}

function optionLabel(option: AssessmentOption) {
  return typeof option === 'string' ? option : option.label
}

export function AssessmentQuestionCanvas({ document, onDocumentChange, onImport, onPreview }: CanvasProps) {
  const items = useMemo(() => assessmentItems(document), [document])
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(items[0] ? [items[0].id] : []))
  const [activeId, setActiveId] = useState(() => items[0]?.id ?? '')
  const [navigatorSearch, setNavigatorSearch] = useState('')
  const [navigatorType, setNavigatorType] = useState<'all' | AssessmentItemType>('all')
  const [navigatorRequired, setNavigatorRequired] = useState<NavigatorRequiredFilter>('all')
  const [navigatorIssuesOnly, setNavigatorIssuesOnly] = useState(false)
  const [insertAt, setInsertAt] = useState<number | null>(null)
  const [deleted, setDeleted] = useState<{ item: AssessmentItem; index: number } | null>(null)
  const [slides, setSlides] = useState<EligibleAssessmentSlide[]>([])
  const [draggedId, setDraggedId] = useState('')
  const [dropTargetId, setDropTargetId] = useState('')
  const [reorderMessage, setReorderMessage] = useState('')
  const [dragVisual, setDragVisual] = useState<DragVisual | null>(null)
  const initializedRef = useRef(items.length > 0)
  const cardRefs = useRef(new Map<string, HTMLElement>())
  const promptRefs = useRef(new Map<string, HTMLTextAreaElement>())
  const navigatorListRef = useRef<HTMLOListElement>(null)
  const dragPreviewRef = useRef<HTMLDivElement>(null)
  const pointerDragRef = useRef<{ itemId: string; pointerId: number } | null>(null)
  const dropTargetIdRef = useRef('')
  const pointerCleanupRef = useRef<() => void>(() => undefined)

  useEffect(() => {
    if (initializedRef.current || !items.length) return
    initializedRef.current = true
    setExpandedIds(new Set([items[0].id]))
    setActiveId(items[0].id)
  }, [items])

  useEffect(() => () => pointerCleanupRef.current(), [])

  const itemIndexById = useMemo(() => new Map(items.map((item, index) => [item.id, index])), [items])
  const navigatorItems = useMemo(() => {
    const query = navigatorSearch.trim().toLocaleLowerCase()
    return items.filter((item) => {
      const matchesSearch = !query || item.prompt.toLocaleLowerCase().includes(query) || questionTypesByType[item.type].label.toLocaleLowerCase().includes(query)
      const matchesType = navigatorType === 'all' || item.type === navigatorType
      const matchesRequired = navigatorRequired === 'all' || (navigatorRequired === 'required' ? item.required : !item.required)
      const matchesIssues = !navigatorIssuesOnly || questionTypesByType[item.type].validate(item).length > 0
      return matchesSearch && matchesType && matchesRequired && matchesIssues
    })
  }, [items, navigatorIssuesOnly, navigatorRequired, navigatorSearch, navigatorType])
  const readyCount = useMemo(() => items.filter((item) => questionTypesByType[item.type].validate(item).length === 0).length, [items])

  function updateItem(itemId: string, update: (item: AssessmentItem) => AssessmentItem) {
    onDocumentChange((current) => replaceAssessmentItems(
      current,
      assessmentItems(current).map((item) => item.id === itemId ? update(item) : item),
    ))
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
      const nextItems = [...assessmentItems(current)]
      nextItems.splice(index, 0, item)
      return replaceAssessmentItems(current, nextItems)
    })
    setInsertAt(null)
    focusItem(item.id, true)
  }

  function moveItem(sourceIndex: number, destinationIndex: number) {
    if (destinationIndex < 0 || destinationIndex >= items.length || sourceIndex === destinationIndex) return
    const movingItem = items[sourceIndex]
    if (!movingItem) return
    onDocumentChange((current) => {
      const currentItems = assessmentItems(current)
      const currentSourceIndex = currentItems.findIndex((item) => item.id === movingItem.id)
      if (currentSourceIndex < 0) return current
      const nextItems = [...currentItems]
      const [item] = nextItems.splice(currentSourceIndex, 1)
      nextItems.splice(destinationIndex, 0, item)
      return replaceAssessmentItems(current, nextItems)
    })
    setActiveId(movingItem.id)
    setReorderMessage(`Moved question ${sourceIndex + 1} to position ${destinationIndex + 1}.`)
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
      const nextItems = [...assessmentItems(current)]
      nextItems.splice(index + 1, 0, copy)
      return replaceAssessmentItems(current, nextItems)
    })
    focusItem(id, true)
  }

  function deleteItem(item: AssessmentItem, index: number) {
    setDeleted({ item: structuredClone(item), index })
    onDocumentChange((current) => replaceAssessmentItems(
      current,
      assessmentItems(current).filter((candidate) => candidate.id !== item.id),
    ))
    setExpandedIds((current) => { const next = new Set(current); next.delete(item.id); return next })
    const nearest = items[index + 1] ?? items[index - 1]
    if (nearest) focusItem(nearest.id)
  }

  function undoDelete() {
    if (!deleted) return
    onDocumentChange((current) => {
      const nextItems = [...assessmentItems(current)]
      nextItems.splice(Math.min(deleted.index, nextItems.length), 0, deleted.item)
      return replaceAssessmentItems(current, nextItems)
    })
    focusItem(deleted.item.id)
    setDeleted(null)
  }

  function startDragging(itemId: string, dataTransfer: DataTransfer) {
    setDraggedId(itemId)
    dataTransfer.effectAllowed = 'move'
    dataTransfer.setData('text/plain', itemId)
  }

  function stopDragging() {
    pointerCleanupRef.current()
    setDraggedId('')
    setDropTargetId('')
    dropTargetIdRef.current = ''
    pointerDragRef.current = null
    setDragVisual(null)
  }

  function targetDragItem(itemId: string) {
    if (dropTargetIdRef.current === itemId) return
    dropTargetIdRef.current = itemId
    setDropTargetId(itemId)
  }

  function startPointerDragging(itemId: string, pointerId: number, clientX: number, clientY: number, width: number) {
    if (pointerDragRef.current) return
    pointerDragRef.current = { itemId, pointerId }
    setDraggedId(itemId)
    setDragVisual({ itemId, x: clientX, y: clientY, width })
    window.requestAnimationFrame(() => positionDragPreview(clientX, clientY))
    const onPointerMove = (event: PointerEvent) => updatePointerTarget(event.clientX, event.clientY)
    const onMouseMove = (event: MouseEvent) => updatePointerTarget(event.clientX, event.clientY)
    const onEnd = () => {
      pointerCleanupRef.current()
      finishPointerDragging()
    }
    const cleanup = () => {
      globalThis.removeEventListener('pointermove', onPointerMove)
      globalThis.removeEventListener('pointerup', onEnd)
      globalThis.removeEventListener('pointercancel', onEnd)
      globalThis.removeEventListener('mousemove', onMouseMove)
      globalThis.removeEventListener('mouseup', onEnd)
      pointerCleanupRef.current = () => undefined
    }
    pointerCleanupRef.current = cleanup
    globalThis.addEventListener('pointermove', onPointerMove)
    globalThis.addEventListener('pointerup', onEnd)
    globalThis.addEventListener('pointercancel', onEnd)
    globalThis.addEventListener('mousemove', onMouseMove)
    globalThis.addEventListener('mouseup', onEnd)
  }

  function updatePointerTarget(clientX: number, clientY: number) {
    if (!pointerDragRef.current) return
    positionDragPreview(clientX, clientY)
    const list = navigatorListRef.current
    if (list) {
      const bounds = list.getBoundingClientRect()
      const delta = clientY < bounds.top + 44 ? -14 : clientY > bounds.bottom - 44 ? 14 : 0
      if (delta && typeof list.scrollBy === 'function') list.scrollBy({ top: delta })
      else if (delta) list.scrollTop += delta
    }
    const target = globalThis.document.elementFromPoint(clientX, clientY)?.closest('[data-navigator-question-id]') as HTMLElement | null | undefined
    const targetId = target?.dataset.navigatorQuestionId ?? ''
    if (targetId && targetId !== pointerDragRef.current.itemId) targetDragItem(targetId)
    else if (!targetId) targetDragItem('')
  }

  function positionDragPreview(clientX: number, clientY: number) {
    if (!dragPreviewRef.current) return
    dragPreviewRef.current.style.transform = `translate3d(${clientX + 14}px, ${clientY - 28}px, 0) rotate(.35deg) scale(1.015)`
  }

  function finishPointerDragging() {
    const pointerDrag = pointerDragRef.current
    const targetIndex = items.findIndex((item) => item.id === dropTargetIdRef.current)
    if (pointerDrag && targetIndex >= 0) dropAt(targetIndex, pointerDrag.itemId)
    else stopDragging()
  }

  function dropAt(targetIndex: number, transferredId = draggedId) {
    const sourceIndex = items.findIndex((item) => item.id === transferredId)
    if (sourceIndex >= 0) moveItem(sourceIndex, targetIndex)
    stopDragging()
  }

  return <main className="assessment-question-workspace">
    <header className="assessment-authoring-toolbar">
      <div className="assessment-authoring-heading"><h2>Questions</h2><p>Build the learner sequence and reorder it at any time.</p></div>
      <div className="assessment-authoring-actions">
        <button type="button" onClick={onPreview}><Eye aria-hidden="true" /> Assignment preview</button>
        <button className="assessment-icon-action" type="button" aria-label="Expand all questions" title="Expand all questions" onClick={() => setExpandedIds(new Set(items.map((item) => item.id)))}><ArrowsOutLineVertical aria-hidden="true" /></button>
        <button className="assessment-icon-action" type="button" aria-label="Collapse all questions" title="Collapse all questions" onClick={() => setExpandedIds(new Set())}><ArrowsInLineVertical aria-hidden="true" /></button>
        <span className="assessment-authoring-divider" aria-hidden="true" />
        <button type="button" onClick={onImport}><Copy aria-hidden="true" /> Import questions</button>
        <button className="assessment-primary assessment-toolbar-add" type="button" onClick={() => setInsertAt(items.length)}><Plus aria-hidden="true" /> Add question</button>
      </div>
    </header>

    <div className="assessment-question-layout">
      <aside className="assessment-question-navigator" aria-label="Question navigator">
        <header><div><strong>Question navigator</strong><small>{items.length} total</small></div><span>{items.length}</span></header>
        <div className="assessment-navigator-tools">
          <label className="assessment-navigator-search"><MagnifyingGlass aria-hidden="true" /><input value={navigatorSearch} onChange={(event) => setNavigatorSearch(event.target.value)} placeholder="Search questions" /></label>
          <select aria-label="Filter by question type" value={navigatorType} onChange={(event) => setNavigatorType(event.target.value as 'all' | AssessmentItemType)}><option value="all">All types</option>{questionTypeRegistry.map((definition) => <option key={definition.type} value={definition.type}>{definition.label}</option>)}</select>
          <select aria-label="Filter by required state" value={navigatorRequired} onChange={(event) => setNavigatorRequired(event.target.value as NavigatorRequiredFilter)}><option value="all">Any requirement</option><option value="required">Required</option><option value="optional">Optional</option></select>
          <label className="assessment-navigator-issues"><input type="checkbox" checked={navigatorIssuesOnly} onChange={(event) => setNavigatorIssuesOnly(event.target.checked)} /> Needs attention</label>
        </div>
        <div className="assessment-navigator-guide"><span><DotsSixVertical aria-hidden="true" />Drag to reorder</span><span>{readyCount} of {items.length} ready</span><progress aria-label={`${readyCount} of ${items.length} questions ready`} max={Math.max(1, items.length)} value={readyCount} /></div>
        <ol ref={navigatorListRef}>
          {navigatorItems.map((item) => {
            const index = itemIndexById.get(item.id) ?? 0
            const issues = questionTypesByType[item.type].validate(item)
            return <li
              key={item.id}
              data-navigator-question-id={item.id}
              className={`${draggedId === item.id ? 'is-dragging' : ''}${dropTargetId === item.id ? ' is-drop-target' : ''}`}
              onDragEnter={() => { if (draggedId && draggedId !== item.id) targetDragItem(item.id) }}
              onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }}
              onDrop={(event) => { event.preventDefault(); dropAt(index, event.dataTransfer.getData('text/plain') || draggedId) }}
            >
              <button
                className="assessment-navigator-drag-handle"
                type="button"
                aria-label={`Drag question ${index + 1} to reorder`}
                title="Drag to reorder. Use arrow keys for keyboard reordering."
                onPointerDown={(event) => {
                  if (event.button !== 0) return
                  event.preventDefault()
                  const row = event.currentTarget.closest('li')
                  startPointerDragging(item.id, event.pointerId, event.clientX, event.clientY, row?.getBoundingClientRect().width ?? 260)
                }}
                onMouseDown={(event) => {
                  if (event.button !== 0 || pointerDragRef.current) return
                  event.preventDefault()
                  const row = event.currentTarget.closest('li')
                  startPointerDragging(item.id, -1, event.clientX, event.clientY, row?.getBoundingClientRect().width ?? 260)
                }}
                onPointerCancel={stopDragging}
                onKeyDown={(event) => {
                if (event.key === 'ArrowUp') { event.preventDefault(); moveItem(index, index - 1) }
                if (event.key === 'ArrowDown') { event.preventDefault(); moveItem(index, index + 1) }
                }}
              ><DotsSixVertical aria-hidden="true" /></button>
              <button type="button" className={`assessment-navigator-link${activeId === item.id ? ' active' : ''}`} aria-current={activeId === item.id ? 'true' : undefined} aria-label={`Go to question ${index + 1}: ${item.prompt || 'Untitled question'}`} onClick={() => focusItem(item.id)}>
                <span>{index + 1}</span>
                <span><strong>{item.prompt || 'Untitled question'}</strong><small><span>{questionTypesByType[item.type].label}</span>{item.required ? <span className="assessment-required-badge">Required</span> : null}{questionTypesByType[item.type].supportsScoring ? <span>{item.points || 0} pt</span> : null}</small></span>
                {issues.length ? <i aria-label={`${issues.length} validation ${issues.length === 1 ? 'issue' : 'issues'}`}>{issues.length}</i> : null}
              </button>
            </li>
          })}
        </ol>
        {navigatorItems.length === 0 ? <p>No matching questions.</p> : null}
      </aside>

      <section className="assessment-question-canvas" aria-label="Questions">
      {items.length === 0 ? <div className="assessment-empty assessment-empty--canvas"><h2>Start with a question</h2><p>Choose a type and build the form in one continuous canvas.</p><button className="assessment-primary" type="button" onClick={() => setInsertAt(0)}><Plus /> Add question</button></div> : null}
      {items.map((item, index) => {
        const expanded = expandedIds.has(item.id)
        const issues = questionTypesByType[item.type].validate(item)
        return <div
          className={`assessment-canvas-item${draggedId === item.id ? ' is-dragging' : ''}${dropTargetId === item.id ? ' is-drop-target' : ''}`}
          key={item.id}
          onDragEnter={() => { if (draggedId && draggedId !== item.id) targetDragItem(item.id) }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }}
          onDrop={(event) => { event.preventDefault(); dropAt(index, event.dataTransfer.getData('text/plain') || draggedId) }}
        >
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
                title="Drag to reorder. Keyboard: Alt + arrow keys."
                onDragStart={(event) => startDragging(item.id, event.dataTransfer)}
                onDragEnd={stopDragging}
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
                {item.required ? <span className="assessment-required-badge">Required</span> : null}
                {questionTypesByType[item.type].supportsScoring ? <span>{item.points || 0} pt</span> : null}
                {issues.length ? <span className="assessment-validation-badge">{issues.length} issue{issues.length === 1 ? '' : 's'}</span> : null}
              </span>
              <details className="assessment-question-menu">
                <summary aria-label={`Question ${index + 1} actions`}>•••</summary>
                <div>
                  <button type="button" disabled={index === 0} onClick={() => moveItem(index, index - 1)}><ArrowUp /> Move up</button>
                  <button type="button" disabled={index === items.length - 1} onClick={() => moveItem(index, index + 1)}><ArrowDown /> Move down</button>
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
      {items.length === 0 && insertAt === 0 ? <TypePicker onClose={() => setInsertAt(null)} onSelect={(type) => insertItem(type, 0)} /> : null}
      </section>
    </div>

    <button className="assessment-mobile-add" type="button" aria-label="Add question" onClick={() => setInsertAt(items.length)}><Plus aria-hidden="true" /></button>
    <p className="visually-hidden" aria-live="polite">{reorderMessage}</p>
    {dragVisual ? (() => { const item = items.find((candidate) => candidate.id === dragVisual.itemId); const index = item ? (itemIndexById.get(item.id) ?? 0) : 0; return item ? createPortal(<div ref={dragPreviewRef} className="assessment-drag-preview" aria-hidden="true" style={{ width: dragVisual.width, transform: `translate3d(${dragVisual.x + 14}px, ${dragVisual.y - 28}px, 0) rotate(.35deg) scale(1.015)` }}><DotsSixVertical /><span>{index + 1}</span><strong>{item.prompt || 'Untitled question'}</strong></div>, globalThis.document.body) : null })() : null}

    {deleted ? <div className="assessment-undo-toast" role="status"><span>Question deleted</span><button type="button" onClick={undoDelete}>Undo</button><button type="button" aria-label="Dismiss" onClick={() => setDeleted(null)}><X /></button></div> : null}

  </main>
}

function InsertControl({ open, onOpen, onClose, onSelect }: { open: boolean; onOpen: () => void; onClose: () => void; onSelect: (type: AssessmentItemType) => void }) {
  return <div className={`assessment-insert-control${open ? ' assessment-insert-control--open' : ''}`}>
    {!open ? <button type="button" aria-label="Insert question here" onClick={onOpen}><Plus aria-hidden="true" /><span>Add question here</span></button> : <TypePicker onClose={onClose} onSelect={onSelect} />}
  </div>
}

// Question editor intentionally remains exported for the v2 section canvas.
function TypePicker({ onClose, onSelect }: { onClose: () => void; onSelect: (type: AssessmentItemType) => void }) {
  return <div className="assessment-type-picker" role="dialog" aria-label="Choose question type">
    <header><strong>Add item</strong><button type="button" aria-label="Close type picker" onClick={onClose}><X /></button></header>
    <div>{questionTypeGroups.map((group) => <section key={group}><h3>{group}</h3>{questionTypeRegistry.filter((definition) => definition.group === group).map((definition) => <button key={definition.type} type="button" aria-label={`Add ${definition.label.toLowerCase()}`} onClick={() => onSelect(definition.type)}><Plus aria-hidden="true" />{definition.label}</button>)}</section>)}</div>
  </div>
}
export function QuestionEditor({ item, slides, setSlides, updateItem, promptRef, routingTargets = [] }: { item: AssessmentItem; slides: EligibleAssessmentSlide[]; setSlides: (slides: EligibleAssessmentSlide[]) => void; updateItem: (itemId: string, update: (item: AssessmentItem) => AssessmentItem) => void; promptRef: (node: HTMLTextAreaElement | null) => void; routingTargets?: AssessmentSection[] }) {
  const supportsScoring = questionTypesByType[item.type].supportsScoring
  const selectedIds = (item.answerKey?.optionIds as string[] | undefined) ?? []

  function change(update: (current: AssessmentItem) => AssessmentItem) {
    updateItem(item.id, update)
  }

  function moveOption(index: number, direction: -1 | 1) {
    change((current) => {
      const options = [...(current.options ?? [])]
      const destination = index + direction
      if (destination < 0 || destination >= options.length) return current
      const [moving] = options.splice(index, 1)
      options.splice(destination, 0, moving)
      return { ...current, options }
    })
  }

  function deleteOption(index: number) {
    change((current) => {
      const options = [...(current.options ?? [])]
      const [removed] = options.splice(index, 1)
      const removedId = removed ? optionId(removed, index) : ''
      const optionIds = ((current.answerKey?.optionIds as string[] | undefined) ?? [])
        .filter((id) => id !== removedId)
      const routing = current.routing ? {
        ...current.routing,
        rules: current.routing.rules?.filter((rule) => rule.when.optionId !== removedId),
      } : undefined
      return { ...current, options, routing, answerKey: { ...current.answerKey, optionIds } }
    })
  }

  function duplicateOption(index: number) {
    change((current) => {
      const options = [...(current.options ?? [])]
      const source = options[index]
      if (!source) return current
      options.splice(index + 1, 0, { id: newId(), label: `${optionLabel(source)} copy` })
      return { ...current, options }
    })
  }

  return <div className="assessment-question-editor" data-testid="question-editor">
    <section className="assessment-editor-section assessment-editor-section--prompt">
      <label className="assessment-question-prompt">Prompt<textarea ref={promptRef} maxLength={2000} value={item.prompt} onChange={(event) => change((current) => ({ ...current, prompt: event.target.value }))} /></label>
      <label>Help text<input maxLength={1000} value={item.helpText ?? ''} placeholder="Optional learner guidance" onChange={(event) => change((current) => ({ ...current, helpText: event.target.value }))} /></label>
    </section>

    {item.options ? <section className="assessment-editor-section assessment-editor-section--answers" aria-label="Answer options">
      <header className="assessment-editor-section-heading"><h3>Answer choices</h3><p>Stable option IDs preserve keys, routing, and deterministic shuffle.</p></header>
      <div className="assessment-option-list">{item.options.map((option, optionIndex) => {
        const id = optionId(option, optionIndex)
        return <div key={id} className="assessment-option assessment-option--editable">
          <button type="button" className="assessment-option-drag" aria-label={`Reorder option ${optionIndex + 1}`} onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveOption(optionIndex, -1); if (event.key === 'ArrowDown') moveOption(optionIndex, 1) }}><DotsSixVertical /></button>
          <input aria-label={`Correct option ${optionIndex + 1}`} type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={`key-${item.id}`} checked={selectedIds.includes(id)} onChange={() => change((current) => { const selected = (current.answerKey?.optionIds as string[] | undefined) ?? []; const optionIds = current.type === 'checkboxes' ? (selected.includes(id) ? selected.filter((selectedId) => selectedId !== id) : [...selected, id]) : [id]; return { ...current, answerKey: { ...current.answerKey, optionIds } } })} />
          <input aria-label={`Option ${optionIndex + 1}`} value={optionLabel(option)} maxLength={1000} onChange={(event) => change((current) => ({ ...current, options: current.options?.map((candidate, candidateIndex) => candidateIndex === optionIndex ? { id, label: event.target.value } : candidate) }))} />
          <button type="button" aria-label={`Move option ${optionIndex + 1} up`} disabled={optionIndex === 0} onClick={() => moveOption(optionIndex, -1)}><ArrowUp /></button>
          <button type="button" aria-label={`Move option ${optionIndex + 1} down`} disabled={optionIndex === item.options!.length - 1} onClick={() => moveOption(optionIndex, 1)}><ArrowDown /></button>
          <button type="button" aria-label={`Duplicate option ${optionIndex + 1}`} onClick={() => duplicateOption(optionIndex)}><Copy /></button>
          <button type="button" aria-label={`Delete option ${optionIndex + 1}`} disabled={item.options!.length <= 2} onClick={() => deleteOption(optionIndex)}><Trash /></button>
        </div>
      })}</div>
      <div className="assessment-option-tools">
        <button className="assessment-secondary-action" type="button" disabled={item.options.length >= 10} onClick={() => change((current) => ({ ...current, options: [...(current.options ?? []), { id: newId(), label: `Option ${(current.options?.length ?? 0) + 1}` }] }))}><Plus /> Add option</button>
        <details><summary>Paste options</summary><label>One option per line<textarea onPaste={(event) => { event.preventDefault(); const labels = event.clipboardData.getData('text').split(/\r?\n/).map((value) => value.trim()).filter(Boolean).slice(0, 10); change((current) => ({ ...current, options: labels.map((label) => ({ id: newId(), label })), routing: undefined, answerKey: { ...current.answerKey, optionIds: [] } })) }} /></label></details>
        <label><input type="checkbox" checked={item.allowOther ?? false} onChange={(event) => change((current) => ({ ...current, allowOther: event.target.checked }))} /> Allow Other</label>
        <label><input type="checkbox" checked={item.shuffleOptions ?? false} onChange={(event) => change((current) => ({ ...current, shuffleOptions: event.target.checked }))} /> Shuffle choices</label>
      </div>
    </section> : null}

    {item.type === 'rating' ? <section className="assessment-editor-section" aria-label="Rating settings">
      <header className="assessment-editor-section-heading"><h3>Rating scale</h3><p>Ratings always begin at 1 and end from 3 through 10.</p></header>
      <label>Maximum<select value={item.rating?.max ?? 5} onChange={(event) => change((current) => ({ ...current, rating: { min: 1, max: Number(event.target.value) as NonNullable<AssessmentItem['rating']>['max'], style: current.rating?.style ?? 'numbers' } }))}>{[3, 4, 5, 6, 7, 8, 9, 10].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Style<select value={item.rating?.style ?? 'numbers'} onChange={(event) => change((current) => ({ ...current, rating: { min: 1, max: current.rating?.max ?? 5, style: event.target.value as NonNullable<AssessmentItem['rating']>['style'] } }))}><option value="numbers">Numbers</option><option value="stars">Stars</option><option value="hearts">Hearts</option><option value="thumbs-up">Thumbs up</option></select></label>
      <div className="assessment-rating-preview" aria-label="Rating preview">{Array.from({ length: item.rating?.max ?? 5 }, (_, index) => <span key={index}>{item.rating?.style === 'stars' ? '★' : item.rating?.style === 'hearts' ? '♥' : item.rating?.style === 'thumbs-up' ? '👍' : index + 1}</span>)}</div>
    </section> : null}

    {item.type === 'diagnostic-field' ? <details className="assessment-progressive-section"><summary>Answer key & diagnostic regions</summary><div className="assessment-diagnostic"><p>Choose a privacy-passed static-DZI slide, then mark accepted points or rectangles.</p><button type="button" onClick={() => void listEligibleAssessmentSlides().then((result) => setSlides(result.items))}>Choose slide</button>{slides.length ? <select aria-label="Eligible slide" value={item.slideId ?? ''} onChange={(event) => change((current) => ({ ...current, slideId: event.target.value, answerKey: { ...current.answerKey, regions: [] } }))}><option value="">Select a slide</option>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select> : null}{item.slideId && slides.find((slide) => slide.id === item.slideId) ? <AssessmentDiagnosticField label="Accepted diagnostic regions" tileSource={slides.find((slide) => slide.id === item.slideId)!.tileSource} selections={(item.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []} multiple onCommit={(selection) => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: [...((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []), selection] } }))} onClear={() => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: [] } }))} /> : null}<label>Accepted diagnoses<input value={((item.answerKey?.diagnoses as string[] | undefined) ?? []).join(', ')} onChange={(event) => change((current) => ({ ...current, answerKey: { ...current.answerKey, diagnoses: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label></div></details> : null}
    {item.type === 'short-answer' ? <details className="assessment-progressive-section"><summary>Answer key</summary><label>Accepted answers<input value={((item.answerKey?.variants as string[] | undefined) ?? []).join(', ')} onChange={(event) => change((current) => ({ ...current, answerKey: { ...current.answerKey, variants: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) } }))} /></label></details> : null}

    <details className="assessment-progressive-section"><summary>Media & education metadata</summary>
      <button type="button" onClick={() => void listEligibleAssessmentSlides().then((result) => setSlides(result.items))}>Load slide thumbnails</button>
      {slides.length ? <label>Question thumbnail<select value={item.media?.slideId ?? ''} onChange={(event) => change((current) => ({ ...current, media: event.target.value ? { kind: 'slide-thumbnail', slideId: event.target.value } : undefined }))}><option value="">No media</option>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select></label> : null}
      <label>Learning objective<input value={item.education?.objective ?? ''} onChange={(event) => change((current) => ({ ...current, education: { ...current.education, objective: event.target.value } }))} /></label>
      <label>Competency<input value={item.education?.competency ?? ''} onChange={(event) => change((current) => ({ ...current, education: { ...current.education, competency: event.target.value } }))} /></label>
      <label>Teacher notes<textarea maxLength={2000} value={item.teacherNotes ?? ''} onChange={(event) => change((current) => ({ ...current, teacherNotes: event.target.value }))} /></label>
    </details>

    {routingTargets.length ? <details className="assessment-progressive-section"><summary>Section routing</summary>
      <p>Routing is evaluated when the learner exits this section. Leave a destination blank to continue normally.</p>
      {item.options?.map((option, index) => { const id = optionId(option, index); const rule = item.routing?.rules?.find((candidate) => candidate.when.optionId === id); return <label key={id}>If “{optionLabel(option)}” is selected<select value={rule?.goToSectionId ?? ''} onChange={(event) => change((current) => { const rules = (current.routing?.rules ?? []).filter((candidate) => candidate.when.optionId !== id); if (event.target.value) rules.push({ when: { operator: 'equals', optionId: id }, goToSectionId: event.target.value }); return { ...current, routing: rules.length || current.routing?.defaultSectionId ? { ...current.routing, rules } : undefined } })}><option value="">Continue normally</option>{routingTargets.map((section) => <option key={section.id} value={section.id}>{section.title || 'Untitled section'}</option>)}</select></label> })}
      <label>Default destination<select value={item.routing?.defaultSectionId ?? ''} onChange={(event) => change((current) => { const defaultSectionId = event.target.value || undefined; const rules = current.routing?.rules ?? []; return { ...current, routing: defaultSectionId || rules.length ? { ...current.routing, rules, defaultSectionId } : undefined } })}><option value="">Next section</option>{routingTargets.map((section) => <option key={section.id} value={section.id}>{section.title || 'Untitled section'}</option>)}</select></label>
    </details> : null}

    {supportsScoring ? <details className="assessment-progressive-section"><summary>Feedback, validation & scoring</summary>
      <label>Correct feedback<textarea maxLength={4000} value={item.feedback?.correct ?? ''} onChange={(event) => change((current) => ({ ...current, feedback: { ...current.feedback, correct: event.target.value } }))} /></label>
      <label>Incorrect feedback<textarea maxLength={4000} value={item.feedback?.incorrect ?? ''} onChange={(event) => change((current) => ({ ...current, feedback: { ...current.feedback, incorrect: event.target.value } }))} /></label>
      <label>Validation message<input maxLength={500} value={item.validation?.message ?? ''} onChange={(event) => change((current) => ({ ...current, validation: { ...current.validation, message: event.target.value } }))} /></label>
      {item.type === 'short-answer' || item.type === 'paragraph' ? <><label>Minimum characters<input type="number" min="0" max="4000" value={item.validation?.minimumLength ?? ''} onChange={(event) => change((current) => ({ ...current, validation: { ...current.validation, minimumLength: event.target.value ? Number(event.target.value) : undefined } }))} /></label><label>Maximum characters<input type="number" min="1" max="4000" value={item.validation?.maximumLength ?? ''} onChange={(event) => change((current) => ({ ...current, validation: { ...current.validation, maximumLength: event.target.value ? Number(event.target.value) : undefined } }))} /></label></> : null}
      {item.type === 'checkboxes' ? <label><input type="checkbox" checked={item.scoring?.partialCredit ?? false} onChange={(event) => change((current) => ({ ...current, scoring: { ...current.scoring, partialCredit: event.target.checked } }))} /> Bounded partial credit</label> : null}
    </details> : null}
    {supportsScoring ? <footer className="assessment-question-footer"><label>Required <input type="checkbox" checked={item.required ?? false} onChange={(event) => change((current) => ({ ...current, required: event.target.checked }))} /></label><label>Points <input value={item.points ?? '0'} onChange={(event) => change((current) => ({ ...current, points: event.target.value }))} inputMode="decimal" /></label></footer> : null}
  </div>
}
