from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from core.database import db
import os

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory="../new/admin/template")

router = APIRouter(tags=["Admin Pages"])


API_BASE = os.getenv("API_BASE")
print('check33333',API_BASE)    
if not API_BASE:
    raise RuntimeError("API_BASE environment variable not set (admin_pages)")


@router.get("/config.js", response_class=HTMLResponse)
async def config_js(request: Request):
    return templates.TemplateResponse(
        "config.js",
        {
            "request": request,
            "API_BASE": API_BASE
        },
        media_type="application/javascript"
    )
# ---------------------------------------
# PUBLIC ROUTES (HTML PAGES ONLY)
# ---------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login_one.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request, tab: str = None):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "active_tab": tab}
    )


@router.get("/students", response_class=HTMLResponse)
async def students_page(request: Request):
    return templates.TemplateResponse("students.html", {"request": request})


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})


@router.get("/question-page", response_class=HTMLResponse)
async def questions_page(request: Request):
    return templates.TemplateResponse("questions.html", {"request": request})



@router.get("/exam_module-page")
async def exam_module_page(request: Request):
    return templates.TemplateResponse("Exammodule.html", {"request": request})

@router.get("/question_generation-page")
async def question_generation_page(request: Request):
    return templates.TemplateResponse("question_generation.html", {"request": request})

@router.get("/generated-question_view-page")
async def generated_question_page(request: Request):
    return templates.TemplateResponse("view_questions.html", {"request": request})


@router.get("/questions/{category}", response_class=HTMLResponse)
async def questions_category_page(request: Request, category: str):
    questions_cursor = db.questions.find({"category": category})
    questions = await questions_cursor.to_list(length=None)

    for q in questions:
        q["_id"] = str(q["_id"])

    return templates.TemplateResponse(
        "questions.html",
        {"request": request, "category": category, "questions": questions}
    )


# ==================== QUIZ MODULE ROUTES ====================

@router.get("/quiz/questions-page", response_class=HTMLResponse)
async def quiz_questions_page(request: Request):
    """Quiz questions management page"""
    return templates.TemplateResponse("quiz_questions.html", {"request": request})


@router.get("/quiz/add-question-page", response_class=HTMLResponse)
async def quiz_add_question_page(request: Request):
    """Add/Edit quiz question page"""
    return templates.TemplateResponse("quiz_add_question.html", {"request": request})


@router.get("/quiz/statistics-page", response_class=HTMLResponse)
async def quiz_statistics_page(request: Request):
    """Quiz statistics dashboard page"""
    return templates.TemplateResponse("quiz_statistics.html", {"request": request})



