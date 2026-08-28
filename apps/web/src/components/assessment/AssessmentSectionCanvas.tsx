import { ArrowDown, ArrowUp, ArrowsInLineVertical, ArrowsOutLineVertical, CaretDown, Copy, DotsSixVertical, Eye, MagnifyingGlass, Plus, Trash, X } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'

import { questionTypeRegistry, questionTypesByType } from '../../assessment/questionTypes'
import { assessmentTemplates, parseAssessmentPaste } from '../../assessment/templates'
import type { AssessmentDocumentV2, AssessmentItem, AssessmentItemType, AssessmentSection, EligibleAssessmentSlide } from '../../assessment/types'
import { QuestionEditor } from './AssessmentQuestionCanvas'

interface SectionCanvasProps {
  document: AssessmentDocumentV2
  onDocumentChange: (update: (document: AssessmentDocumentV2) => AssessmentDocumentV2) => void
  onImport: () => void
  onPreview: () => void
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

function freshItem(source: AssessmentItem): AssessmentItem {
  const options = (source.options ?? []).map((option) => ({ ...option, id: newId('option') }))
  const optionIds = new Map((source.options ?? []).map((option, index) => [option.id, options[index].id]))
  const selected = ((source.answerKey?.optionIds as string[] | undefined) ?? []).map((id) => optionIds.get(id)).filter(Boolean) as string[]
  return { ...structuredClone(source), id: newId('item'), options, answerKey: { ...source.answerKey, optionIds: selected }, routing: undefined }
}

export function AssessmentSectionCanvas({ document, onDocumentChange, onImport, onPreview }: SectionCanvasProps) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState(document.sections[0]?.items[0]?.id ?? '')
  const [deleted, setDeleted] = useState<{ section: AssessmentSection; index: number } | null>(null)
  const [slides, setSlides] = useState<EligibleAssessmentSlide[]>([])
  const [draggedSection, setDraggedSection] = useState('')
  const [draggedItem, setDraggedItem] = useState<{ sectionId: string; itemId: string } | null>(null)
  const [message, setMessage] = useState('')
  const [starterOpen, setStarterOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
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

  function dropItem(sectionId: string, destinationIndex: number) {
    if (!draggedItem) return
    let moving: AssessmentItem | undefined
    const stripped = document.sections.map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (item.id !== draggedItem.itemId) return true
        moving = item
        return false
      }),
    }))
    if (!moving) return
    onDocumentChange((current) => ({
      ...current,
      sections: stripped.map((section) => {
        if (section.id !== sectionId) return section
        const items = [...section.items]
        items.splice(Math.min(destinationIndex, items.length), 0, moving!)
        return { ...section, items }
      }),
    }))
    setDraggedItem(null)
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

  return <main className="assessment-question-workspace assessment-section-workspace">
    <header className="assessment-authoring-toolbar">
      <div><h2>Questions</h2><p>{document.sections.length} sections · {itemCount} questions · {issueCount ? `${issueCount} issues` : 'Ready to review'}</p></div>
      <div className="assessment-authoring-actions">
        <button className="assessment-icon-action" type="button" aria-label="Assignment preview" title="Assignment preview" onClick={onPreview}><Eye aria-hidden="true" /></button>
        <button className="assessment-icon-action" type="button" aria-label="Expand all sections" title="Expand all sections" onClick={() => setCollapsed(new Set())}><ArrowsOutLineVertical aria-hidden="true" /></button>
        <button className="assessment-icon-action" type="button" aria-label="Collapse all sections" title="Collapse all sections" onClick={() => setCollapsed(new Set(document.sections.map((section) => section.id)))}><ArrowsInLineVertical aria-hidden="true" /></button>
        <button type="button" onClick={onImport}>Import</button>
        <button type="button" onClick={() => setStarterOpen((open) => !open)}>Templates & paste</button>
        <button className="assessment-primary" type="button" onClick={addSection}><Plus aria-hidden="true" /> Add section</button>
      </div>
    </header>
    {starterOpen ? <section className="assessment-starter-panel" aria-label="Templates and paste creation">
      <div><h3>Start from a template</h3><p>Five versioned teaching patterns. Applying one replaces this draft&apos;s current sections.</p><div className="assessment-template-grid">{assessmentTemplates.map((template) => <button key={template.id} type="button" onClick={() => { onDocumentChange((current) => ({ ...structuredClone(template.document), title: current.title })); setStarterOpen(false) }}><strong>{template.name}</strong><span>{template.description}</span><small>Template v{template.version}</small></button>)}</div></div>
      <div><h3>Paste questions</h3><p>One per line: <code>mc | Prompt | Option A | Option B</code></p><textarea aria-label="Paste questions" value={pasteText} onChange={(event) => setPasteText(event.target.value)} /><div className="assessment-paste-preview" aria-live="polite">{parseAssessmentPaste(pasteText).errors.map((error) => <p key={`${error.line}-${error.message}`}>Line {error.line}: {error.message}</p>)}{pasteText && !parseAssessmentPaste(pasteText).errors.length ? <p>{parseAssessmentPaste(pasteText).items.length} questions ready</p> : null}</div><button type="button" disabled={!parseAssessmentPaste(pasteText).items.length || Boolean(parseAssessmentPaste(pasteText).errors.length)} onClick={() => { const parsed = parseAssessmentPaste(pasteText); updateSections((sections) => sections.map((section, index) => index === 0 ? { ...section, items: [...section.items, ...parsed.items.map(freshItem)] } : section)); setPasteText(''); setStarterOpen(false) }}>Create questions</button></div>
    </section> : null}
    <div className="assessment-question-layout">
      <aside className="assessment-question-navigator assessment-section-navigator" aria-label="Question navigator">
        <header><div><strong>Assignment</strong><small>{document.sections.length} sections</small></div><span>{itemCount}</span></header>
        <label className="assessment-navigator-search"><MagnifyingGlass aria-hidden="true" /><input placeholder="Search sections and questions" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <div className="assessment-navigator-guide"><span><DotsSixVertical aria-hidden="true" />Drag to reorder</span><span>{issueCount ? `${issueCount} issues` : 'Ready'}</span></div>
        <ol className="assessment-section-outline">
          {document.sections.map((section, sectionIndex) => {
            const visible = !query || section.title.toLocaleLowerCase().includes(query) || section.items.some((item) => item.prompt.toLocaleLowerCase().includes(query))
            if (!visible) return null
            return <li key={section.id}>
              <button type="button" className="assessment-section-outline-title" onClick={() => globalThis.document.getElementById(section.id)?.scrollIntoView({ block: 'start' })}>
                <span>{sectionIndex + 1}</span><strong>{section.title || 'Untitled section'}</strong><small>{section.items.length}</small>
              </button>
              <ol>{section.items.filter((item) => !query || item.prompt.toLocaleLowerCase().includes(query)).map((item) => <li key={item.id}><button type="button" className={selectedId === item.id ? 'active' : ''} onClick={() => { setSelectedId(item.id); setCollapsed((current) => { const next = new Set(current); next.delete(section.id); return next }); globalThis.setTimeout(() => globalThis.document.querySelector(`[data-question-id="${item.id}"]`)?.scrollIntoView({ block: 'center' }), 0) }}><span>{numbering.get(item.id)}</span><span><strong>{item.prompt || 'Untitled question'}</strong><small>{questionTypesByType[item.type].label}</small></span></button></li>)}</ol>
            </li>
          })}
        </ol>
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
              if (draggedItem) { dropItem(section.id, section.items.length); return }
              const sourceId = event.dataTransfer.getData('text/section') || draggedSection
              const sourceIndex = document.sections.findIndex((candidate) => candidate.id === sourceId)
              if (sourceIndex < 0 || sourceIndex === sectionIndex) return
              updateSections((sections) => { const next = [...sections]; const [moving] = next.splice(sourceIndex, 1); next.splice(sectionIndex, 0, moving); return next })
            }}
          >
            <header className="assessment-section-header">
              <button className="assessment-question-drag" type="button" aria-label={`Reorder section ${sectionIndex + 1}`} title="Drag or use Alt + arrow keys" onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveSection(sectionIndex, -1); if (event.key === 'ArrowDown') moveSection(sectionIndex, 1) }}><DotsSixVertical aria-hidden="true" /></button>
              <span className="assessment-section-number">Section {sectionIndex + 1}</span>
              <label><span className="visually-hidden">Section title</span><input aria-label={`Section ${sectionIndex + 1} title`} value={section.title} maxLength={200} onChange={(event) => updateSection(section.id, (current) => ({ ...current, title: event.target.value }))} /></label>
              <span>{section.items.length} items</span>
              <button type="button" aria-label={`${sectionCollapsed ? 'Expand' : 'Collapse'} section ${sectionIndex + 1}`} onClick={() => setCollapsed((current) => { const next = new Set(current); if (next.has(section.id)) next.delete(section.id); else next.add(section.id); return next })}><CaretDown aria-hidden="true" /></button>
              <button type="button" aria-label={`Duplicate section ${sectionIndex + 1}`} onClick={() => updateSections((sections) => { const next = [...sections]; next.splice(sectionIndex + 1, 0, cloneSection(section)); return next })}><Copy aria-hidden="true" /></button>
              <button type="button" aria-label={`Delete section ${sectionIndex + 1}`} disabled={document.sections.length === 1} onClick={() => deleteSection(section, sectionIndex)}><Trash aria-hidden="true" /></button>
            </header>
            {!sectionCollapsed ? <>
              <label className="assessment-section-description">Description<textarea maxLength={2000} value={section.description ?? ''} onChange={(event) => updateSection(section.id, (current) => ({ ...current, description: event.target.value }))} /></label>
              <div className="assessment-section-items">
                {section.items.map((item, itemIndex) => <article
                  key={item.id}
                  data-question-id={item.id}
                  className={`assessment-question-card assessment-question-card--expanded${selectedId === item.id ? ' assessment-question-card--focused' : ''}`}
                  draggable
                  onDragStart={(event) => { event.stopPropagation(); setDraggedItem({ sectionId: section.id, itemId: item.id }); event.dataTransfer.setData('text/item', item.id) }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => { event.preventDefault(); event.stopPropagation(); dropItem(section.id, itemIndex) }}
                  onFocus={() => setSelectedId(item.id)}
                >
                  <header className="assessment-question-card-header">
                    <button className="assessment-question-drag" type="button" aria-label={`Reorder question ${numbering.get(item.id)}`} onKeyDown={(event) => { if (!event.altKey) return; if (event.key === 'ArrowUp') moveItem(section.id, itemIndex, -1); if (event.key === 'ArrowDown') moveItem(section.id, itemIndex, 1) }}><DotsSixVertical /></button>
                    <span className="assessment-question-number">{numbering.get(item.id)}</span>
                    <span className="assessment-question-summary-copy"><small>{questionTypesByType[item.type].label}</small><strong>{item.prompt || 'Untitled question'}</strong></span>
                    {item.required ? <span className="assessment-required-badge">Required</span> : null}
                    <button type="button" aria-label={`Move question ${numbering.get(item.id)} up`} disabled={itemIndex === 0} onClick={() => moveItem(section.id, itemIndex, -1)}><ArrowUp /></button>
                    <button type="button" aria-label={`Move question ${numbering.get(item.id)} down`} disabled={itemIndex === section.items.length - 1} onClick={() => moveItem(section.id, itemIndex, 1)}><ArrowDown /></button>
                    <button type="button" aria-label={`Delete question ${numbering.get(item.id)}`} onClick={() => updateSection(section.id, (current) => ({ ...current, items: current.items.filter((candidate) => candidate.id !== item.id) }))}><Trash /></button>
                  </header>
                  <QuestionEditor item={item} slides={slides} setSlides={setSlides} updateItem={updateItem} promptRef={() => undefined} />
                </article>)}
              </div>
              <div className="assessment-section-add-question"><label><span>Add question</span><select aria-label={`Question type for section ${sectionIndex + 1}`} defaultValue="multiple-choice">{questionTypeRegistry.filter((type) => type.type !== 'information').map((type) => <option key={type.type} value={type.type}>{type.label}</option>)}</select></label><button type="button" onClick={(event) => { const select = event.currentTarget.previousElementSibling?.querySelector('select') as HTMLSelectElement | null; addItem(section.id, (select?.value ?? 'multiple-choice') as AssessmentItemType) }}><Plus /> Add</button></div>
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
