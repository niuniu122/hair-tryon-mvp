from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DomainError(RuntimeError):
    """Base error for invalid domain operations."""


class AttemptLimitExceeded(DomainError):
    """Raised when a view would exceed two provider calls."""


class InvalidViewTransition(DomainError):
    """Raised when a view state transition is not allowed."""


class BackViewNotReady(DomainError):
    """Raised when back generation starts before front and side succeed."""


class SessionEnded(DomainError):
    """Raised when an ended session receives new work."""


class GenerationSetConflict(DomainError):
    """Raised when an idempotency key is reused for another hairstyle."""


class ViewName(str, Enum):
    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class ViewState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationSetState(str, Enum):
    GENERATING_FRONT_SIDE = "generating_front_side"
    PARTIAL_READY = "partial_ready"
    READY_FOR_BACK = "ready_for_back"
    GENERATING_BACK = "generating_back"
    THREE_VIEWS_READY = "three_views_ready"
    PARTIAL_FAILURE = "partial_failure"


class SessionState(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"


@dataclass
class ViewAttempt:
    number: int
    state: ViewState = ViewState.RUNNING
    result_id: str | None = None
    error_code: str | None = None


class ViewRecord:
    def __init__(self, name: ViewName) -> None:
        self.name = name
        self.attempts: list[ViewAttempt] = []

    @property
    def state(self) -> ViewState:
        if not self.attempts:
            return ViewState.QUEUED
        return self.attempts[-1].state

    @property
    def final_attempt(self) -> ViewAttempt:
        if not self.attempts:
            raise InvalidViewTransition(f"{self.name.value} has no attempt")
        return self.attempts[-1]

    def start_attempt(self) -> ViewAttempt:
        if len(self.attempts) >= 2:
            raise AttemptLimitExceeded(f"{self.name.value} already used two attempts")
        if self.attempts and self.final_attempt.state is ViewState.RUNNING:
            raise InvalidViewTransition(f"{self.name.value} is already running")
        if self.attempts and self.final_attempt.state is ViewState.CANCELLED:
            raise InvalidViewTransition(f"{self.name.value} was cancelled")

        attempt = ViewAttempt(number=len(self.attempts) + 1)
        self.attempts.append(attempt)
        return attempt

    def succeed(self, result_id: str) -> None:
        attempt = self._running_attempt()
        attempt.state = ViewState.SUCCEEDED
        attempt.result_id = result_id

    def fail(self, error_code: str) -> None:
        attempt = self._running_attempt()
        attempt.state = ViewState.FAILED
        attempt.error_code = error_code

    def cancel(self) -> None:
        self._running_attempt().state = ViewState.CANCELLED

    def _running_attempt(self) -> ViewAttempt:
        attempt = self.final_attempt
        if attempt.state is not ViewState.RUNNING:
            raise InvalidViewTransition(f"{self.name.value} is not running")
        return attempt


class GenerationSet:
    def __init__(self, generation_set_id: str, hairstyle_id: str) -> None:
        self.generation_set_id = generation_set_id
        self.hairstyle_id = hairstyle_id
        self._views = {name: ViewRecord(name) for name in ViewName}

    def view(self, name: ViewName) -> ViewRecord:
        return self._views[name]

    def start_attempt(self, name: ViewName) -> ViewAttempt:
        if name is ViewName.BACK and not self.front_and_side_succeeded:
            raise BackViewNotReady("back requires final front and side success")
        return self.view(name).start_attempt()

    def succeed_view(self, name: ViewName, result_id: str) -> None:
        self.view(name).succeed(result_id)

    def fail_view(self, name: ViewName, error_code: str) -> None:
        self.view(name).fail(error_code)

    def cancel_view(self, name: ViewName) -> None:
        self.view(name).cancel()

    @property
    def front_and_side_succeeded(self) -> bool:
        return all(
            self.view(name).state is ViewState.SUCCEEDED
            for name in (ViewName.FRONT, ViewName.SIDE)
        )

    @property
    def state(self) -> GenerationSetState:
        front = self.view(ViewName.FRONT).state
        side = self.view(ViewName.SIDE).state
        back = self.view(ViewName.BACK).state

        if back is ViewState.SUCCEEDED:
            return GenerationSetState.THREE_VIEWS_READY
        if back is ViewState.RUNNING:
            return GenerationSetState.GENERATING_BACK
        if back in (ViewState.FAILED, ViewState.CANCELLED):
            return GenerationSetState.PARTIAL_FAILURE
        if self.front_and_side_succeeded:
            return GenerationSetState.READY_FOR_BACK
        if front in (ViewState.FAILED, ViewState.CANCELLED) or side in (
            ViewState.FAILED,
            ViewState.CANCELLED,
        ):
            return GenerationSetState.PARTIAL_FAILURE
        if front is ViewState.SUCCEEDED or side is ViewState.SUCCEEDED:
            return GenerationSetState.PARTIAL_READY
        return GenerationSetState.GENERATING_FRONT_SIDE


class Session:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state = SessionState.ACTIVE
        self._generation_sets: dict[str, GenerationSet] = {}

    def create_generation_set(
        self,
        generation_set_id: str,
        hairstyle_id: str,
    ) -> GenerationSet:
        if self.state is SessionState.ENDED:
            raise SessionEnded(f"session {self.session_id} has ended")

        existing = self._generation_sets.get(generation_set_id)
        if existing is not None:
            if existing.hairstyle_id != hairstyle_id:
                raise GenerationSetConflict(
                    f"generation set {generation_set_id} already targets "
                    f"{existing.hairstyle_id}"
                )
            return existing

        generation_set = GenerationSet(generation_set_id, hairstyle_id)
        self._generation_sets[generation_set_id] = generation_set
        return generation_set

    def end(self) -> None:
        self.state = SessionState.ENDED
