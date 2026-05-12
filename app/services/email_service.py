import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os

from app.config import settings


def _send(to: str, subject: str, body: str, attachment_path: str | None = None, cc: str | None = None):
    if not settings.SMTP_USER or not settings.SMTP_PASS:
        print(f"[email] SMTP not configured — would send to {to}: {subject}")
        return

    msg = MIMEMultipart()
    msg["From"] = f"{settings.FROM_NAME} <{settings.SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(attachment_path)}"')
        msg.attach(part)

    recipients = [to] + ([cc] if cc else [])
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.sendmail(settings.SMTP_USER, recipients, msg.as_string())


def send_magic_link(to_email: str, student_name: str, token: str):
    link = f"{settings.BASE_URL}/student/auth/magic/{token}"
    body = f"""Hello {student_name or 'there'},

You have been invited to complete your Working at Height training profile.

Click the link below to access your Student Portal (valid for {settings.MAGIC_LINK_EXPIRE_MINUTES} minutes):

{link}

If you did not request this, you can safely ignore this email.

{settings.FROM_NAME}
"""
    _send(to_email, f"Your SafeHeight Portal Access Link", body)


def send_otp(to_email: str, code: str):
    body = f"""Your SafeHeight one-time verification code is:

  {code}

This code expires in {settings.OTP_EXPIRE_MINUTES} minutes. Do not share it with anyone.

{settings.FROM_NAME}
"""
    _send(to_email, "Your SafeHeight Verification Code", body)


def send_certificate(to_email: str, student_name: str, serial: str,
                     date_expiry: str, pdf_path: str, cc_email: str | None = None):
    body = f"""Dear {student_name},

Your Working at Height Certificate has been issued.

Certificate Serial:  {serial}
Expiry Date:         {date_expiry}

Please find your certificate attached. Keep it on file and present it upon request.

To verify this certificate, visit:
{settings.BASE_URL}/?serial={serial}

{settings.FROM_NAME}
"""
    _send(to_email, f"Certificate Issued: {serial}", body, attachment_path=pdf_path, cc=cc_email)


def send_invite(to_email: str, token: str, training_date: str):
    link = f"{settings.BASE_URL}/student/auth/magic/{token}"
    body = f"""You have been registered for a Working at Height training session on {training_date}.

Please complete your profile before the training date by clicking the link below:

{link}

This link is valid for {settings.MAGIC_LINK_EXPIRE_MINUTES} minutes. Contact your instructor if it has expired.

{settings.FROM_NAME}
"""
    _send(to_email, f"Training Invitation: Working at Height — {training_date}", body)
