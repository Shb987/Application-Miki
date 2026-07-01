# System Entrypoint & Boot Sequence — `main.py` Deep Dive

`main.py` is the **single root file** that starts and controls the entire Miki Application backend. Every request from every user of the platform passes through this file's configuration before it ever reaches business logic. Here it is explained line-by-line.

---

## Step 1 — All Imports

The very first section of `main.py` imports every single thing the backend needs, organized into groups:

```python
import firebase_admin
from firebase_admin import credentials
import os
from fastapi.templating import Jinja2Templates
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
```

- `firebase_admin` — Google Firebase SDK for sending mobile push notifications.
- `Jinja2Templates` — Full HTML rendering engine used by the Admin dashboard panel.
- `StaticFiles` — Allows FastAPI to serve raw static assets (CSS, JS, PDFs, images).
- `CORSMiddleware` — Handles the browser security rules for cross-domain requests.

Then all 27 route modules are imported in one large block:

```python
from app.routes import (
    admin_routes, user_routes, otp_routes, admin_pages,
    admin_exam_routes, user_exam_routes, exam_evaluation_routes,
    user_futurestudy_routes, admin_quiz_routes, user_quiz_routes,
    companion_routes, chat_routes, ai_tutor_routes,
    admin_tutorial_routes, user_tutorial_routes,
    user_analysis_routes, admin_analysis_routes, user_game_wordle, user_game_squares,
    user_game_chess,
    admin_special_day_routes, user_special_day_routes, voice_assistant_routes,
    admin_stats_routes, admin_user_management_routes,
    admin_notification_routes, admin_games_routes
)
```

Importing a route module does not activate it. It must also be registered with `app.include_router(...)` further below. This separation is intentional — a developer can import a route for testing without accidentally exposing it to the network.

---

## Step 2 — App Initialization

```python
app = FastAPI(title="Miki Application")
```

This single line creates the central ASGI web application object. Everything else in this file attaches to this `app` object. The `title` parameter populates the Swagger documentation interface automatically.

---

## Step 3 — Startup Event (Background Scheduler)

```python
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_special_day_scheduler(db))
```

This is a **FastAPI Lifecycle Hook**. It runs exactly once: the moment `uvicorn` boots the server.

- `start_special_day_scheduler(db)` is a function inside `app/services/scheduler_service.py` that infinitely loops in the background — checking if any holidays or reminders are scheduled for today.
- `asyncio.create_task()` is critical. It runs the scheduler as a **non-blocking background task**. This means the scheduler never pauses web traffic. It co-exists peacefully alongside the rest of the API, sharing the same asyncio event loop.

> If you remove this line, the automatic holiday notification system stops completely.

---

## Step 4 — Firebase Initialization

```python
try:
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin Initialized Successfully")
    else:
        print(f"⚠️ Firebase Credentials not found at {cred_path}.")
except Exception as e:
    print(f"❌ Failed to initialize Firebase: {e}")
```

- Reads the path to the Firebase service account JSON from the `.env` file (`FIREBASE_CREDENTIALS_PATH`). 
- If the file exists at that path, Firebase is initialized. From this point, any service anywhere in the app can issue push notifications to mobile users.
- The entire block is inside `try/except` — so if the file is missing on a developer's local machine, the server still boots gracefully. It just prints a warning and skips push notifications.

---

## Step 5 — Custom Validation Error Handler

```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("💥 Validation Error:", exc.errors())
    print("💥 Body Received:", exc.body)
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "body": exc.body})
```

By default, FastAPI silently returns a `422 Unprocessable Entity` error when a client sends malformed data. This custom handler **intercepts those errors** and also:
- Prints the exact validation error to the server terminal for debugging.
- Echoes back exactly what request body was received, making it incredibly easy to diagnose what the client sent incorrectly.

---

## Step 6 — CORS Middleware (Security)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

CORS controls which external websites (domains) are permitted to call this API from a user's browser.

- `allow_origins=["*"]` — Currently allows **all** origins. In a production environment this should be locked down to specific frontend URLs (e.g., `["https://miki-app.com"]`).
- `allow_credentials=True` — Permits cookies and Authorization headers to be sent cross-origin.
- `allow_methods=["*"]` — All HTTP verbs (GET, POST, PUT, DELETE) are permitted.

---

## Step 7 — Jinja2 Templates

```python
templates = Jinja2Templates(directory="app/templates")
```

This points FastAPI's template engine at the `app/templates/` folder. The `admin_pages.py` router uses this `templates` object to render full HTML pages for the Admin dashboard — returning a complete webpage instead of JSON.

---

## Step 8 — Static File Mounts

```python
app.mount("/assets", StaticFiles(directory="app/static/assets"), name="assets")
app.mount("/dist",   StaticFiles(directory="app/static/dist"),   name="dist")
app.mount("/uploads", StaticFiles(directory="app/static/uploads"), name="uploads")
app.mount("/subject_images", StaticFiles(directory="app/static/subject_images"), name="subject_images")
app.mount("/Domain_pictures", StaticFiles(directory="app/static/Domain_pictures"), name="Domain_pictures")
app.mount("/generated_papers", StaticFiles(directory="app/static/generated_papers"), name="generated_papers")
```

Each `app.mount()` call maps a **URL path** to a **physical folder** on disk, making that folder's files directly downloadable:

| URL Path | Folder on Disk | Purpose |
|---|---|---|
| `/assets` | `app/static/assets` | CSS, JS, fonts for Admin UI |
| `/dist` | `app/static/dist` | Compiled frontend bundles |
| `/uploads` | `app/static/uploads` | User-uploaded media |
| `/subject_images` | `app/static/subject_images` | Subject thumbnail icons |
| `/Domain_pictures` | `app/static/Domain_pictures` | Career/Domain imagery |
| `/generated_papers` | `app/static/generated_papers` | Exported PDF exam files |

---

## Step 9 — Router Registry (The Full Table)

This is where all 27 imported route modules are actually **connected to the live web server**. Each `app.include_router()` call specifies:
- Which router module to attach.
- The **URL prefix** that all its endpoints will be grouped under.
- A **tag** label that appears in the Swagger UI grouping.

| Router Module | URL Prefix | Tag |
|---|---|---|
| `admin_routes` | `/admin-panel` | Admin |
| `admin_exam_routes` | `/admin-panel` | Exam Module |
| `user_routes` | `/user` | User |
| `otp_routes` | `/otp` | OTP |
| `user_exam_routes` | `/user` | User_Exam Module |
| `exam_evaluation_routes` | `/user` | User_Exam Module |
| `user_futurestudy_routes` | `/user` | User_Futurestudy Module |
| `companion_routes` | *(none)* | AI Student Companion |
| `chat_routes` | `/user` | — |
| `ai_tutor_routes` | `/user` | — |
| `admin_pages` | `/admin-panel` | Admin Pages |
| `admin_quiz_routes` | `/admin-panel` | Quiz Module - Admin |
| `user_quiz_routes` | `/user` | Quiz Module - User |
| `admin_tutorial_routes` | *(none)* | Admin Tutorial |
| `user_tutorial_routes` | *(none)* | User Tutorial |
| `admin_analysis_routes` | `/admin-panel` | Analytics Module - Admin |
| `user_analysis_routes` | `/user` | Analytics Module - User |
| `user_game_wordle` | `/user` | Game - Wordle |
| `user_game_squares` | `/user` | Game - Squares |
| `user_game_chess` | `/user` | Game - Chess |
| `admin_special_day_routes` | `/admin-panel` | Special Days - Admin |
| `user_special_day_routes` | `/user` | Special Days - User |
| `admin_stats_routes` | `/admin-panel` | Admin Stats |
| `admin_user_management_routes` | *(none)* | User Management - Admin |
| `admin_notification_routes` | *(none)* | Notifications - Admin |
| `admin_games_routes` | *(none)* | Games - Admin |
| `voice_assistant_routes` | `/user` | Voice Assistant |

> **Ordering matters!** Notice that `admin_pages` is registered *before* `admin_quiz_routes`. This is an intentional URL conflict-prevention strategy — Jinja page routes take precedence.

---

## The Seed Files

Two utility scripts exist at the root level: `seed_wordle.py` and `seed_squares.py`. They are standalone Python scripts that do **not** use FastAPI. A newcomer must run them once on a fresh installation:

```bash
python seed_wordle.py
python seed_squares.py
```

They connect directly to Motor and perform a massive `insert_many()` to populate the `WordleDictionary` and `SquaresLevels` MongoDB collections. Without this step, all game endpoints will return errors because query results will be empty.
