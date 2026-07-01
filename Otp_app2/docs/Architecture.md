# Architecture Strategy

This application is engineered using a **Monolithic Modularity** architecture. While the entire system deploys as a single executable FastAPI application (the Monolith), the internal structure is strictly segregated by domain (Modularity).

This layout ensures that as the educational or interactive features scale, the core application doesn't succumb to spaghetti code. It enables distinct boundaries where authentication logic does not intertwine with chess game validation.

---

## 📂 In-Depth Directory Functionality

The entire runtime domain exists inside the `app/` envelope.

### `app/core/` (The Foundation)
Contains the lowest-level configurations required before the web framework can even accept traffic.
*   **`database.py`**: Initializes the asynchronous `Motor` client and establishes the connection pool to MongoDB.
*   **`settings.py`**: Uses `pydantic-settings` or simple `os.getenv` loaders to parse the `.env` file into a strictly typed configuration object available everywhere in the app.

### `app/models/` (The Enforcers)
Because MongoDB is inherently NoSQL and schema-less, the platform enforces rigid operational structure using **Pydantic**.
*   **Data Validation:** Every file here defines data schemas. These define what an incoming POST request MUST look like (e.g. `SpecialDayCreate`), what the data looks like within MongoDB, and how data is serialized back to the client (`SpecialDayResponse`).
*   **Domain Isolation:** There are distinct model files for users (`user_models.py`), questions (`question_models.py`), quizzes (`quiz_models.py`), etc., ensuring models only represent one domain.

### `app/services/` (The Brain)
Where the business logic lives. FastAPI Best Practices dictate that Routers should only handle HTTP concerns.
*   **Separation of Concerns:** When `users_game_chess.py` receives a "move" payload, it doesn't calculate the move itself. It hands the payload to `chess_service.py` to calculate validity, Minimax probabilities, and checkmate detection.
*   **Service Interactions:** Services can call other services. For example, `exam_service` can call `analysis_service` to generate student reports after grading.

### `app/routes/` (The Traffic Controllers)
The FastAPI Routers list. They define the explicit endpoints (`@router.get(...)`), inject dependencies (like `get_current_user`), and serialize the response. 
*   **Split by Role:** The system distinctly separates (`admin_routes.py` vs `user_routes.py`) at the file level to ensure administrative actions are heavily gated and less likely to be accidentally exposed to unprivileged users.

### `app/templates/` & `app/static/` (SSR Frontend)
The Server-Side Rendered implementation layer.
*   **Jinja2 Templates:** Houses the HTML necessary for compiling the Admin Interface. `admin_pages.py` accesses these templates and passes database contexts into them.
*   **Static Mounts:** `app/static/` serves physical assets to browsers. This directory is deeply nested, with mounts assigned in `main.py` explicitly for `/dist`, `/uploads` (user media), and `/generated_papers` (PDF exams).

---

## 🔄 The Life Cycle of a Request

Understanding how data travels through this architecture is critical for debugging:

1.  **Ingestion (`main.py`)**: An HTTP request arrives. The FastAPI ASGI app checks its mount points and router prefixes. It forwards the request based on the path (e.g., `/user/chess/move`).
2.  **Middleware Execution**: Any global middleware (like CORS) evaluates the request.
3.  **Authentication Dependency**: The specific route likely requires a user. FastAPI executes `Depends(get_current_user)` from `utils/auth.py`. 
    *   This function extracts the `Bearer` token.
    *   Verifies the cryptographic signature.
    *   Looks up the User ID in MongoDB.
    *   Returns the active User object. (If any step fails, an automatic `401 Unauthorized` aborts the request).
4.  **Schema Validation (`app/models`)**: FastAPI takes the JSON Body and pushes it into the respective `Pydantic` model. If the client sent a string where an integer was expected, the engine immediately throws a `422 Unprocessable Entity`.
5.  **Service Processing (`app/services`)**: The validated model and the active User object are passed off to the service layer to perform the complex educational logic or gamification validation.
6.  **Database I/O (`app/core/database.py`)**: The Service queries Motor. Because we use `await`, the asyncio event loop pauses execution here and processes other concurrent web traffic until MongoDB responds.
7.  **Serialization & Response**: The return values are bundled into a Response model and shipped back to the client as JSON!

---

## 🗄️ Database Strategy & Indexing

Collections in this application map directly to domains. Because we utilize Motor, collections can be created on-the-fly and queried fluidly. 

**Common Architectural Document Relationships:**
*   **Users Collection:** The root node. Students (`role: user`) and Staff (`role: admin`) are distinguished via flags.
*   **References vs Embedding:** For heavy items (like Exam details and questions), we use document referencing (e.g., `exam_id: "xyz"`) rather than embedding 50 questions directly into user profiles, which would bloat documents beyond MongoDB's 16MB limit.
*   **Statistics Isolation:** Gamification analytics are intentionally stored in tracking collections (e.g., `PlayerStats` or AI usage trackers) independently of the core user entity. This allows for frequent, heavy writes (like playing 50 turns of chess) without triggering heavy locking on the user profile collection.
