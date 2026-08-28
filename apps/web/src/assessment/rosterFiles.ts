import type { AssessmentRosterLearner } from './api'

export const ROSTER_COLUMNS = [
  { key: 'student_id', label: 'Student ID', required: true, example: '66001234' },
  { key: 'first_name', label: 'Given name', required: true, example: 'กัญญา' },
  { key: 'last_name', label: 'Surname', required: false, example: 'วัฒนกุล' },
  { key: 'group', label: 'Group', required: false, example: 'Year 3' },
  { key: 'subgroup', label: 'Subgroup', required: false, example: 'Lab A' },
  { key: 'other_information', label: 'Other information', required: false, example: 'Exchange student' },
] as const

const escapeCsv = (value: unknown) => {
  const text = value instanceof Date ? value.toISOString() : String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function rowsToCsv(rows: unknown[][], delimiter = ',') {
  return rows.map((row) => row.map(escapeCsv).join(delimiter)).join('\r\n')
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  URL.revokeObjectURL(url)
}

export async function parseRosterFile(file: File) {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (extension === 'xlsx') {
    const { default: readXlsxFile } = await import('read-excel-file')
    return rowsToCsv(await readXlsxFile(file))
  }
  if (extension === 'tsv') return rowsToCsv((await file.text()).split(/\r?\n/).filter(Boolean).map((row) => row.split('\t')))
  if (extension === 'csv') return (await file.text()).replace(/^\ufeff/, '')
  throw new Error('Choose an Excel (.xlsx), CSV, or TSV roster file.')
}

const templateRows = () => [
  ROSTER_COLUMNS.map((column) => column.key),
  ROSTER_COLUMNS.map((column) => column.example),
  ['66001235', 'Narin', 'Kittisak', 'Year 3', 'Lab B', 'Scholarship cohort'],
]

export function downloadRosterCsvTemplate() {
  downloadBlob(new Blob([`\ufeff${rowsToCsv(templateRows())}`], { type: 'text/csv;charset=utf-8' }), 'PathLab-roster-template.csv')
}

export async function downloadRosterExcelTemplate() {
  const { default: writeXlsxFile } = await import('write-excel-file')
  const rows = templateRows().map((row, rowIndex) => row.map((value) => ({ value, type: String, ...(rowIndex === 0 ? { fontWeight: 'bold' as const, backgroundColor: '#F3D2C5' } : {}) })))
  await writeXlsxFile(rows, { fileName: 'PathLab-roster-template.xlsx', columns: ROSTER_COLUMNS.map(() => ({ width: 22 })) })
}

export async function downloadRosterExcel(courseCode: string, learners: AssessmentRosterLearner[]) {
  const { default: writeXlsxFile } = await import('write-excel-file')
  const includeEmail = learners.some((learner) => learner.email)
  const metadataKeys = [...new Set(learners.flatMap((learner) => Object.entries(learner.metadata).filter(([, value]) => value).map(([key]) => key)))]
  const header = ['student_id', 'first_name', 'last_name', 'group', 'subgroup', ...(includeEmail ? ['email'] : []), ...metadataKeys, 'status']
  const values = [
    header,
    ...learners.map((learner) => [
      learner.studentId ?? '', learner.firstName ?? '', learner.lastName ?? '', learner.group ?? '', learner.subgroup ?? '',
      ...(includeEmail ? [learner.email ?? ''] : []), ...metadataKeys.map((key) => learner.metadata[key] ?? ''), learner.status,
    ]),
  ]
  const rows = values.map((row, rowIndex) => row.map((value) => ({ value, type: String, ...(rowIndex === 0 ? { fontWeight: 'bold' as const, backgroundColor: '#F3D2C5' } : {}) })))
  await writeXlsxFile(rows, { fileName: `${courseCode.replaceAll(/[^a-z0-9_-]/gi, '-')}-roster.xlsx`, columns: values[0].map(() => ({ width: 22 })) })
}
