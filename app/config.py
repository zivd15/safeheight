from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "SafeHeight"
    BASE_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "change-me-to-a-long-random-string-in-production"

    DATABASE_URL: str = "sqlite:///./safeheight.db"

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    MAGIC_LINK_EXPIRE_MINUTES: int = 10080   # 7 days
    OTP_EXPIRE_MINUTES: int = 5

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    FROM_NAME: str = "SafeHeight Certification System"

    UPLOAD_DIR: str = "uploads"
    CERT_DIR: str = "certificates"

    INITIAL_INSTRUCTOR_EMAIL: str = ""
    INITIAL_INSTRUCTOR_PASSWORD: str = ""

    GDRIVE_CREDS_FILE: str = ""
    GDRIVE_FOLDER_ID: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
