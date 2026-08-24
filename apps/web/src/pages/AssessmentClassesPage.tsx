import { Plus, UsersThree } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { createAssessmentClass, listAssessmentClasses } from '../assessment/api'
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
  useEffect(() => { void listAssessmentClasses().then((result) => setClasses(result.items)) }, [])

  async function addClass() {
    if (!name.trim()) return
    const created = await createAssessmentClass(name.trim())
    setClasses((current) => [{ ...created, studentCount: 0 }, ...current])
    setName('')
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
        <button type="button">Manage students</button>
      </article>)}
    </section>
  </main>
}
