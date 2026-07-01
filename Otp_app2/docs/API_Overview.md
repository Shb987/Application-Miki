# Comprehensive API Usage & Standards

The FastAPI backend exposes dozens of operational endpoints. This document outlines the global patterns, strict security standards, and communication schemas governing the entire REST layer.

## 🌟 Interactive Auto-Documentation

The system generates complete OpenAPI schema documentation on the fly. 

*   **Swagger URL:** `http://localhost:8000/docs`
    *   *Usage:* You can actively test endpoints here without Postman. It supports injecting your JWT Token to test authenticated routes.
*   **ReDoc URL:** `http://localhost:8000/redoc`
    *   *Usage:* Provides a highly scannable, three-pane layout for reading deeply nested JSON models and constraints.

---

## 🔐 The Authentication Protocol

Almost all operational routes within `/user/*` or `/admin-panel/*` are strictly protected by `Depends()` authentication guards located in `app.utils.auth`.

### The Security Flow
1.  **Transport:** Clients must attach the `Authorization` header to requests.
    *   *Format:* `Bearer <eyJhbGciOiJIUzI1NiIsIn...>`
2.  **Decoding:** The dependency extracts the token and uses the `SECRET_KEY` and algorithm (typically `HS256`) defined in your `.env` to attempt a decipher.
3.  **Validation:** It verifies the 'exp' (expiration) timestamp.
4.  **Role Verification:** Finally, the guard explicitly checks that the decyphered `role` matches the expected scope (e.g. `admin_auth` will forcibly reject a token belonging to `role: user`, even if the cryptographic signature is flawless).

If any stage fails, the API immediately short-circuits and returns a `401 Unauthorized`.

---

## 🏗 Standardized Request Handling

Because FastAPI utilizes Pydantic under the hood, the parsing and casting of variables is completely automated and type-safe.

### 422 Unprocessable Entity - The Automated Rejection
If a client sends data that violates a model's constraints (e.g., sending an integer ID instead of an expected `UUID` string, or passing a password less than 8 characters), the route logic **never executes**.

Instead, FastAPI intercepts the payload and returns an automated 422 detailing exactly what went wrong.

```json
{
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "ensure this value has at least 8 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

### JSON Response Wrappers
Most endpoints return a standardized wrapper format, often using `JSONResponse`. This guarantees that frontend parsers can reliably check status flags.

**Typical Success (200 OK):**
```json
{
  "status": "success",
  "message": "Move calculated successfully",
  "data": {
    "board_state": "rnbqkbnr/...",
    "is_checkmate": false
  }
}
```

**Typical Handled Error (400 Bad Request):**
```json
{
  "status": "error",
  "message": "Illegal move attempted.",
  "data": null
}
```

---

## 📌 Notable Endpoint Trees

You can find the specific configurations for these routes in the `app/routes/` directory.

### `/user/game/...`
Handles high-frequency gamification pinging.
*   **Example Path:** `POST /user/game/chess/move`
*   **Payload Expectation:** Accepts coordinate string arrays (e.g. `e2e4`).
*   **Latency Profile:** Must remain under 200ms to maintain real-time interactivity.

### `/user/exam/...` & `/user/evaluation/...`
Responsible for the core educational flows.
*   **Example Path:** `POST /user/evaluation/submit_subjective`
*   **Functionality:** Accepts massive string payloads of essay answers. Because this route interfaces with an external AI service to parse and score the subjective data, it is expected to have high latency (often 5+ seconds). 
*   **Design Note:** Frontend implementations must deploy explicit loading states when calling this endpoint to prevent duplicate user submissions.

### `/otp/...`
The authentication origin points.
*   **Example Paths:** `POST /otp/send`, `POST /otp/verify`
*   **Security:** These routes exist strictly *outside* the JWT dependency guards, as they are used to acquire the tokens in the first place. They must implement rate-limiting to prevent SMS bridging or brute-force bombing.
