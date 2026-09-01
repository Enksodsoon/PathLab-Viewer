import { ArrowLeft, CaretLeft, CaretRight, ChartBar, CheckCircle, DownloadSimple, FileXls, ImageSquare, UsersThree } from '@phosphor-icons/react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import {
  getAssessmentDraft,
  getAssessmentMetadata,
  getAssessmentResults,
  gradeAssessmentResponse,
  listAssessmentAdministrations,
  setAssessmentAdministrationStatus,
  type AssessmentAdministrationSummary,
  type AssessmentResults,
} from '../assessment/api'
import { assessmentItems, type AssessmentDocument, type AssessmentDraft, type AssessmentItem } from '../assessment/types'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import './assessment.css'

type ReportView = 'overall' | 'questions' | 'students' | 'grading'
type OverviewChart = 'scores' | 'questions'

function scoreBinsFor(cohortSize: number) {
  const width = cohortSize >= 30 ? 10 : 20
  return Array.from({ length: Math.ceil(100 / width) }, (_, index) => {
    const minimum = index * width
    const upper = minimum + width >= 100 ? 100 : minimum + width - 1
    return { label: `${minimum}-${upper}%`, minimum, maximum: upper === 100 ? 101 : upper + 1 }
  })
}

function number(value: string | null | undefined) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function percent(value: string | number | null | undefined) {
  const parsed = number(String(value ?? 0))
  return Math.max(0, Math.min(100, parsed <= 1 ? parsed * 100 : parsed))
}

function formatPoints(value: string | number | null | undefined) {
  const parsed = number(String(value ?? 0))
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(parsed)
}

function scoredPoints(item: AssessmentResults['individuals']['items'][number], manualPoints = new Map<string, number>()) {
  let points = number(item.points)
  manualPoints.forEach((_maximum, itemId) => {
    const earned = item.breakdown[itemId]
    if (earned !== null && earned !== undefined) points -= number(earned)
  })
  return Math.max(0, points)
}

function scoredMaximum(item: AssessmentResults['individuals']['items'][number], manualPoints = new Map<string, number>()) {
  let maximum = number(item.maximumPoints)
  manualPoints.forEach((points) => {
    maximum -= points
  })
  return Math.max(0, maximum)
}

function scorePercent(item: AssessmentResults['individuals']['items'][number], manualPoints = new Map<string, number>()) {
  const maximum = scoredMaximum(item, manualPoints)
  return maximum > 0 ? Math.max(0, Math.min(100, (scoredPoints(item, manualPoints) / maximum) * 100)) : 0
}

function fileStem(title: string) {
  return title.toLocaleLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'assessment-report'
}

async function loadAllResults(administrationId: string) {
  const first = await getAssessmentResults(administrationId)
  if (first.individuals.items.length >= first.individuals.total) return first
  const pages = await Promise.all(
    Array.from({ length: Math.ceil((first.individuals.total - first.individuals.items.length) / 50) }, (_, index) =>
      getAssessmentResults(administrationId, first.individuals.items.length + index * 50),
    ),
  )
  return {
    ...first,
    individuals: {
      total: first.individuals.total,
      items: [first, ...pages].flatMap((page) => page.individuals.items),
    },
  }
}

function median(values: number[]) {
  if (!values.length) return 0
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

function EmptyReport({ draft }: { draft: AssessmentDraft }) {
  return <section className="assessment-report-zero" aria-labelledby="report-zero-title">
    <ChartBar aria-hidden="true" />
    <div><p className="assessment-kicker">Report ready</p><h2 id="report-zero-title">No responses yet</h2><p>Publish {draft.title} and collect learner responses. This dashboard will populate automatically.</p></div>
  </section>
}

function needsManualReview(item?: AssessmentItem) {
  if (!item || item.type === 'information') return false
  if (item.type === 'paragraph' || item.manual) return true
  if (item.type === 'short-answer') {
    return !((item.answerKey?.variants as string[] | undefined)?.filter(Boolean).length)
  }
  return false
}

export function AssessmentReportPage({ embedded = false }: { embedded?: boolean }) {
  const { draftId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedView = searchParams.get('view')
  const view: ReportView = requestedView === 'students' || requestedView === 'questions' || requestedView === 'grading' ? requestedView : 'overall'
  const [draft, setDraft] = useState<AssessmentDraft | null>(null)
  const [reportDocument, setReportDocument] = useState<AssessmentDocument | null>(null)
  const [administration, setAdministration] = useState<AssessmentAdministrationSummary | null>(null)
  const [results, setResults] = useState<AssessmentResults | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [excelUrl, setExcelUrl] = useState('')
  const [selectedScoreRange, setSelectedScoreRange] = useState('')
  const [overviewChart, setOverviewChart] = useState<OverviewChart>('scores')
  const [selectedLearnerIndex, setSelectedLearnerIndex] = useState(0)
  const [statusBusy, setStatusBusy] = useState(false)
  const [learnerSearch, setLearnerSearch] = useState('')
  const [gradePoints, setGradePoints] = useState<Record<string, string>>({})
  const [gradeFeedback, setGradeFeedback] = useState<Record<string, string>>({})
  const [gradingBusy, setGradingBusy] = useState(false)

  const selectView = (nextView: ReportView) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (nextView === 'overall') next.delete('view')
      else next.set('view', nextView)
      return next
    })
  }

  useEffect(() => {
    let active = true
    void Promise.all([getAssessmentDraft(draftId), listAssessmentAdministrations()])
      .then(async ([draftResult, administrationResult]) => {
        if (!active) return
        const latest = administrationResult.items.find((item) => item.draftId === draftId) ?? null
        setDraft(draftResult)
        setAdministration(latest)
        if (latest) {
          const [loadedResults, metadata] = await Promise.all([
            loadAllResults(latest.id),
            Promise.resolve(getAssessmentMetadata(latest.publicId)).catch(() => null),
          ])
          if (!active) return
          setResults(loadedResults)
          setReportDocument(metadata?.manifest ?? draftResult.document)
        } else {
          setReportDocument(draftResult.document)
        }
        if (active) setState('ready')
      })
      .catch(() => { if (active) setState('error') })
    return () => { active = false }
  }, [draftId])

  const refreshResults = useCallback(async () => {
    if (!administration || document.visibilityState === 'hidden') return
    setResults(await loadAllResults(administration.id))
  }, [administration])

  useEffect(() => {
    if (!administration) return
    const timer = window.setInterval(() => { void refreshResults() }, 15_000)
    const visible = () => { if (document.visibilityState === 'visible') void refreshResults() }
    document.addEventListener('visibilitychange', visible)
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', visible) }
  }, [administration, refreshResults])

  const draftItems = useMemo(() => draft ? assessmentItems(draft.document) : [], [draft])
  const editableQuestions = useMemo(() => draftItems.filter((item) => item.type !== 'information' && item.type !== 'section-information'), [draftItems])
  const reportItems = useMemo(() => (reportDocument ? assessmentItems(reportDocument) : draftItems).filter((item) => item.type !== 'information' && item.type !== 'section-information'), [draftItems, reportDocument])
  const reportQuestions = reportItems
  const publishedVersionDiffers = Boolean(administration && reportDocument && (
    editableQuestions.length !== reportQuestions.length
    || editableQuestions.some((item, index) => item.id !== reportQuestions[index]?.id)
  ))
  const questions = useMemo(() => {
    const summaries = results?.summary.questions ?? {}
    return reportItems.map((item, index) => ({
      itemId: item.id,
      index,
      item,
      summary: summaries[item.id] ?? { responseCount: 0, scoredCount: 0, averagePoints: '0' },
    }))
  }, [reportItems, results])

  const individuals = useMemo(() => results?.individuals.items ?? [], [results])
  const manualPoints = useMemo(() => new Map<string, number>(
    reportItems.filter((item) => needsManualReview(item)).map((item) => [item.id, number(item.points)]),
  ), [reportItems])
  const completion = percent(results?.summary.completionRate)
  const averagePossible = individuals.length
    ? individuals.reduce((sum, item) => sum + scoredMaximum(item, manualPoints), 0) / individuals.length
    : 0
  const averageEarned = individuals.length
    ? individuals.reduce((sum, item) => sum + scoredPoints(item, manualPoints), 0) / individuals.length
    : 0
  const distribution = useMemo(() => scoreBinsFor(individuals.length).map((bin) => ({ ...bin, value: individuals.filter((item) => {
    const value = scorePercent(item, manualPoints)
    return value >= bin.minimum && value < bin.maximum
  }).length })), [individuals, manualPoints])
  const distributionMax = Math.max(1, ...distribution.map((bin) => bin.value))
  const learnerScores = useMemo(() => individuals.map((item) => ({
    attemptId: item.attemptId,
    name: item.displayName ?? 'Private learner',
    score: scorePercent(item, manualPoints),
    status: item.status,
    points: number(item.points),
    maximumPoints: number(item.maximumPoints),
  })).sort((left, right) => left.score - right.score), [individuals, manualPoints])
  const learnersNeedingSupport = learnerScores.filter((learner) => learner.score < 50)
  const questionDiagnostics = useMemo(() => {
    const cohort = [...individuals].sort((left, right) => scorePercent(left, manualPoints) - scorePercent(right, manualPoints))
    const groupSize = Math.max(1, Math.ceil(cohort.length / 3))
    const lower = cohort.slice(0, groupSize)
    const upper = cohort.slice(-groupSize)
    return questions.map(({ itemId, index, item, summary }) => {
      const possible = Math.max(0, number(item?.points))
      const success = possible > 0 ? Math.min(100, (number(summary.averagePoints) / possible) * 100) : 0
      const groupAverage = (group: typeof cohort) => {
        const values = group.map((learner) => learner.breakdown[itemId]).filter((value): value is string => value !== null && value !== undefined)
        return values.length && possible > 0 ? values.reduce((sum, value) => sum + number(value) / possible, 0) / values.length : 0
      }
      const discrimination = (groupAverage(upper) - groupAverage(lower)) * 100
      const coverage = individuals.length ? Math.min(100, (summary.responseCount / individuals.length) * 100) : 0
      const priority = Math.max(0, 70 - success) + Math.max(0, -discrimination) * 1.5 + Math.max(0, 100 - coverage) * .35
      return { itemId, index, item, summary, possible, success, discrimination, coverage, priority }
    }).sort((left, right) => right.priority - left.priority)
  }, [individuals, manualPoints, questions])
  const scoreValues = learnerScores.map((learner) => learner.score)
  const medianScore = median(scoreValues)
  const dominantBin = distribution.reduce((best, bin) => bin.value > best.value ? bin : best, distribution[0])
  const activeScoreBin = distribution.find((bin) => bin.label === selectedScoreRange) ?? dominantBin
  const questionResponses = useMemo(() => questions.map((question) => {
    const item = question.item
    const answers = individuals.map((learner) => learner.responses[question.itemId]).filter((answer) => answer && Object.keys(answer).length)
    const correctOptions = new Set((item?.answerKey?.optionIds as string[] | undefined) ?? [])
    const optionCounts = new Map((item?.options ?? []).map((option) => [option.id, 0]))
    const textCounts = new Map<string, number>()
    answers.forEach((answer) => {
      if (item?.type === 'multiple-choice') {
        const optionId = String(answer.optionId ?? '')
        if (optionCounts.has(optionId)) optionCounts.set(optionId, (optionCounts.get(optionId) ?? 0) + 1)
      } else if (item?.type === 'checkboxes') {
        const optionIds = Array.isArray(answer.optionIds) ? answer.optionIds.map(String) : []
        optionIds.forEach((optionId) => { if (optionCounts.has(optionId)) optionCounts.set(optionId, (optionCounts.get(optionId) ?? 0) + 1) })
      } else {
        const text = String(answer.text ?? '').trim()
        if (text) textCounts.set(text, (textCounts.get(text) ?? 0) + 1)
      }
    })
    return {
      ...question,
      answers,
      options: (item?.options ?? []).map((option) => ({ ...option, count: optionCounts.get(option.id) ?? 0, correct: correctOptions.has(option.id) })),
      texts: [...textCounts.entries()].sort((left, right) => right[1] - left[1]),
      manualReview: needsManualReview(item),
      correctCount: needsManualReview(item) || number(item?.points) <= 0
        ? null
        : individuals.filter((learner) => {
          const earned = learner.breakdown[question.itemId]
          return earned !== null && earned !== undefined && number(earned) >= number(item?.points)
        }).length,
    }
  }), [individuals, questions])
  const filteredIndividuals = individuals.filter((learner) => (learner.displayName ?? learner.studentId ?? '').toLocaleLowerCase().includes(learnerSearch.trim().toLocaleLowerCase()))
  const selectedLearner = filteredIndividuals[Math.min(selectedLearnerIndex, Math.max(0, filteredIndividuals.length - 1))]
  const gradingQueue = filteredIndividuals.flatMap((learner) => reportItems.filter((item) => needsManualReview(item) && learner.breakdown[item.id] === null).map((item) => ({ learner, item })))
  const saveGrade = async (attemptId: string, item: AssessmentItem, expectedScoreVersion: number | null) => {
    if (!administration || expectedScoreVersion === null) return
    const key = `${attemptId}:${item.id}`
    setGradingBusy(true)
    try {
      await gradeAssessmentResponse(administration.id, { attemptId, itemId: item.id, points: gradePoints[key] ?? '0', feedback: gradeFeedback[key], expectedScoreVersion })
      await refreshResults()
    } finally { setGradingBusy(false) }
  }
  const toggleResponses = async () => {
    if (!administration || statusBusy) return
    const target = administration.status === 'open' ? 'closed' : 'open'
    setStatusBusy(true)
    try {
      await setAssessmentAdministrationStatus(administration.id, administration.status, target)
      setAdministration((current) => current ? { ...current, status: target } : current)
    } finally {
      setStatusBusy(false)
    }
  }

  useEffect(() => {
    let active = true
    let objectUrl = ''
    if (!draft || !individuals.length) {
      setExcelUrl('')
      return () => { active = false }
    }
    const metadataKeys = [...new Set(individuals.flatMap((item) => Object.keys(item.metadata ?? {})))].sort()
    const headings = ['Student ID', 'First name', 'Surname', 'Display name', 'Group', 'Subgroup', 'Email', ...metadataKeys, 'Status', 'Points', 'Maximum points', 'Score percent']
    void import('write-excel-file').then(({ default: writeXlsxFile }) => writeXlsxFile([
      headings.map((value) => ({ value, fontWeight: 'bold' as const })),
      ...individuals.map((item) => [
        { value: item.studentId ?? '' },
        { value: item.firstName ?? '' },
        { value: item.lastName ?? '' },
        { value: item.displayName ?? 'Private learner' },
        { value: item.group ?? '' },
        { value: item.subgroup ?? '' },
        { value: item.email ?? '' },
        ...metadataKeys.map((key) => ({ value: item.metadata?.[key] ?? '' })),
        { value: item.status.replaceAll('_', ' ') },
        { value: scoredPoints(item, manualPoints), type: Number },
        { value: scoredMaximum(item, manualPoints), type: Number },
        { value: scorePercent(item, manualPoints) / 100, type: Number, format: '0%' },
      ]),
    ], { sheet: 'Individual results' })).then((workbook) => {
      if (typeof URL.createObjectURL !== 'function') {
        if (active) setExcelUrl('data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,')
        return
      }
      objectUrl = URL.createObjectURL(workbook)
      if (active) setExcelUrl(objectUrl)
      else URL.revokeObjectURL(objectUrl)
    })
    return () => {
      active = false
      if (objectUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(objectUrl)
    }
  }, [draft, individuals, manualPoints])

  const visualSvg = (() => {
    if (!draft) return ''
    const width = 1200
    const exportHeight = 760
    const averageScore = Math.round(averageEarned / Math.max(1, averagePossible) * 100)
    const circumference = 2 * Math.PI * 82
    const escapeXml = (value: string) => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;')
    const bars = distribution.map((bin, index) => {
      const x = 410 + index * 142
      const valueHeight = Math.max(8, (bin.value / distributionMax) * 160)
      const isPeak = bin.value === distributionMax
      return `<rect x="${x}" y="${350 - valueHeight}" width="112" height="${valueHeight}" rx="8" fill="${isPeak ? '#43845e' : '#cb765d'}"/><text x="${x + 56}" y="${326 - valueHeight}" text-anchor="middle" fill="#181512" font-family="Arial" font-size="18" font-weight="700">${bin.value}</text><text x="${x + 56}" y="382" text-anchor="middle" fill="#6d665e" font-family="Arial" font-size="14">${bin.label}</text>`
    }).join('')
    const questionBars = [...questionDiagnostics].sort((left, right) => left.index - right.index).slice(0, 6).map((question, index) => {
      const x = 80 + index * 172
      const height = Math.max(5, question.success * 1.35)
      return `<rect x="${x}" y="${650 - height}" width="132" height="${height}" rx="7" fill="${question.success >= 70 ? '#43845e' : '#cb765d'}"/><text x="${x + 66}" y="675" text-anchor="middle" fill="#6d665e" font-family="Arial" font-size="13">Q${question.index + 1} · ${Math.round(question.success)}%</text>`
    }).join('')
    const support = learnersNeedingSupport.length
      ? `<rect x="64" y="432" width="1072" height="74" rx="12" fill="#fff0ee" stroke="#b9473f"/><text x="88" y="462" fill="#b9473f" font-family="Arial" font-size="13" font-weight="700">${learnersNeedingSupport.length} NEED SUPPORT</text><text x="88" y="488" fill="#6d3f3a" font-family="Arial" font-size="15">Below 50% · ${results?.summary.responses ?? 0} responses · ${Math.round(completion)}% completion</text>`
      : `<text x="64" y="472" fill="#43845e" font-family="Arial" font-size="16" font-weight="700">No learners below the 50% support threshold</text>`
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${exportHeight}" viewBox="0 0 ${width} ${exportHeight}"><rect width="1200" height="760" rx="20" fill="#faf8f4"/><text x="64" y="54" fill="#c86749" font-family="Arial" font-size="14" font-weight="700" letter-spacing="2">ASSESSMENT REPORT</text><text x="64" y="104" fill="#181512" font-family="Georgia" font-size="36">${escapeXml(draft.title)}</text><line x1="64" y1="132" x2="1136" y2="132" stroke="#ded7cf"/><circle cx="210" cy="280" r="82" fill="none" stroke="#eee8e1" stroke-width="20"/><circle cx="210" cy="280" r="82" fill="none" stroke="#43845e" stroke-width="20" stroke-linecap="round" transform="rotate(-90 210 280)" stroke-dasharray="${circumference}" stroke-dashoffset="${circumference * (1 - averageScore / 100)}"/><text x="210" y="291" text-anchor="middle" fill="#181512" font-family="Georgia" font-size="48">${averageScore}%</text><text x="210" y="390" text-anchor="middle" fill="#6d665e" font-family="Arial" font-size="14">AVERAGE SCORE</text><text x="410" y="178" fill="#181512" font-family="Georgia" font-size="28">Score distribution</text>${bars}${support}<text x="64" y="552" fill="#181512" font-family="Georgia" font-size="28">Question performance</text>${questionBars}<text x="64" y="730" fill="#6d665e" font-family="Arial" font-size="13">PathLab · ${new Date().toLocaleDateString()}</text></svg>`
  })()

  const renderQuestionResponse = (question: (typeof questionResponses)[number]) => {
    const diagnostic = questionDiagnostics.find((entry) => entry.itemId === question.itemId)
    const possible = Math.max(0, number(question.item?.points))
    const average = possible ? Math.round((number(question.summary.averagePoints) / possible) * 100) : 0
    const responseTotal = Math.max(1, question.answers.length || question.summary.responseCount)
    const hasOptions = question.options.length > 0
    const heatmap = question.summary.spatialHeatmap
    const heatmapMaximum = Math.max(1, ...(heatmap?.counts.flat() ?? [0]))
    const keyedRegion = (question.item?.answerKey?.regions as Array<{ kind?: string, x: number, y: number, width?: number, height?: number }> | undefined)?.[0]
    const slidePreview = question.item?.slideId
      ? `/api/v1/admin/slides/${encodeURIComponent(question.item.slideId)}/preview/thumbnail.jpg`
      : null
    return <article id={`assessment-question-${question.itemId}`} key={question.itemId} className={`assessment-response-question-card assessment-response-question-card--${question.item?.type ?? 'unknown'}${question.manualReview ? ' is-manual-review' : ''}`}>
      <header>
        <div><span>Question {question.index + 1}</span><h3>{question.item?.prompt || `Question ${question.index + 1}`}</h3></div>
        <dl><div><dt>Responses</dt><dd>{question.summary.responseCount}</dd></div>{question.item?.type !== 'information' ? <><div><dt>{question.manualReview ? 'Scoring' : 'Average'}</dt><dd>{question.manualReview ? 'Manual review' : `${average}%`}</dd></div><div><dt>Weight</dt><dd>{possible} {possible === 1 ? 'point' : 'points'}</dd></div></> : <div><dt>Type</dt><dd>Information</dd></div>}</dl>
      </header>
      {hasOptions ? <div className="assessment-response-option-chart" role="list" aria-label={`Answer distribution for question ${question.index + 1}`}>
        {question.options.map((option) => {
          const share = Math.round((option.count / responseTotal) * 100)
          return <div key={option.id} role="listitem" className={option.correct ? 'is-correct' : ''}>
            <span>{option.label}{option.correct ? <em>Correct</em> : null}</span>
            <div aria-hidden="true"><i style={{ width: `${share}%` }} /></div>
            <strong>{option.count} <small>({share}%)</small></strong>
          </div>
        })}
      </div> : question.item?.type === 'diagnostic-field' && heatmap ? <div className="assessment-response-spatial-chart" role="img" aria-label={`Spatial response heatmap for question ${question.index + 1}`}><div className="assessment-response-wsi-field" style={{ gridTemplateColumns: `repeat(${heatmap.width}, 1fr)` }}>{slidePreview ? <img src={slidePreview} alt="Assessment slide thumbnail" /> : null}{heatmap.counts.flat().map((count, index) => <i key={index} style={{ opacity: count ? .18 + count / heatmapMaximum * .72 : 0 }} />)}{keyedRegion ? <b className="assessment-response-answer-region" style={{ left: `${keyedRegion.x * 100}%`, top: `${keyedRegion.y * 100}%`, width: `${(keyedRegion.width ?? .08) * 100}%`, height: `${(keyedRegion.height ?? .08) * 100}%` }}><span>Authored answer region</span></b> : null}</div><div className="assessment-response-spatial-key"><strong>{question.summary.responseCount} marked regions</strong><span>{Object.keys(question.summary.diagnosticLabels ?? {}).length ? `Learner labels: ${Object.keys(question.summary.diagnosticLabels ?? {}).join(', ')}` : 'No diagnostic labels submitted'}</span><small>Protected teacher analytics</small></div></div>
        : question.texts.length ? <div className="assessment-response-text-list" role="list" aria-label={`Text responses for question ${question.index + 1}`}>
          {question.texts.slice(0, 6).map(([answer, count]) => <div key={answer} role="listitem"><q>{answer}</q>{count > 1 ? <span>{count}</span> : null}</div>)}
          {question.texts.length > 6 ? <p>+{question.texts.length - 6} unique answers</p> : null}
        </div> : question.item?.type === 'information' ? <div className="assessment-response-information"><span aria-hidden="true">i</span><p>Reference content shown to learners. It has no score or response chart.</p></div>
          : question.manualReview ? <div className="assessment-response-manual"><strong>Awaiting review</strong><p>This response type has no configured answer key, so PathLab does not assign an automatic score.</p></div>
            : <div className="assessment-response-score-summary"><div><span>Average</span><strong>{average}%</strong></div><div role="img" aria-label={`${average}% average score`}><i style={{ width: `${average}%` }} /></div><p>{diagnostic ? `${Math.round(diagnostic.coverage)}% answered` : 'Awaiting graded responses'}</p></div>}
    </article>
  }

  if (state === 'loading') return <>{embedded ? null : <AssessmentToolbar title="Assessment report" />}<main className="assessment-main"><p role="status">Loading assessment report…</p></main></>
  if (state === 'error' || !draft) return <>{embedded ? null : <AssessmentToolbar title="Assessment report" />}<main className="assessment-main"><section className="assessment-report-zero" role="alert"><ChartBar aria-hidden="true" /><div><h1>Report unavailable</h1><p>The assessment report could not be loaded.</p></div></section></main></>

  return <>
    {embedded ? null : <AssessmentToolbar title="Assessment report" />}
    <main className={`assessment-main assessment-report-page assessment-responses-page${embedded ? ' assessment-report-page--embedded' : ''}`}>
      {embedded ? null : <Link className="assessment-report-back" to="/admin/assessments"><ArrowLeft aria-hidden="true" /> Assessments</Link>}
      <header className="assessment-responses-header">
        <div><h1>{draft.title.replace(/[—–]/g, '-')}</h1><p>{administration ? `${administration.mode.replaceAll('_', ' ')} / ${reportQuestions.length} questions / version ${administration.version}` : `${reportQuestions.length} questions / unpublished`}</p></div>
        <div className="assessment-responses-header-actions">{learnersNeedingSupport.length ? <aside className="assessment-response-support" aria-label="Learners needing support"><UsersThree aria-hidden="true" /><strong>{learnersNeedingSupport.length}</strong><span>below 50%</span><button type="button" onClick={() => selectView('students')}>Review</button></aside> : null}<aside className={`assessment-response-status is-${administration?.status ?? 'draft'}`}><span aria-hidden="true" /><div><strong>{administration?.status === 'open' ? 'Active' : administration?.status === 'closed' ? 'Closed' : 'Draft'}</strong><small>{administration ? `${administration.completedParticipants} of ${administration.expectedParticipants ?? administration.completedParticipants} learners completed` : 'Not accepting responses'}</small></div>{administration && administration.status !== 'draft' ? <button type="button" role="switch" aria-checked={administration.status === 'open'} aria-label="Accepting responses" disabled={statusBusy} onClick={() => void toggleResponses()}><i /></button> : null}</aside></div>
      </header>
      {publishedVersionDiffers ? <p className="assessment-report-version-note">Showing published version {administration?.version} with {reportQuestions.length} questions. The editable draft currently has {editableQuestions.length} questions.</p> : null}

      <div className="assessment-responses-navigation">
        <nav className="assessment-responses-tabs" aria-label="Response views">
          <button type="button" aria-current={view === 'overall' ? 'page' : undefined} onClick={() => selectView('overall')}>Summary</button>
          <button type="button" aria-current={view === 'questions' ? 'page' : undefined} onClick={() => selectView('questions')}>Questions</button>
          <button type="button" aria-current={view === 'students' ? 'page' : undefined} onClick={() => selectView('students')}>Individuals</button>
          <button type="button" aria-current={view === 'grading' ? 'page' : undefined} onClick={() => selectView('grading')}>Needs grading {results?.summary.needsGrading ? `(${results.summary.needsGrading})` : ''}</button>
        </nav>
        <div className="assessment-report-export-actions" aria-label="Export report">
          {administration ? <a href={`/api/v2/admin/assessment/administrations/${encodeURIComponent(administration.id)}/export.csv`} download><DownloadSimple aria-hidden="true" /> CSV</a> : null}
          {excelUrl ? <a href={excelUrl} download={`${fileStem(draft.title)}.xlsx`}><FileXls aria-hidden="true" /> Excel</a> : <button type="button" disabled><FileXls aria-hidden="true" /> Excel</button>}
          <a href={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(visualSvg)}`} download={`${fileStem(draft.title)}-visual-report.svg`}><ImageSquare aria-hidden="true" /> Visual</a>
        </div>
      </div>

      {!results ? <EmptyReport draft={draft} /> : null}

      {results && view === 'overall' ? <div className="assessment-responses-summary">
        <section className="assessment-responses-overview" aria-label="Response overview">
          <div className="assessment-response-average"><div className="assessment-response-score-ring" role="img" aria-label={`${Math.round(averageEarned / Math.max(1, averagePossible) * 100)}% average score`}><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="50" /><circle cx="60" cy="60" r="50" pathLength="100" style={{ strokeDasharray: `${Math.round(averageEarned / Math.max(1, averagePossible) * 100)} 100` }} /></svg><strong>{Math.round(averageEarned / Math.max(1, averagePossible) * 100)}%</strong></div><dl><div><dt>Points</dt><dd>{formatPoints(averageEarned)} / {averagePossible ? formatPoints(averagePossible) : '—'}</dd></div><div><dt>Median</dt><dd>{Math.round(medianScore)}%</dd></div><div><dt>Responses</dt><dd>{results.summary.responses}</dd></div></dl></div>
          <div className="assessment-response-distribution"><header><h2>{overviewChart === 'scores' ? 'Score distribution' : 'Question performance'}</h2><div className="assessment-response-chart-toggle" aria-label="Overview chart"><button type="button" aria-pressed={overviewChart === 'scores'} onClick={() => setOverviewChart('scores')}>Scores</button><button type="button" aria-pressed={overviewChart === 'questions'} onClick={() => setOverviewChart('questions')}>Questions</button></div></header>{overviewChart === 'scores' ? <div className="assessment-response-score-bars">{distribution.map((bin) => <button key={bin.label} type="button" className={bin.value === distributionMax ? 'is-peak' : ''} aria-label={`${bin.label}: ${bin.value} learners`} aria-pressed={activeScoreBin.label === bin.label} onClick={() => setSelectedScoreRange(bin.label)}><strong>{bin.value}</strong><i style={{ height: `${Math.max(4, bin.value / distributionMax * 100)}%` }} /><span>{bin.label}</span></button>)}</div> : <><div className="assessment-response-question-bars">{questionResponses.filter((question) => question.item?.type !== 'information').map((question) => <button key={question.itemId} type="button" aria-label={`Question ${question.index + 1}: ${question.summary.responseCount} answered${question.correctCount === null ? ', manual review' : `, ${question.correctCount} correct`}`} onClick={() => document.getElementById(`assessment-question-${question.itemId}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })}><span className="assessment-question-bar-values"><i className="is-answered" style={{ height: `${Math.max(4, question.summary.responseCount / Math.max(1, individuals.length) * 100)}%` }} />{question.correctCount === null ? <i className="is-review" /> : <i className="is-correct" style={{ height: `${Math.max(4, question.correctCount / Math.max(1, individuals.length) * 100)}%` }} />}</span><strong>Q{question.index + 1}</strong><small>{question.correctCount === null ? 'Review' : `${question.correctCount}/${question.summary.responseCount}`}</small></button>)}</div><footer className="assessment-response-chart-legend"><span><i className="is-answered" />Answered</span><span><i className="is-correct" />Correct</span><span><i className="is-review" />Manual review</span></footer></>}</div>
        </section>
      </div> : null}

      {results && view === 'questions' ? <section className="assessment-response-question-stack" aria-label="Question response summaries">{questionResponses.map((question) => renderQuestionResponse(question))}</section> : null}

      {results && view === 'students' ? <section className="assessment-response-individual" aria-labelledby="individual-response-title">
        <header><div><h2 id="individual-response-title">Individual response</h2><p>Review every answer from one learner without losing the assessment context.</p></div><div className="assessment-response-learner-picker"><label className="assessment-response-learner-search"><span className="visually-hidden">Search learners</span><input type="search" aria-label="Search learners" placeholder="Search learners" value={learnerSearch} onChange={(event) => { setLearnerSearch(event.target.value); setSelectedLearnerIndex(0) }} /></label><button type="button" aria-label="Previous learner" disabled={selectedLearnerIndex <= 0 || !filteredIndividuals.length} onClick={() => setSelectedLearnerIndex((value) => Math.max(0, value - 1))}><CaretLeft aria-hidden="true" /></button><select aria-label="Select learner" value={filteredIndividuals.length ? Math.min(selectedLearnerIndex, filteredIndividuals.length - 1) : ''} disabled={!filteredIndividuals.length} onChange={(event) => setSelectedLearnerIndex(Number(event.target.value))}>{filteredIndividuals.map((learner, index) => <option key={learner.attemptId} value={index}>{learner.displayName ?? `Learner ${index + 1}`}</option>)}</select><button type="button" aria-label="Next learner" disabled={!filteredIndividuals.length || selectedLearnerIndex >= filteredIndividuals.length - 1} onClick={() => setSelectedLearnerIndex((value) => Math.min(filteredIndividuals.length - 1, value + 1))}><CaretRight aria-hidden="true" /></button></div></header>
        {selectedLearner ? <><article className="assessment-response-learner-summary"><div><span>{selectedLearner.displayName?.slice(0, 1) ?? 'L'}</span><div><strong>{selectedLearner.displayName ?? 'Private learner'}</strong><small>{selectedLearner.status.replaceAll('_', ' ')}</small></div></div><p><strong>{formatPoints(scoredPoints(selectedLearner, manualPoints))} / {formatPoints(scoredMaximum(selectedLearner, manualPoints))}</strong><span>{Math.round(scorePercent(selectedLearner, manualPoints))}% score</span></p></article><div className="assessment-response-answer-stack">{questionResponses.map((question) => {
          const response = selectedLearner.responses[question.itemId] ?? {}
          const selectedIds = response.optionId ? [String(response.optionId)] : Array.isArray(response.optionIds) ? response.optionIds.map(String) : []
          const answerText = selectedIds.length
            ? question.options.filter((option) => selectedIds.includes(option.id)).map((option) => option.label).join(', ')
            : String(response.text ?? response.diagnosis ?? '').trim()
              || (response.selection || response.kind ? 'Spatial selection recorded' : 'No answer')
          const points = selectedLearner.breakdown[question.itemId]
          return <article key={question.itemId}><header><span>Question {question.index + 1}</span><strong>{points ?? '—'} / {question.item?.points ?? '—'} pts</strong></header><h3>{question.item?.prompt || `Question ${question.index + 1}`}</h3><p className={answerText === 'No answer' ? 'is-empty' : ''}>{answerText}</p></article>
        })}</div></> : <p>No learner responses are available.</p>}
      </section> : null}

      {results && view === 'grading' ? <section className="assessment-grading-workspace" aria-labelledby="grading-title"><header><div><h2 id="grading-title">Needs grading</h2><p>{gradingQueue.length} responses require a teacher decision.</p></div><label>Search learners<input type="search" value={learnerSearch} onChange={(event) => setLearnerSearch(event.target.value)} /></label><button type="button" onClick={() => void refreshResults()}>Refresh</button></header>{gradingQueue.length ? <ol>{gradingQueue.map(({ learner, item }, index) => { const key = `${learner.attemptId}:${item.id}`; const response = learner.responses[item.id] ?? {}; return <li key={key}><header><span>{index + 1} of {gradingQueue.length}</span><strong>{learner.displayName ?? learner.studentId ?? 'Private learner'}</strong></header><h3>{item.prompt}</h3><blockquote>{String(response.text ?? response.diagnosis ?? 'No answer')}</blockquote><div><label>Points<input type="number" min="0" max={item.points ?? '0'} step="0.001" value={gradePoints[key] ?? ''} onChange={(event) => setGradePoints((current) => ({ ...current, [key]: event.target.value }))} /></label><label>Feedback<textarea maxLength={4000} value={gradeFeedback[key] ?? ''} onChange={(event) => setGradeFeedback((current) => ({ ...current, [key]: event.target.value }))} /></label><button className="assessment-primary" type="button" disabled={gradingBusy || !gradePoints[key]} onClick={() => void saveGrade(learner.attemptId, item, learner.scoreVersion)}>Save & next</button></div></li>})}</ol> : <div className="assessment-report-zero"><CheckCircle aria-hidden="true" /><div><h3>Grading complete</h3><p>No responses match the current queue.</p></div></div>}</section> : null}
    </main>
  </>
}
