import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.db.models import AuditLog
from app.db.session import async_session_factory


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Writes one audit_logs row per request, restricted to the fields
    security.logging.allowed permits: request_id, user_uuid, timestamp, module, latency,
    error_code. Never logs request/response bodies (raw_symptoms, full_conversations, etc.
    per security.logging.avoid)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4()
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - start) * 1000
        error_code = str(response.status_code) if response.status_code >= 400 else None
        user_uuid = getattr(request.state, "user_uuid", None)

        if request.url.path != "/healthz":
            async with async_session_factory() as session:
                session.add(
                    AuditLog(
                        request_id=request_id,
                        user_uuid=user_uuid,
                        module=request.url.path,
                        latency_ms=latency_ms,
                        error_code=error_code,
                    )
                )
                await session.commit()

        response.headers["X-Request-ID"] = str(request_id)
        return response
