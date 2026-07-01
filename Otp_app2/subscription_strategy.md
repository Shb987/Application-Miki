# Miki App Subscription Strategy Proposal

Based on the capabilities and AI modules currently in the application, here is a proposal for how a subscription model could be implemented.

## 1. Feature Tiering Strategy

The standard approach is a **Freemium Model**, where basic functionality is accessible to everyone, but advanced, high-cost AI features are gated behind a "Premium" or "Miki Pro" subscription.

### 🆓 Free Tier (Basic Access)
*Goal: Hook students in and provide value without incurring heavy AI costs.*
* **Syllabus & Basic Content**: Access to standardized study materials and text-based textbook content.
* **Basic Games**: Limited daily plays for standard educational games (e.g., Wordle, Squares).
* **AI Tutor (Limited)**: Basic text-based textbook search (`search_textbook` via RAG). Limited to e.g., 5 questions per day.
* **Basic Analytics**: View simple dashboards comparing scores on standard quizzes.
* **Standard Exam Access**: Can view and take standard multiple-choice questions or pre-generated tests.

### 💎 Premium Tier / Miki Pro (Full AI Access)
*Goal: Monetize high-cost AI features like Voice, Vision OCR, and deep generative tasks.*
* **Real-Time Voice Assistant**: Unlimited or high-cap access to the `gpt-4o-realtime-preview` voice tutor.
* **Automated Exam Evaluation**: Ability to upload handwritten answer sheets for `gpt-4o` Vision OCR and RAG-based automated grading.
* **Advanced AI Mentor & Tasks**: Full access to the AI Mentor, Socratic Homework Guide, and daily Habit/Skill Coach tasks.
* **Parental Insights**: Specialized AI reports generated tailored for parents comparing long-term growth.
* **Future Study & Career Guidance**: Full access to the personalized career roadmap generator.
* **Unlimited Games**: No daily limits on educational games.
* **Web-Aware AI**: Tutor can use `search_web` for current events and knowledge outside the textbook.

---

## 2. Modules to Include in the Subscription

Here are the specific backend modules that can be guarded by subscription checks:

1. **`voice_assistant_routes.py`**: The entire WebSocket endpoint for real-time voice (`/ws/{student_id}/{session_id}`). This is likely the most expensive feature (running `gpt-4o-realtime` and Whisper) and the biggest selling point for Premium.
2. **`exam_evaluation_routes.py`**: The `/evaluate-answersheet` endpoint which processes images via Vision AI.
3. **`companion_routes.py`**: Endpoints like `/homework/guide`, `/mentor/advice`, `/parent/insights`, and `/coach/tasks`.
4. **`user_futurestudy_routes.py`**: The career guidance generation endpoint (`/{student_id}`).
5. **`ai_tutor_routes.py`**: The `/chat` endpoint can remain free, but a cap should be implemented, or the `search_web` tool can be restricted.

---

## 3. How to Implement Technically

To add this effectively, changes are needed across the database, middleware, and specific route logic.

### Step 1: Database Updates (Students Collection)
Update the `students` (or `users`) schema/document to include subscription status fields:
```json
{
  "_id": "...",
  "student_name": "Ravi",
  "subscription": {
    "plan_type": "free", // "free", "premium", "pro_annual", etc.
    "status": "active",
    "expires_at": ISODate("2026-12-31T23:59:59Z"),
    "stripe_customer_id": "cus_12345"
  },
  "usage_limits": {
    "daily_ai_chats": 5, // Reset nightly via cron job
    "last_reset_date": ISODate("2026-02-23T00:00:00Z")
  }
}
```

### Step 2: Create a Dependency / Middleware (`app/utils/subscription_auth.py`)
Create a FastAPI dependency to strictly check for active premium status before allowing a route to execute.

```python
from fastapi import Depends, HTTPException
from app.utils.user_auth import get_current_user
from app.core.database import db
from datetime import datetime

async def require_premium(current_user: dict = Depends(get_current_user)):
    student_id = current_user.get("student_id")
    student_doc = await db.students.find_one({"_id": ObjectId(student_id)})
    
    sub = student_doc.get("subscription", {})
    
    # Check if plan is premium and hasn't expired
    if sub.get("plan_type") in ["premium", "pro"]:
        expires = sub.get("expires_at")
        if expires and expires > datetime.utcnow():
            return current_user # Valid
            
    raise HTTPException(
        status_code=403, 
        detail="This feature requires a Premium Subscription."
    )
```

### Step 3: Apply the Dependency to Premium Routes
In your routers, simply add the dependency.

**Example in `exam_evaluation_routes.py`:**
```python
from app.utils.subscription_auth import require_premium

@router.post("/evaluate-answersheet", dependencies=[Depends(require_premium)])
async def evaluate_answersheet(
    background_tasks: BackgroundTasks,
    # ...
):
    # This code only runs if the user is a premium member
```

### Step 4: Add Payment Integration (Stripe or Razorpay)
Create a new module `app/routes/subscription_routes.py` that handles:
* **Checkout/Payment Link Creation**: Generating a session for Stripe/Razorpay.
* **Webhooks**: Listening for successful payment events to automatically update `expires_at` and `plan_type` in your `students` collection.
* **Portal**: A way for users to view, manage, or cancel their subscription.

### Step 5: Implement Usage Caps for Free Users (Optional but Recommended)
For free features that consume AI (like basic `ai_tutor_routes.py`), implement a daily cap interceptor to prevent heavy costs from free users. You can increment a counter in Redis or MongoDB until it hits the daily limit.
