from fastapi import APIRouter, Depends, HTTPException
from models.admin_models import AdminLogin
from core.database import db
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from utils.auth import verify_password, create_access_token, get_password_hash,get_current_admin

router = APIRouter(tags=["Admin"])

# ✅ Register new admin (for testing, later can restrict)
@router.post("/register")
async def register_admin(admin: AdminLogin):
    existing = await db.admins.find_one({"username": admin.username})
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")

    hashed_pw = get_password_hash(admin.password)
    await db.admins.insert_one({"username": admin.username, "password": hashed_pw})
    return {"message": "Admin registered"}

# ✅ Login
@router.post("/login")
async def login(admin: AdminLogin):
    record = await db.admins.find_one({"username": admin.username})
    if not record:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(admin.password, record["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": record["username"], "role": "admin"})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/get_details")
async def get_admin_me(current_admin: dict = Depends(get_current_admin)):
    return {"username": current_admin["sub"]}


# # Dynamic admin panel route
# @router.get("/admin-panel", response_class=HTMLResponse)
# async def admin_panel(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})