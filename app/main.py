import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import public, student, instructor

app = FastAPI(
    title="SafeHeight",
    docs_url=None,     # disable public docs in production
    redoc_url=None,
)

# Ensure upload/cert directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CERT_DIR, exist_ok=True)

app.include_router(public.router)
app.include_router(student.router)
app.include_router(instructor.router)


@app.on_event("startup")
def on_startup():
    init_db()
    _seed_instructor()


def _seed_instructor():
    """Create the initial instructor account from env vars if none exists."""
    from app.database import SessionLocal
    from app.models.models import Instructor
    from app.services.auth import hash_password

    if not settings.INITIAL_INSTRUCTOR_EMAIL or not settings.INITIAL_INSTRUCTOR_PASSWORD:
        return

    db = SessionLocal()
    try:
        if db.query(Instructor).count() == 0:
            inst = Instructor(
                email=settings.INITIAL_INSTRUCTOR_EMAIL,
                hashed_password=hash_password(settings.INITIAL_INSTRUCTOR_PASSWORD),
                full_name="Instructor",
                license_no="",
                mfa_enabled=False,
            )
            db.add(inst)
            db.commit()
            print(f"[startup] Seeded instructor: {settings.INITIAL_INSTRUCTOR_EMAIL}")
    finally:
        db.close()
