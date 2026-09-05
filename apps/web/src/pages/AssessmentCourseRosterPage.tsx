import { ArrowLeft, CaretDown, CaretLeft, CaretRight, CaretUp, CaretUpDown, CloudArrowUp, DownloadSimple, FileCsv, FileXls, MagnifyingGlass, PencilSimple, Plus, Trash, UploadSimple, UserList, UserMinus, UserPlus, UsersThree, X } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { assessmentCourseRosterExportUrl, AssessmentHttpError, commitAssessmentCourseRoster, getAssessmentCourse, listAllAssessmentCourseRoster, listAssessmentCourseRoster, previewAssessmentCourseRoster, removeAllAssessmentCourseLearners, type AssessmentRosterColumn, type AssessmentRosterLearner, type AssessmentRosterLearnerInput, type AssessmentRosterSort, type AssessmentRosterWarning, updateAssessmentCourseEnrollment, updateAssessmentCourseLearner } from '../assessment/api'
import { downloadRosterCsvTemplate, downloadRosterExcel, downloadRosterExcelTemplate, parseRosterFile, ROSTER_COLUMNS } from '../assessment/rosterFiles'
import { AssessmentToolbar } from '../components/assessment/AssessmentChrome'
import './assessment.css'

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const
const DEFAULT_PAGE_SIZE = 25
const exampleRows = 'student_id,first_name,last_name,group,subgroup,other_information\n66001234,กัญญา,วัฒนกุล,Year 3,Lab A,Exchange student'
type MetadataRow = { id: number; key: string; value: string }
let metadataRowId = 0

function importError(error: unknown) {
  if (error instanceof AssessmentHttpError) {
    const code = error.detail.code
    if (code === 'ASSESSMENT_ROSTER_HEADER_REQUIRED') return 'The first row must contain the template column headings.'
    if (code === 'ASSESSMENT_ROSTER_NAME_COLUMNS_REQUIRED') return 'Add the required first_name column.'
    if (code === 'ASSESSMENT_ROSTER_REQUIRED_VALUE') return 'Every row needs a student ID and given name.'
    if (code === 'ASSESSMENT_ROSTER_LIMIT') return 'A roster import can contain up to 5,000 learners.'
    if (code === 'ASSESSMENT_ROSTER_INVALID') return 'Check for duplicate student IDs or malformed rows.'
    if (code === 'ASSESSMENT_ROSTER_CONFIRMATION_REQUIRED') return 'The roster changed while you were reviewing it. Please validate it again.'
  }
  return error instanceof Error ? error.message : 'The roster could not be imported.'
}

export function AssessmentCourseRosterPage() {
  const { courseId = '' } = useParams()
  const [course, setCourse] = useState({ name: 'Course', code: 'course' })
  const [learners, setLearners] = useState<AssessmentRosterLearner[]>([])
  const [columns, setColumns] = useState<AssessmentRosterColumn[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [query, setQuery] = useState('')
  const [sortBy, setSortBy] = useState<AssessmentRosterSort>('name')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [rows, setRows] = useState('')
  const [fileName, setFileName] = useState('')
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState<AssessmentRosterWarning[]>([])
  const [warningCount, setWarningCount] = useState(0)
  const [pendingChecksum, setPendingChecksum] = useState('')
  const [editingLearner, setEditingLearner] = useState<AssessmentRosterLearner | null>(null)
  const [editForm, setEditForm] = useState<AssessmentRosterLearnerInput | null>(null)
  const [metadataRows, setMetadataRows] = useState<MetadataRow[]>([])
  const [showRemoveAll, setShowRemoveAll] = useState(false)

  const refresh = useCallback(async (nextOffset = offset, nextQuery = query, nextSortBy = sortBy, nextSortDirection = sortDirection, nextPageSize = pageSize) => {
    const roster = await listAssessmentCourseRoster(courseId, { limit: nextPageSize, offset: nextOffset, query: nextQuery, sortBy: nextSortBy, sortDirection: nextSortDirection })
    setLearners(roster.items); setColumns(roster.columns ?? []); setTotal(roster.total); setOffset(nextOffset)
  }, [courseId, offset, pageSize, query, sortBy, sortDirection])
  useEffect(() => { void getAssessmentCourse(courseId).then((value) => setCourse({ name: value.name, code: value.courseCode })); void refresh(0, '') }, [courseId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function chooseFile(file: File) {
    setBusy(true); setError(''); setMessage(''); setWarnings([]); setPendingChecksum('')
    try { setRows(await parseRosterFile(file)); setFileName(file.name); setMessage(`${file.name} is ready to import.`) }
    catch (caught) { setError(importError(caught)); setFileName(''); setRows('') }
    finally { setBusy(false) }
  }
  async function importRoster() {
    if (!rows.trim()) return
    setBusy(true); setError(''); setMessage('Checking every row…')
    try {
      const preview = await previewAssessmentCourseRoster(courseId, rows)
      if (preview.warningCount) {
        setWarnings(preview.warnings); setWarningCount(preview.warningCount); setPendingChecksum(preview.checksum)
        setMessage(`${preview.validCount.toLocaleString()} valid rows found. Review ${preview.warningCount.toLocaleString()} possible ${preview.warningCount === 1 ? 'match' : 'matches'} before adding.`)
        return
      }
      await commitPreparedRoster(preview.checksum, false)
    } catch (caught) { setMessage(''); setError(importError(caught)) } finally { setBusy(false) }
  }
  async function commitPreparedRoster(checksum: string, confirmWarnings: boolean) {
    const result = await commitAssessmentCourseRoster(courseId, rows, checksum, confirmWarnings)
    setMessage(`${result.created.toLocaleString()} new ${result.created === 1 ? 'learner' : 'learners'} added.${result.skipped ? ` ${result.skipped.toLocaleString()} already in the roster and skipped.` : ''}`)
    setRows(''); setFileName(''); setWarnings([]); setWarningCount(0); setPendingChecksum(''); await refresh(0, query)
  }
  async function confirmImport() {
    if (!pendingChecksum) return
    setBusy(true); setError('')
    try { await commitPreparedRoster(pendingChecksum, true) }
    catch (caught) { setError(importError(caught)) }
    finally { setBusy(false) }
  }
  async function toggle(learner: AssessmentRosterLearner) {
    const status = learner.status === 'active' ? 'withdrawn' : 'active'
    await updateAssessmentCourseEnrollment(courseId, learner.id, status)
    setLearners((current) => current.map((item) => item.id === learner.id ? { ...item, status } : item))
  }
  function openEditor(learner: AssessmentRosterLearner) {
    setEditingLearner(learner)
    setEditForm({ studentId: learner.studentId ?? '', firstName: learner.firstName ?? '', lastName: learner.lastName ?? '', group: learner.group ?? '', subgroup: learner.subgroup ?? '', email: learner.email ?? '', metadata: learner.metadata })
    setMetadataRows(Object.entries(learner.metadata).map(([key, value]) => ({ id: ++metadataRowId, key, value })))
    setError('')
  }
  function closeEditor() { setEditingLearner(null); setEditForm(null); setMetadataRows([]) }
  async function saveLearner() {
    if (!editingLearner || !editForm || !editForm.studentId.trim() || !editForm.firstName.trim()) return
    const metadata = Object.fromEntries(metadataRows.map((row) => [row.key.trim(), row.value.trim()]).filter(([key]) => key))
    setBusy(true); setError('')
    try {
      await updateAssessmentCourseLearner(courseId, editingLearner.id, { ...editForm, studentId: editForm.studentId.trim(), firstName: editForm.firstName.trim(), lastName: editForm.lastName.trim(), group: editForm.group.trim(), subgroup: editForm.subgroup.trim(), email: editForm.email.trim(), metadata })
      closeEditor(); setMessage('Learner information updated.'); await refresh(offset, query)
    } catch (caught) {
      setError(caught instanceof AssessmentHttpError && caught.detail.code === 'ASSESSMENT_STUDENT_ID_EXISTS' ? 'That student ID is already in use.' : importError(caught))
    } finally { setBusy(false) }
  }
  async function removeAllLearners() {
    setBusy(true); setError('')
    try {
      const result = await removeAllAssessmentCourseLearners(courseId)
      setShowRemoveAll(false); setMessage(`${result.removed.toLocaleString()} ${result.removed === 1 ? 'learner' : 'learners'} removed from this course.`); await refresh(0, '')
    } catch (caught) { setError(importError(caught)) }
    finally { setBusy(false) }
  }
  async function exportExcel() { setBusy(true); try { await downloadRosterExcel(course.code, await listAllAssessmentCourseRoster(courseId)) } finally { setBusy(false) } }
  async function search(value: string) { setQuery(value); await refresh(0, value) }
  async function changePageSize(value: string) {
    const nextPageSize = Number(value)
    setPageSize(nextPageSize)
    await refresh(0, query, sortBy, sortDirection, nextPageSize)
  }
  async function sort(column: AssessmentRosterSort) {
    const direction = sortBy === column && sortDirection === 'asc' ? 'desc' : 'asc'
    setSortBy(column); setSortDirection(direction); await refresh(0, query, column, direction)
  }
  const sortHeading = (label: string, column: AssessmentRosterSort) => <button type="button" onClick={() => void sort(column)}>{label}<span aria-hidden="true">{sortBy !== column ? <CaretUpDown /> : sortDirection === 'asc' ? <CaretUp /> : <CaretDown />}</span></button>
  const columnSort = (column: AssessmentRosterColumn): AssessmentRosterSort | null => column.sortable && ['student_id', 'name', 'group', 'subgroup', 'email', 'status'].includes(column.key) ? column.key as AssessmentRosterSort : null
  const cellValue = (column: AssessmentRosterColumn, learner: AssessmentRosterLearner) => {
    if (column.key === 'student_id') return <strong>{learner.studentId || '—'}</strong>
    if (column.key === 'name') return <strong>{learner.firstName || '—'} {learner.lastName || ''}</strong>
    if (column.key === 'group') return learner.group || '—'
    if (column.key === 'subgroup') return learner.subgroup || '—'
    if (column.key === 'email') return learner.email || '—'
    if (column.key === 'status') return <span className={`assessment-status assessment-status--${learner.status === 'active' ? 'open' : 'closed'}`}>{learner.status}</span>
    if (column.key.startsWith('metadata:')) return learner.metadata[column.key.slice(9)] || '—'
    return '—'
  }

  return <><AssessmentToolbar title="Course roster" /><div className="assessment-main assessment-roster-page">
    <Link className="assessment-back-link" to={`/admin/assessments/courses/${courseId}`}><ArrowLeft aria-hidden="true" /> {course.name}</Link>
    <header className="assessment-page-header"><div><p className="assessment-kicker">Shared enrollment</p><h1>Course roster</h1><p>Import once, then assign learners to classes.</p></div></header>
    <section className="assessment-roster-import" aria-labelledby="import-heading"><div className="assessment-roster-import-intro"><UserList aria-hidden="true" /><div><h2 id="import-heading">Import learners</h2><p>Add learners from a spreadsheet or a copied table.</p></div></div>
      <ol className="assessment-import-progress" aria-label="Roster import steps"><li><i aria-hidden="true">1</i><strong>Template</strong></li><li><i aria-hidden="true">2</i><strong>Add learners</strong></li><li><i aria-hidden="true">3</i><strong>Upload</strong></li></ol>
      <div className="assessment-import-start">
        <aside className="assessment-template-help" aria-labelledby="template-help-heading"><h3 id="template-help-heading">Template</h3><p>Download a blank roster and add your learners.</p><div className="assessment-template-actions"><button type="button" onClick={() => downloadRosterCsvTemplate()}><FileCsv /><b>CSV template</b></button><button type="button" onClick={() => void downloadRosterExcelTemplate()}><FileXls /><b>Excel template</b></button></div><small>Works with Excel, Numbers, and Google Sheets.</small></aside>
        <div className="assessment-import-upload"><h3>Upload your roster</h3><p>Excel, CSV, or TSV</p><label className={`assessment-roster-dropzone${dragging ? ' is-dragging' : ''}`} onDragEnter={(event) => { event.preventDefault(); setDragging(true) }} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false) }} onDrop={(event) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) void chooseFile(file) }}><CloudArrowUp aria-hidden="true" /><strong>{fileName || 'Drop a file here'}</strong><span>{fileName ? 'Choose another file' : 'or choose from your computer'}</span><input type="file" accept=".xlsx,.csv,.tsv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,text/tab-separated-values" onChange={(event) => { const file = event.target.files?.[0]; if (file) void chooseFile(file) }} /></label></div>
      </div>
      <div className="assessment-import-help">
        <details className="assessment-column-help"><summary><span>What should my file contain?</span><small>2 required columns</small></summary><div><p>Every learner needs a student ID and given name. Everything else is optional.</p><div className="assessment-column-guide">{ROSTER_COLUMNS.map((column) => <span className={column.required ? 'is-required' : undefined} key={column.key}><code>{column.key}{column.required ? <i aria-label="required">*</i> : null}</code><small>{column.required ? 'Required' : 'Optional'}</small></span>)}</div><p className="assessment-adaptive-column-note">You can add extra columns. PathLab keeps them with each learner.</p></div></details>
        <details className="assessment-paste-roster"><summary>Paste rows instead</summary><p>Copy the table from your spreadsheet and include the header row.</p><textarea rows={6} value={rows} placeholder={exampleRows} aria-label="Roster rows with student ID, given name, surname, group, subgroup, and adaptive information" onChange={(event) => { setRows(event.target.value); setFileName('Pasted rows'); setMessage(''); setWarnings([]); setPendingChecksum('') }} /></details>
      </div>
      {pendingChecksum ? <div className="assessment-roster-warning" role="region" aria-labelledby="roster-warning-heading"><div><strong id="roster-warning-heading">Check possible matches</strong><p>Names can legitimately repeat. Confirm only after checking the student IDs and identifiers below. Existing roster entries will be skipped, not overwritten.</p></div><ul>{warnings.slice(0, 5).map((warning, index) => <li key={`${warning.code}-${warning.studentId}-${index}`}>{warning.message}{warning.matchedStudentId ? <small>Existing ID: {warning.matchedStudentId}</small> : null}</li>)}</ul>{warningCount > warnings.slice(0, 5).length ? <p>And {(warningCount - warnings.slice(0, 5).length).toLocaleString()} more possible matches.</p> : null}<div><button type="button" onClick={() => { setWarnings([]); setWarningCount(0); setPendingChecksum(''); setMessage('Import cancelled. Your file is still ready to review.') }}>Cancel</button><button className="assessment-primary" type="button" disabled={busy} onClick={() => void confirmImport()}>{busy ? 'Adding…' : 'Confirm and add new learners'}</button></div></div> : null}
      <div className="assessment-import-footer"><div aria-live="polite">{error ? <p className="assessment-import-error" role="alert">{error}</p> : message ? <p>{message}</p> : <p>Your file is checked before anything is added.</p>}</div><button className="assessment-primary" type="button" disabled={busy || !rows.trim() || Boolean(pendingChecksum)} onClick={() => void importRoster()}><UploadSimple /> {busy ? 'Working…' : 'Import roster'}</button></div>
    </section>
    <section className="assessment-roster-table" aria-labelledby="roster-heading"><header className="assessment-roster-table-header"><div><UsersThree aria-hidden="true" /><span><h2 id="roster-heading">Enrolled learners</h2><p>{total.toLocaleString()} matching learners</p></span></div><div className="assessment-roster-actions"><a href={assessmentCourseRosterExportUrl(courseId)} download><DownloadSimple /> Export CSV</a><button type="button" disabled={busy} onClick={() => void exportExcel()}><FileXls /> Export Excel</button><button className="assessment-danger-action" type="button" disabled={busy || total === 0} onClick={() => setShowRemoveAll(true)}><Trash /> Remove all</button></div></header>
      <label className="assessment-roster-search"><MagnifyingGlass aria-hidden="true" /><span className="visually-hidden">Search roster</span><input value={query} placeholder="Search student ID, name, group, or subgroup" onChange={(event) => void search(event.target.value)} /></label>
      <div className="assessment-roster-table-scroll" tabIndex={0} aria-label="Scrollable course roster"><table style={{ minWidth: Math.max(680, columns.length * 132 + 110) }}><caption className="visually-hidden">Course roster</caption><thead><tr>{columns.map((column) => { const sortable = columnSort(column); return <th key={column.key} aria-sort={sortable && sortBy === sortable ? `${sortDirection}ending` : sortable ? 'none' : undefined}>{sortable ? sortHeading(column.label, sortable) : column.label}</th> })}<th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>{learners.map((learner) => <tr key={learner.id}>{columns.map((column) => <td key={column.key}>{cellValue(column, learner)}</td>)}<td><div className="assessment-roster-row-actions"><button className="assessment-roster-edit" type="button" aria-label={`Edit ${learner.displayName || learner.studentId || 'learner'}`} title="Edit learner" onClick={() => openEditor(learner)}><PencilSimple aria-hidden="true" /></button><button className={learner.status === 'active' ? 'assessment-roster-withdraw' : 'assessment-roster-reinstate'} type="button" aria-label={`${learner.status === 'active' ? 'Withdraw' : 'Reinstate'} ${learner.displayName || learner.studentId || 'learner'}`} title={learner.status === 'active' ? 'Withdraw learner' : 'Reinstate learner'} onClick={() => void toggle(learner)}>{learner.status === 'active' ? <UserMinus aria-hidden="true" /> : <UserPlus aria-hidden="true" />}</button></div></td></tr>)}</tbody></table></div>
      {!learners.length ? <div className="assessment-empty"><UsersThree /><h3>No learners found</h3><p>Import a roster or change the search.</p></div> : null}
      <footer className="assessment-roster-pagination"><div className="assessment-roster-page-summary"><label>Students per page<select aria-label="Students per page" value={pageSize} onChange={(event) => void changePageSize(event.target.value)}>{PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}</select></label><span>{total ? `${offset + 1}–${Math.min(offset + learners.length, total)} of ${total.toLocaleString()}` : '0 learners'}</span></div><div className="assessment-roster-page-buttons"><button type="button" aria-label="Previous roster page" disabled={offset === 0} onClick={() => void refresh(Math.max(0, offset - pageSize), query)}><CaretLeft /></button><button type="button" aria-label="Next roster page" disabled={offset + learners.length >= total} onClick={() => void refresh(offset + pageSize, query)}><CaretRight /></button></div></footer>
    </section>
  </div>
  {editingLearner && editForm ? <div className="assessment-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor() }}><section className="assessment-learner-dialog" role="dialog" aria-modal="true" aria-labelledby="edit-learner-title"><header><div><p className="assessment-kicker">Learner profile</p><h2 id="edit-learner-title">Edit learner</h2></div><button type="button" aria-label="Close editor" onClick={closeEditor}><X /></button></header><div className="assessment-edit-grid"><label><span>Student ID <i>*</i></span><input required value={editForm.studentId} onChange={(event) => setEditForm({ ...editForm, studentId: event.target.value })} /></label><label><span>Given name <i>*</i></span><input required value={editForm.firstName} onChange={(event) => setEditForm({ ...editForm, firstName: event.target.value })} /></label><label>Surname<input value={editForm.lastName} onChange={(event) => setEditForm({ ...editForm, lastName: event.target.value })} /></label><label>Group<input value={editForm.group} onChange={(event) => setEditForm({ ...editForm, group: event.target.value })} /></label><label>Subgroup<input value={editForm.subgroup} onChange={(event) => setEditForm({ ...editForm, subgroup: event.target.value })} /></label><label>Email<input type="email" value={editForm.email} onChange={(event) => setEditForm({ ...editForm, email: event.target.value })} /></label></div><div className="assessment-edit-metadata"><div><strong>Additional information</strong><button type="button" onClick={() => setMetadataRows((current) => [...current, { id: ++metadataRowId, key: '', value: '' }])}><Plus /> Add field</button></div>{metadataRows.map((row) => <div className="assessment-metadata-row" key={row.id}><input aria-label="Field name" placeholder="Field name" value={row.key} onChange={(event) => setMetadataRows((current) => current.map((item) => item.id === row.id ? { ...item, key: event.target.value } : item))} /><input aria-label="Field value" placeholder="Value" value={row.value} onChange={(event) => setMetadataRows((current) => current.map((item) => item.id === row.id ? { ...item, value: event.target.value } : item))} /><button type="button" aria-label={`Remove ${row.key || 'additional'} field`} onClick={() => setMetadataRows((current) => current.filter((item) => item.id !== row.id))}><X /></button></div>)}</div>{error ? <p className="assessment-dialog-error" role="alert">{error}</p> : null}<p className="assessment-dialog-note">Changes apply anywhere this learner is rostered.</p><footer><button type="button" onClick={closeEditor}>Cancel</button><button className="assessment-primary" type="button" disabled={busy || !editForm.studentId.trim() || !editForm.firstName.trim()} onClick={() => void saveLearner()}>{busy ? 'Saving…' : 'Save changes'}</button></footer></section></div> : null}
  {showRemoveAll ? <div className="assessment-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowRemoveAll(false) }}><section className="assessment-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="remove-all-title" aria-describedby="remove-all-description"><Trash aria-hidden="true" /><h2 id="remove-all-title">Remove all learners?</h2><p id="remove-all-description">This removes {total.toLocaleString()} learners from this course and its classes. Their profiles are kept for future imports.</p><footer><button type="button" onClick={() => setShowRemoveAll(false)}>Cancel</button><button className="assessment-danger-button" type="button" disabled={busy} onClick={() => void removeAllLearners()}>{busy ? 'Removing…' : 'Remove all learners'}</button></footer></section></div> : null}
  </>
}
