"""Day 20: passwords and login tokens.

Passwords: we store a bcrypt HASH, never the password. A hash is a one-way
scramble: you can check a password against it, but you can't turn it back
into the password. If the database leaks, the passwords don't.

Tokens (JWT): after login, the server gives the app a signed token that says
"this is user 42, valid until next week". The app sends it with every
request. The signature (made with JWT_SECRET) means nobody can fake or edit
a token without the secret.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """The user id inside a valid token, or None if it's fake, edited or expired."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
