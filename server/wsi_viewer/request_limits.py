from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AuthBodyLimitMiddleware:
    """Bound every auth request without buffering an unbounded body."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        path_prefixes: tuple[str, ...] = ("/api/v1/auth/",),
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefixes = path_prefixes

    def _declared_too_large(self, scope: Scope) -> bool:
        for name, raw_value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                if int(raw_value.strip()) > self.max_bytes:
                    return True
            except ValueError:
                continue
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(
            self.path_prefixes
        ):
            await self.app(scope, receive, send)
            return
        if self._declared_too_large(scope):
            await self._reject(scope, receive, send)
            return

        consumed = 0
        buffered: deque[Message] = deque()
        while True:
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            else:
                buffered.append(message)
                break

        async def replay_receive() -> Message:
            if buffered:
                return buffered.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": {"code": "REQUEST_TOO_LARGE"}},
        )
        await response(scope, receive, send)
