from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routes import admin_routes, user_routes, otp_routes, admin_pages  # ✅ import new

app = FastAPI(title="OTP & User Managements")

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
app.include_router(admin_routes.router, prefix="/admin", tags=["Admin"])
app.include_router(user_routes.router, prefix="/user", tags=["User"])
app.include_router(otp_routes.router, prefix="/otp", tags=["OTP"])

# Admin Panel page routes (Jinja)
app.include_router(admin_pages.router)
