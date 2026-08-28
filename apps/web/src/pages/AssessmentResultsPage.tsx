import { DownloadSimple } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { getAssessmentResults, gradeAssessmentResponse, listAssessmentAdministrations, purgeAssessmentRecords, releaseAssessmentResults, updateAssessmentRetention, type AssessmentAdministrationSummary, type AssessmentResults } from '../assessment/api'
import { AssessmentToolbar, AssessmentWorkspaceNav } from '../components/assessment/AssessmentChrome'
import './assessment.css'

type Tab = 'summary' | 'question' | 'individual' | 'grading'

export function AssessmentResultsPage() {
  const [administrations, setAdministrations] = useState<AssessmentAdministrationSummary[]>([])
  const [selected, setSelected] = useState('')
  const [results, setResults] = useState<AssessmentResults | null>(null)
  const [tab, setTab] = useState<Tab>('summary')
  const [grading, setGrading] = useState({ attemptId: '', itemId: '', points: '' })
  const [message, setMessage] = useState('')
  const [retentionDays, setRetentionDays] = useState(365)
  const [hold, setHold] = useState(false)

  useEffect(() => { void listAssessmentAdministrations().then((value) => { setAdministrations(value.items); if (value.items[0]) setSelected(value.items[0].id) }) }, [])
  useEffect(() => { if (selected) void getAssessmentResults(selected).then(setResults) }, [selected])

  async function grade() {
    const individual = results?.individuals.items.find((item) => item.attemptId === grading.attemptId)
    if (!results || !individual?.scoreVersion || !grading.itemId || !grading.points) return
    await gradeAssessmentResponse(selected, { ...grading, expectedScoreVersion: individual.scoreVersion })
    setResults(await getAssessmentResults(selected)); setMessage('Grade saved as a new score version.')
  }

  async function release() {
    await releaseAssessmentResults(selected)
    setMessage('Results deliberately released. Answers remain hidden.')
  }

  async function saveRetention() {
    await updateAssessmentRetention(selected, retentionDays, hold)
    setMessage(hold ? 'Academic/legal hold enabled.' : 'Retention policy saved.')
  }

  return <><AssessmentToolbar title="Results" /><div className="assessment-main">
    <header className="assessment-page-header"><div><h1>Results</h1><p>Review responses, grade written work, and deliberately release scores.</p></div></header>
    <AssessmentWorkspaceNav />
    {administrations.length === 0 ? <section className="assessment-settings"><h2>No recorded administrations yet</h2><p>Published Formative and Quiz/Test results appear here.</p></section> : <>
      <label>Administration<select value={selected} onChange={(event) => setSelected(event.target.value)}>{administrations.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.mode} · {item.status}</option>)}</select></label>
      <div className="assessment-tabs" role="tablist" aria-label="Result views">{(['summary', 'question', 'individual', 'grading'] as const).map((value) => <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{value === 'grading' ? `Needs grading (${results?.summary.needsGrading ?? 0})` : value[0].toUpperCase() + value.slice(1)}</button>)}</div>
      {message ? <p role="status">{message}</p> : null}
      {results && tab === 'summary' ? <><section className="assessment-metrics" aria-label="Response summary"><article><strong>{results.summary.responses}</strong><span>Responses</span></article><article><strong>{results.summary.averagePoints}</strong><span>Average points</span></article><article><strong>{Math.round(Number(results.summary.completionRate) * 100)}%</strong><span>Completion</span></article><article><strong>{results.summary.needsGrading}</strong><span>Needs grading</span></article></section><section className="assessment-settings"><h2>Retention and hold</h2><label>Retention days<input type="number" min="1" max="3650" value={retentionDays} onChange={(event) => setRetentionDays(Number(event.target.value))} /></label><label><input type="checkbox" checked={hold} onChange={(event) => setHold(event.target.checked)} /> Academic or legal hold</label><button type="button" onClick={() => void saveRetention()}>Save retention</button><button type="button" disabled={hold || results.administration.status !== 'closed'} onClick={() => void purgeAssessmentRecords(selected).then((value) => setMessage(`Purge batch removed ${value.deleted}; ${value.remaining} remain.`))}>Purge eligible records</button></section></> : null}
      {results && tab === 'question' ? <section className="assessment-results-grid">{Object.entries(results.summary.questions).map(([itemId, question], index) => <article key={itemId}><h2>Question {index + 1}</h2><p>{question.responseCount} responses · {question.averagePoints} average points</p>{question.spatialHeatmap ? <><div className="assessment-heatmap" style={{ gridTemplateColumns: `repeat(${question.spatialHeatmap.width}, 1fr)` }} aria-hidden="true">{question.spatialHeatmap.counts.flat().map((count, cell) => <span key={cell} style={{ opacity: Math.max(.08, Math.min(1, count / 10)) }} />)}</div><table><caption>Spatial selection heatmap values</caption><tbody>{question.spatialHeatmap.counts.map((row, rowIndex) => <tr key={rowIndex}>{row.map((count, columnIndex) => <td key={columnIndex}>{count}</td>)}</tr>)}</tbody></table></> : null}</article>)}</section> : null}
      {results && tab === 'individual' ? <section><a className="assessment-primary" href={`/api/v2/admin/assessment/administrations/${encodeURIComponent(selected)}/export.csv`}><DownloadSimple /> Export CSV</a><table><caption>Individual gradebook</caption><thead><tr><th>Student</th><th>Status</th><th>Score</th></tr></thead><tbody>{results.individuals.items.map((item) => <tr key={item.attemptId}><td>{item.displayName ?? 'Private learner'}</td><td>{item.status}</td><td>{item.points ?? '—'} / {item.maximumPoints ?? '—'}</td></tr>)}</tbody></table></section> : null}
      {results && tab === 'grading' ? <section className="assessment-settings"><h2>Sequential manual grading</h2>{results.individuals.items.filter((item) => item.status === 'needs_grading').map((item) => <button key={item.attemptId} type="button" onClick={() => { setGrading((current) => ({ ...current, attemptId: item.attemptId, itemId: Object.entries(item.breakdown).find(([, points]) => points === null)?.[0] ?? '' })) }}>{item.displayName ?? 'Private learner'} · score version {item.scoreVersion}</button>)}{grading.attemptId ? <pre aria-label="Student answer">{JSON.stringify(results.individuals.items.find((item) => item.attemptId === grading.attemptId)?.responses[grading.itemId] ?? {}, null, 2)}</pre> : null}<label>Question ID<input value={grading.itemId} onChange={(event) => setGrading((current) => ({ ...current, itemId: event.target.value }))} /></label><label>Points<input inputMode="decimal" value={grading.points} onChange={(event) => setGrading((current) => ({ ...current, points: event.target.value }))} /></label><button className="assessment-primary" type="button" onClick={() => void grade()}>Save grade & next</button><button type="button" disabled={results.summary.needsGrading > 0 || results.administration.status !== 'closed'} onClick={() => void release()}>Release scores</button></section> : null}
    </>}
  </div></>
}
