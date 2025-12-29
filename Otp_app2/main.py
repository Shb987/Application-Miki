
import firebase_admin
from firebase_admin import credentials
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routes import admin_routes, user_routes, otp_routes, admin_pages ,admin_exam_routes,user_exam_routes, exam_evaluation_routes, user_futurestudy_routes, admin_quiz_routes, user_quiz_routes
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


# Mount static assets (CSS, JS, images)
app.mount("/assets", StaticFiles(directory="../new/admin/assets"), name="assets")
app.mount("/dist", StaticFiles(directory="../new/admin/dist"), name="dist")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.mount("/static/generated_papers", StaticFiles(directory="Exams/generated_papers"), name="generated_papers")
app.mount("/subject_images", StaticFiles(directory="Subject_images"), name="subject_images")

# API routers
app.include_router(admin_routes.router, prefix="/admin-panel", tags=["Admin"])
app.include_router(admin_exam_routes.router,prefix="/admin-panel", tags=["Exam Module"])
app.include_router(user_routes.router, prefix="/user", tags=["User"])
app.include_router(otp_routes.router, prefix="/otp", tags=["OTP"])
app.include_router(user_exam_routes.router,prefix="/user", tags=["User_Exam Module"])
app.include_router(exam_evaluation_routes.router,prefix="/user", tags=["User_Exam Module"])
app.include_router(user_futurestudy_routes.router,prefix="/user", tags=["User_Futurestudy Module"])

# Admin Panel page routes (Jinja) - MUST come before admin_quiz_routes to avoid conflicts
app.include_router(admin_pages.router,prefix="/admin-panel",tags=["Admin Pages"])

# Quiz API routes - comes after pages to avoid shadowing
app.include_router(admin_quiz_routes.router, prefix="/admin-panel", tags=["Quiz Module - Admin"])
app.include_router(user_quiz_routes.router, prefix="/user", tags=["Quiz Module - User"])
# router = APIRouter(tags=["Exam Module11"])



