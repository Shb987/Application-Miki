# Utility Functions & Defenses

The `app/utils/` directory is the backbone of the platform's security and cost-management. It is completely isolated from business logic plugins, focusing purely on intercepting requests and tracking metrics before the Routers are even allowed to process data.

## 1. Authentication Guards (`admin_auth.py` & `user_auth.py`)

FastAPI utilizes a concept called **Dependencies** (`Depends()`). Instead of writing `"Is the user logged in?"` at the top of every single one of our 100+ endpoints, we push that logic into these utility files.

### The Mechanism of Action
When an endpoint is declared like this:
`@router.get("/profile", dependencies=[Depends(get_current_user)])`

The following lifecycle occurs invisibly within `user_auth.py`:
1.  **Header Extraction:** The framework sniffs the HTTP `Authorization` header, explicitly looking for a `Bearer <token>` payload. If missing, it immediately throws a `401 Unauthorized`.
2.  **Cryptographic Decryption:** It uses the `PyJWT` library alongside the `SECRET_KEY` (from `app/core/settings.py`) to mathematically decrypt the token string back into a Python Dictionary.
3.  **Timestamp Validation:** It checks the `exp` (Expiration) integer inside the decoded payload. If the token is too old, it throws a `401`.
4.  **Database Hydration:** It takes the embedded `user_id`, reaches into the MongoDB `Users` collection, and verifies the user hasn't been deleted or banned since the token was issued.
5.  **Role Enforcement:** `admin_auth.py` strictly checks if the resulting user model has `role == "admin"`. If not, access is flatly denied.

*The greatest strength of this utility folder is that endpoints strictly rely on this injection, making it mathematically impossible for an endpoint to accidentally leak data to an unauthenticated user.*

---

## 2. Artificial Intelligence Cost Tracking (`ai_usage_logger.py`)

Because the platform relies so heavily on external services (LLMs for Exams, Tutors, and Companions) that bill based on usage, we built a global tracking utility to ensure we never lose track of API costs.

### The Objective
Instead of manually calculating OpenAI token-pricing in every single service file, the `ai_usage_logger` acts as the single source-of-truth for writing to the `AIUsageLogs` MongoDB collection.

### How It Calculates
1.  **Ingestion:** At the end of any AI request (e.g., inside `ai_tutor_service.py`), the specific route calls `log_ai_usage()`, passing in the user ID, the specific AI Module called, and the raw Usage Dictionary returned by the OpenAI API wrapper.
2.  **Rate Abstraction:** The logger contains hardcoded metric rates for models.
3.  **Database Write:** It pushes an asynchronous write to MongoDB capturing the exact date, total prompt tokens, total completion tokens, and the calculated fiat cost ($USD).
4.  **Usage Analytics:** Because every single module uses this exact same utility file, the `admin_analysis_routes.py` can later simply group the MongoDB collection by date and generate a perfect financial dashboard of AI spending over the last 30 days without complex aggregations.
