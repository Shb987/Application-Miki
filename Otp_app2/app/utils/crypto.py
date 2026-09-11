"""
crypto.py — Fernet symmetric encryption helpers for EduSoft credential storage.

Fernet guarantees that a message encrypted using it cannot be manipulated
or read without the key. The key is loaded once from settings at import time.

IMPORTANT: Keep FERNET_SECRET_KEY in .env safe and backed up.
           Losing the key means stored passwords cannot be decrypted.
"""

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from app.core.settings import settings


def _get_fernet() -> Fernet:
    key = settings.FERNET_SECRET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_SECRET_KEY is not set in environment. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_password(plain: str) -> str:
    """Encrypt a plain-text password and return the encrypted token as a string."""
    fernet = _get_fernet()
    return fernet.encrypt(plain.encode()).decode()


def decrypt_password(token: str) -> str:
    """Decrypt a Fernet-encrypted password token back to plain-text.
    
    Raises HTTP 500 if decryption fails (wrong key / corrupted data).
    """
    fernet = _get_fernet()
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise HTTPException(
            status_code=500,
            detail="Failed to decrypt stored credentials. Contact system administrator."
        )


import secrets
import string

def generate_default_edusoft_credentials(student_doc: dict = None, student_id_str: str = ""):
    """
    Generates default EduSoft auto-credentials:
    - Username: Short numeric student identifier like '327'
    - Password: 6-character random lowercase alphanumeric code like '5uwzop'
    """
    student_doc = student_doc or {}
    raw_user = (
        student_doc.get("admission_no") or 
        student_doc.get("roll_no") or 
        student_doc.get("student_code") or 
        student_doc.get("user_id")
    )
    if raw_user:
        auto_username = str(raw_user).strip()
    elif student_id_str:
        try:
            num_val = int(student_id_str[-6:], 16) % 900 + 100
            auto_username = str(num_val)
        except Exception:
            auto_username = "327"
    else:
        auto_username = "327"

    alphabet = string.ascii_lowercase + string.digits
    auto_password = ''.join(secrets.choice(alphabet) for _ in range(6))

    return auto_username, auto_password
