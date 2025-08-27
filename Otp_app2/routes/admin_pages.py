from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Project root = Otp_app2
BASE_DIR = Path(__file__).resolve().parent.parent  # this gives .../Otp_app2
print(BASE_DIR)
templates = Jinja2Templates(directory="../new/admin/template")
print(templates)
router = APIRouter(prefix="/admin-panel", tags=["Admin Pages"])

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login_one.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    response = templates.TemplateResponse("index.html", {"request": request})
    response.headers["Cache-Control"] = "no-store"  # Prevents back button from showing old page
    return response

@router.get("/students", response_class=HTMLResponse)
async def students_page(request: Request):
    return templates.TemplateResponse("students.html", {"request": request})

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})

# @router.get("/logins", response_class=HTMLResponse)
# async def logins_page(request: Request):
#     return templates.TemplateResponse("logins.html", {"request": request})
