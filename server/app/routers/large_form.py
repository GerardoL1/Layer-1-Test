"""A route class for form endpoints with big fields (Shortcuts sends weeks of readings in one field)."""

from collections.abc import Callable

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.core import limits


class LargeFormRoute(APIRoute):
    """
    Starlette caps each form field at 1 MB, which a first Shortcuts sync can pass. This reads the
    form first with the endpoint's own size limit, and FastAPI then uses the form already read.
    """

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def read_form_first(request: Request) -> Response:
            await request.form(max_part_size=limits.MAX_JSON_BYTES)
            return await handler(request)

        return read_form_first
