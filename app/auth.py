"""Password hashing + session-based login helpers.

Uses pbkdf2_sha256 (pure-stdlib via passlib) so there's no native bcrypt build to
worry about. Session state is a signed cookie managed by Starlette's
SessionMiddleware — we only ever store the ``user_id``.
"""

from __future__ import annotations

from passlib.context import CryptContext

_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

SESSION_USER_KEY = "user_id"


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    if not hashed:
        return False
    return _pwd.verify(raw, hashed)


def login_session(session: dict, user_id: str) -> None:
    session[SESSION_USER_KEY] = user_id


def logout_session(session: dict) -> None:
    session.pop(SESSION_USER_KEY, None)


def current_user_id(session: dict) -> str | None:
    return session.get(SESSION_USER_KEY)
