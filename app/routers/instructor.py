import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Body
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.models import (
    Instructor, TrainingSession, Student, StudentStatus,
    Certificate, CertificateStatus, MagicToken,
)
from app.services.auth import (
    hash_password, verify_password,
    create_jwt, require_instructor,
    create_magic_token, generate_serial,
)
from app.services.email_service import send_certificate, send_invite
from app.services.storage import save_upload
from app.services.certificate_service import generate_pdf

router = APIRouter(prefix="/instructor")


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/login")
def login_page():
    return FileResponse("app/templates/instructor_login.html")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str = ""


@router.post("/auth/login")
def login(req: LoginRequest = Body(...), db: Session = Depends(get_db)):
    instructor = db.query(Instructor).filter_by(email=req.email).first()
    if not instructor or not verify_password(req.password, instructor.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if instructor.mfa_enabled:
        import pyotp
        totp = pyotp.TOTP(instructor.totp_secret)
        if not totp.verify(req.totp_code, valid_window=1):
            raise HTTPException(status_code=401, detail="Invalid MFA code.")

    token = create_jwt(str(instructor.id), "instructor")
    resp = JSONResponse({"redirect": "/instructor/dashboard"})
    resp.set_cookie("access_token", token, httponly=True, samesite="lax", max_age=3600)
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/instructor/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp


# ── First-Time Setup ──────────────────────────────────────────────────────────

@router.get("/setup")
def setup_page(db: Session = Depends(get_db)):
    if db.query(Instructor).count() > 0:
        raise HTTPException(status_code=403, detail="Setup already completed.")
    return FileResponse("app/templates/instructor_setup.html")


class SetupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    license_no: str


@router.post("/api/setup")
def do_setup(req: SetupRequest = Body(...), db: Session = Depends(get_db)):
    if db.query(Instructor).count() > 0:
        raise HTTPException(status_code=403, detail="Setup already completed.")
    import pyotp
    secret = pyotp.random_base32()
    inst = Instructor(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        license_no=req.license_no,
        totp_secret=secret,
        mfa_enabled=True,
    )
    db.add(inst)
    db.commit()
    otp_uri = pyotp.totp.TOTP(secret).provisioning_uri(req.email, issuer_name="SafeHeight")
    return {"message": "Instructor account created.", "totp_uri": otp_uri, "totp_secret": secret}


# ── Protected Pages ───────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(_: dict = Depends(require_instructor)):
    return FileResponse("app/templates/instructor_dashboard.html")


@router.get("/settings")
def settings_page(_: dict = Depends(require_instructor)):
    return FileResponse("app/templates/instructor_settings.html")


@router.get("/sessions/new")
def new_session_page(_: dict = Depends(require_instructor)):
    return FileResponse("app/templates/instructor_session.html")


@router.get("/queue")
def queue_page(_: dict = Depends(require_instructor)):
    return FileResponse("app/templates/instructor_queue.html")


@router.get("/database")
def database_page(_: dict = Depends(require_instructor)):
    return FileResponse("app/templates/instructor_database.html")


# ── API ───────────────────────────────────────────────────────────────────────

@router.get("/api/me")
def api_me(payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    inst = db.query(Instructor).get(int(payload["sub"]))
    return {
        "full_name": inst.full_name,
        "full_name_he": inst.full_name_he,
        "license_no": inst.license_no,
        "email": inst.email,
    }


@router.get("/api/stats")
def stats(payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    from datetime import datetime
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    active_sessions = db.query(TrainingSession).filter(
        TrainingSession.created_at >= month_start
    ).count()
    return {
        "active_sessions_month": active_sessions,
        "pending": db.query(Student).filter_by(status=StudentStatus.PENDING).count(),
        "issued": db.query(Certificate).filter_by(status=CertificateStatus.ACTIVE).count(),
        "total_students": db.query(Student).count(),
        "revoked": db.query(Certificate).filter_by(status=CertificateStatus.REVOKED).count(),
    }


class SettingsUpdate(BaseModel):
    full_name: str
    full_name_he: str = ""
    license_no: str


@router.post("/api/settings")
def update_settings(data: SettingsUpdate = Body(...), payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    inst = db.query(Instructor).get(int(payload["sub"]))
    inst.full_name = data.full_name.strip()
    inst.full_name_he = data.full_name_he.strip()
    inst.license_no = data.license_no.strip()
    db.commit()
    return {"message": "Settings saved."}


@router.post("/api/settings/signature")
def upload_signature(
    file: UploadFile = File(...),
    payload: dict = Depends(require_instructor),
    db: Session = Depends(get_db),
):
    inst = db.query(Instructor).get(int(payload["sub"]))
    path = save_upload(file, "instructor_signatures")
    inst.signature_path = path
    db.commit()
    return {"message": "Signature uploaded."}


class SessionCreate(BaseModel):
    training_date: str
    scopes: list[str]
    student_emails: list[str]


MAX_SESSION_PARTICIPANTS = 10


@router.post("/api/sessions")
def create_session(data: SessionCreate = Body(...), payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    valid_emails = [e.strip().lower() for e in data.student_emails if e.strip()]
    if len(valid_emails) > MAX_SESSION_PARTICIPANTS:
        raise HTTPException(
            status_code=400,
            detail=f"A session cannot have more than {MAX_SESSION_PARTICIPANTS} participants. You submitted {len(valid_emails)}."
        )

    sess = TrainingSession(
        instructor_id=int(payload["sub"]),
        training_date=data.training_date,
        scopes=json.dumps(data.scopes),
    )
    db.add(sess)
    db.flush()

    invited = []
    for email in valid_emails:
        student = db.query(Student).filter_by(email=email).first()
        if not student:
            student = Student(email=email, session_id=sess.id, status=StudentStatus.INVITED)
            db.add(student)
            db.flush()
        token = create_magic_token(db, student.id)
        send_invite(email, token, data.training_date)
        invited.append(email)

    db.commit()
    return {"message": f"Session created. {len(invited)} invitation(s) sent.", "session_id": sess.id}


@router.get("/api/queue")
def get_queue(payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    students = db.query(Student).filter_by(status=StudentStatus.PENDING).order_by(Student.updated_at.desc()).all()
    return [
        {
            "id": s.id,
            "email": s.email,
            "full_name": s.full_name,
            "employer": s.employer,
            "has_photo": bool(s.photo_id_path),
            "has_signature": bool(s.signature_path),
            "submitted_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in students
    ]


@router.get("/api/student/{student_id}")
def get_student_detail(student_id: int, payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    s = db.query(Student).get(student_id)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found.")
    session_scopes = []
    if s.session_id:
        sess = db.query(TrainingSession).get(s.session_id)
        if sess:
            session_scopes = json.loads(sess.scopes) if sess.scopes else []
    return {
        "id": s.id,
        "email": s.email,
        "full_name": s.full_name,
        "full_name_he": s.full_name_he,
        "employer": s.employer,
        "status": s.status,
        "has_photo": bool(s.photo_id_path),
        "has_selfie": bool(s.selfie_path),
        "has_signature": bool(s.signature_path),
        "session_scopes": session_scopes,
    }


@router.get("/api/student/{student_id}/photo")
def get_student_photo(student_id: int, payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    s = db.query(Student).get(student_id)
    if not s or not s.photo_id_path:
        raise HTTPException(status_code=404, detail="Photo not found.")
    import mimetypes
    mime = mimetypes.guess_type(s.photo_id_path)[0] or "image/jpeg"
    return FileResponse(s.photo_id_path, media_type=mime)


@router.get("/api/student/{student_id}/signature")
def get_student_signature(student_id: int, payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    s = db.query(Student).get(student_id)
    if not s or not s.signature_path:
        raise HTTPException(status_code=404, detail="Signature not found.")
    return FileResponse(s.signature_path, media_type="image/png")


class ApproveRequest(BaseModel):
    scopes_override: list[str] | None = None


@router.post("/api/approve/{student_id}")
def approve_student(
    student_id: int,
    body: ApproveRequest = Body(default=ApproveRequest()),
    payload: dict = Depends(require_instructor),
    db: Session = Depends(get_db),
):
    student = db.query(Student).get(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if not student.national_id:
        raise HTTPException(status_code=400, detail="Student has not submitted their ID number.")

    inst = db.query(Instructor).get(int(payload["sub"]))

    # Use instructor override → session scopes → default
    if body.scopes_override:
        scopes = body.scopes_override
    else:
        scopes = ["Ladders (Climbing & Anchoring)"]
        if student.session_id:
            sess = db.query(TrainingSession).get(student.session_id)
            if sess and sess.scopes:
                scopes = json.loads(sess.scopes)

    result = generate_pdf(
        student_name=student.full_name or student.email,
        national_id=student.national_id,
        employer=student.employer or "",
        scopes=scopes,
        instructor_name=inst.full_name,
        license_no=inst.license_no,
        instructor_sig_path=inst.signature_path,
    )

    cert = Certificate(
        student_id=student.id,
        instructor_id=int(payload["sub"]),
        serial=result["serial"],
        checksum="",
        scopes=json.dumps(scopes),
        date_issue=result["date_issue"],
        date_expiry=result["date_expiry"],
        pdf_path=result["path"],
        status=CertificateStatus.ACTIVE,
    )
    db.add(cert)
    student.status = StudentStatus.APPROVED
    db.commit()

    send_certificate(
        to_email=student.email,
        student_name=student.full_name or student.email,
        serial=result["serial"],
        date_expiry=result["date_expiry"],
        pdf_path=result["path"],
        cc_email=inst.email,
    )

    return {"message": f"Certificate {result['serial']} issued and emailed.", "serial": result["serial"]}


@router.post("/api/reject/{student_id}")
def reject_student(student_id: int, payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    student = db.query(Student).get(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    student.status = StudentStatus.REJECTED
    db.commit()
    return {"message": "Student rejected."}


@router.get("/api/certificates")
def list_certificates(
    q: str = "", status: str = "",
    payload: dict = Depends(require_instructor),
    db: Session = Depends(get_db),
):
    query = db.query(Certificate).join(Student)
    if q:
        query = query.filter(
            (Certificate.serial.ilike(f"%{q}%")) | (Student.full_name.ilike(f"%{q}%"))
        )
    if status:
        query = query.filter(Certificate.status == status)
    certs = query.order_by(Certificate.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "serial": c.serial,
            "student_name": c.student.full_name,
            "employer": c.student.employer,
            "date_issue": c.date_issue,
            "date_expiry": c.date_expiry,
            "status": c.status,
        }
        for c in certs
    ]


@router.post("/api/certificates/{cert_id}/revoke")
def revoke_certificate(cert_id: int, payload: dict = Depends(require_instructor), db: Session = Depends(get_db)):
    cert = db.query(Certificate).get(cert_id)
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    cert.status = CertificateStatus.REVOKED
    cert.revoked_at = datetime.utcnow()
    db.commit()
    return {"message": f"Certificate {cert.serial} has been revoked."}
