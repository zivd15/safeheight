import json
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.models import Certificate, CertificateStatus, Student, Instructor

router = APIRouter()


def _mask_name(name: str) -> str:
    """J*hn D*e — first and last char of each word, rest masked."""
    def mask_word(w: str) -> str:
        if len(w) <= 2:
            return w
        return w[0] + "*" * (len(w) - 2) + w[-1]
    return " ".join(mask_word(p) for p in name.split())


@router.get("/")
def landing():
    return FileResponse("app/templates/landing.html")


class VerifyRequest(BaseModel):
    serial: str


@router.post("/api/verify")
def verify_certificate(req: VerifyRequest = Body(...), db: Session = Depends(get_db)):
    """
    Public endpoint.
    Returns: validity, masked name, scopes, expiry, instructor credentials.
    NEVER returns: student ID, email, employer, or any personal identifier.
    """
    cert = db.query(Certificate).filter_by(serial=req.serial.strip()).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")

    if cert.status == CertificateStatus.REVOKED:
        return {"valid": False, "reason": "REVOKED", "message": "This certificate has been revoked by the issuing instructor."}

    from datetime import date, datetime
    expiry = datetime.strptime(cert.date_expiry, "%d/%m/%Y").date()
    if expiry < date.today():
        return {"valid": False, "reason": "EXPIRED", "message": "Certificate Not Found or Expired. Please contact the certifying instructor."}

    student = db.query(Student).get(cert.student_id)
    masked_name = _mask_name(student.full_name or "") if student and student.full_name else "Unknown"

    # Instructor credentials for public display
    instructor_name = ""
    instructor_license = ""
    if cert.instructor_id:
        inst = db.query(Instructor).get(cert.instructor_id)
        if inst:
            instructor_name = inst.full_name
            instructor_license = inst.license_no

    scopes = json.loads(cert.scopes) if cert.scopes else []

    return {
        "valid": True,
        "student_name_masked": masked_name,
        "scopes": scopes,
        "date_issue": cert.date_issue,
        "date_expiry": cert.date_expiry,
        "serial": cert.serial,
        "instructor_name": instructor_name,
        "instructor_license": instructor_license,
    }
