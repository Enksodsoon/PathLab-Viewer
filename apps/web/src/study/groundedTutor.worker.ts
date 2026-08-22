import { retrieveGroundedClaimIds } from './groundedTutor'
import type { KnowledgePack } from './types'

self.onmessage = (event: MessageEvent<{
  requestId: string; pack: KnowledgePack; question: string; allowedClaimIds: string[]
}>) => {
  const { requestId, pack, question, allowedClaimIds } = event.data
  self.postMessage({ requestId, claimIds: retrieveGroundedClaimIds(pack, question, allowedClaimIds) })
}
