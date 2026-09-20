from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

_fernet = Fernet(settings.field_encryption_key.encode())


class EncryptedString(TypeDecorator):
    """Application-level encryption at rest for sensitive text columns.

    Per medai_spec.yaml security.minimum_requirements: encrypted_sensitive_data. This
    complements (not replaces) transport-level TLS and any infra-level disk encryption
    decided in Phase 13 — see docs/SECURITY.md.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return _fernet.decrypt(value.encode()).decode()
