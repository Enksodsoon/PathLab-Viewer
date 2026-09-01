import { Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { commitAssessmentRoster, createAssessmentClass, listAssessmentClasses, listAssessmentStudents, previewAssessmentRoster, updateAssessmentEnrollment } from '../assessment/api'
import './assessment.css'

interface ClassSummary {
  id: string
  name: string
  status: string
  studentCount: number
}

export function AssessmentClassesPage() {
  const [classes, setClasses] = useState<ClassSummary[]>([])
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<ClassSummary | null>(null)
  const [rows, setRows] = useState('')
  const [checksum, setChecksum] = useState('')
  const [preview, setPreview] = useState<Array<{ displayName: string | null }>>([])
  const [students, setStudents] = useState<Array<{ id: string; displayName: string | null; status: string }>>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  useEffect(() => { void listAssessmentClasses().then((result) => setClasses(result.items)) }, [])

  async function addClass() {
    if (!name.trim()) return
    const created = await createAssessmentClass(name.trim())
    setClasses((current) => [{ ...created, studentCount: 0 }, ...current])
    setName('')
  }

  async function manage(item: ClassSummary, nextOffset = 0) {
    setSelected(item)
    setOffset(nextOffset)
    const result = await listAssessmentStudents(item.id, nextOffset)
    setStudents(result.items)
    setTotal(result.total)
  }

  async function previewRows() {
    if (!selected || !rows.trim()) return
    const result = await previewAssessmentRoster(selected.id, rows)
    setChecksum(result.checksum)
    setPreview(result.preview)
  }

  async function commitRows() {
    if (!selected || !checksum) return
    await commitAssessmentRoster(selected.id, rows, checksum)
    setRows(''); setChecksum(''); setPreview([])
    await manage(selected)
  }

  async function changeStatus(learnerId: string, status: 'active' | 'withdrawn') {
    if (!selected) return
    await updateAssessmentEnrollment(selected.id, learnerId, status)
    setStudents((current) => current.map((student) => student.id === learnerId ? { ...student, status } : student))
  }

  return <main className="assessment-main">
    <p className="assessment-kicker">Roster management</p>
    <h1>Classes</h1>
    <div className="assessment-class-create">
      <label>Class name <input value={name} onChange={(event) => setName(event.target.value)} /></label>
      <button className="assessment-primary" type="button" onClick={() => void addClass()}>
        <Plus /> Create class
      </button>
    </div>
    <section className="assessment-class-grid" aria-label="Classes">
      {classes.map((item) => <article key={item.id}>
        <UsersThree aria-hidden="true" />
        <div><h2>{item.name}</h2><p>{item.studentCount} students · {item.status}</p></div>
        <button type="button" onClick={() => void manage(item)}>Manage students</button>
      </article>)}
    </section>
    {selected ? <section className="assessment-settings" aria-label={`Students in ${selected.name}`}>
      <button type="button" onClick={() => setSelected(null)}>Close</button>
      <h2>{selected.name}</h2><p>{total} enrolled students</p>
      <label>Paste student identifier and optional display name, one row per student
        <textarea value={rows} placeholder={'student001, Somchai P.\nstudent002, Malee T.'} onChange={(event) => { setRows(event.target.value); setChecksum('') }} />
      </label>
      <label>Or choose a CSV file<input type="file" accept=".csv,text/csv" onChange={(event) => { const file = event.target.files?.[0]; if (file) void file.text().then((text) => { setRows(text); setChecksum('') }) }} /></label>
      <button type="button" onClick={() => void previewRows()}>Preview import</button>
      {checksum ? <div role="status"><p>{preview.length} preview rows validated. Confirm to add the roster.</p><ul>{preview.map((student, index) => <li key={`${student.displayName}-${index}`}>{student.displayName ?? 'Display name omitted'}</li>)}</ul><button className="assessment-primary" type="button" onClick={() => void commitRows()}>Commit import</button></div> : null}
      <table><caption>Class roster</caption><thead><tr><th>Name</th><th>Status</th><th>Enrollment</th></tr></thead><tbody>{students.map((student) => <tr key={student.id}><td>{student.displayName ?? 'Private learner'}</td><td>{student.status}</td><td><button type="button" onClick={() => void changeStatus(student.id, student.status === 'active' ? 'withdrawn' : 'active')}>{student.status === 'active' ? 'Withdraw' : 'Reinstate'}</button></td></tr>)}</tbody></table>
      <div className="assessment-pagination"><button type="button" disabled={offset === 0} onClick={() => void manage(selected, Math.max(0, offset - 50))}>Previous</button><span>{offset + 1}–{Math.min(offset + students.length, total)} of {total}</span><button type="button" disabled={offset + 50 >= total} onClick={() => void manage(selected, offset + 50)}>Next</button></div>
    </section> : null}
  </main>
}
