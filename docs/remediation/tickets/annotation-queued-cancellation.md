# Annotation queue cancellation after navigation

Status: confirmed; candidate repair, not deployed.

Review of PR 277 traced all four users of `serializeLayerMutation`: layer
creation, layer patch, layer reorder and annotation reload. The shared queue
checked a workspace generation by throwing before entering each caller's
stale-operation handler. Switching slides while a request was held therefore
rejected the queued UI callback without a handler.

The rendered regression holds a layer PATCH, queues either another patch or
Reload annotations, and replaces slide A with slide B before releasing the
response. Both cases produce an unhandled `StaleWorkspaceOperationError` on
the reviewed PR 277 head `824ab69360f4d19435ac62014aeb5b2360f25941`.
The guard prevented stale writes, so this is not evidence of data loss.

Skip an obsolete operation in the shared queue before starting it. Keep the
existing generation/store checks for in-flight operations and all active
workspace error handling. The regression verifies that no second old-slide
PATCH or manifest request starts and that the new slide remains intact.

This candidate builds on PR 277's reload serialization; keep those changes
together through review and fresh checks. Required CI, native browser
qualification and production verification remain separate gates.
