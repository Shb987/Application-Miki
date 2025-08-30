from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routes import admin_routes, user_routes, otp_routes, admin_pages  # ✅ import new
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler


app = FastAPI(title="OTP & User Managements")
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

# API routers
app.include_router(admin_routes.router, prefix="/admin-panel", tags=["Admin"])
app.include_router(user_routes.router, prefix="/user", tags=["User"])
app.include_router(otp_routes.router, prefix="/otp", tags=["OTP"])

# Admin Panel page routes (Jinja)
app.include_router(admin_pages.router,prefix="/admin-panel",tags=["Admin Pages"])
