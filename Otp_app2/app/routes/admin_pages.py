# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Request
# pyrefly: ignore [missing-import]
from fastapi.responses import HTMLResponse
# pyrefly: ignore [missing-import]
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.core.database import db
import os

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory="app/templates/admin/template")

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

@router.get("/manage-textbooks-page")
async def manage_textbooks_page(request: Request):
    return templates.TemplateResponse("manage_textbooks.html", {"request": request})

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

@router.get("/tutorials-page", response_class=HTMLResponse)
async def tutorials_page(request: Request):
    """Tutorial management page"""
    return templates.TemplateResponse("tutorials.html", {"request": request})

@router.get("/manage-syllabus-page", response_class=HTMLResponse)
async def manage_syllabus_page(request: Request):
    """Syllabus management page"""
    return templates.TemplateResponse("manage_syllabus.html", {"request": request})


@router.get("/special-days-page", response_class=HTMLResponse)
async def special_days_page(request: Request):
    """Special Days management page"""
    return templates.TemplateResponse("special_days.html", {"request": request})


# ==================== ANALYTICS MODULE ROUTES ====================

@router.get("/analytics-dashboard-page", response_class=HTMLResponse)
async def analytics_dashboard_page(request: Request):
    """Analytics dashboard page"""
    return templates.TemplateResponse("analysis_dashboard.html", {"request": request})


@router.get("/student-analytics-page", response_class=HTMLResponse)
async def student_analytics_page(request: Request):
    """Individual student analytics page"""
    return templates.TemplateResponse("student_analytics.html", {"request": request})

@router.get("/ai-usage-dashboard-page", response_class=HTMLResponse)
async def ai_usage_dashboard_page(request: Request):
    """AI Usage dashboard page"""
    return templates.TemplateResponse("admin_ai_dashboard.html", {"request": request})


# ==================== NEW FEATURE ROUTES ====================

@router.get("/user-management-page", response_class=HTMLResponse)
async def user_management_page(request: Request):
    """User Management page — search, filter, delete students & parents"""
    return templates.TemplateResponse("user_management.html", {"request": request})

@router.get("/student-profile-page", response_class=HTMLResponse)
async def student_profile_page(request: Request, id: str):
    """Dedicated Student Profile Dashboard"""
    return templates.TemplateResponse("student_profile.html", {"request": request, "student_id": id})


@router.get("/notification-center-page", response_class=HTMLResponse)
async def notification_center_page(request: Request):
    """Notification Center — compose & broadcast push notifications"""
    return templates.TemplateResponse("notification_center.html", {"request": request})


@router.get("/games-management-page", response_class=HTMLResponse)
async def games_management_page(request: Request):
    """Games Management — Wordle & Squares admin UI"""
    return templates.TemplateResponse("games_management.html", {"request": request})

@router.get("/manage-plans-page", response_class=HTMLResponse)
async def manage_plans_page(request: Request):
    """Admin page to view and edit subscription plans"""
    return templates.TemplateResponse("manage_plans.html", {"request": request})

@router.get("/transaction-history-page", response_class=HTMLResponse)
async def transaction_history_page(request: Request):
    """Admin page to view all subscription transactions"""
    return templates.TemplateResponse("transaction_history.html", {"request": request})

@router.get("/manage-schools-page", response_class=HTMLResponse)
async def manage_schools_page(request: Request):
    """Render the Manage Schools admin page."""
    return templates.TemplateResponse("manage_schools.html", {"request": request})

@router.get("/manage-contributors-page", response_class=HTMLResponse)
async def manage_contributors_page(request: Request):
    """Render the Manage Contributors admin page for Social Media."""
    return templates.TemplateResponse("manage_contributors.html", {"request": request})

@router.get("/manage-social-content-page", response_class=HTMLResponse)
async def manage_social_content_page(request: Request):
    """Render the Manage Social Content admin page."""
    return templates.TemplateResponse("manage_social_content.html", {"request": request})

@router.get("/manage-roles-page", response_class=HTMLResponse)
async def manage_roles_page(request: Request):
    """Render the Roles & Permissions management page (superadmin only)."""
    return templates.TemplateResponse("manage_roles.html", {"request": request})
