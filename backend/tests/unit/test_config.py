"""Phase 13 (secrets_management): Settings must refuse to start with a known dev-only default
secret outside environment=="development" — see app/core/config.py's model_validator.

Every test passes both secret fields explicitly rather than relying on the ambient .env file's
current content (which happens to still hold the dev placeholders on this machine, but a test
must not depend on that) — deterministic regardless of what's in .env or the OS environment.
"""

import pytest

from app.core.config import Settings

_DEV_JWT_SECRET = "change-me-in-real-environments-min-32-bytes-long"
_DEV_FIELD_KEY = "kgcgyGwg_TOkwTOdpCClu340NKpRIVU15x2EeNDDtqg="


def _real_fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


_REAL_JWT_SECRET = "a-real-random-secret-at-least-32-bytes-long"


def test_development_environment_allows_the_dev_default_secrets() -> None:
    settings = Settings(environment="development", jwt_secret_key=_DEV_JWT_SECRET, field_encryption_key=_DEV_FIELD_KEY)
    assert settings.jwt_secret_key == _DEV_JWT_SECRET


def test_non_development_environment_rejects_the_default_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(environment="production", jwt_secret_key=_DEV_JWT_SECRET, field_encryption_key=_real_fernet_key())


def test_non_development_environment_rejects_the_default_field_encryption_key() -> None:
    with pytest.raises(ValueError, match="FIELD_ENCRYPTION_KEY"):
        Settings(environment="production", jwt_secret_key=_REAL_JWT_SECRET, field_encryption_key=_DEV_FIELD_KEY)


def test_non_development_environment_rejects_both_defaults_at_once() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY, FIELD_ENCRYPTION_KEY"):
        Settings(environment="staging", jwt_secret_key=_DEV_JWT_SECRET, field_encryption_key=_DEV_FIELD_KEY)


def test_non_development_environment_starts_fine_with_real_secrets() -> None:
    settings = Settings(
        environment="production",
        jwt_secret_key=_REAL_JWT_SECRET,
        field_encryption_key=_real_fernet_key(),
    )
    assert settings.environment == "production"
