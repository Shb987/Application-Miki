
import firebase_admin
from firebase_admin import credentials
import os
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routes import (
    admin_routes, admin_roles_routes, user_routes, otp_routes, admin_pages,
    admin_exam_routes, user_exam_routes, exam_evaluation_routes,
    user_futurestudy_routes, admin_quiz_routes, user_quiz_routes,
    companion_routes, chat_routes, ai_tutor_routes,
    admin_tutorial_routes, user_tutorial_routes,
    user_analysis_routes, admin_analysis_routes, user_game_wordle, user_game_squares,
    user_game_chess, user_game_puzzle,
    admin_special_day_routes, user_special_day_routes, voice_assistant_routes,
    admin_stats_routes, admin_user_management_routes,
    admin_notification_routes, admin_games_routes, user_tuition_routes,
    payment_routes, admin_plan_routes, admin_school_routes, public_school_routes,
    external_registration_routes, admin_social_routes, contributor_routes, user_social_routes,
    edusoft_routes
) 

from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from app.core.database import db
from app.services.scheduler_service import start_special_day_scheduler, start_tuition_scheduler
import asyncio



app = FastAPI(title="Miki Application")

@app.on_event("startup")
async def startup_event():
    # Automatically seed default admin if not existing
    try:
        pass
    except Exception as e:
        print(f"[WARN] Failed to auto-seed admin: {e}")
    # Start the background scheduler for Special Days
    asyncio.create_task(start_special_day_scheduler(db))
    # Start the background scheduler for Digital Tuition
    asyncio.create_task(start_tuition_scheduler(db))

# ----------------------------------------
# 🔥 FIREBASE INITIALIZATION
# ----------------------------------------
try:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("[Firebase] Admin Initialized Successfully")
    else:
        print(f"[WARN] Firebase Credentials not found at {cred_path}. Push notifications will not work.")
except Exception as e:
    print(f"[ERROR] Failed to initialize Firebase: {e}")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("[ERROR] Validation Error:", exc.errors())
    print("[ERROR] Body Received:", exc.body)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )




# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


templates = Jinja2Templates(directory="app/templates")

app.mount("/assets", StaticFiles(directory="app/static/assets"), name="assets")
app.mount("/dist", StaticFiles(directory="app/static/dist"), name="dist")
app.mount("/uploads", StaticFiles(directory="app/static/uploads"), name="uploads")
app.mount("/subject_images", StaticFiles(directory="app/static/subject_images"), name="subject_images")
app.mount("/Domain_pictures", StaticFiles(directory="app/static/Domain_pictures"), name="Domain_pictures")
app.mount("/generated_papers", StaticFiles(directory="app/static/generated_papers"), name="generated_papers")
app.mount("/static/games", StaticFiles(directory="app/static/games"), name="games")
# API routers
app.include_router(admin_routes.router, prefix="/admin-panel", tags=["Admin"])
app.include_router(admin_roles_routes.router, prefix="/admin-panel", tags=["Admin Roles"])
app.include_router(admin_exam_routes.router,prefix="/admin-panel", tags=["Exam Module"])
app.include_router(user_routes.router, prefix="/user", tags=["User"])
app.include_router(otp_routes.router, prefix="/otp", tags=["OTP"])
app.include_router(user_exam_routes.router,prefix="/user", tags=["User_Exam Module"])
app.include_router(exam_evaluation_routes.router,prefix="/user", tags=["User_Exam Module"])
app.include_router(user_futurestudy_routes.router,prefix="/user", tags=["User_Futurestudy Module"])
app.include_router(companion_routes.router, tags=["AI Student Companion"])
app.include_router(chat_routes.router, prefix="/user")
app.include_router(ai_tutor_routes.router, prefix="/user")

# Admin Panel page routes (Jinja) - MUST come before admin_quiz_routes to avoid conflicts
app.include_router(admin_pages.router,prefix="/admin-panel",tags=["Admin Pages"])

# Quiz API routes - comes after pages to avoid shadowing
app.include_router(admin_quiz_routes.router, prefix="/admin-panel", tags=["Quiz Module - Admin"])
app.include_router(user_quiz_routes.router, prefix="/user", tags=["Quiz Module - User"])
app.include_router(admin_tutorial_routes.router, tags=["Admin Tutorial"])
app.include_router(user_tutorial_routes.router, tags=["User Tutorial"])
        
# Analytics Module routes
app.include_router(admin_analysis_routes.router, prefix="/admin-panel", tags=["Analytics Module - Admin"])
app.include_router(user_analysis_routes.router, prefix="/user", tags=["Analytics Module - User"])

app.include_router(user_game_wordle.router, prefix="/user", tags=["Game - Wordle"])
app.include_router(user_game_squares.router, prefix="/user", tags=["Game - Squares"])
app.include_router(user_game_chess.router, prefix="/user", tags=["Game - Chess"])
app.include_router(user_game_puzzle.router, prefix="/user", tags=["Game - Puzzle"])

# Special Days
app.include_router(admin_special_day_routes.router, prefix="/admin-panel", tags=["Special Days - Admin"])
app.include_router(user_special_day_routes.router, prefix="/user", tags=["Special Days - User"])

# New Admin Features
app.include_router(admin_stats_routes.router, prefix="/admin-panel", tags=["Admin Stats"])
app.include_router(admin_user_management_routes.router, prefix="", tags=["User Management - Admin"])
app.include_router(admin_notification_routes.router, prefix="", tags=["Notifications - Admin"])
app.include_router(admin_plan_routes.router, prefix="/admin-panel", tags=["Admin Plan Management"])

app.include_router(admin_games_routes.router, prefix="", tags=["Games - Admin"])

app.include_router(voice_assistant_routes.router,prefix="/user",tags=["Voice Assistant"])

# Digital Tuition
app.include_router(user_tuition_routes.router,prefix="",tags=["Digital Tuition"])

# Payment & Subscriptions
app.include_router(payment_routes.router)

# Schools
app.include_router(admin_school_routes.router, prefix="/admin-panel", tags=["Admin Schools"])
app.include_router(public_school_routes.router, prefix="/public", tags=["Public Schools"])

# External Partner API
app.include_router(external_registration_routes.router, prefix="/api/v1", tags=["External Registration"])

# EduSoft External App — Credential Storage & Retrieval
app.include_router(edusoft_routes.router, prefix="/api/v1/edusoft", tags=["EduSoft External API"])

# Social Media Module
app.include_router(admin_social_routes.router, prefix="/admin-panel/social", tags=["Admin Social"])
app.include_router(contributor_routes.router, prefix="/contributor", tags=["Contributor Social"])
app.include_router(user_social_routes.router, prefix="/user/social", tags=["User Social"])
