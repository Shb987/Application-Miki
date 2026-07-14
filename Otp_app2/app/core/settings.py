import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Settings:
    # Database
    MONGO_URI: str = os.getenv("MONGO_URI")
    DB_NAME: str = os.getenv("DB_NAME")
    #Onesignal
    ONESIGNAL_APP_ID = os.getenv("ONESIGNAL_APP_ID")
    ONESIGNAL_API_KEY = os.getenv("ONESIGNAL_API_KEY")
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_HOURS: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", 24))
    
    # OTP
    OTP_EXPIRY_MINUTES: int = int(os.getenv("OTP_EXPIRY_MINUTES", 5))
    
    # CORS
    CORS_ALLOWED_ORIGINS: List[str] = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")

    # YouTube API
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY")

    # External Partner API Key (used by external apps to register students)
    EXTERNAL_API_KEY: str = os.getenv("EXTERNAL_API_KEY", "miki-external-api-key-change-me")

    # EduSoft External App API Key
    EDUSOFT_API_KEY: str = os.getenv("EDUSOFT_API_KEY", "edusoft-change-me")

    # Fernet symmetric encryption key — used to encrypt/decrypt EduSoft passwords
    # Generate once with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_SECRET_KEY: str = os.getenv("FERNET_SECRET_KEY", "")

settings = Settings()
