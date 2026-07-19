from enum import StrEnum


class SlideState(StrEnum):
    UPLOADING = "uploading"
    QUEUED = "queued"
    VALIDATING = "validating"
    CONVERTING = "converting"
    READY_PRIVATE = "ready_private"
    PUBLISHED = "published"
    FAILED = "failed"
    DELETING = "deleting"


class InvalidTransition(ValueError):
    pass


_TRANSITIONS: dict[SlideState, frozenset[SlideState]] = {
    SlideState.UPLOADING: frozenset({SlideState.QUEUED, SlideState.DELETING}),
    SlideState.QUEUED: frozenset({SlideState.VALIDATING, SlideState.FAILED, SlideState.DELETING}),
    SlideState.VALIDATING: frozenset({SlideState.CONVERTING, SlideState.FAILED}),
    SlideState.CONVERTING: frozenset({SlideState.READY_PRIVATE, SlideState.FAILED}),
    SlideState.READY_PRIVATE: frozenset({SlideState.PUBLISHED, SlideState.DELETING}),
    SlideState.PUBLISHED: frozenset({SlideState.READY_PRIVATE, SlideState.DELETING}),
    SlideState.FAILED: frozenset({SlideState.QUEUED, SlideState.DELETING}),
    SlideState.DELETING: frozenset(),
}


def transition(source: SlideState, target: SlideState) -> SlideState:
    if target not in _TRANSITIONS[source]:
        raise InvalidTransition(f"Cannot transition slide from {source} to {target}")
    return target
