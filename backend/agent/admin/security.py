import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def crear_token(admin_id: str) -> str:
    payload = {
        "sub": admin_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, os.environ["ADMIN_JWT_SECRET"], algorithm="HS256")


def decodificar_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, os.environ["ADMIN_JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
