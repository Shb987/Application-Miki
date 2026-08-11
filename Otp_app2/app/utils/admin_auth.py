from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer
from app.core.settings import settings
from app.core.database import db
from datetime import datetime, timedelta, timezone

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Use simple Bearer token instead of OAuth2 password flow
oauth2_scheme = HTTPBearer()

def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str = Depends(oauth2_scheme)):
    try:
        # HTTPBearer returns object with .credentials
        token_str = token.credentials  
        payload = jwt.decode(token_str, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_admin(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    username: str = payload.get("sub")
    role: str = payload.get("role")

    if username is None or role is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {"sub": username, "role": role}

async def log_admin_activity(username: str, role: str, action: str, details: str, status: str = "success"):
    """Centralized helper to log admin activity into db.admin_activity_logs."""
    try:
        await db.admin_activity_logs.insert_one({
            "username": username,
            "role": role,
            "action": action,
            "status": status,
            "details": details,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:
        pass

def require_permission(module: str, action: str):
    async def permission_checker(token: str = Depends(oauth2_scheme)):
        payload = decode_access_token(token)
        username: str = payload.get("sub")
        role_name: str = payload.get("role")

        if username is None or role_name is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        act_normalized = action.strip().lower()
        mod_normalized = module.strip().lower().replace(" ", "_").replace(",", "")

        if role_name != "superadmin":
            role = await db.roles.find_one({"role_name": role_name})
            if not role:
                raise HTTPException(status_code=403, detail="Role not found")
                
            permissions = role.get("permissions", {})

            # Normalize keys: compare lowercase+stripped to handle typos like
            # "Questions Base" vs "Question Base" saved in DB
            module_normalized = module.strip().lower()
            module_perms = {}
            for db_key, db_val in permissions.items():
                if db_key.strip().lower() == module_normalized:
                    module_perms = db_val
                    break

            if not module_perms.get(action, False):
                raise HTTPException(status_code=403, detail=f"Permission denied for module '{module}' with action '{action}'")

        # Automatically log activity for mutating actions (create, update, delete)
        if act_normalized in ["create", "update", "delete"]:
            action_key = f"{act_normalized}_{mod_normalized}"
            details_str = f"Admin performed {action.upper()} on module '{module}'"
            await log_admin_activity(
                username=username,
                role=role_name,
                action=action_key,
                details=details_str,
                status="success"
            )

        return {"sub": username, "role": role_name}
        
    return permission_checker
