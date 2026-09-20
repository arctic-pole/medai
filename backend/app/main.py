from fastapi import FastAPI

from app.api.allergies import router as allergies_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.history import router as history_router
from app.api.medications import router as medications_router
from app.api.patient import router as patient_router
from app.api.profile import router as profile_router
from app.audit.middleware import AuditLogMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="MEDAI Backend", version="0.1.0")
    app.add_middleware(AuditLogMiddleware)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(patient_router)
    app.include_router(profile_router)
    app.include_router(history_router)
    app.include_router(allergies_router)
    app.include_router(medications_router)

    return app


app = create_app()
