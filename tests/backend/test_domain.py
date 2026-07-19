import pytest
from wsi_viewer.domain import InvalidTransition, SlideState, transition


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (SlideState.UPLOADING, SlideState.QUEUED),
        (SlideState.QUEUED, SlideState.VALIDATING),
        (SlideState.VALIDATING, SlideState.CONVERTING),
        (SlideState.CONVERTING, SlideState.READY_PRIVATE),
        (SlideState.READY_PRIVATE, SlideState.PUBLISHED),
        (SlideState.PUBLISHED, SlideState.READY_PRIVATE),
        (SlideState.FAILED, SlideState.QUEUED),
        (SlideState.READY_PRIVATE, SlideState.DELETING),
    ],
)
def test_allowed_slide_transitions(source: SlideState, target: SlideState) -> None:
    assert transition(source, target) is target


def test_publication_cannot_skip_processing() -> None:
    with pytest.raises(InvalidTransition):
        transition(SlideState.UPLOADING, SlideState.PUBLISHED)
