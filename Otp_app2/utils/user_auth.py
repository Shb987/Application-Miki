# user_auth.py
from jose import JWTError, jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer
from core.settings import settings
from datetime import datetime, timedelta, timezone
from .admin_auth import decode_access_token as decode_admin_token


oauth2_user_scheme = HTTPBearer()

def create_user_token(mobile_number: str, usertype: str, student_id: str | None = None):
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": mobile_number,
        "role": "user",
        "usertype": usertype,
        "exp": expire
    }
    
    # Only include student_id if it's actually provided (e.g. for student sessions)
    if student_id:
        payload["student_id"] = student_id
    print(payload)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_user_token(token_obj=Depends(oauth2_user_scheme)):
    try:
        token = token_obj.credentials
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired user token")


def get_current_user(token_obj=Depends(oauth2_user_scheme)):
    payload = decode_user_token(token_obj)
    if payload.get("role") != "user":
        raise HTTPException(status_code=403, detail="Users only")
    return payload


def admin_or_user(token_obj=Depends(oauth2_user_scheme)):
    """
    Allows BOTH admin AND user to access endpoints.
    """
    try:
        return decode_user_token(token_obj)
    except:
        try:
            payload = decode_admin_token(token_obj)
            if payload.get("role") == "admin":
                return payload
        except:
            pass

    raise HTTPException(status_code=401, detail="Invalid token")
