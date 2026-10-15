"""The request size limit. Sizes and messages live in core/limits.py."""

import json

from app.core import limits


class _TooLarge(Exception):
    pass


class LimitRequestSize:
    """
    Refuses requests bigger than limits.LIMITS_BY_PATH with a 413. Checks the declared size
    first, and also counts the bytes as they arrive in case the client didn't declare one.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        limit = limits.LIMITS_BY_PATH.get(scope.get("path")) if scope["type"] == "http" else None
        if limit is None:
            return await self.app(scope, receive, send)

        async def refuse():
            body = json.dumps({"detail": limits.too_large_message(scope["path"], limit)}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
                }
            )
            await send({"type": "http.response.body", "body": body})

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            return await refuse()

        seen, over, started = 0, False, False

        async def counting_receive():
            nonlocal seen, over
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    over = True
                    raise _TooLarge()
            return message

        async def guarded_send(message):
            nonlocal started
            # FastAPI turns a failed body read into its own error reply. Send the 413 instead.
            if over:
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _TooLarge:
            pass
        if over and not started:
            await refuse()
