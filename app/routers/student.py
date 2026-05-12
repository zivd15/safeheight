import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form, Cookie, Body
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.models import Student, StudentStatus, Certificate, CertificateStatus
from app.services.auth import (
    create_jwt, require_student,
    create_magic_token, consume_magic_token,
    create_otp, verify_otp,
)
from app.services.email_service import send_magic_link, send_otp as email_otp
from app.services.storage import save_upload, save_signature_base64

router = APIRouter(prefix="/student")


# ── Auth pages ────────────────────────────────────────────────────────────────

@router.get("/login")
def login_page():
    return FileResponse("app/templates/student_login.html")


class MagicRequest(BaseModel):
    email: EmailStr


@router.post("/auth/magic-link")
def request_magic_link(req: MagicRequest = Body(...), db: Session = Depends(get_db)):
    student = db.query(Student).filter_by(email=req.email).first()
    if not student:
        # Return 200 regardless — don't reveal whether email exists
        return {"message": "If that email is registered, a link has been sent."}
    token = create_magic_token(db, student.id)
    send_magic_link(req.email, student.full_name or "", token)
    return {"message": "If that email is registered, a link has been sent."}


@router.get("/auth/magic/{token}")
def consume_magic(token: str, response: Response, db: Session = Depends(get_db)):
    student = consume_magic_token(db, token)
    if not student:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired. Please request a new one.")
    jwt_token = create_jwt(str(student.id), "student")
    resp = RedirectResponse(url="/student/portal", status_code=302)
    resp.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=3600)
    return resp


class OTPRequest(BaseModel):
    email: EmailStr


@router.post("/auth/otp/request")
def request_otp(req: OTPRequest = Body(...), db: Session = Depends(get_db)):
    student = db.query(Student).filter_by(email=req.email).first()
    if student:
        code = create_otp(db, req.email)
        email_otp(req.email, code)
    return {"message": "If that email is registered, a code has been sent."}


class OTPVerify(BaseModel):
    email: EmailStr
    code: str


@router.post("/auth/otp/verify")
def verify_otp_route(req: OTPVerify = Body(...), db: Session = Depends(get_db)):
    if not verify_otp(db, req.email, req.code):
        raise HTTPException(status_code=400, detail="Invalid or expired code.")
    student = db.query(Student).filter_by(email=req.email).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    jwt_token = create_jwt(str(student.id), "student")
    resp_data = {"redirect": "/student/portal"}
    from fastapi.responses import JSONResponse
    resp = JSONResponse(resp_data)
    resp.set_cookie("access_token", jwt_token, httponly=True, samesite="lax", max_age=3600)
    return resp


# ── Portal ────────────────────────────────────────────────────────────────────

@router.get("/portal")
def portal(payload: dict = Depends(require_student)):
    return FileResponse("app/templates/student_portal.html")


@router.get("/api/me")
def me(payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    return {
        "id": student.id,
        "email": student.email,
        "full_name": student.full_name,
        "full_name_he": student.full_name_he,
        "employer": student.employer,
        "status": student.status,
        "has_photo": bool(student.photo_id_path),
        "has_selfie": bool(student.selfie_path),
        "has_signature": bool(student.signature_path),
    }


class ProfileUpdate(BaseModel):
    full_name: str
    full_name_he: str = ""
    employer: str


@router.post("/api/profile")
def update_profile(data: ProfileUpdate = Body(...), payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    student.full_name = data.full_name.strip()
    student.full_name_he = data.full_name_he.strip()
    student.employer = data.employer.strip()
    if student.status == StudentStatus.INVITED:
        student.status = StudentStatus.PENDING
    db.commit()
    return {"message": "Profile saved."}


class IDUpdate(BaseModel):
    national_id: str


@router.post("/api/national-id")
def update_national_id(data: IDUpdate = Body(...), payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    student.national_id = data.national_id.strip()
    db.commit()
    return {"message": "ID saved."}


@router.post("/api/photo-id")
def upload_photo(
    file: UploadFile = File(...),
    payload: dict = Depends(require_student),
    db: Session = Depends(get_db),
):
    from app.services.storage import save_photo_id
    student = db.query(Student).get(int(payload["sub"]))
    path = save_photo_id(file, subfolder=f"photo_ids/{student.id}")
    student.photo_id_path = path
    if student.status == StudentStatus.INVITED:
        student.status = StudentStatus.PENDING
    db.commit()
    return {"message": "Photo ID uploaded."}


@router.post("/api/selfie")
def upload_selfie(
    file: UploadFile = File(...),
    payload: dict = Depends(require_student),
    db: Session = Depends(get_db),
):
    student = db.query(Student).get(int(payload["sub"]))
    path = save_upload(file, subfolder=f"selfies/{student.id}")
    student.selfie_path = path
    db.commit()
    return {"message": "Profile photo uploaded."}


class SignatureData(BaseModel):
    data_url: str


@router.post("/api/signature")
def upload_signature(data: SignatureData = Body(...), payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    path = save_signature_base64(data.data_url, student.id)
    student.signature_path = path
    db.commit()
    return {"message": "Signature saved."}


@router.get("/api/certificates")
def list_certificates(payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    certs = db.query(Certificate).filter_by(student_id=student.id).all()
    return [
        {
            "id": cert.id,
            "serial": cert.serial,
            "scopes": json.loads(cert.scopes) if cert.scopes else [],
            "date_issue": cert.date_issue,
            "date_expiry": cert.date_expiry,
            "status": cert.status,
        }
        for cert in certs
    ]


@router.get("/certificate/{cert_id}/download")
def download_certificate(cert_id: int, payload: dict = Depends(require_student), db: Session = Depends(get_db)):
    student = db.query(Student).get(int(payload["sub"]))
    cert = db.query(Certificate).filter_by(id=cert_id, student_id=student.id).first()
    if not cert or not cert.pdf_path:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    from fastapi.responses import FileResponse as FR
    return FR(cert.pdf_path, media_type="application/pdf", filename=f"{cert.serial}.pdf")


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/student/login", status_code=302)
    resp.delete_cookie("access_token")
    return resp
