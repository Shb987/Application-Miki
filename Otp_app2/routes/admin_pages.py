from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from core.database import db

# Project root = Otp_app2
BASE_DIR = Path(__file__).resolve().parent.parent  # this gives .../Otp_app2
print(BASE_DIR)
templates = Jinja2Templates(directory="../new/admin/template")
print(templates)
router = APIRouter(tags=["Admin Pages"])

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
@router.get("/question-page", response_class=HTMLResponse)
async def questions_page(request: Request):
    return templates.TemplateResponse("questions.html", {"request": request})

@router.get("/questions/{category}", response_class=HTMLResponse)
async def questions_category_page(request: Request, category: str):
    # Fetch questions for this category from MongoDB (async)
    questions_cursor = db.questions.find({"category": category})
    questions = await questions_cursor.to_list(length=None)

    # Convert ObjectId to string for template rendering
    for q in questions:
        q["_id"] = str(q["_id"])

    return templates.TemplateResponse(
        "questions.html",
        {
            "request": request,
            "category": category,
            "questions": questions
        }
    )


# @router.get("/logins", response_class=HTMLResponse)
# async def logins_page(request: Request):
#     return templates.TemplateResponse("logins.html", {"request": request})
