import asyncio
from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class AnswerAdmissionSlots:
    """Favor answer writes, with one ordinary admission after at most three writes."""

    def __init__(self, concurrency: int) -> None:
        self.available = concurrency
        self.answers: deque[asyncio.Future[None]] = deque()
        self.ordinary: deque[asyncio.Future[None]] = deque()
        self.answer_streak = 0

    def locked(self) -> bool:
        return self.available == 0

    async def acquire(self, answer: bool) -> None:
        if self.available:
            self.available -= 1
            return
        queue = self.answers if answer else self.ordinary
        waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        queue.append(waiter)
        try:
            await waiter
        except BaseException:
            # Cancellation can arrive after release assigned this waiter a slot.
            if waiter.done() and not waiter.cancelled():
                self.release()
            raise
        finally:
            if waiter in queue:
                queue.remove(waiter)

    def release(self) -> None:
        for queue in (self.answers, self.ordinary):
            while queue and queue[0].done():
                queue.popleft()
        if self.answers and (not self.ordinary or self.answer_streak < 3):
            self.answer_streak += 1
            waiter = self.answers.popleft()
        elif self.ordinary:
            self.answer_streak = 0
            waiter = self.ordinary.popleft()
        else:
            self.answer_streak = 0
            self.available += 1
            return
        waiter.set_result(None)


def is_answer_write(scope: Scope) -> bool:
    parts = scope.get("path", "").split("/")
    return (
        len(parts) == 7 and parts[1:5] == ["api", "v2", "assessment", "attempts"]
        and bool(parts[5])
        and (scope.get("method"), parts[6]) in {("PATCH", "responses"), ("POST", "submit")}
    )


class AssessmentAdmissionMiddleware:
    """Queue requests without occupying database connections or worker threads."""

    def __init__(
        self, app: ASGIApp, *, concurrency: int, max_waiting: int = 512,
        wait_seconds: float = 30,
    ) -> None:
        if concurrency < 1 or max_waiting < 0 or wait_seconds <= 0:
            raise ValueError("Invalid Assessment admission bounds")
        self.app = app
        self.slots = AnswerAdmissionSlots(concurrency)
        self.limit = concurrency + max_waiting
        self.wait_seconds = wait_seconds
        self.pending = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # These endpoints do not check out a connection and must remain observable.
        if scope["type"] != "http" or scope.get("path") in {
            "/livez", "/api/v1/internal/capacity/pressure",
        }:
            await self.app(scope, receive, send)
            return
        if self.pending >= self.limit:
            await self.reject(scope, receive, send)
            return
        self.pending += 1
        acquired = False
        try:
            try:
                async with asyncio.timeout(self.wait_seconds):
                    await self.slots.acquire(is_answer_write(scope))
                    acquired = True
            except TimeoutError:
                await self.reject(scope, receive, send)
                return
            # Keep the slot through ASGI completion, including dependency teardown.
            await self.app(scope, receive, send)
        finally:
            if acquired:
                self.slots.release()
            self.pending -= 1

    @staticmethod
    async def reject(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            status_code=503, content={"detail": {"code": "ASSESSMENT_BUSY"}},
            headers={"Retry-After": "1", "Cache-Control": "no-store"},
        )(scope, receive, send)
