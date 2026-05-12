from __future__ import annotations
import secrets
import hashlib
import base64
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from jose import jwt, JWTError
from fastapi import Cookie, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import Student, Instructor, MagicToken, OTPCode


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_jwt(subject: str, role: str, expires_minutes: int | None = None) -> str:
    exp = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": subject, "role": role, "exp": exp},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")


# ── RBAC Dependencies ─────────────────────────────────────────────────────────

def _get_payload(access_token: str | None = Cookie(default=None)) -> dict:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")
    return decode_jwt(access_token)


def require_student(access_token: str | None = Cookie(default=None)) -> dict:
    p = _get_payload(access_token)
    if p.get("role") != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required.")
    return p


def require_instructor(access_token: str | None = Cookie(default=None)) -> dict:
    p = _get_payload(access_token)
    if p.get("role") != "instructor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor access required.")
    return p


# ── Magic Links ───────────────────────────────────────────────────────────────

def create_magic_token(db: Session, student_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires = datetime.utcnow() + timedelta(minutes=settings.MAGIC_LINK_EXPIRE_MINUTES)
    mt = MagicToken(student_id=student_id, token=token, expires_at=expires)
    db.add(mt)
    db.commit()
    return token


def consume_magic_token(db: Session, token: str) -> Student | None:
    mt = db.query(MagicToken).filter_by(token=token, used=False).first()
    if not mt or mt.expires_at < datetime.utcnow():
        return None
    mt.used = True
    db.commit()
    return db.query(Student).get(mt.student_id)


# ── OTP ───────────────────────────────────────────────────────────────────────

def create_otp(db: Session, email: str) -> str:
    code = str(secrets.randbelow(900000) + 100000)   # 6-digit
    expires = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    db.add(OTPCode(email=email, code=code, expires_at=expires))
    db.commit()
    return code


def verify_otp(db: Session, email: str, code: str) -> bool:
    record = (
        db.query(OTPCode)
        .filter_by(email=email, code=code, used=False)
        .order_by(OTPCode.created_at.desc())
        .first()
    )
    if not record or record.expires_at < datetime.utcnow():
        return False
    record.used = True
    db.commit()
    return True


# ── Certificate Crypto ────────────────────────────────────────────────────────

def generate_serial(student_name: str) -> str:
    year = datetime.utcnow().year
    parts = student_name.strip().split()
    initials = "".join(p[0].upper() for p in parts[:2]) if parts else "XX"
    suffix = secrets.token_hex(3).upper()
    return f"GWH-{year}-{initials}{suffix}"


def generate_checksum(national_id: str, serial: str) -> str:
    raw = (national_id + serial).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return base64.b64encode(digest).decode("utf-8")[:16]
