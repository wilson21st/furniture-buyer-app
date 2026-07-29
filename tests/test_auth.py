from app import auth


def test_hash_and_verify_roundtrip():
    hashed = auth.hash_password("s3cret")
    assert hashed != "s3cret"
    assert auth.verify_password("s3cret", hashed) is True


def test_verify_wrong_password():
    hashed = auth.hash_password("s3cret")
    assert auth.verify_password("nope", hashed) is False


def test_verify_empty_hash_is_false():
    assert auth.verify_password("anything", "") is False


def test_session_helpers():
    session: dict = {}
    assert auth.current_user_id(session) is None
    auth.login_session(session, "u001")
    assert auth.current_user_id(session) == "u001"
    auth.logout_session(session)
    assert auth.current_user_id(session) is None
    # logout is idempotent
    auth.logout_session(session)
    assert auth.current_user_id(session) is None
