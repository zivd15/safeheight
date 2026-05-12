from __future__ import annotations
import secrets
from datetime import datetime
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Text, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class StudentStatus(str, enum.Enum):
    INVITED = "invited"
    PENDING = "pending"      # submitted profile, awaiting review
    APPROVED = "approved"
    REJECTED = "rejected"


class CertificateStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ── Instructor ────────────────────────────────────────────────────────────────

class Instructor(Base):
    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    full_name_he: Mapped[str] = mapped_column(String(255), default="")
    license_no: Mapped[str] = mapped_column(String(100), default="")
    signature_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    sessions: Mapped[list[TrainingSession]] = relationship(back_populates="instructor")


# ── Training Session ──────────────────────────────────────────────────────────

class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("instructors.id"), nullable=False)
    training_date: Mapped[str] = mapped_column(String(20), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, default="")   # JSON-encoded list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    instructor: Mapped[Instructor] = relationship(back_populates="sessions")
    students: Mapped[list[Student]] = relationship(back_populates="session")


# ── Student ───────────────────────────────────────────────────────────────────

class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("training_sessions.id"), nullable=True)

    # Profile fields — filled in by the student
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name_he: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Hebrew
    national_id: Mapped[str | None] = mapped_column(String(100), nullable=True)   # never exposed publicly
    employer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_id_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selfie_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[StudentStatus] = mapped_column(
        SAEnum(StudentStatus), default=StudentStatus.INVITED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session: Mapped[TrainingSession | None] = relationship(back_populates="students")
    certificates: Mapped[list[Certificate]] = relationship(back_populates="student")


# ── Certificate ───────────────────────────────────────────────────────────────

class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"), nullable=True)
    serial: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, default="")   # JSON-encoded list
    date_issue: Mapped[str] = mapped_column(String(20), nullable=False)
    date_expiry: Mapped[str] = mapped_column(String(20), nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drive_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[CertificateStatus] = mapped_column(
        SAEnum(CertificateStatus), default=CertificateStatus.ACTIVE
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped[Student] = relationship(back_populates="certificates")


# ── Auth Tokens ───────────────────────────────────────────────────────────────

class MagicToken(Base):
    __tablename__ = "magic_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False,
                                       default=lambda: secrets.token_urlsafe(48))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
