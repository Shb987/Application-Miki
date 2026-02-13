
import firebase_admin
from firebase_admin import credentials
import os
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routes import (
    admin_routes, user_routes, otp_routes, admin_pages,
    admin_exam_routes, user_exam_routes, exam_evaluation_routes,
    user_futurestudy_routes, admin_quiz_routes, user_quiz_routes,
    companion_routes, chat_routes, ai_tutor_routes,
    admin_tutorial_routes, user_tutorial_routes,
    user_analysis_routes, user_game_wordle, user_game_squares
)
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler


app = FastAPI(title="OTP & User Managements")

# ----------------------------------------
# 🔥 FIREBASE INITIALIZATION
# ----------------------------------------
try:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin Initialized Successfully")
    else:
        print(f"⚠️ Firebase Credentials not found at {cred_path}. Push notifications will not work.")
except Exception as e:
    print(f"❌ Failed to initialize Firebase: {e}")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("💥 Validation Error:", exc.errors())
    print("💥 Body Received:", exc.body)
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
# API routers
app.include_router(admin_routes.router, prefix="/admin-panel", tags=["Admin"])
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
app.include_router(user_analysis_routes.router, prefix="/user", tags=["Analytics Module - User"])
# router = APIRouter(tags=["Exam Module11"])

app.include_router(user_game_wordle.router, prefix="/user", tags=["Game - Wordle"])
app.include_router(user_game_squares.router, prefix="/user", tags=["Game - Squares"])


