import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { gzipSync } from 'node:zlib'

const MAX_LEARNER_GZIP_BYTES = 15 * 1024
const dist = resolve(process.argv[2] ?? 'dist')
const baselineDist = process.argv[3] ? resolve(process.argv[3]) : null
const manifestPath = resolve(dist, '.vite/manifest.json')
if (!existsSync(manifestPath)) throw new Error(`Missing Vite manifest: ${manifestPath}`)
const entries = JSON.parse(readFileSync(manifestPath, 'utf8'))
const student = Object.entries(entries).find(([, entry]) => entry.src === 'src/pages/AssessmentStudentPage.tsx')
if (!student) throw new Error('Assessment learner entry is missing')

function collect(key, visited = new Set(), assets = new Set()) {
  if (visited.has(key)) return { visited, assets }
  visited.add(key)
  const entry = entries[key]
  if (!entry) throw new Error(`Manifest references missing entry: ${key}`)
  if (entry.file) assets.add(entry.file)
  for (const css of entry.css ?? []) assets.add(css)
  for (const imported of entry.imports ?? []) collect(imported, visited, assets)
  return { visited, assets }
}
const { visited, assets } = collect(student[0])
const initial = collect('index.html')

const forbiddenSources = [
  'AssessmentBuilderPage.tsx',
  'AssessmentReportPage.tsx',
  'AssessmentSectionCanvas.tsx',
  'qrcode.react',
]
const sources = [...visited].map((key) => entries[key]?.src ?? key)
for (const forbidden of forbiddenSources) {
  if (sources.some((source) => source.includes(forbidden))) {
    throw new Error(`Teacher-only module leaked into learner closure: ${forbidden}`)
  }
}
const campaignAssets = [...assets].filter((file) => !initial.assets.has(file))
const gzipBytes = campaignAssets.reduce((total, file) => (
  total + gzipSync(readFileSync(resolve(dist, file)), { level: 9 }).byteLength
), 0)
function learnerCampaignGzip(directory) {
  const baselineEntries = JSON.parse(readFileSync(resolve(directory, '.vite/manifest.json'), 'utf8'))
  const baselineStudent = Object.entries(baselineEntries).find(([, entry]) => entry.src === 'src/pages/AssessmentStudentPage.tsx')
  if (!baselineStudent) throw new Error('Baseline assessment learner entry is missing')
  function baselineCollect(key, visited = new Set(), files = new Set()) {
    if (visited.has(key)) return files
    visited.add(key)
    const entry = baselineEntries[key]
    if (entry.file) files.add(entry.file)
    for (const css of entry.css ?? []) files.add(css)
    for (const imported of entry.imports ?? []) baselineCollect(imported, visited, files)
    return files
  }
  const files = baselineCollect(baselineStudent[0])
  const initialFiles = baselineCollect('index.html')
  return [...files].filter((file) => !initialFiles.has(file)).reduce((total, file) => (
    total + gzipSync(readFileSync(resolve(directory, file)), { level: 9 }).byteLength
  ), 0)
}
const baselineGzipBytes = baselineDist ? learnerCampaignGzip(baselineDist) : null
const campaignDeltaGzipBytes = baselineGzipBytes === null ? null : gzipBytes - baselineGzipBytes
const result = { learnerCampaignGzipBytes: gzipBytes, baselineLearnerGzipBytes: baselineGzipBytes, campaignDeltaGzipBytes, learnerCampaignBudgetBytes: MAX_LEARNER_GZIP_BYTES, assets: campaignAssets.sort(), excludedTeacherModules: forbiddenSources }
if (campaignDeltaGzipBytes !== null && campaignDeltaGzipBytes > MAX_LEARNER_GZIP_BYTES) throw new Error(`Learner assessment campaign grew ${campaignDeltaGzipBytes} bytes gzip; budget is ${MAX_LEARNER_GZIP_BYTES}`)
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
