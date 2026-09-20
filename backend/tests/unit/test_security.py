import uuid

import jwt
import pytest

from app.core.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_token(user_id, "access")
    assert decode_token(token, expected_type="access") == user_id


def test_refresh_token_rejected_as_access_token() -> None:
    user_id = uuid.uuid4()
    token = create_token(user_id, "refresh")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")
