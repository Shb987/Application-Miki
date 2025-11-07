from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from routes import admin_routes, user_routes, otp_routes, admin_pages

app = FastAPI(title="OTP & User Managements")

# ✅ Custom Validation Exception Handler (fixed FormData issue)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("💥 Validation Error:", exc.errors())

    # Safely extract body or form data
    body_data = None
    try:
        body_data = await request.json()
    except Exception:
        try:
            form = await request.form()
            body_data = dict(form)
        except Exception:
            pass

    print("💥 Body Received:", body_data)

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": body_data
        },
    )

# ✅ CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Mount static assets (for admin panel)
app.mount("/assets", StaticFiles(directory="../new/admin/assets"), name="assets")
app.mount("/dist", StaticFiles(directory="../new/admin/dist"), name="dist")

# ✅ Include API routes
app.include_router(admin_routes.router, prefix="/admin-panel", tags=["Admin"])
app.include_router(user_routes.router, prefix="/user", tags=["User"])
app.include_router(otp_routes.router, prefix="/otp", tags=["OTP"])
app.include_router(admin_pages.router, prefix="/admin-panel", tags=["Admin Pages"])
