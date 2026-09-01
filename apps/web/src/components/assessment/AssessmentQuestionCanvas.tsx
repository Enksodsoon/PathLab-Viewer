import { ArrowDown, ArrowUp, ArrowsInLineVertical, ArrowsOutLineVertical, CaretDown, Check, Copy, DotsSixVertical, Eye, Image, MagnifyingGlass, Plus, SpinnerGap, Trash, UploadSimple, X } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { listEligibleAssessmentSlides } from '../../assessment/api'
import { parseAssessmentChoices } from '../../assessment/choiceParser'
import { authorableQuestionTypeRegistry, questionTypeGroups, questionTypeRegistry, questionTypesByType } from '../../assessment/questionTypes'
import { assessmentItems, assessmentQuestionMedia, replaceAssessmentItems, withAssessmentQuestionMedia, type AssessmentDocument, type AssessmentItem, type AssessmentItemType, type AssessmentQuestionMedia, type AssessmentSection, type DiagnosticSelection, type EligibleAssessmentSlide } from '../../assessment/types'
import { AssessmentDiagnosticField } from '../AssessmentDiagnosticField'
import { AutoGrowTextarea } from './AutoGrowTextarea'

interface CanvasProps {
  document: AssessmentDocument
  draftId?: string
  mediaScopeLabel?: string
  onDocumentChange: (update: (document: AssessmentDocument) => AssessmentDocument) => void
  onImport: () => void
  onPreview: () => void
}

type NavigatorRequiredFilter = 'all' | 'required' | 'optional'
type AssessmentOption = NonNullable<AssessmentItem['options']>[number] | string
type DragVisual = { itemId: string; x: number; y: number; width: number }
const MAX_QUESTION_MEDIA = 10
const MAX_OPTION_MEDIA = 3

function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `assessment-${Date.now()}-${Math.random()}`
}

function optionId(option: AssessmentOption, index: number) {
  return typeof option === 'string' ? `legacy-option-${index}` : option.id
}

function optionLabel(option: AssessmentOption) {
  return typeof option === 'string' ? option : option.label
}

function commaSeparatedValues(value: string) {
  return value.split(',').map((entry) => entry.trim()).filter(Boolean)
}

function escapedPattern(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function KeywordMatchPreview({ response, keywords }: { response: string; keywords: string[] }) {
  const usableKeywords = keywords.map((keyword) => keyword.trim()).filter(Boolean)
  if (!response.trim()) return <p className="assessment-keyword-empty">Enter a sample learner response to test keyword recognition.</p>
  if (!usableKeywords.length) return <p className="assessment-keyword-empty">Add keywords above to preview matching.</p>
  const pattern = new RegExp(`(${usableKeywords.sort((left, right) => right.length - left.length).map(escapedPattern).join('|')})`, 'giu')
  const matched = new Set(response.match(pattern)?.map((value) => value.toLocaleLowerCase()) ?? [])
  return <div className="assessment-keyword-result" aria-live="polite">
    <p>{response.split(pattern).map((part, index) => matched.has(part.toLocaleLowerCase()) ? <mark key={`${part}-${index}`}>{part}</mark> : <span key={`${part}-${index}`}>{part}</span>)}</p>
    <small>{usableKeywords.filter((keyword) => matched.has(keyword.toLocaleLowerCase())).length} of {usableKeywords.length} keywords matched</small>
  </div>
}

function optionMediaCollection(option: AssessmentOption) {
  if (typeof option === 'string') return []
  return [...(option.media ? [option.media] : []), ...(option.mediaItems ?? [])].slice(0, MAX_OPTION_MEDIA)
}

function withOptionMedia(option: AssessmentOption, media: AssessmentQuestionMedia[]) {
  const normalized = media.slice(0, MAX_OPTION_MEDIA)
  return {
    ...(typeof option === 'string' ? { id: newId(), label: option } : option),
    media: normalized[0],
    mediaItems: normalized.length > 1 ? normalized.slice(1) : undefined,
  }
}

export function AssessmentQuestionCanvas({ document, draftId = '', mediaScopeLabel = 'this lesson', onDocumentChange, onImport, onPreview }: CanvasProps) {
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
  const [mediaRequest, setMediaRequest] = useState<{ itemId: string; nonce: number }>({ itemId: '', nonce: 0 })
  const initializedRef = useRef(items.length > 0)
  const cardRefs = useRef(new Map<string, HTMLElement>())
  const promptRefs = useRef(new Map<string, HTMLTextAreaElement>())
  const navigatorListRef = useRef<HTMLOListElement>(null)
  const dragPreviewRef = useRef<HTMLDivElement>(null)
  const pointerDragRef = useRef<{ itemId: string; pointerId: number } | null>(null)
  const dropTargetIdRef = useRef('')
  const pointerCleanupRef = useRef<() => void>(() => undefined)
  const mediaSlidesRequestRef = useRef('')

  useEffect(() => {
    if (initializedRef.current || !items.length) return
    initializedRef.current = true
    setExpandedIds(new Set([items[0].id]))
    setActiveId(items[0].id)
  }, [items])

  useEffect(() => () => pointerCleanupRef.current(), [])

  useEffect(() => {
    const attachedSlideIds = items.flatMap((item) => assessmentQuestionMedia(item).flatMap((media) => media.kind === 'slide-thumbnail' && media.slideId ? [media.slideId] : []))
    if (!attachedSlideIds.length || attachedSlideIds.every((slideId) => slides.some((slide) => slide.id === slideId))) return
    const requestKey = `${draftId}:${attachedSlideIds.sort().join(',')}`
    if (mediaSlidesRequestRef.current === requestKey) return
    mediaSlidesRequestRef.current = requestKey
    void listEligibleAssessmentSlides('', draftId)
      .then((result) => setSlides(result.items))
      .catch(() => { mediaSlidesRequestRef.current = '' })
  }, [draftId, items, slides])

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
      options: item.options?.map((option, optionIndex) => ({ ...structuredClone(typeof option === 'string' ? {} : option), id: optionMap.get(optionId(option, optionIndex))!, label: optionLabel(option) })),
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
                <button type="button" className={`assessment-header-media${assessmentQuestionMedia(item).length ? ' is-active' : ''}`} aria-label={`${assessmentQuestionMedia(item).length ? 'Edit' : 'Add'} media for question ${index + 1}`} onClick={() => { setExpandedIds((current) => new Set(current).add(item.id)); setMediaRequest({ itemId: item.id, nonce: Date.now() }) }}><Image aria-hidden="true" />{assessmentQuestionMedia(item).length ? <b>{assessmentQuestionMedia(item).length}</b> : null}</button>
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
            {expanded ? <QuestionEditor item={item} slides={slides} setSlides={setSlides} updateItem={updateItem} promptRef={(node) => { if (node) promptRefs.current.set(item.id, node); else promptRefs.current.delete(item.id) }} draftId={draftId} mediaScopeLabel={mediaScopeLabel} mediaDialogRequest={mediaRequest.itemId === item.id ? mediaRequest.nonce : 0} /> : null}
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
    <div>{questionTypeGroups.map((group) => <section key={group}><h3>{group}</h3>{authorableQuestionTypeRegistry.filter((definition) => definition.group === group).map((definition) => <button key={definition.type} type="button" aria-label={`Add ${definition.label.toLowerCase()}`} onClick={() => onSelect(definition.type)}><Plus aria-hidden="true" />{definition.label}</button>)}</section>)}</div>
  </div>
}

function QuestionMediaAuthoringPreview({ media, slide, index }: { media: AssessmentQuestionMedia; slide?: EligibleAssessmentSlide; index: number }) {
  const source = media.capturedImage?.assetPath ?? (media.kind === 'uploaded-image' ? media.assetPath : media.assetPath ?? slide?.thumbnail)
  const capture = media.capture
  const scale = media.capturedImage ? 1 : capture ? Math.min(1 / capture.width, 1 / capture.height) : 1
  const origin = media.capturedImage ? '50% 50%' : capture ? `${(capture.x + capture.width / 2) * 100}% ${(capture.y + capture.height / 2) * 100}%` : '50% 50%'
  return <figure className="assessment-authoring-media-preview" aria-label="Question media preview">
    <div>{source ? <img src={source} alt="" style={{ transform: `scale(${scale})`, transformOrigin: origin }} /> : <span><Image aria-hidden="true" />Media selected</span>}{source && capture ? media.marks?.map((mark, markIndex) => {
      if (mark.kind === 'point') return <i key={markIndex} className="assessment-authoring-media-point" style={{ left: `${((mark.x - capture.x) / capture.width) * 100}%`, top: `${((mark.y - capture.y) / capture.height) * 100}%` }}>{mark.label ? <em>{mark.label}</em> : null}</i>
      if (mark.kind === 'rectangle') return <i key={markIndex} className="assessment-authoring-media-rectangle" style={{ left: `${((mark.x - capture.x) / capture.width) * 100}%`, top: `${((mark.y - capture.y) / capture.height) * 100}%`, width: `${(mark.width / capture.width) * 100}%`, height: `${(mark.height / capture.height) * 100}%` }}>{mark.label ? <em>{mark.label}</em> : null}</i>
      const first = mark.points[0]
      return <i key={markIndex} className="assessment-authoring-media-freehand"><svg viewBox={`0 0 ${capture.width} ${capture.height}`} preserveAspectRatio="none" aria-hidden="true"><polyline points={mark.points.map((point) => `${point.x - capture.x},${point.y - capture.y}`).join(' ')} /></svg>{mark.label && first ? <em style={{ left: `${((first.x - capture.x) / capture.width) * 100}%`, top: `${((first.y - capture.y) / capture.height) * 100}%` }}>{mark.label}</em> : null}</i>
    }) : null}</div>
    <figcaption><small>Media {index + 1}</small><strong>{slide?.displayName ?? media.fileName ?? 'Question image'}</strong>{media.alt ? <span>{media.alt}</span> : null}</figcaption>
  </figure>
}

export function QuestionEditor({ item, slides, setSlides, updateItem, promptRef, draftId = '', mediaScopeLabel = 'this lesson', mediaDialogRequest = 0 }: { item: AssessmentItem; slides: EligibleAssessmentSlide[]; setSlides: (slides: EligibleAssessmentSlide[]) => void; updateItem: (itemId: string, update: (item: AssessmentItem) => AssessmentItem) => void; promptRef: (node: HTMLTextAreaElement | null) => void; routingTargets?: AssessmentSection[]; draftId?: string; mediaScopeLabel?: string; mediaDialogRequest?: number }) {
  const supportsScoring = questionTypesByType[item.type].supportsScoring
  const supportsFeedback = supportsScoring && item.type !== 'rating'
  const selectedIds = (item.answerKey?.optionIds as string[] | undefined) ?? []
  const savedKeywordText = ((item.answerKey?.keywords as string[] | undefined) ?? []).join(', ')
  const [draggedOptionIndex, setDraggedOptionIndex] = useState<number | null>(null)
  const [optionDropTarget, setOptionDropTarget] = useState<{ index: number; after: boolean } | null>(null)
  const [mediaError, setMediaError] = useState('')
  const [mediaDialogTarget, setMediaDialogTarget] = useState<'question' | number | null>(null)
  const [mediaLoading, setMediaLoading] = useState(false)
  const [mediaSourceTab, setMediaSourceTab] = useState<'slides' | 'upload'>(() => item.media?.kind === 'uploaded-image' ? 'upload' : 'slides')
  const [activeMediaIndex, setActiveMediaIndex] = useState(0)
  const [diagnosticLoading, setDiagnosticLoading] = useState(false)
  const [diagnosticError, setDiagnosticError] = useState('')
  const [keywordPreview, setKeywordPreview] = useState('')
  const [keywordDraft, setKeywordDraft] = useState(() => savedKeywordText)
  const handledMediaDialogRequest = useRef(0)
  const mediaCollection = assessmentQuestionMedia(item)
  const optionMediaDialogIndex = typeof mediaDialogTarget === 'number' ? mediaDialogTarget : null
  const dialogMediaCollection = optionMediaDialogIndex !== null && item.options?.[optionMediaDialogIndex]
    ? optionMediaCollection(item.options[optionMediaDialogIndex])
    : mediaCollection
  const dialogMediaLimit = optionMediaDialogIndex === null ? MAX_QUESTION_MEDIA : MAX_OPTION_MEDIA
  const dialogMediaOwner = optionMediaDialogIndex === null ? 'question' : 'answer choice'
  const dialogMediaOwnerWithArticle = optionMediaDialogIndex === null ? 'A question' : 'An answer choice'
  const activeMedia = dialogMediaCollection[Math.min(activeMediaIndex, Math.max(0, dialogMediaCollection.length - 1))]

  useEffect(() => {
    if (mediaDialogTarget === null) return undefined
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMediaDialogTarget(null)
    }
    globalThis.document.addEventListener('keydown', closeOnEscape)
    return () => globalThis.document.removeEventListener('keydown', closeOnEscape)
  }, [mediaDialogTarget])

  useEffect(() => { setMediaDialogTarget(null); setKeywordPreview(''); setKeywordDraft(savedKeywordText); setDiagnosticError('') }, [item.id, savedKeywordText])

  useEffect(() => {
    if (mediaDialogRequest <= 0 || handledMediaDialogRequest.current === mediaDialogRequest) return
    handledMediaDialogRequest.current = mediaDialogRequest
    setMediaDialogTarget('question')
    setActiveMediaIndex(0)
    setMediaError('')
    setMediaSourceTab(activeMedia?.kind === 'uploaded-image' ? 'upload' : 'slides')
    void listEligibleAssessmentSlides('', draftId)
      .then((result) => setSlides(result.items))
      .catch(() => setMediaError('Slides could not be loaded. You can still upload an image.'))
  }, [activeMedia?.kind, draftId, mediaDialogRequest, setSlides])

  useEffect(() => {
    if (activeMediaIndex >= dialogMediaCollection.length && dialogMediaCollection.length > 0) setActiveMediaIndex(dialogMediaCollection.length - 1)
  }, [activeMediaIndex, dialogMediaCollection.length])

  function change(update: (current: AssessmentItem) => AssessmentItem) {
    updateItem(item.id, update)
  }

  async function loadDiagnosticSlides() {
    setDiagnosticLoading(true)
    setDiagnosticError('')
    try {
      const result = await listEligibleAssessmentSlides('', draftId)
      setSlides(result.items)
      if (!result.items.length) setDiagnosticError(`No privacy-passed slides are available in ${mediaScopeLabel}.`)
    } catch {
      setDiagnosticError('Slides could not be loaded. Retry after checking the lesson slide library.')
    } finally {
      setDiagnosticLoading(false)
    }
  }

  function moveOption(index: number, direction: -1 | 1) {
    moveOptionTo(index, index + direction)
  }

  function moveOptionTo(index: number, destination: number) {
    change((current) => {
      const options = [...(current.options ?? [])]
      if (destination < 0 || destination >= options.length) return current
      const [moving] = options.splice(index, 1)
      options.splice(destination, 0, moving)
      return { ...current, options }
    })
    setDraggedOptionIndex(null)
    setOptionDropTarget(null)
  }

  function moveOptionToInsertion(index: number, insertion: number) {
    change((current) => {
      const options = [...(current.options ?? [])]
      if (index < 0 || index >= options.length) return current
      const [moving] = options.splice(index, 1)
      const adjustedInsertion = index < insertion ? insertion - 1 : insertion
      options.splice(Math.max(0, Math.min(adjustedInsertion, options.length)), 0, moving)
      return { ...current, options }
    })
    setDraggedOptionIndex(null)
    setOptionDropTarget(null)
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
      options.splice(index + 1, 0, { ...structuredClone(typeof source === 'string' ? {} : source), id: newId(), label: `${optionLabel(source)} copy` })
      return { ...current, options }
    })
  }

  function pasteOptionsAt(index: number, text: string) {
    const labels = parseAssessmentChoices(text)
    if (labels.length < 2) return false
    change((current) => {
      const options = [...(current.options ?? [])]
      const existing = options[index]
      const replacement = labels.map((label, labelIndex) => ({
        ...(labelIndex === 0 && existing && typeof existing !== 'string' ? existing : {}),
        id: labelIndex === 0 && existing ? optionId(existing, index) : newId(),
        label,
      }))
      options.splice(index, 1, ...replacement)
      return { ...current, options: options.slice(0, 10) }
    })
    return true
  }

  function updateActiveMedia(update: (media: AssessmentQuestionMedia) => AssessmentQuestionMedia) {
    updateDialogMediaCollection((media) => {
      if (!media[activeMediaIndex]) return media
      const next = [...media]
      next[activeMediaIndex] = update(next[activeMediaIndex])
      return next
    })
  }

  function removeMediaAt(index: number) {
    updateDialogMediaCollection((media) => media.filter((_, mediaIndex) => mediaIndex !== index))
    setActiveMediaIndex((current) => Math.max(0, current > index ? current - 1 : Math.min(current, dialogMediaCollection.length - 2)))
    setMediaError('')
  }

  function removeSlideMedia(slideId: string) {
    updateDialogMediaCollection((media) => media.filter((entry) => entry.slideId !== slideId))
    setActiveMediaIndex(0)
    setMediaError('')
  }

  async function prepareQuestionImage(file: File): Promise<AssessmentQuestionMedia> {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 100 * 1024 * 1024) {
      throw new Error('IMAGE_INVALID')
    }
    if (file.size <= 475 * 1024) {
      const assetPath = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('IMAGE_READ_FAILED'))
        reader.onerror = () => reject(new Error('IMAGE_READ_FAILED'))
        reader.readAsDataURL(file)
      })
      return { kind: 'uploaded-image', assetPath, fileName: file.name, alt: '' }
    }
      const bitmap = await createImageBitmap(file)
      let width = bitmap.width
      let height = bitmap.height
      const longest = Math.max(width, height)
      if (longest > 2400) {
        const ratio = 2400 / longest
        width = Math.max(1, Math.round(width * ratio))
        height = Math.max(1, Math.round(height * ratio))
      }
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d', { alpha: false })
      if (!context) throw new Error('IMAGE_PROCESSING_FAILED')
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, width, height)
      context.drawImage(bitmap, 0, 0, width, height)
      let quality = 0.88
      let blob: Blob | null = null
      do {
        blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', quality))
        quality -= 0.08
      } while (blob && blob.size > 475 * 1024 && quality >= 0.48)
      while (blob && blob.size > 475 * 1024 && Math.max(width, height) > 720) {
        width = Math.max(1, Math.round(width * 0.78))
        height = Math.max(1, Math.round(height * 0.78))
        canvas.width = width
        canvas.height = height
        const resizedContext = canvas.getContext('2d', { alpha: false })
        if (!resizedContext) throw new Error('IMAGE_PROCESSING_FAILED')
        resizedContext.fillStyle = '#ffffff'
        resizedContext.fillRect(0, 0, width, height)
        resizedContext.drawImage(bitmap, 0, 0, width, height)
        blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', 0.68))
      }
      bitmap.close()
      if (!blob || blob.size > 475 * 1024) throw new Error('IMAGE_PROCESSING_FAILED')
      const assetPath = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('IMAGE_READ_FAILED'))
        reader.onerror = () => reject(new Error('IMAGE_READ_FAILED'))
        reader.readAsDataURL(blob)
      })
      return { kind: 'uploaded-image', assetPath, fileName: file.name, alt: '' }
  }

  async function uploadMediaImages(files: FileList | null) {
    if (!files?.length) return
    const room = dialogMediaLimit - dialogMediaCollection.length
    if (room <= 0) {
      setMediaError(`${dialogMediaOwnerWithArticle} can contain up to ${dialogMediaLimit} media items.`)
      return
    }
    setMediaLoading(true)
    setMediaError('')
    try {
      const selectedFiles = Array.from(files).slice(0, room)
      const prepared = await Promise.all(selectedFiles.map(prepareQuestionImage))
      const startIndex = dialogMediaCollection.length
      updateDialogMediaCollection((current) => [...current, ...prepared].slice(0, dialogMediaLimit))
      setActiveMediaIndex(startIndex)
      if (files.length > room) setMediaError(`Added ${room} images. ${dialogMediaOwnerWithArticle} can contain up to ${dialogMediaLimit} media items.`)
    } catch {
      setMediaError(isOptionMediaDialog ? 'One or more answer images could not be prepared. Use JPG, PNG, or WebP files up to 100 MB each.' : 'One or more images could not be prepared. Use JPG, PNG, or WebP files up to 100 MB each.')
    } finally {
      setMediaLoading(false)
    }
  }

  function updateOptionMediaCollection(index: number, update: (media: AssessmentQuestionMedia[]) => AssessmentQuestionMedia[]) {
    change((current) => ({
      ...current,
      options: current.options?.map((candidate, candidateIndex) => candidateIndex === index
        ? withOptionMedia(candidate, update(optionMediaCollection(candidate)))
        : candidate),
    }))
  }

  function updateDialogMediaCollection(update: (media: AssessmentQuestionMedia[]) => AssessmentQuestionMedia[]) {
    if (optionMediaDialogIndex !== null) {
      updateOptionMediaCollection(optionMediaDialogIndex, (media) => update(media).slice(0, MAX_OPTION_MEDIA))
      return
    }
    change((current) => withAssessmentQuestionMedia(current, update(assessmentQuestionMedia(current)).slice(0, MAX_QUESTION_MEDIA)))
  }

  function openOptionMediaDialog(index: number) {
    setMediaDialogTarget(index)
    setActiveMediaIndex(0)
    setMediaError('')
    const firstMedia = item.options?.[index] ? optionMediaCollection(item.options[index])[0] : undefined
    setMediaSourceTab(firstMedia?.kind === 'uploaded-image' ? 'upload' : 'slides')
    void listEligibleAssessmentSlides('', draftId)
      .then((result) => setSlides(result.items))
      .catch(() => setMediaError('Slides could not be loaded. You can still upload an answer image.'))
  }

  const selectedMediaSlide = activeMedia?.kind === 'slide-thumbnail'
    ? slides.find((slide) => slide.id === activeMedia.slideId)
    : undefined
  const isOptionMediaDialog = optionMediaDialogIndex !== null
  const mediaDialogId = `${item.id}-${optionMediaDialogIndex ?? 'question'}`
  const mediaCollectionLabel = isOptionMediaDialog ? 'Answer media' : 'Question media'

  return <div className="assessment-question-editor" data-testid="question-editor">
    <section className="assessment-editor-section assessment-editor-section--prompt">
      <label className="assessment-question-prompt">{item.type === 'information' || item.type === 'section-information' ? 'Description' : 'Question'}<AutoGrowTextarea ref={promptRef} maxLength={2000} value={item.prompt} onChange={(event) => change((current) => ({ ...current, prompt: event.target.value }))} /></label>
      {mediaCollection.length ? <div className="assessment-authoring-media-gallery">{mediaCollection.map((media, index) => <QuestionMediaAuthoringPreview key={`${media.kind}-${media.slideId ?? media.fileName ?? index}-${index}`} media={media} index={index} slide={media.kind === 'slide-thumbnail' ? slides.find((slide) => slide.id === media.slideId) : undefined} />)}</div> : null}
    </section>

    {item.options ? <section className="assessment-editor-section assessment-editor-section--answers" aria-label="Answer options">
      <header className="assessment-editor-section-heading"><h3>Answer choices</h3></header>
      <div className="assessment-option-list">{item.options.map((option, optionIndex) => {
        const id = optionId(option, optionIndex)
        const attachedMedia = optionMediaCollection(option)
        const dropAfter = optionDropTarget?.index === optionIndex && optionDropTarget.after
        return <div key={id} draggable className={`assessment-option assessment-option--editable${draggedOptionIndex === optionIndex ? ' is-dragging' : ''}${optionDropTarget?.index === optionIndex ? ` is-drop-target${dropAfter ? ' is-drop-after' : ''}` : ''}`} onDragStart={(event) => { event.stopPropagation(); setDraggedOptionIndex(optionIndex); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/option', String(optionIndex)) }} onDragEnd={() => { setDraggedOptionIndex(null); setOptionDropTarget(null) }} onDragOver={(event) => { event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = 'move'; const rect = event.currentTarget.getBoundingClientRect(); setOptionDropTarget({ index: optionIndex, after: event.clientY >= rect.top + rect.height / 2 }) }} onDrop={(event) => { event.preventDefault(); event.stopPropagation(); const transferred = event.dataTransfer.getData('text/option'); const source = transferred === '' ? draggedOptionIndex : Number(transferred); if (source !== null && Number.isInteger(source)) { const rect = event.currentTarget.getBoundingClientRect(); const after = event.clientY >= rect.top + rect.height / 2; moveOptionToInsertion(source, optionIndex + (after ? 1 : 0)) } }} onMouseEnter={() => { if (draggedOptionIndex !== null) setOptionDropTarget({ index: optionIndex, after: true }) }} onMouseUp={() => { if (draggedOptionIndex !== null && draggedOptionIndex !== optionIndex) moveOptionTo(draggedOptionIndex, optionIndex) }}>
          <button type="button" className="assessment-option-drag" aria-label={`Reorder option ${optionIndex + 1}`} onMouseDown={(event) => { if (event.button === 0) setDraggedOptionIndex(optionIndex) }} onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveOption(optionIndex, -1); if (event.key === 'ArrowDown') moveOption(optionIndex, 1) }}><DotsSixVertical /></button>
          <input aria-label={`Correct option ${optionIndex + 1}`} type={item.type === 'checkboxes' ? 'checkbox' : 'radio'} name={`key-${item.id}`} checked={selectedIds.includes(id)} onChange={() => change((current) => { const selected = (current.answerKey?.optionIds as string[] | undefined) ?? []; const optionIds = current.type === 'checkboxes' ? (selected.includes(id) ? selected.filter((selectedId) => selectedId !== id) : [...selected, id]) : [id]; return { ...current, answerKey: { ...current.answerKey, optionIds } } })} />
          <div className="assessment-option-content"><input aria-label={`Option ${optionIndex + 1}`} value={optionLabel(option)} maxLength={1000} onPaste={(event) => { if (pasteOptionsAt(optionIndex, event.clipboardData.getData('text'))) event.preventDefault() }} onChange={(event) => change((current) => ({ ...current, options: current.options?.map((candidate, candidateIndex) => candidateIndex === optionIndex ? { ...(typeof candidate === 'string' ? {} : candidate), id, label: event.target.value } : candidate) }))} />{attachedMedia.length ? <span className="assessment-option-media-thumbs">{attachedMedia.map((media, mediaIndex) => { const source = media.capturedImage?.assetPath ?? media.assetPath ?? (media.slideId ? slides.find((slide) => slide.id === media.slideId)?.thumbnail : undefined); return <span className="assessment-option-media-thumb" key={`${media.kind}-${media.slideId ?? media.fileName ?? mediaIndex}`}>{source ? <img src={source} alt={media.alt || ''} /> : <Image aria-hidden="true" />}<small>{media.fileName ?? 'Class slide'}</small></span> })}</span> : null}</div>
          <div className="assessment-option-actions">
            <button type="button" className={attachedMedia.length ? 'has-media' : ''} aria-label={`${attachedMedia.length ? 'Edit' : 'Add'} media for option ${optionIndex + 1}`} title={`${attachedMedia.length ? 'Edit' : 'Add'} answer media`} onClick={() => openOptionMediaDialog(optionIndex)}><Image aria-hidden="true" />{attachedMedia.length ? <span>{attachedMedia.length}</span> : null}</button>
            <button type="button" aria-label={`Duplicate option ${optionIndex + 1}`} onClick={() => duplicateOption(optionIndex)}><Copy /></button>
            <button type="button" aria-label={`Delete option ${optionIndex + 1}`} disabled={item.options!.length <= 2} onClick={() => deleteOption(optionIndex)}><Trash /></button>
          </div>
        </div>
      })}
      {item.allowOther ? <div className="assessment-option assessment-option--other" data-testid="other-choice-preview">
        <span className="assessment-option-other-marker" aria-hidden="true" />
        <span><strong>Other</strong><small>Learner enters their own response</small></span>
        <button type="button" aria-label="Remove Other choice" onClick={() => change((current) => ({ ...current, allowOther: false }))}><X /></button>
      </div> : null}</div>
      <div className="assessment-option-tools">
        <button className="assessment-secondary-action assessment-icon-action" type="button" aria-label="Add choice" title="Add choice" disabled={item.options.length >= 10} onClick={() => change((current) => ({ ...current, options: [...(current.options ?? []), { id: newId(), label: `Option ${(current.options?.length ?? 0) + 1}` }] }))}><Plus aria-hidden="true" /></button>
        <label className="assessment-option-toggle"><input type="checkbox" checked={item.allowOther ?? false} onChange={(event) => change((current) => ({ ...current, allowOther: event.target.checked }))} /><span className="assessment-toggle-track" aria-hidden="true" /><span>Allow Other</span></label>
        <label className="assessment-option-toggle"><input type="checkbox" checked={item.shuffleOptions ?? false} onChange={(event) => change((current) => ({ ...current, shuffleOptions: event.target.checked }))} /><span className="assessment-toggle-track" aria-hidden="true" /><span>Shuffle choices</span></label>
      </div>
    </section> : null}

    {item.type === 'rating' ? <section className="assessment-editor-section assessment-rating-settings" aria-label="Rating settings">
      <header className="assessment-editor-section-heading"><h3>Rating scale</h3><p>Ratings always begin at 1 and end from 3 through 10.</p></header>
      <div className="assessment-rating-controls"><label><span>Maximum choices</span><select value={item.rating?.max ?? 5} onChange={(event) => change((current) => ({ ...current, rating: { min: 1, max: Number(event.target.value) as NonNullable<AssessmentItem['rating']>['max'], style: current.rating?.style ?? 'numbers' } }))}>{[3, 4, 5, 6, 7, 8, 9, 10].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <label><span>Display style</span><select value={item.rating?.style ?? 'numbers'} onChange={(event) => change((current) => ({ ...current, rating: { min: 1, max: current.rating?.max ?? 5, style: event.target.value as NonNullable<AssessmentItem['rating']>['style'] } }))}><option value="numbers">Numbers</option><option value="stars">Stars</option><option value="hearts">Hearts</option><option value="thumbs-up">Thumbs up</option></select></label></div>
      <div className="assessment-rating-preview-panel"><small>Learner preview</small><div className="assessment-rating-preview" aria-label="Rating preview">{Array.from({ length: item.rating?.max ?? 5 }, (_, index) => <span key={index}>{item.rating?.style === 'stars' ? '★' : item.rating?.style === 'hearts' ? '♥' : item.rating?.style === 'thumbs-up' ? '👍' : index + 1}</span>)}</div></div>
    </section> : null}

    {item.type === 'diagnostic-field' ? <details className="assessment-progressive-section" onToggle={(event) => { if (event.currentTarget.open && !slides.length && !diagnosticLoading) void loadDiagnosticSlides() }}><summary>Answer key & diagnostic regions</summary><div className="assessment-diagnostic">
      <div className="assessment-diagnostic-heading"><span><strong>Accepted slide regions</strong><small>Choose a class slide, then add points, rectangles, or freehand regions that count as correct.</small></span><b>{((item.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []).length} regions</b></div>
      <button type="button" disabled={diagnosticLoading} onClick={() => void loadDiagnosticSlides()}>{diagnosticLoading ? <SpinnerGap aria-hidden="true" /> : <Image aria-hidden="true" />}{diagnosticLoading ? 'Loading slides…' : slides.length ? 'Refresh class slides' : 'Load class slides'}</button>
      {diagnosticError ? <p role="alert" className="assessment-diagnostic-status">{diagnosticError}</p> : null}
      {slides.length ? <label>Class slide<select aria-label="Eligible slide" value={item.slideId ?? ''} onChange={(event) => change((current) => ({ ...current, slideId: event.target.value || undefined, answerKey: { ...current.answerKey, regions: [] } }))}><option value="">Select a slide</option>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select></label> : null}
      {item.slideId && slides.find((slide) => slide.id === item.slideId) ? <AssessmentDiagnosticField label="Accepted diagnostic regions" authoringLabel="Diagnostic answer region tools" allowFreehand tileSource={slides.find((slide) => slide.id === item.slideId)!.tileSource} selections={(item.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []} multiple onCommit={(selection) => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: [...((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []), selection] } }))} onUpdateSelection={(index, selection) => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: ((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []).map((candidate, candidateIndex) => candidateIndex === index ? selection : candidate) } }))} onDeleteSelection={(index) => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: ((current.answerKey?.regions as DiagnosticSelection[] | undefined) ?? []).filter((_, candidateIndex) => candidateIndex !== index) } }))} onClear={() => change((current) => ({ ...current, answerKey: { ...current.answerKey, regions: [] } }))} /> : null}
      <label>Accepted diagnoses<input aria-label="Accepted diagnoses" placeholder="e.g. adenocarcinoma, invasive carcinoma" value={((item.answerKey?.diagnoses as string[] | undefined) ?? []).join(', ')} onChange={(event) => change((current) => ({ ...current, answerKey: { ...current.answerKey, diagnoses: commaSeparatedValues(event.target.value) } }))} /></label>
      <div className="assessment-diagnostic-thresholds"><label><span>Point tolerance</span><input aria-label="Point tolerance" type="number" min="0.005" max="0.25" step="0.005" value={item.scoring?.pointTolerance ?? 0.03} onChange={(event) => change((current) => ({ ...current, scoring: { ...current.scoring, pointTolerance: Number(event.target.value) } }))} /></label><label><span>Rectangle overlap</span><input aria-label="Rectangle overlap" type="number" min="0.05" max="1" step="0.05" value={item.scoring?.rectangleIou ?? 0.25} onChange={(event) => change((current) => ({ ...current, scoring: { ...current.scoring, rectangleIou: Number(event.target.value) } }))} /></label></div>
    </div></details> : null}
    {item.type === 'short-answer' || item.type === 'paragraph' ? <details className="assessment-progressive-section assessment-text-answer-key"><summary>Answer key & keywords</summary><div>
      <p>Accept a short phrase or a longer response. Keywords are recognized anywhere in the learner's text and highlighted below.</p>
      <label>Accepted exact answers<input aria-label="Accepted exact answers" placeholder="Separate alternatives with commas" value={((item.answerKey?.variants as string[] | undefined) ?? []).join(', ')} onChange={(event) => change((current) => ({ ...current, answerKey: { ...current.answerKey, variants: commaSeparatedValues(event.target.value) } }))} /></label>
      <label>Keywords<input aria-label="Answer keywords" placeholder="e.g. atypia, mitosis, invasion" value={keywordDraft} onChange={(event) => setKeywordDraft(event.target.value)} onBlur={() => change((current) => ({ ...current, answerKey: { ...current.answerKey, keywords: commaSeparatedValues(keywordDraft) } }))} /></label>
      <label className="assessment-feedback-credit"><input type="checkbox" checked={item.manual ?? false} onChange={(event) => change((current) => ({ ...current, manual: event.target.checked }))} /><span>Review responses manually instead of auto-scoring</span></label>
      <label>Test a learner response<textarea aria-label="Keyword match preview" rows={4} placeholder="Type a sample short or long response" value={keywordPreview} onChange={(event) => setKeywordPreview(event.target.value)} /></label>
      <KeywordMatchPreview response={keywordPreview} keywords={commaSeparatedValues(keywordDraft)} />
    </div></details> : null}

    {mediaDialogTarget !== null ? createPortal(<div className="assessment-dialog-backdrop assessment-media-dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setMediaDialogTarget(null) }}>
      <section className={`assessment-media-dialog${optionMediaDialogIndex !== null ? ' assessment-option-media-dialog' : ''}`} role="dialog" aria-modal="true" aria-labelledby={`media-dialog-title-${item.id}-${optionMediaDialogIndex ?? 'question'}`}>
        <header className="assessment-media-dialog-header"><span className="assessment-media-dialog-icon"><Image aria-hidden="true" /></span><span><h3 id={`media-dialog-title-${item.id}-${optionMediaDialogIndex ?? 'question'}`}>{optionMediaDialogIndex !== null ? `Edit answer ${optionMediaDialogIndex + 1} media` : `${dialogMediaCollection.length ? 'Edit' : 'Add'} question media`}</h3><p>Add up to {dialogMediaLimit} slides, uploads, or captured teaching fields.</p></span><button type="button" aria-label={optionMediaDialogIndex !== null ? 'Close answer media dialog' : 'Close media dialog'} onClick={() => setMediaDialogTarget(null)}><X /></button></header>
        <div className="assessment-media-dialog-body">
          <section className="assessment-media-source-browser" aria-label={isOptionMediaDialog ? 'Choose answer media source' : 'Choose media source'}>
            <div className="assessment-media-source-tabs" role="tablist" aria-label={isOptionMediaDialog ? 'Answer media source' : 'Media source'}><button id={`media-tab-slides-${mediaDialogId}`} type="button" role="tab" aria-label="Class slides" aria-controls={`media-panel-slides-${mediaDialogId}`} aria-selected={mediaSourceTab === 'slides'} onClick={() => setMediaSourceTab('slides')}><Image aria-hidden="true" /><span><strong>Class slides</strong></span></button><button id={`media-tab-upload-${mediaDialogId}`} type="button" role="tab" aria-label={isOptionMediaDialog ? 'Upload images' : 'Upload image'} aria-controls={`media-panel-upload-${mediaDialogId}`} aria-selected={mediaSourceTab === 'upload'} onClick={() => setMediaSourceTab('upload')}><UploadSimple aria-hidden="true" /><span><strong>Upload images</strong></span></button></div>
            {mediaSourceTab === 'slides' ? <div id={`media-panel-slides-${mediaDialogId}`} className="assessment-media-source-panel" role="tabpanel" aria-labelledby={`media-tab-slides-${mediaDialogId}`}><strong>{mediaScopeLabel} slides</strong>{slides.length ? <div className="assessment-media-slide-grid" role="list" aria-label={`${mediaScopeLabel} whole-slide images`}>{slides.map((slide) => { const selectedIndex = dialogMediaCollection.findIndex((media) => media.kind === 'slide-thumbnail' && media.slideId === slide.id); const selected = selectedIndex >= 0; return <button key={slide.id} type="button" role="listitem" className={selected ? 'is-selected' : ''} aria-pressed={selected} aria-label={`${selected ? 'Deselect' : 'Select'} slide ${slide.displayName}`} onClick={() => { setMediaError(''); if (selected) { removeSlideMedia(slide.id); return } if (dialogMediaCollection.length >= dialogMediaLimit) { setMediaError(`${dialogMediaOwnerWithArticle} can contain up to ${dialogMediaLimit} media items.`); return } const nextIndex = dialogMediaCollection.length; updateDialogMediaCollection((current) => [...current, { kind: 'slide-thumbnail' as const, slideId: slide.id, assetPath: slide.thumbnail ?? undefined, fileName: slide.displayName, viewport: { x: 50, y: 50, scale: 1 }, alt: '', marks: [] }]); setActiveMediaIndex(nextIndex) }}><span>{slide.thumbnail ? <img src={slide.thumbnail} alt="" /> : <Image aria-hidden="true" />}{selected ? <i aria-hidden="true"><Check /></i> : null}</span><strong>{slide.displayName}</strong></button> })}</div> : <div className="assessment-media-source-status"><Image aria-hidden="true" /><strong>No class slides available</strong><span>Attach a privacy-passed WSI to {mediaScopeLabel}.</span></div>}</div> : <div id={`media-panel-upload-${mediaDialogId}`} className="assessment-media-upload-panel" role="tabpanel" aria-labelledby={`media-tab-upload-${mediaDialogId}`}><label className={`assessment-media-upload${mediaLoading ? ' is-loading' : ''}`}>{mediaLoading ? <SpinnerGap aria-hidden="true" /> : <UploadSimple aria-hidden="true" />}<strong>{mediaLoading ? 'Preparing images…' : 'Choose images'}</strong><span>Multiple JPG, PNG or WebP files · up to 100 MB each</span><input type="file" multiple accept="image/jpeg,image/png,image/webp" aria-label={isOptionMediaDialog ? `Upload images for option ${optionMediaDialogIndex + 1}` : 'Upload images'} disabled={mediaLoading} onChange={(event) => void uploadMediaImages(event.target.files)} /></label></div>}
          </section>
          {dialogMediaCollection.length ? <section className="assessment-media-collection" aria-label={`${mediaCollectionLabel} collection`}><header><span><strong>{mediaCollectionLabel}</strong><small>Select an item to edit it</small></span><b>{dialogMediaCollection.length} / {dialogMediaLimit}</b></header><div>{dialogMediaCollection.map((media, index) => { const source = media.capturedImage?.assetPath ?? media.assetPath ?? (media.slideId ? slides.find((slide) => slide.id === media.slideId)?.thumbnail : undefined); const mediaName = media.fileName ?? `${isOptionMediaDialog ? 'Answer' : 'Question'} image`; return <div key={`${media.kind}-${media.slideId ?? media.fileName ?? index}-${index}`} className="assessment-media-collection-card"><button type="button" className="assessment-media-collection-select" aria-pressed={activeMediaIndex === index} aria-label={`Edit ${isOptionMediaDialog ? 'answer ' : ''}media ${index + 1}: ${mediaName}`} onClick={() => { setActiveMediaIndex(index); setMediaSourceTab(media.kind === 'uploaded-image' ? 'upload' : 'slides') }}><span>{source ? <img src={source} alt="" /> : <Image aria-hidden="true" />}</span><strong>{index + 1}. {mediaName}</strong></button><button type="button" className="assessment-media-collection-remove" aria-label={`Remove ${isOptionMediaDialog ? 'answer ' : ''}media ${index + 1}: ${mediaName}`} title="Remove media" onClick={() => removeMediaAt(index)}><X aria-hidden="true" /></button></div> })}</div></section> : null}
          {activeMedia ? <div className="assessment-media-composer">
            {activeMedia.kind === 'uploaded-image' && activeMedia.assetPath ? <div className="assessment-media-preview"><img src={activeMedia.assetPath} alt={activeMedia.alt || `${mediaCollectionLabel} preview`} /></div> : activeMedia.kind === 'slide-thumbnail' && selectedMediaSlide ? <div className="assessment-media-wsi"><div className="assessment-media-wsi-heading"><strong>Frame and annotate media {activeMediaIndex + 1}</strong><span>Pan to a teaching field. Each additional capture is saved as another image for this {dialogMediaOwner}.</span></div><AssessmentDiagnosticField label={`${isOptionMediaDialog ? 'Answer' : 'Question'} WSI media editor`} authoringLabel={`${isOptionMediaDialog ? 'Answer' : 'Question'} media annotation tools`} tileSource={selectedMediaSlide.tileSource} capture={activeMedia.capture} selections={activeMedia.marks ?? []} multiple allowFreehand showLoadingMode={false} onCapture={(capture, image) => { const capturedImage = image ? { assetPath: image.dataUrl, width: image.width, height: image.height, bytes: image.bytes } : activeMedia.capturedImage; if (activeMedia.capturedImage && dialogMediaCollection.length < dialogMediaLimit) { const nextIndex = dialogMediaCollection.length; updateDialogMediaCollection((current) => [...current, { ...activeMedia, capture, capturedImage, marks: [] }]); setActiveMediaIndex(nextIndex) } else { updateActiveMedia((media) => ({ ...media, capture, capturedImage })); if (activeMedia.capturedImage) setMediaError(`${dialogMediaOwnerWithArticle} can contain up to ${dialogMediaLimit} media items.`) } }} onCommit={(mark) => updateActiveMedia((media) => ({ ...media, marks: [...(media.marks ?? []), mark].slice(0, 20) }))} onUpdateSelection={(index, mark) => updateActiveMedia((media) => ({ ...media, marks: (media.marks ?? []).map((candidate, candidateIndex) => candidateIndex === index ? mark : candidate) }))} onDeleteSelection={(index) => updateActiveMedia((media) => ({ ...media, marks: (media.marks ?? []).filter((_, candidateIndex) => candidateIndex !== index) }))} onClear={() => updateActiveMedia((media) => ({ ...media, marks: [] }))} /></div> : <div className="assessment-media-preview"><div><Image aria-hidden="true" /><strong>Preview unavailable</strong><span>{selectedMediaSlide ? 'Choose another slide or upload an image.' : 'Loading WSI…'}</span></div></div>}
            <label className="assessment-media-alt-field">Image description<input aria-label={`${isOptionMediaDialog ? 'Answer image' : 'Image'} ${activeMediaIndex + 1} description`} maxLength={500} placeholder="Describe what learners should understand from this image" value={activeMedia.alt ?? ''} onChange={(event) => updateActiveMedia((media) => ({ ...media, alt: event.target.value }))} /></label>
            <div className="assessment-media-danger-row"><button type="button" className="assessment-danger-action" onClick={() => removeMediaAt(activeMediaIndex)}><Trash aria-hidden="true" /> Remove this media</button></div>
          </div> : <div className="assessment-media-empty"><Image aria-hidden="true" /><strong>No media selected</strong><span>Choose a class WSI above or upload an image to place it with this {dialogMediaOwner}.</span></div>}
          {mediaError ? <p role="alert" className="assessment-dialog-error">{mediaError}</p> : null}
        </div>
        <footer><button type="button" onClick={() => setMediaDialogTarget(null)}>Done</button></footer>
      </section>
    </div>, globalThis.document.body) : null}

    {supportsFeedback ? <details className={`assessment-progressive-section assessment-feedback-panel${item.feedback?.correct?.trim() || item.feedback?.incorrect?.trim() ? ' has-content' : ''}`}><summary><span className="assessment-feedback-panel-icon"><Check aria-hidden="true" /></span><span><strong>Feedback</strong>{item.feedback?.correct?.trim() || item.feedback?.incorrect?.trim() ? <small><Check aria-hidden="true" /> Added</small> : <small>Optional</small>}</span><CaretDown aria-hidden="true" /></summary><div className="assessment-feedback-grid">
      <label className="assessment-feedback-card"><span>Correct response</span><textarea maxLength={4000} placeholder="Optional feedback shown after a correct response" value={item.feedback?.correct ?? ''} onChange={(event) => change((current) => ({ ...current, feedback: { ...current.feedback, correct: event.target.value } }))} /></label>
      <label className="assessment-feedback-card"><span>Incorrect response</span><textarea maxLength={4000} placeholder="Optional feedback shown after an incorrect response" value={item.feedback?.incorrect ?? ''} onChange={(event) => change((current) => ({ ...current, feedback: { ...current.feedback, incorrect: event.target.value } }))} /></label>
      {item.type === 'short-answer' || item.type === 'paragraph' ? <div className="assessment-feedback-lengths"><label><span>Minimum characters</span><input type="number" min="0" max="4000" value={item.validation?.minimumLength ?? ''} onChange={(event) => change((current) => ({ ...current, validation: { ...current.validation, minimumLength: event.target.value ? Number(event.target.value) : undefined } }))} /></label><label><span>Maximum characters</span><input type="number" min="1" max="4000" value={item.validation?.maximumLength ?? ''} onChange={(event) => change((current) => ({ ...current, validation: { ...current.validation, maximumLength: event.target.value ? Number(event.target.value) : undefined } }))} /></label></div> : null}
      {item.type === 'checkboxes' ? <label className="assessment-feedback-credit"><input type="checkbox" checked={item.scoring?.partialCredit ?? false} onChange={(event) => change((current) => ({ ...current, scoring: { ...current.scoring, partialCredit: event.target.checked } }))} /><span>Allow bounded partial credit</span></label> : null}
    </div>
    </details> : null}
  </div>
}
