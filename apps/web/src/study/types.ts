export type StudyTask = {
  id: string
  type: 'multiple-choice' | 'spatial'
  slideId: string
  prompt: string
  options?: string[]
  hints: string[]
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
    schema: 'pathlab.study-pack/1'
    packKey: string
    version: number
    title: string
    languages: Array<'en' | 'th'>
    slides: Array<{
      viewerSlideId: string
      displayName: string
      tileSource: string
    }>
    tasks: StudyTask[]
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
  schema: 'pathlab.study-pack/1'
  packKey: string
  version: number
  title: string
  author: string
  license: string
  provenance: string
  revision: string
  languages: Array<'en' | 'th'>
  slides: Array<{ viewerSlideId: string; sha256: string; displayName: string }>
  tasks: StudyPackTaskDefinition[]
  checksum?: string
  facultyPreview?: { packChecksum: string; previewVersion: 'pathlab.study-preview/1'; reviewedAt: string }
}
