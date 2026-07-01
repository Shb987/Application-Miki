# Subscription Payment Implementation & Rate Limiting Strategy

This guide outlines exactly how you can implement the subscription payment flow (using Stripe or Razorpay) and how to physically limit the usage of free tier features in your backend.

## 1. The Payment Flow (Stripe/Razorpay Integration)

To handle subscriptions, you need three key components:
1. **Checkout Endpoint**: To generate a payment link.
2. **Webhook Endpoint**: To receive updates when a user successfully pays or cancels.
3. **Database Schema**: To store the subscription status.

### A. Checkout Endpoint
When the user clicks "Upgrade to Premium" in your frontend, your backend must generate a secure Checkout Session.

```python
import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.database import db
from bson import ObjectId

stripe.api_key = "your_stripe_secret_key"
router = APIRouter()

class CheckoutRequest(BaseModel):
    price_id: str # The ID of the subscription plan from Stripe Dashboard

@router.post("/create-checkout-session")
async def create_checkout_session(req: CheckoutRequest, current_user: dict = Depends(get_current_user)):
    student_id = current_user.get("student_id")
    
    try:
        # Create a Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': req.price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url="https://yourdomain.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://yourdomain.com/cancel",
            # VERY IMPORTANT: Pass your internal student_id so the webhook knows who paid
            client_reference_id=str(student_id), 
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### B. The Webhook (The Source of Truth)
Never trust the frontend to say "I paid!". Always wait for Stripe to send a secure webhook to your server.

```python
import stripe

@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, "your_stripe_webhook_secret"
        )
    except Exception as e:
        return {"status": "error", "message": "Invalid signature"}

    # Handle the event
    if event.type == 'checkout.session.completed':
        session = event.data.object
        student_id = session.client_reference_id
        stripe_customer_id = session.customer
        stripe_subscription_id = session.subscription
        
        # Calculate expiration (usually 1 month from now)
        # Update MongoDB
        await db.students.update_one(
            {"_id": ObjectId(student_id)},
            {"$set": {
                "subscription.plan_type": "premium",
                "subscription.status": "active",
                "subscription.stripe_customer_id": stripe_customer_id,
                "subscription.stripe_subscription_id": stripe_subscription_id,
                # Set expires_at based on the Stripe object details
                "subscription.expires_at": ... 
            }}
        )

    # Handle cancellations
    elif event.type == 'customer.subscription.deleted':
        # Subscription cancelled
        subscription = event.data.object
        await db.students.update_one(
            {"subscription.stripe_subscription_id": subscription.id},
            {"$set": {
                "subscription.plan_type": "free",
                "subscription.status": "cancelled"
            }}
        )

    return {"status": "success"}
```

---

## 2. Rate Limiting Free Users (How to limit usage)

If you have a feature that is free but uses AI (like the basic text-based AI Tutor), you must limit it to prevent abuse and high OpenAI bills (e.g., 5 free questions per day).

### A. Database Schema Updates
Add a usage tracking object to the `students` generic document:
```json
{
  "_id": "student_123",
  "subscription": {
    "plan_type": "free"
  },
  "usage": {
    "tutor_questions_today": 3,
    "last_reset_date": "2026-02-23"
  }
}
```

### B. Python Logic to Check and Increment Usage
Create a helper function in your service logic (e.g., in `ai_tutor_routes.py`) that checks this before calling OpenAI.

```python
from datetime import datetime, timezone
from app.core.database import db
from bson import ObjectId

async def check_and_increment_usage(student_id: str, limit: int = 5):
    """
    Returns True if the user is allowed to proceed.
    Returns False if they hit the limit.
    """
    student = await db.students.find_one({"_id": ObjectId(student_id)})
    if not student:
        return False
        
    subscription = student.get("subscription", {}).get("plan_type", "free")
    
    # Premium users have no limits!
    if subscription == "premium":
        return True
        
    usage = student.get("usage", {})
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    current_count = usage.get("tutor_questions_today", 0)
    last_reset = usage.get("last_reset_date", "")
    
    # Reset count if it's a new day
    if last_reset != today_str:
        current_count = 0
        
    if current_count >= limit:
        return False # They hit the limit!
        
    # Increment the count and save
    await db.students.update_one(
        {"_id": ObjectId(student_id)},
        {"$set": {
            "usage.tutor_questions_today": current_count + 1,
            "usage.last_reset_date": today_str
        }}
    )
    return True
```

### C. Integrating the Check into the Route
Now, simply inject this logic right before the expensive OpenAI API call.

```python
@router.post("/chat")
async def chat_with_tutor(payload: TutorChatRequest, current_user: dict = Depends(get_current_user)):
    student_id = payload.student_id
    
    # --- 1. ENFORCE LIMIT ---
    allowed = await check_and_increment_usage(student_id, limit=5)
    if not allowed:
        return {
            "status": "error",
            "reply": "You've reached your free limit of 5 questions for today! Upgrade to Miki Pro for unlimited access.",
            "source": "SYSTEM"
        }
        
    # --- 2. Proceed with heavy OpenAI Calls ---
    # intent = await classify_intent(...)
    # response = await client.chat.completions.create(...)
    # ...
```

### Summary of the Flow:
1. **Frontend**: Calls `/create-checkout-session` -> User goes to Stripe -> Pays.
2. **Backend**: Stripe calls your `/webhook`, your DB flips `"plan_type": "premium"`.
3. **API Logic**: 
   - Strict Premium Routes (e.g., Voice Assistant) use a FastAPI Dependency (`Depends(require_premium)`) to throw a 403 error instantly if they aren't premium.
   - Freemium Routes (e.g., AI Tutor text chat) use `check_and_increment_usage()` to track daily counts and return an "upgrade" message if they hit their daily limit of 5.
