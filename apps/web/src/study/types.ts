export type StudyTask = {
  id: string
  type: 'multiple-choice' | 'spatial'
  slideId: string
  prompt: string
  options?: string[]
  hints: string[]
  claimIds?: string[]
}

export type KnowledgeClaim = {
  id: string
  text: string
  retrievalText: string
  source: { title: string; url: string; revision: string }
  license: string
  allowedUse: 'private-research-education'
  reviewedAt: string
  tags: string[]
}

export type KnowledgePack = {
  schema: 'pathlab.knowledge-pack/1'
  packId: string
  version: string
  language: 'en'
  claims: KnowledgeClaim[]
  checksum: string
}

export type EvidenceBundle = {
  schema: 'pathlab.ai-evidence/1'
  manifestSha256: string
  status: 'completed' | 'partial' | 'abstained' | 'unsupported' | 'failed'
  researchOnly: true
  notDiagnostic: true
  evidence: Array<{
    id: string; stage: 'coarse' | 'refined'; kind: 'support' | 'similar' | 'contrast'
    x: number; y: number; width: number; height: number; score: number; thumbnail?: string
  }>
  cellAggregates: Array<{
    regionId: string; algorithm: 'hovernet-fast' | 'od-watershed'; count: number
    densityPerMm2: number | null; meanNucleusAreaPx2: number | null
    meanNucleusPerimeterPx?: number | null; meanNucleusEccentricity?: number | null
    meanNucleusSolidity?: number | null; uncertainty?: number
  }>
  ihcDescriptors: Array<{
    regionId: string; marker: string; compartment: string
    dabAreaFraction: number; meanDabOd: number; researchEstimate: true
    markerId?: string; analysisMode?: 'marker-aware' | 'generic-fallback'
    cellMaskSource?: 'hovernet-fast' | 'od-watershed'
    compartmentSource?: 'none' | 'faculty-authored' | 'faculty-approved' | 'model-suggested'
    calibrationStatus?: 'calibrated' | 'relative_only' | 'not_evaluable'
    uncertainty?: number; abstentionReason?: string | null
  }>
  qc: {
    focus: number; tissueFraction: number; uncertainty: number; abstentionReasons: string[]
    calibrationStatus?: 'calibrated' | 'relative_only' | 'not_evaluable'
    backgroundFraction?: number; saturationFraction?: number; stainSeparation?: number; warnings?: string[]
  }
}

export type StudySession = {
  pseudonym: string
  course: {
    id: string
    title: string
    status: 'preparation' | 'active'
    retentionDays: number
    endsAt: string | null
  }
  pack: {
    schema: 'pathlab.study-pack/1' | 'pathlab.study-pack/2'
    packKey: string
    version: number
    title: string
    languages: Array<'en' | 'th'>
    slides: Array<{
      viewerSlideId: string
      displayName: string
      tileSource: string
      evidenceBundleSha256?: string
      evidenceUrl?: string
    }>
    tasks: StudyTask[]
    knowledgePackChecksum?: string
    knowledgePackUrl?: string
  }
  progress: Array<{
    taskId: string
    status: 'attempted' | 'completed'
    latestCorrectness: boolean
    attemptCount: number
    modelManifestId: string | null
    createdAt: string
    updatedAt: string
  }>
  ai: {
    eligible: boolean
    manifest: StudyModelManifest | null
    coldStartDistinctTasks: 5
    allowedActions: StudyAction[]
    authorizationMode: 'approved' | 'closed_pilot'
  }
}

export type StudyModelManifest = {
  schema: 'pathlab.study-model-release/1'
  id: string
  artifactSha256: string
  artifactBytes: number
  assetUrl: string
  approvalStatus: string
  pilotAuthorization?: 'closed_pilot_unapproved'
  allowedActions: StudyAction[]
  knownVector: {
    inputLength: number
    expectedOutputs?: Record<string, number>
    expectedOutputTolerance: number
  }
}

export type StudyAction =
  | 'continue'
  | 'offer_hint'
  | 'ask_confidence'
  | 'ask_source_check'
  | 'retrieve'
  | 'pause'

export type StudyReason =
  | 'CONTINUE_PRACTICE'
  | 'HINT_SUPPORT'
  | 'CHECK_CONFIDENCE'
  | 'VERIFY_SOURCE'
  | 'REVIEW_PREVIOUS'
  | 'TAKE_BREAK'
  | 'MODEL_SUGGESTION'

export type LocalStudyRecord = {
  taskId: string
  completedAt: number
  completed: boolean
  features: [number, number, number, number, number, number, number, number, number, number, number, number]
}

export type StudyPackSummary = {
  id: string
  packKey: string
  version: number
  title: string
  checksum: string
  createdAt: string
}

export type StudyCourseSummary = {
  id: string
  packId: string
  title: string
  status: 'draft' | 'preparation' | 'active' | 'ended' | 'purged'
  retentionDays: number
  learnerLimit: number
  invitations: number
  redeemed: number
  endsAt: string | null
  purgeAfter: string | null
  readiness: { ready: number; fallback: number }
  aiMode: 'deterministic' | 'closed_pilot_trace_sim'
  modelManifestId: string | null
  pilotAcknowledgedAt: string | null
  aiActions: Record<StudyAction, number>
}

export type StudyAuthoringSlide = { id: string; displayName: string; sha256: string }

export type StudyPackTaskDefinition = StudyTask & {
  answerKey?: string
  targetX?: number
  targetY?: number
  targetWidth?: number
  targetHeight?: number
  tolerance?: number
  explanation: string
  sources: Array<{ title: string; url: string }>
}

export type StudyPackDefinition = {
  schema: 'pathlab.study-pack/1' | 'pathlab.study-pack/2'
  packKey: string
  version: number
  title: string
  author: string
  license: string
  provenance: string
  revision: string
  languages: Array<'en' | 'th'>
  slides: Array<{
    viewerSlideId: string; sha256: string; displayName: string; evidenceBundleSha256?: string
  }>
  tasks: StudyPackTaskDefinition[]
  knowledgePackChecksum?: string
  checksum?: string
  facultyPreview?: { packChecksum: string; previewVersion: 'pathlab.study-preview/1'; reviewedAt: string }
}
