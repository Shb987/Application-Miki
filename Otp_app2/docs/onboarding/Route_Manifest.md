# The Complete Route Manifest

Every user request enters the backend through one of 27 route modules. This page explains every single file: what it does, what URL prefix it sits under, who can call it, and what real-world scenarios it handles.

---

## Understanding Route Prefixes

Before reading the list, it is important to understand how URL prefixes work in this system. When `main.py` registers:

```python
app.include_router(user_exam_routes.router, prefix="/user", tags=["User_Exam Module"])
```

...it means every endpoint defined inside `user_exam_routes.py` will be available at `/user/<whatever_path_the_route_defines>`. So an endpoint like `@router.get("/exams")` inside that file becomes reachable at `GET /user/exams`.

---

## Group 1 — Admin Management (`/admin-panel`)

All routes in this group are protected by `admin_auth.py`. Any request without a valid Admin JWT will be rejected at the middleware level before reaching the route logic.

---

### `admin_routes.py` → prefix: `/admin-panel`
**Tag:** Admin

The general-purpose admin hub. This handles foundational administrative operations that don't belong to a specific sub-module. Think of it as the "miscellaneous admin drawer":
- Fetching the full list of enrolled students.
- Updating globalized platform configuration settings.
- Accessing admin profile details and password management.

---

### `admin_pages.py` → prefix: `/admin-panel`
**Tag:** Admin Pages

> ⚠️ This is the only route file that does NOT return JSON responses.

This router renders the full Admin Dashboard as HTML pages using Jinja2 templates. When an admin opens their browser and visits `/admin-panel/dashboard`, this router fetches data from MongoDB, injects it into the HTML template, and returns a fully rendered page to the browser. This is the Server-Side Rendering (SSR) layer powering the visual admin interface:
- `/admin-panel/` → Login page
- `/admin-panel/dashboard` → Main stats overview
- `/admin-panel/students` → Student list table
- `/admin-panel/exam-module` → Exam management panel

> It is registered in `main.py` **before** `admin_quiz_routes` intentionally. If their URL paths ever conflict, the Pages router wins.

---

### `admin_exam_routes.py` → prefix: `/admin-panel`
**Tag:** Exam Module

This router owns the entire Question Bank and Exam lifecycle from the admin's perspective:
- **CRUD for Questions:** Creating questions with subject tags, difficulty levels, and correct answer mappings. Questions may also contain image references or HTML equation markup.
- **Exam Assembly:** Pulling a filtered set of questions (e.g., "10 Hard Chemistry questions") and packaging them into a named Exam collection.
- **PDF Generation:** Triggering the report module to compile the exam into a downloadable `.pdf` file stored in `/app/static/generated_papers/`.

---

### `admin_quiz_routes.py` → prefix: `/admin-panel`
**Tag:** Quiz Module - Admin

A lighter-weight alternative to formal exams. Where exams are comprehensive and PDF-based, quizzes are short (5-15 questions), ephemeral, and auto-graded. Admin routes here handle:
- Creating and publishing quiz sets for specific grades/subjects.
- Viewing aggregate quiz results per student class.

---

### `admin_user_management_routes.py` → prefix: *(none)*
**Tag:** User Management - Admin

Despite the admin theme, this router has no prefix, meaning its routes are mounted directly on the root (e.g., `/admin/users`). Its exclusive purpose:
- Listing all registered users with pagination.
- Banning or suspending specific user accounts.
- Elevating standard users to admin role.
- Deleting stale or test accounts from the database.

---

### `admin_analysis_routes.py` → prefix: `/admin-panel`
**Tag:** Analytics Module - Admin

Provides the admin with a bird's-eye view of platform-wide educational health:
- Aggregated exam score distributions.
- Subject-specific failure rate trends over a date range.
- Overall student engagement metrics derived from `analysis_service.py`.

---

### `admin_stats_routes.py` → prefix: `/admin-panel`
**Tag:** Admin Stats

Focused specifically on gamification and AI cost metrics:
- Leaderboard standings for Chess, Wordle, and Squares across all users.
- Total AI token consumption and estimated cost reports (sourced from the `ai_usage_logger` MongoDB collection).

---

### `admin_notification_routes.py` → prefix: *(none)*
**Tag:** Notifications - Admin

The manual blast mechanism for push notifications:
- Admin provides a title and message body.
- This router collects all active user FCM (Firebase Cloud Messaging) device tokens.
- It hands them off to `notification_service.py` which batches and dispatches push notifications to every registered mobile device simultaneously.

---

### `admin_games_routes.py` → prefix: *(none)*
**Tag:** Games - Admin

Provides administrative controls over the gamification layer:
- Resetting leaderboard standings at the end of a season/month.
- Force-completing or resetting a user's game streak.
- Monitoring which games have had the highest activity recently.

---

### `admin_special_day_routes.py` → prefix: `/admin-panel`
**Tag:** Special Days - Admin

Manages the calendar-aware notification scheduler. From here, admins:
- Create "Special Day" entries (holidays, exam reminder dates) in the MongoDB collection.
- Update or delete existing entries.
- The `scheduler_service.py` background task silently reads this collection daily to determine if automated push notifications should fire.

---

### `admin_tutorial_routes.py` → prefix: *(none)*
**Tag:** Admin Tutorial

Manages the video onboarding curriculum that students must watch:
- Uploading tutorial video links and descriptions.
- Tagging tutorials to apply to specific grade levels.
- Managing whether a specific tutorial is active or archived.

---

## Group 2 — User-Facing Endpoints (`/user`)

All routes here require a valid **Student/User JWT Token**. Admin tokens are rejected.

---

### `user_routes.py` → prefix: `/user`
**Tag:** User

The personal account hub for a logged-in student:
- `GET /user/profile` — Fetch the full user profile document.
- `PUT /user/profile` — Update avatar, name, or preferences.
- `POST /user/register` — Create a brand-new user account.
- `POST /user/login` — Authenticate with credentials and receive a JWT.

---

### `user_exam_routes.py` → prefix: `/user`
**Tag:** User_Exam Module

Provides study access to formal exams:
- Listing all published exams the student is eligible to take.
- Fetching the question list for a specific exam.
- Submitting final answers at the end of a timed session.

---

### `exam_evaluation_routes.py` → prefix: `/user`
**Tag:** User_Exam Module

> This is one of the most complex and slowest endpoints in the application.

When students submit **subjective/essay-type answers**, this route handles the evaluation pipeline:
1. Accepts the student's written answer alongside the original question ID.
2. Fetches the expected answer key from the Question Bank.
3. Bundles both into a structured prompt.
4. Sends the prompt to an external LLM (e.g., OpenAI GPT) with explicit grading instructions.
5. Parses the AI's structured JSON score (marks, feedback, weak areas) and stores it against the student's record.

> Because it calls an external AI API, this endpoint may take 5-15 seconds. Frontend implementations must show a loading indicator to prevent duplicate submissions.

---

### `user_quiz_routes.py` → prefix: `/user`
**Tag:** Quiz Module - User

Student-facing quiz experience:
- Starting a quiz session (selecting subject and difficulty).
- Fetching questions one-at-a-time or in batch.
- Submitting answers and receiving an immediate, server-calculated results summary.
- Viewing historical quiz scores and progression.

---

### `user_futurestudy_routes.py` → prefix: `/user`
**Tag:** User_Futurestudy Module

Returns the personalized AI-calculated study recommendations for a student:
- Reads the student's historical exam and quiz performance from MongoDB.
- Pipes it through `future_study_service.py` which calculates subject-level weakness vectors.
- Integrates YouTube video supplements from `youtube_service.py`.
- Returns a prioritized study plan specific to that student.

---

### `user_analysis_routes.py` → prefix: `/user`
**Tag:** Analytics Module - User

Personal analytics visible to the student:
- Score trends over the last N exams.
- Subject-by-subject breakdown of accuracy.
- Comparison of their performance relative to class averages.

---

### `user_special_day_routes.py` → prefix: `/user`
**Tag:** Special Days - User

Read-only access to the holiday and reminder calendar:
- `GET /user/special-days` — Returns the list of upcoming holidays.
- Students use this to plan around school calendars.

---

### `user_tutorial_routes.py` → prefix: *(none)*
**Tag:** User Tutorial

Student read-only access to the tutorial curriculum:
- Fetching available tutorial videos for their grade level.
- Marking a tutorial as "watched" to track completion.

---

## Group 3 — Authentication (`/otp`)

### `otp_routes.py` → prefix: `/otp`
**Tag:** OTP

> These routes have **no authentication dependency**. They exist specifically to issue authentication to users who don't have tokens yet.

The One-Time Password (OTP) system handles identity verification:
- `POST /otp/send` — Generates a short-lived numeric code and dispatches it to the user's phone or email.
- `POST /otp/verify` — Verifies the code entered by the user. On success, it issues a JWT token that the client stores for subsequent API calls.
- Rate limiting should be enforced at the infrastructure layer (e.g., nginx or a gateway) to prevent OTP flooding/brute-force attacks.

---

## Group 4 — AI-Powered Interactions

### `ai_tutor_routes.py` → prefix: `/user`
The interactive AI tutoring endpoint. A student types a question about a syllabus topic. This route:
- Prepends a strict "act as a Socratic tutor" system prompt to prevent the AI from simply giving away answers.
- Passes the conversation history alongside the new query to maintain context.
- Returns a guided response nudging the student toward self-discovery.

---

### `companion_routes.py` → prefix: *(none)*
**Tag:** AI Student Companion

Different in tone from the Tutor, the Companion focuses on motivation and emotional support:
- Maintains longer-term conversational memory about the student.
- Discusses study habits, stress, and goal-setting.
- Can access the student's `FutureStudy` data to weave in specific, personalized encouragement.

---

### `chat_routes.py` → prefix: `/user`
Standard messaging infrastructure powering both the Tutor and Companion UIs:
- Creating new chat sessions.
- Fetching paginated conversation history.
- Clearing or archiving chat threads.

---

### `voice_assistant_routes.py` → prefix: `/user`
**Tag:** Voice Assistant

The multi-modal audio interface:
1. Accepts an audio payload (Base64-encoded or binary stream).
2. Transcribes voice to text using an STT (Speech-to-Text) engine.
3. Routes the transcribed intent through the `ai_tutor_service`.
4. Converts the AI text response back to speech using TTS.
5. Returns the audio output for playback on the client device.

---

## Group 5 — Game Engines (`/user`)

### `user_game_chess.py` → prefix: `/user`
**Tag:** Game - Chess

Every chess move a student makes is validated server-side:
- `POST /user/chess/move` — Accepts a move string (e.g. `e2e4`), validates it against the current board state, calculates the AI bot's counter-move using Minimax, and returns the new game state.
- `POST /user/chess/new-game` — Initializes a fresh board and resets session state.
- Move validation ensures no illegal moves (en passant, castling misuse) can be submitted by a modified client.

---

### `user_game_wordle.py` → prefix: `/user`
**Tag:** Game - Wordle

Daily word-guessing game endpoints:
- `POST /user/wordle/guess` — Takes a 5-letter string. Returns a feedback array: `G` (Green/correct position), `Y` (Yellow/wrong position), `B` (Black/not in word). All letter-frequency edge cases are handled natively by `wordle_service.py`.
- `GET /user/wordle/status` — Returns today's attempt history and win/loss state.
- The system tracks daily streaks and updates the student's `PlayerStats` document on each win.

---

### `user_game_squares.py` → prefix: `/user`
**Tag:** Game - Squares

The spatial puzzle game:
- `GET /user/squares/board` — Fetches a dynamically generated puzzle from the `SquaresLevels` collection seeded by `seed_squares.py`.
- `POST /user/squares/submit` — Validates the student's solution path against the proven correct solution stored server-side, preventing any client-side cheating.
