"""Bound JSON uploads before parsing, including chunked requests."""

from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app, max_bytes: int = 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared_size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            response = JSONResponse({"detail": "Invalid request length."}, status_code=400)
            return await response(scope, receive, send)
        if declared_size > self.max_bytes:
            response = JSONResponse(
                {"detail": "The request must not exceed 1 MB."}, status_code=413
            )
            return await response(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                response = JSONResponse(
                    {"detail": "The request must not exceed 1 MB."}, status_code=413
                )
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
