# Key Services — Deep Dive

Services are the **brain** of the application. Routers handle HTTP traffic; Services handle all complex logic. This document dissects the most critical service files with real code references so you understand exactly what's happening under the hood.

---

## `chess_service.py` — The Pure Python Chess Engine

This is arguably the most technically sophisticated file in the entire project. Instead of relying on an external program like Stockfish (which is impossible to run in most cloud containers), the team built a fully self-contained chess AI in pure Python.

### How the Bot Evaluates a Board

The engine uses two systems working together:

**1. Material Value (Piece Worth)**

Each piece on the board has a numeric value assigned:

```python
PIECE_VALUES = {
    chess.PAWN:   100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK:   500,
    chess.QUEEN:  900,
    chess.KING: 20000,
}
```

The engine sums all the white pieces' values and subtracts all the black pieces' values. A positive result means White is winning materially; negative means Black is winning.

**2. Positional Bonus Tables (Piece-Square Tables)**

Simply counting material isn't enough — a Knight in the center of the board is far stronger than a Knight stuck in a corner. Each piece type has a 64-square lookup table that awards or penalizes points based on position. For example, a Knight on `a1` (a corner) earns `-50` bonus points, while a Knight on `d4` (active center) earns `+20`:

```python
KNIGHT_TABLE = [
    -50,-40,-30,-30,-30,-30,-40,-50,  # Rank 8 — corners penalized heavily
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,  # Center positions heavily rewarded
    ...
]
```

This is how the bot "prefers" active development and center control rather than random moves.

### The Minimax Algorithm with Alpha-Beta Pruning

```python
def alpha_beta(board, depth, alpha, beta, maximizing):
    if depth == 0 or board.is_game_over():
        return evaluate_board(board)
    ...
```

The Minimax algorithm works by thinking several moves ahead recursively:
- It imagines all possible moves for the current player.
- For each move, it imagines all the opponent's possible responses.
- It keeps drilling down until it hits the `depth` limit or the game ends.
- It then picks the move that maximizes its own best outcome while assuming the opponent always plays optimally.

**Alpha-Beta Pruning** is an optimization that cuts off tree branches that can never affect the final result. For example, if the engine already found a move scoring `+300`, it stops exploring any branch where the opponent can force a result below `+300`. This makes the engine **up to 10× faster** without changing the result.

### Difficulty Levels Mapped to Search Depth

```python
def difficulty_to_depth(difficulty):
    if difficulty <= 3:  return 1   # Beginner — 1 move lookahead
    elif difficulty <= 7:  return 2
    elif difficulty <= 12: return 3
    elif difficulty <= 17: return 4
    else:               return 5   # Expert — 5 moves ahead
```

A difficulty of 0–3 only looks 1 move ahead (very weak). Difficulty 18–20 looks 5 moves ahead, which is strong enough to defeat most casual players. The trade-off is response time — depth 5 may take 1-3 seconds to compute.

### The Two Public Methods

**`ChessService.calculate_new_fen(fen, move_uci)`** — Called when a student makes a move:
1. Parses the board state from the FEN string (a standard board encoding).
2. Validates the move. If illegal, raises `HTTP 400`.
3. Applies the move to the board.
4. Detects and returns status: `"playing"`, `"checkmate"`, `"stalemate"`, or `"draw"`.

**`ChessService.get_bot_move(fen, difficulty)`** — Called to get the AI's response:
1. Loads the board from the FEN.
2. Maps the `difficulty` integer to a search depth.
3. Runs `alpha_beta()` across all legal moves.
4. Returns the single best move as a UCI string (e.g., `"e2e4"`).

---

## `scheduler_service.py` — The Background Notification Loop

This service runs **continuously in the background** from the moment the server boots until it shuts down. It is an autonomous process that doesn't need any user action to trigger.

### How It Works

```python
async def start_special_day_scheduler(db):
    tz = pytz.timezone("Asia/Kolkata")
    while True:                          # Infinite loop
        await check_and_notify_special_days(db)
        
        now = datetime.datetime.now(tz)
        next_run = now.replace(hour=8, minute=0, second=0, microsecond=0)
        
        if next_run <= now:
            next_run += datetime.timedelta(days=1)
        
        sleep_duration = (next_run - now).total_seconds()
        await asyncio.sleep(sleep_duration)  # Sleep until 8:00 AM IST
```

1. When `main.py` boots, it calls `asyncio.create_task(start_special_day_scheduler(db))`.
2. The function runs its check immediately, then calculates how many seconds remain until **8:00 AM IST the next morning**.
3. It calls `asyncio.sleep(sleep_duration)` — this is **non-blocking**. The rest of the server continues serving traffic normally while this task waits silently.
4. At 8:00 AM the next day, it wakes up and checks again.

### The Daily Check Logic

```python
async def check_and_notify_special_days(db):
    today_str = now_ist.strftime("%Y-%m-%d")
    
    special_day = await db.special_days.find_one({
        "date": today_str,
        "is_active": True,
        "notification_sent": {"$ne": True}   # Only unsent events!
    })
```

It queries the `special_days` MongoDB collection matching three criteria:
- The date matches **today's date** in IST timezone.
- The event is marked `is_active: True` (not deleted/disabled).
- `notification_sent` is NOT `True` — prevents re-sending the same notification twice if server restarts.

If a match is found, it triggers `broadcast_notification(...)` and then marks the event with `notification_sent: True` so it won't fire again.

---

## `notification_service.py` — OneSignal Push Dispatcher

This is the push notification delivery engine. It handles both targeted (to one student) and broadcast (to all students) pipelines. It integrates with **OneSignal** — a popular cross-platform push notification service.

### The Two Core Functions

**`create_notification(db, user_id, title, message, ...)`** — Targeted, per-student:

1. **MongoDB History Write:** Saves the notification to the `notifications` collection first, giving users an in-app notification history even if the push fails.
2. **Parent Targeting:** Instead of pushing directly to the student's phone, it looks up the student's **linked parent accounts** in `usertable` and targets their mobile numbers. This prevents the scenario where a missed push on a student's shared family phone means nobody got the message.
3. **OneSignal API Call:** Constructs a JSON payload and POSTs it to the OneSignal REST API endpoint using `httpx.AsyncClient`. OneSignal then routes it to the correct iOS/Android devices.

**`broadcast_notification(db, title, message, ...)`** — Platform-wide blast:

1. If no `student_ids` list is provided, it fetches **all student IDs** from MongoDB automatically.
2. Saves individual notification history records for every student via `insert_many()` (a single efficient bulk write).
3. **Deduplication:** Before pushing, it collects all **unique mobile numbers** from linked parents using `db.usertable.distinct(...)`. This ensures that if a parent has multiple children enrolled, they only receive **one** push notification, not ten.
4. Sends a single OneSignal broadcast to all unique parent mobile numbers.

### Priority Levels

```python
"priority": priority,
"ios_interruption_level": "active" if priority == 10 else "passive",
"android_visibility": 1,
```

- Priority `10` = Critical / Active notification (shows on lock screen, makes sound).
- Priority `5` = Passive (silent, delivered to notification tray only).
- The scheduler uses `priority=5` for holiday reminders since they're informational.

---

## `analysis_service.py` — Student Performance Analytics

This service processes all historical quiz and exam data for a student to generate meaningful performance metrics.

### Core Responsibility

When a student's weaknesses need computing (e.g., to generate a future study plan), this service:
1. Queries all of the student's completed exam records from MongoDB.
2. Maps each wrong answer back to its **subject tag** and **difficulty level** stored in the Question Bank.
3. Aggregates error counts per subject to identify which topics need the most review.
4. Returns a structured weakness dictionary like:

```json
{
    "Mathematics": { "score": 45, "weak_topics": ["Algebra", "Trigonometry"] },
    "Physics":     { "score": 72, "weak_topics": ["Optics"] }
}
```

This output is consumed by `future_study_service.py` to rank study priorities.

---

## `youtube_service.py` — Educational Video Supplements

When `future_study_service.py` identifies a weak topic (e.g., "Algebra"), it calls this service to find relevant study videos.

### How It Works
1. Constructs a targeted YouTube Data API v3 search query (e.g., `"Class 10 Algebra basics educational"`).
2. Fetches the top 3-5 results filtered by duration (preferring videos under 20 minutes) and view-count credibility.
3. Returns a list of video IDs, titles, and thumbnail URLs appended to the student's study plan.

> The `YOUTUBE_API_KEY` in `.env` must be a valid Google Cloud API key with YouTube Data API v3 access enabled, or all calls to this service will fail silently with a 403 error.

---

## `wordle_service.py` — Dictionary & Feedback Engine

The Wordle engine is the **largest service file** (18KB) because it handles complex letter-frequency scenarios that naive implementations get wrong.

### The Core Challenge: Duplicate Letters

Consider guessing `"SLEEP"` against the target word `"SPELL"`:
- The first `L` in `SLEEP` should be marked **Yellow** (wrong position).
- The second `L` in `SLEEP` should be marked **Gray** (excess — already accounted for).

A naive approach would mark both `L`s as Yellow, which is incorrect. The Wordle service handles this by doing two passes:
1. **First pass** — Mark all exact position matches (Green) and remove them from consideration.
2. **Second pass** — For remaining letters, check if they exist in the remaining target pool (Yellow), marking them one at a time while consuming from the pool.

This ensures duplicates are never over-counted.

### Dictionary Validation

Before calculating feedback, the service checks if the submitted guess exists in the `WordleDictionary` MongoDB collection (seeded by `seed_wordle.py`). Invalid words are rejected with a `400 Bad Request` before any feedback is generated.

---

## `squares_service.py` — Puzzle Level Generation

Handles the spatial puzzle game board logic:
- **Level Fetching:** Reads pre-generated levels from the `SquaresLevels` collection seeded by `seed_squares.py`. Each level has a mathematically proven solution path stored server-side.
- **Submission Validation:** When a student submits their solution, the service compares the sequence of moves against the stored correct solution. Partial solutions or alternative paths that also lead to a solution are evaluated programmatically.
- **Difficulty Scaling:** Levels are tagged by difficulty (Easy, Medium, Hard) allowing the game to progressively increase challenge as a student completes previous levels.

---

## `ai_tutor_service.py` — The Intelligent Tutoring System

The AI Tutor is not a simple chatbot. It is a **Retrieval-Augmented Generation (RAG)** system — meaning before the AI answers, it first searches the actual textbook content stored in MongoDB to ground its response in curriculum-accurate material.

### The Three-Layer Pipeline

When a student asks "Explain Newton's second law":

**Layer 1 — Vector Embedding**

```python
response = await self.client.embeddings.create(
    model="text-embedding-3-large",
    input=query
)
query_vector = response.data[0].embedding
```

The student's question is converted into a 1536-dimensional mathematical vector using OpenAI's `text-embedding-3-large` model. This vector captures the *semantic meaning* of the question — not just keywords.

**Layer 2 — Cosine Similarity Search**

```python
def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

scored_chapters.sort(key=lambda x: x[0], reverse=True)
top_k = scored_chapters[:5]
```

Every textbook chapter in MongoDB (for the student's grade/class) has a pre-computed vector stored alongside it. The service computes the cosine similarity between the student's question vector and every chapter vector. The top 5 most semantically relevant chapters are selected. Only chapters scoring above `0.30` (30% similarity threshold) are included as context.

**Layer 3 — Web Search Fallback**

If no textbook content is found, the service falls back to a live web search using `DDGS` (DuckDuckGo Search):

```python
with DDGS() as ddgs:
    results = list(ddgs.text(query, max_results=3))
```

This ensures the AI can still answer questions about current events or topics not covered in the textbook database.

### Adaptive Persona by Grade Level

```python
def get_persona_instructions(self, student_name, student_class):
    if class_num <= 5:
        tone = "kind, energetic PRIMARY SCHOOL TEACHER. Use simple words, fun analogies, and emojis 🌟."
    elif class_num <= 10:
        tone = "helpful HIGH SCHOOL TEACHER. Be clear, structured, and informative."
    else:
        tone = "PROFESSOR / SENIOR TUTOR. Provide detailed academic answers."
```

The system prompt that shapes the AI's personality automatically adapts based on the student's grade. A Class 3 student gets a fun, emoji-filled explanation. A Class 12 student gets a university-level academic answer. The AI is always named **"Miki"**.

### Token Cost Tracking

Every embedding and chat completion call logs its token usage:

```python
await log_ai_usage("SYSTEM", "AI Tutor - Embedding", "text-embedding-3-large", response.usage)
```

This flows into the admin's financial analytics dashboard.

---

## `ai_companion_service.py` — The Student Life Coach

Where the Tutor focuses purely on academics, the Companion is the student's personal support system. It has **four distinct modes**, each powered by a separate LLM call:

### Mode 1 — Homework Guide (`ai_companion_guide_homework`)

The system prompt is strict: **"Do NOT give the direct answer."** Instead it uses Socratic questioning, breaking the problem into smaller conceptual pieces and asking guiding questions like "What formula relates force, mass, and acceleration?" This is pedagogically designed to build understanding rather than dependency.

### Mode 2 — Mentor Advice (`ai_mentor_advice`)

Before generating advice, the companion fetches the student's 5 most recent evaluations from MongoDB:

```python
evaluations = await db.evaluations.find(
    {"student_id": ObjectId(student_id)}
).sort("completed_at", -1).to_list(5)
```

This real performance data is injected into the AI's prompt as context, so when it says "You've improved significantly in science," it's actually based on real score data — not generic encouragement.

### Mode 3 — Parent Insights (`ai_parent_insights`)

Uses the same performance data but reframes it for a parent's perspective. The prompt instructs it to behave as an **"AI Parenting Consultant"** — professional, empathetic, and focused on how parents can support learning at home.

### Mode 4 — Coach Tasks (`ai_coach_tasks`)

Generates structured daily study tasks returned as a strict JSON array:

```python
response_format={"type": "json_object"}
```

By forcing `json_object` format, the AI cannot return markdown or prose — it is constrained to output parseable task objects with `title` and `description` fields that the frontend can render directly as a to-do list.

---

## `analysis_service.py` — The "Core 3" Visual Analytics Engine

This service powers the **three main analytics screens** that every student sees in their personal dashboard. It is organized as a static class with one method per analytics domain.

### Method 1 — Career Analytics (`get_visual_career_stats`)

Reads from the `career_analyzer` MongoDB collection, fetching the student's most recent career assessment. It formats the raw scores dictionary (e.g., `{"Naturalistic": 82, "Logical": 67}`) into a list of `CareerScoreItem` objects ready for chart rendering, and identifies the student's top intelligence category.

### Method 2 — Exam Analytics (`get_visual_exam_stats`)

Queries all **completed** evaluation records (status: `"COMPLETED"`) and calculates:

- **Overall average score percentage** across all exams taken.
- **Chronological history** — a timeline of performance for trend charts.
- **Trend detection** — compares the average of the last 2 exams against all previous exams:

```python
if recent_avg > prev_avg + 5:  trend = "Improving"
elif recent_avg < prev_avg - 5: trend = "Declining"
else:                           trend = "Stable"
```

This `trend` string drives the color and icon shown on the student dashboard (green arrow up, red arrow down, or flat line).

### Method 3 — Quiz Analytics (`get_visual_quiz_stats`)

Analyses quiz submissions grouped by difficulty level:

```python
diff_map = {"Easy": [], "Medium": [], "Hard": []}
for q in quizzes:
    lvl = q.get("difficulty_level", "Medium")
    diff_map[lvl].append(q.get("percentage", 0))
```

For each difficulty bucket, it calculates: total quizzes taken and average percentage. Additionally, it extracts the last 10 quiz sessions as a chronological trend array to power sparkline charts.

### The Dashboard Aggregator (`get_visual_dashboard`)

The main entry point that calls all three methods in parallel, assembles results into a single `VisualCoreDashboard` response object, and returns everything in one API call — minimizing round-trips from the frontend.

---

## `future_study_service.py` — The Personalized Career Road Map Generator

This is the most prompt-engineering-heavy service in the application. It takes a student's profile (class level, top intelligence category, recommended career) and generates a complete, India-specific educational resource package using GPT.

### The Strict Prompt Architecture

The prompt enforces **mandatory structure rules** that prevent the AI from generating vague or inappropriate content:

```
CLASS GUIDELINES:
- Class 1–5 → curiosity, awareness, basic concepts, fun learning
- Class 9–10 → structured basics and entry-level exams
- Class 11–12 → subject depth and competitive exams

RESOURCE QUANTITY (MANDATORY):
- YouTube videos → EXACTLY 5 items
- Tutorial links → EXACTLY 5 items
- Competitive exams → EXACTLY 5 items

STRICT CONTENT RULES:
- NO advanced professional topics for junior classes
- NO medical/engineering syllabus for Class ≤7
```

This prevents the AI from recommending MBBS curricula to a Class 3 student.

### JSON Extraction with Robust Parsing

```python
def extract_json(text: str):
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])
```

Even if the AI wraps its response in markdown code blocks, this parser strips the fencing and extracts only the raw JSON. This defensive approach is essential because LLMs occasionally ignore `response_format` instructions.

### MongoDB Upsert Pattern

```python
await db.future_study.update_one(
    {"student_id": student_id},
    {"$set": { "resources": ai_data, "created_at": ... }},
    upsert=True
)
```

Using `upsert=True` means if a study plan already exists for the student, it is **updated in-place** rather than duplicated. This keeps the `future_study` collection clean — exactly one document per student, always reflecting their latest profile.
