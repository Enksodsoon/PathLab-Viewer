import {
  ArrowLeft, ArrowRight, Brain, CheckCircle, DownloadSimple, FileArrowUp, Plus, Trash,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Brand } from '../components/Brand'
import {
  listStudyAuthoringSlides, publishStudyPack, validateStudyPack,
} from '../study/api'
import {
  clearStudyPackDraft, loadStudyPackDraft, saveStudyPackDraft,
} from '../study/authoringStore'
import type { StudyAuthoringSlide, StudyPackDefinition, StudyPackTaskDefinition } from '../study/types'
import { ThemeControl } from '../theme/ThemeControl'
import './StudyPackAuthoringPage.css'

const ACTIONS = [
  ['continue', 'Continue practice', 'เรียนต่อ', 'CONTINUE_PRACTICE'],
  ['offer_hint', 'Open a faculty hint', 'เปิดคำใบ้ของอาจารย์', 'HINT_SUPPORT'],
  ['ask_confidence', 'Check confidence', 'ตรวจสอบความมั่นใจ', 'CHECK_CONFIDENCE'],
  ['ask_source_check', 'Verify the source', 'ตรวจสอบแหล่งข้อมูล', 'VERIFY_SOURCE'],
  ['retrieve', 'Review a previous task', 'ทบทวนคำถามก่อนหน้า', 'REVIEW_PREVIOUS'],
  ['pause', 'Take a short break', 'พักสั้น ๆ', 'TAKE_BREAK'],
] as const

const emptyTask = (slideId = ''): StudyPackTaskDefinition => ({
  id: '', type: 'multiple-choice', slideId, prompt: '', options: ['', ''], answerKey: '',
  hints: [], explanation: '', sources: [{ title: '', url: 'https://' }],
})

const emptyPack: StudyPackDefinition = {
  schema: 'pathlab.study-pack/1', packKey: '', version: 1, title: '', author: '', license: '',
  provenance: '', revision: '', languages: ['en', 'th'], slides: [], tasks: [],
}

export function StudyPackAuthoringPage() {
  const navigate = useNavigate()
  const [slides, setSlides] = useState<StudyAuthoringSlide[]>([])
  const [pack, setPack] = useState<StudyPackDefinition>(emptyPack)
  const [draft, setDraft] = useState<StudyPackTaskDefinition>(emptyTask())
  const [preview, setPreview] = useState<{ canonicalCore: StudyPackDefinition; checksum: string }>()
  const [previewIndex, setPreviewIndex] = useState(0)
  const [visited, setVisited] = useState<Set<number>>(new Set())
  const [keyboardChecked, setKeyboardChecked] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('Loading eligible Viewer slides…')
  const [error, setError] = useState('')
  const csvInput = useRef<HTMLInputElement>(null)
  const jsonInput = useRef<HTMLInputElement>(null)
  const previewHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    void Promise.all([listStudyAuthoringSlides(), loadStudyPackDraft()]).then(([nextSlides, saved]) => {
      setSlides(nextSlides)
      if (saved) setPack(saved)
      setDraft(emptyTask(saved?.tasks.at(-1)?.slideId ?? nextSlides[0]?.id ?? ''))
      setNotice(nextSlides.length ? 'Drafts stay on this device until publication.' : 'No accepted static-DZI slides are available.')
      setLoaded(true)
    }).catch((caught) => setError(message(caught)))
  }, [])

  useEffect(() => {
    if (!loaded) return
    const timer = window.setTimeout(() => {
      void saveStudyPackDraft(pack).then(() => setNotice('Draft saved on this device.')).catch((caught) => setError(message(caught)))
    }, 350)
    return () => window.clearTimeout(timer)
  }, [loaded, pack])

  useEffect(() => {
    if (!preview) return
    setVisited((current) => new Set(current).add(previewIndex))
    previewHeading.current?.focus()
  }, [preview, previewIndex])

  const definition = useMemo<StudyPackDefinition>(() => ({
    ...pack,
    slides: [...new Set(pack.tasks.map((task) => task.slideId))].map((slideId) => {
      const slide = slides.find((item) => item.id === slideId)
      const imported = pack.slides.find((item) => item.viewerSlideId === slideId)
      return {
        viewerSlideId: slideId, displayName: slide?.displayName ?? '', sha256: slide?.sha256 ?? '',
        ...(pack.schema === 'pathlab.study-pack/2'
          ? { evidenceBundleSha256: imported?.evidenceBundleSha256 ?? '' }
          : pack.schema === 'pathlab.study-pack/3'
            ? { evidenceSetSha256: imported?.evidenceSetSha256 ?? '' } : {}),
      }
    }),
  }), [pack, slides])

  const changePack = (name: keyof StudyPackDefinition, value: string | number) => {
    setPack((current) => ({ ...current, [name]: value })); setPreview(undefined)
  }

  const addTask = () => {
    const task: StudyPackTaskDefinition = {
      ...draft,
      id: draft.id.trim(), prompt: draft.prompt.trim(),
      options: draft.type === 'multiple-choice' ? draft.options?.map((item) => item.trim()).filter(Boolean) : undefined,
      answerKey: draft.type === 'multiple-choice' ? draft.answerKey?.trim() : undefined,
      hints: draft.hints.map((item) => item.trim()).filter(Boolean).slice(0, 3),
      explanation: draft.explanation.trim(),
      sources: draft.sources.map((source) => ({ title: source.title.trim(), url: source.url.trim() })),
    }
    setPack((current) => ({ ...current, tasks: [...current.tasks.filter((item) => item.id !== task.id), task] }))
    setDraft({ ...emptyTask(draft.slideId), id: `task-${pack.tasks.length + 2}` })
    setPreview(undefined); setNotice('Task added. Preview again after every edit.')
  }

  const importCsv = async (file?: File) => {
    if (!file) return
    if (file.size > 2 * 1024 * 1024) return setError('CSV exceeds 2 MiB.')
    try {
      const [header, ...rows] = csvRows(await file.text())
      const at = (name: string) => header.indexOf(name)
      for (const name of ['id', 'type', 'slideId', 'prompt', 'explanation', 'sourceTitle', 'sourceUrl']) {
        if (at(name) < 0) throw new Error(`CSV column ${name} is required.`)
      }
      const tasks = rows.map((row): StudyPackTaskDefinition => {
        const type = row[at('type')] as StudyPackTaskDefinition['type']
        return {
          id: row[at('id')], type, slideId: row[at('slideId')], prompt: row[at('prompt')],
          ...(type === 'multiple-choice' ? {
            options: (row[at('options')] ?? '').split('|').map((item) => item.trim()).filter(Boolean),
            answerKey: row[at('answerKey')],
          } : {
            targetX: Number(row[at('targetX')]), targetY: Number(row[at('targetY')]),
            targetWidth: Number(row[at('targetWidth')]), targetHeight: Number(row[at('targetHeight')]),
            tolerance: Number(row[at('tolerance')]),
          }),
          hints: [row[at('hint1')], row[at('hint2')], row[at('hint3')]].filter(Boolean),
          explanation: row[at('explanation')],
          sources: [{ title: row[at('sourceTitle')], url: row[at('sourceUrl')] }],
        }
      })
      if (!tasks.length || tasks.length + pack.tasks.length > 500) throw new Error('CSV must keep the pack between 1 and 500 tasks.')
      setPack((current) => ({ ...current, tasks: [...current.tasks, ...tasks] })); setPreview(undefined)
      setNotice(`${tasks.length} tasks imported with explicit answer data.`); setError('')
    } catch (caught) { setError(message(caught)) }
  }

  const importJson = async (file?: File) => {
    if (!file || file.size > 2 * 1024 * 1024) return setError('JSON draft must be at most 2 MiB.')
    try {
      const value = JSON.parse(await file.text()) as StudyPackDefinition
      if (!['pathlab.study-pack/1', 'pathlab.study-pack/2', 'pathlab.study-pack/3'].includes(value.schema)) {
        throw new Error('Unsupported Study Pack schema.')
      }
      setPack({ ...value, checksum: undefined, facultyPreview: undefined }); setPreview(undefined); setError('')
    } catch (caught) { setError(message(caught)) }
  }

  const exportJson = () => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([JSON.stringify(definition, null, 2)], { type: 'application/json' }))
    link.download = `${definition.packKey || 'study-pack'}-draft.json`; link.click(); URL.revokeObjectURL(link.href)
  }

  const startPreview = async () => {
    setBusy(true); setError('')
    try {
      const value = await validateStudyPack(definition)
      setPreview(value); setPreviewIndex(0); setVisited(new Set()); setKeyboardChecked(false)
      setNotice('Inspect every task and every bilingual AI action card.')
    } catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  const publish = async () => {
    if (!preview || visited.size !== preview.canonicalCore.tasks.length || !keyboardChecked) return
    setBusy(true); setError('')
    try {
      const published = await publishStudyPack({
        ...preview.canonicalCore, checksum: preview.checksum,
        facultyPreview: {
          packChecksum: preview.checksum, previewVersion: 'pathlab.study-preview/1', reviewedAt: new Date().toISOString(),
        },
      })
      await clearStudyPackDraft(); setNotice(`Published immutable ${published.title} v${published.version}.`)
      window.setTimeout(() => navigate('/admin/study'), 700)
    } catch (caught) { setError(message(caught)) }
    finally { setBusy(false) }
  }

  const clearDraft = async () => {
    await clearStudyPackDraft(); setPack(emptyPack); setDraft(emptyTask(slides[0]?.id)); setPreview(undefined)
    setNotice('Local authoring draft deleted.')
  }

  const task = preview?.canonicalCore.tasks[previewIndex]
  return <main className="study-author-shell">
    <header className="study-author-topbar"><Brand product="Study" /><div><button type="button" onClick={() => navigate('/admin/study')}><ArrowLeft /> Study Coach</button><ThemeControl /></div></header>
    <div className="study-author-layout">
      <section className="study-author-editor" aria-labelledby="author-title">
        <span className="study-eyebrow">Viewer-native faculty workspace</span><h1 id="author-title">Author a Study Pack</h1>
        <p>Choose privacy-passed static-DZI slides already in Viewer. Unpublished drafts remain only on this device.</p>
        <div className="study-author-grid">
          <label>Pack key<input value={pack.packKey} onChange={(event) => changePack('packKey', event.target.value)} /></label>
          <label>Version<input type="number" min="1" value={pack.version} onChange={(event) => changePack('version', Number(event.target.value))} /></label>
          <label>Title<input value={pack.title} onChange={(event) => changePack('title', event.target.value)} /></label>
          <label>Author<input value={pack.author} onChange={(event) => changePack('author', event.target.value)} /></label>
          <label>License<input value={pack.license} onChange={(event) => changePack('license', event.target.value)} /></label>
          <label>Revision<input value={pack.revision} onChange={(event) => changePack('revision', event.target.value)} /></label>
          <label className="wide">Provenance<textarea value={pack.provenance} onChange={(event) => changePack('provenance', event.target.value)} /></label>
        </div>
        <fieldset className="study-author-task"><legend>Add or replace a task</legend><div className="study-author-grid">
          <label>Task ID<input value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} /></label>
          <label>Type<select value={draft.type} onChange={(event) => setDraft({ ...draft, type: event.target.value as StudyPackTaskDefinition['type'] })}><option value="multiple-choice">Multiple choice</option><option value="spatial">Spatial identification</option></select></label>
          <label>Viewer slide<select value={draft.slideId} onChange={(event) => setDraft({ ...draft, slideId: event.target.value })}>{slides.map((slide) => <option key={slide.id} value={slide.id}>{slide.displayName}</option>)}</select></label>
          <label className="wide">Prompt<textarea value={draft.prompt} onChange={(event) => setDraft({ ...draft, prompt: event.target.value })} /></label>
          {draft.type === 'multiple-choice' ? <><label className="wide">Options, one per line<textarea value={draft.options?.join('\n')} onChange={(event) => setDraft({ ...draft, options: event.target.value.split('\n') })} /></label><label>Explicit answer<input value={draft.answerKey} onChange={(event) => setDraft({ ...draft, answerKey: event.target.value })} /></label></> : <div className="study-spatial-fields">{(['targetX', 'targetY', 'targetWidth', 'targetHeight', 'tolerance'] as const).map((name) => <label key={name}>{name}<input type="number" min="0" max="1" step=".01" value={draft[name] ?? (name === 'tolerance' ? .06 : .1)} onChange={(event) => setDraft({ ...draft, [name]: Number(event.target.value) })} /></label>)}</div>}
          <label className="wide">Hints, one per line (maximum 3)<textarea value={draft.hints.join('\n')} onChange={(event) => setDraft({ ...draft, hints: event.target.value.split('\n') })} /></label>
          <label className="wide">Faculty explanation<textarea value={draft.explanation} onChange={(event) => setDraft({ ...draft, explanation: event.target.value })} /></label>
          <label>Source title<input value={draft.sources[0].title} onChange={(event) => setDraft({ ...draft, sources: [{ ...draft.sources[0], title: event.target.value }] })} /></label>
          <label>HTTPS source URL<input value={draft.sources[0].url} onChange={(event) => setDraft({ ...draft, sources: [{ ...draft.sources[0], url: event.target.value }] })} /></label>
        </div><button type="button" onClick={addTask}><Plus /> Add task</button></fieldset>
        <div className="study-author-actions"><button type="button" onClick={() => csvInput.current?.click()}><FileArrowUp /> Import CSV</button><button type="button" onClick={() => jsonInput.current?.click()}><FileArrowUp /> Import JSON</button><button type="button" onClick={exportJson}><DownloadSimple /> Export draft</button><button type="button" onClick={() => void clearDraft()}><Trash /> Delete draft</button><input ref={csvInput} hidden type="file" accept=".csv,text/csv" onChange={(event) => void importCsv(event.currentTarget.files?.[0])} /><input ref={jsonInput} hidden type="file" accept=".json,application/json" onChange={(event) => void importJson(event.currentTarget.files?.[0])} /></div>
        {pack.tasks.length ? <ol className="study-author-task-list">{pack.tasks.map((item) => <li key={item.id}><strong>{item.prompt}</strong><span>{item.type} · {slides.find((slide) => slide.id === item.slideId)?.displayName}</span><button type="button" onClick={() => { setDraft(item); setPack((current) => ({ ...current, tasks: current.tasks.filter((value) => value.id !== item.id) })); setPreview(undefined) }}>Edit</button></li>)}</ol> : null}
        <button className="study-author-primary" type="button" disabled={busy || !pack.tasks.length} onClick={() => void startPreview()}><CheckCircle /> Start mandatory preview ({pack.tasks.length})</button>
      </section>
      <aside className="study-author-preview" aria-label="Exact learner and AI-card preview">
        {preview && task ? <><span className="study-eyebrow">Faculty preview</span><h2 ref={previewHeading} tabIndex={-1}>Task {previewIndex + 1} of {preview.canonicalCore.tasks.length}</h2><h3>{task.prompt}</h3>
          {task.options ? <ol>{task.options.map((option) => <li key={option}>{option}{option === task.answerKey ? <strong> — correct key</strong> : null}</li>)}</ol> : <p>Spatial target {task.targetX}, {task.targetY}; {task.targetWidth} × {task.targetHeight}; tolerance {task.tolerance}</p>}
          {task.hints.map((hint, index) => <p key={hint}><strong>Hint {index + 1}:</strong> {hint}</p>)}<p><strong>Explanation:</strong> {task.explanation}</p><ul>{task.sources.map((source) => <li key={source.url}><a href={source.url}>{source.title}</a></li>)}</ul>
          <h3>All bounded local-AI cards</h3><div className="study-author-cards">{ACTIONS.map(([action, en, th, reason]) => <article key={action}><Brain /><strong>{en}</strong><span lang="th">{th}</span><code>{reason}</code><small>No probability or raw output.</small></article>)}</div>
          <nav><button type="button" disabled={previewIndex === 0} onClick={() => setPreviewIndex((value) => value - 1)}><ArrowLeft /> Previous</button><button type="button" disabled={previewIndex === preview.canonicalCore.tasks.length - 1} onClick={() => setPreviewIndex((value) => value + 1)}>Next <ArrowRight /></button></nav>
          <label className="study-author-attest"><input type="checkbox" checked={keyboardChecked} onChange={(event) => setKeyboardChecked(event.target.checked)} /> I reviewed every task, faculty response, source, keyboard focus order, and English/Thai AI card.</label>
          <button className="study-author-primary" type="button" disabled={busy || visited.size !== preview.canonicalCore.tasks.length || !keyboardChecked} onClick={() => void publish()}><CheckCircle /> Attest and publish immutable version</button>
        </> : <><span className="study-eyebrow">Mandatory gate</span><h2>Preview before publication</h2><p>Viewer validates the same immutable contract used by Study Mode. Every task and all six bilingual action cards must be reviewed.</p></>}
        <p role="status">{notice}</p>{error ? <p role="alert" className="study-error">{error}</p> : null}
      </aside>
    </div>
  </main>
}

function csvRows(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = []; let cell = ''; let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index]
    if (character === '"') { if (quoted && text[index + 1] === '"') { cell += '"'; index += 1 } else quoted = !quoted }
    else if (character === ',' && !quoted) { row.push(cell.trim()); cell = '' }
    else if ((character === '\r' || character === '\n') && !quoted) { if (character === '\r' && text[index + 1] === '\n') index += 1; row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = '' }
    else cell += character
  }
  if (quoted) throw new Error('CSV contains an unclosed quoted field.')
  row.push(cell.trim()); if (row.some(Boolean)) rows.push(row)
  return rows
}

function message(error: unknown) { return error instanceof Error ? error.message : 'Unexpected Study Pack error.' }
