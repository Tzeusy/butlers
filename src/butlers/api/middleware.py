"""API error handling middleware — consistent error responses.

Registers FastAPI exception handlers that convert domain exceptions into
standardised ``{"error": {"code": "...", "message": "...", "butler": "..."}}``
JSON responses.

Status code mapping:
- ``ButlerUnreachableError`` → 502 Bad Gateway
- ``KeyError`` (unknown butler lookup) → 404 Not Found
- ``ValueError`` → 400 Bad Request
- Any other ``Exception`` → 500 Internal Server Error
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from butlers.api.deps import ButlerUnreachableError
from butlers.api.models import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


async def _handle_butler_unreachable(
    request: Request,
    exc: ButlerUnreachableError,
) -> JSONResponse:
    """Return 502 when a butler MCP server cannot be reached."""
    logger.warning("Butler unreachable: %s", exc.butler_name, exc_info=exc)
    body = ErrorResponse(
        error=ErrorDetail(
            code="BUTLER_UNREACHABLE",
            message=str(exc),
            butler=exc.butler_name,
        )
    )
    return JSONResponse(status_code=502, content=body.model_dump())


async def _handle_key_error(
    request: Request,
    exc: KeyError,
) -> JSONResponse:
    """Return 404 when a butler name is not found in the pool/registry."""
    butler_name = exc.args[0] if exc.args else None
    logger.info("Butler not found: %s", butler_name)
    body = ErrorResponse(
        error=ErrorDetail(
            code="BUTLER_NOT_FOUND",
            message=f"Butler not found: {butler_name}",
            butler=str(butler_name) if butler_name is not None else None,
        )
    )
    return JSONResponse(status_code=404, content=body.model_dump())


async def _handle_value_error(
    request: Request,
    exc: ValueError,
) -> JSONResponse:
    """Return 400 for validation / value errors."""
    logger.info("Validation error: %s", exc)
    body = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=str(exc),
        )
    )
    return JSONResponse(status_code=400, content=body.model_dump())


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that catches any unhandled exception and returns a 500.

    This sits above the Starlette exception handler layer, ensuring that
    even exceptions not caught by ``add_exception_handler`` are converted
    to the standard error envelope rather than bubbling up as raw 500s.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.error(
                "Unhandled exception on %s %s",
                request.method,
                request.url.path,
                exc_info=True,
            )
            body = ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Internal server error",
                )
            )
            return JSONResponse(status_code=500, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the FastAPI application.

    Call this from ``create_app()`` after constructing the ``FastAPI`` instance.

    Domain-specific exceptions are registered via ``add_exception_handler``.
    The generic catch-all is an ASGI middleware that wraps the entire app
    to intercept any unhandled exception before Starlette's default
    ``ServerErrorMiddleware`` can convert it to a plain-text 500.
    """
    app.add_exception_handler(ButlerUnreachableError, _handle_butler_unreachable)  # type: ignore[arg-type]
    app.add_exception_handler(KeyError, _handle_key_error)  # type: ignore[arg-type]
    app.add_exception_handler(ValueError, _handle_value_error)  # type: ignore[arg-type]
    app.add_middleware(CatchAllErrorMiddleware)
