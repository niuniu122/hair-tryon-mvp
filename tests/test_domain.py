import pytest

from hair_tryon.domain import (
    AttemptLimitExceeded,
    BackViewNotReady,
    GenerationSet,
    GenerationSetState,
    Session,
    SessionEnded,
    SessionState,
    ViewName,
    ViewState,
)


def test_view_never_starts_a_third_provider_attempt() -> None:
    generation_set = GenerationSet("set-1", "H01")

    generation_set.start_attempt(ViewName.FRONT)
    generation_set.fail_view(ViewName.FRONT, "provider_timeout")
    generation_set.start_attempt(ViewName.FRONT)
    generation_set.fail_view(ViewName.FRONT, "provider_timeout")

    with pytest.raises(AttemptLimitExceeded):
        generation_set.start_attempt(ViewName.FRONT)


def test_second_attempt_becomes_final_and_preserves_first_for_analysis() -> None:
    generation_set = GenerationSet("set-1", "H01")

    first = generation_set.start_attempt(ViewName.FRONT)
    generation_set.succeed_view(ViewName.FRONT, "front-first")
    second = generation_set.start_attempt(ViewName.FRONT)

    front = generation_set.view(ViewName.FRONT)
    assert first.number == 1
    assert second.number == 2
    assert front.final_attempt.number == 2
    assert front.final_attempt.result_id is None
    assert front.attempts[0].result_id == "front-first"

    generation_set.succeed_view(ViewName.FRONT, "front-second")

    assert front.final_attempt.result_id == "front-second"
    assert front.attempts[0].result_id == "front-first"


def test_back_cannot_start_until_final_front_and_side_both_succeed() -> None:
    generation_set = GenerationSet("set-1", "H01")

    generation_set.start_attempt(ViewName.FRONT)
    generation_set.succeed_view(ViewName.FRONT, "front-result")

    with pytest.raises(BackViewNotReady):
        generation_set.start_attempt(ViewName.BACK)

    generation_set.start_attempt(ViewName.SIDE)
    generation_set.succeed_view(ViewName.SIDE, "side-result")
    back_attempt = generation_set.start_attempt(ViewName.BACK)

    assert back_attempt.number == 1
    assert generation_set.view(ViewName.BACK).state is ViewState.RUNNING
    assert generation_set.state is GenerationSetState.GENERATING_BACK


def test_result_set_state_tracks_partial_and_complete_results() -> None:
    generation_set = GenerationSet("set-1", "H01")
    assert generation_set.state is GenerationSetState.GENERATING_FRONT_SIDE

    generation_set.start_attempt(ViewName.FRONT)
    generation_set.succeed_view(ViewName.FRONT, "front-result")
    assert generation_set.state is GenerationSetState.PARTIAL_READY

    generation_set.start_attempt(ViewName.SIDE)
    generation_set.succeed_view(ViewName.SIDE, "side-result")
    assert generation_set.state is GenerationSetState.READY_FOR_BACK

    generation_set.start_attempt(ViewName.BACK)
    generation_set.succeed_view(ViewName.BACK, "back-result")
    assert generation_set.state is GenerationSetState.THREE_VIEWS_READY


def test_ended_session_rejects_new_generation_sets() -> None:
    session = Session("session-1")
    assert session.state is SessionState.ACTIVE

    created = session.create_generation_set("set-1", "H01")
    assert created.generation_set_id == "set-1"

    session.end()
    assert session.state is SessionState.ENDED

    with pytest.raises(SessionEnded):
        session.create_generation_set("set-2", "H02")
