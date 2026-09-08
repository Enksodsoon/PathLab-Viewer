import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class AssessmentAdmissionMiddleware:
    """Queue requests without occupying database connections or worker threads."""

    def __init__(
        self, app: ASGIApp, *, concurrency: int, max_waiting: int = 512,
        wait_seconds: float = 30,
    ) -> None:
        if concurrency < 1 or max_waiting < 0 or wait_seconds <= 0:
            raise ValueError("Invalid Assessment admission bounds")
        self.app = app
        self.slots = asyncio.Semaphore(concurrency)
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
                await asyncio.wait_for(self.slots.acquire(), timeout=self.wait_seconds)
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
