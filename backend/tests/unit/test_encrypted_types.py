from app.db.encrypted_types import EncryptedString


def test_encrypted_string_roundtrip() -> None:
    col = EncryptedString()
    ciphertext = col.process_bind_param("penicillin allergy", dialect=None)

    assert ciphertext is not None
    assert ciphertext != "penicillin allergy"
    assert col.process_result_value(ciphertext, dialect=None) == "penicillin allergy"


def test_encrypted_string_none_passthrough() -> None:
    col = EncryptedString()
    assert col.process_bind_param(None, dialect=None) is None
    assert col.process_result_value(None, dialect=None) is None
