from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AuthBodyLimitMiddleware:
    """Bound selected request prefixes without buffering an unbounded body."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int | None = None,
        path_prefixes: tuple[str, ...] = ("/api/v1/auth/",),
        path_limits: tuple[tuple[str, int], ...] | None = None,
        suffix_limits: tuple[tuple[str, str, int], ...] = (),
    ) -> None:
        self.app = app
        if path_limits is None:
            if max_bytes is None:
                raise ValueError("max_bytes is required without path_limits")
            path_limits = tuple((prefix, max_bytes) for prefix in path_prefixes)
        self.path_limits = tuple(
            sorted(path_limits, key=lambda item: len(item[0]), reverse=True)
        )
        self.suffix_limits = suffix_limits

    def _limit_for(self, path: str) -> int | None:
        for prefix, suffix, max_bytes in self.suffix_limits:
            if path.startswith(prefix) and path.endswith(suffix):
                return max_bytes
        for prefix, max_bytes in self.path_limits:
            if path.startswith(prefix):
                return max_bytes
        return None

    @staticmethod
    def _declared_too_large(scope: Scope, max_bytes: int) -> bool:
        for name, raw_value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                if int(raw_value.strip()) > max_bytes:
                    return True
            except ValueError:
                continue
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = self._limit_for(scope.get("path", ""))
        if max_bytes is None:
            await self.app(scope, receive, send)
            return
        if self._declared_too_large(scope, max_bytes):
            await self._reject(scope, receive, send)
            return

        consumed = 0
        buffered: deque[Message] = deque()
        while True:
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > max_bytes:
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
