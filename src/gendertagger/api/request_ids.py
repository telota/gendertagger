"""Server-generated request correlation identifiers."""

from collections.abc import Callable
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

RequestIdFactory = Callable[[], str]


class RequestIdMiddleware:
    """Assign one server-owned request ID to every HTTP response and scope."""

    def __init__(self, app: ASGIApp, *, request_id_factory: RequestIdFactory) -> None:
        self._app = app
        self._request_id_factory = request_id_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach a request ID to one HTTP scope and response."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = self._request_id_factory()
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["x-request-id"] = request_id
            await send(message)

        await self._app(scope, receive, send_with_request_id)


def generate_request_id() -> str:
    """Return one opaque UUID request identifier."""
    return str(uuid4())
