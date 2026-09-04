from fastapi import HTTPException
from app.core.database import db
from bson import ObjectId
from datetime import datetime, timezone

FEATURE_MAP = {
    "exam": "exam_balance",
    "voice": "voice_balance_mins",
    "tutor": "tutor_balance_qs",
    "class": "class_balance"
}

async def check_and_use_quota(student_id: str, feature: str, cost: int = 1):
    """
    Checks if a student has enough balance for a feature.
    If yes, decrements the balance and returns True.
    If no, raises an HTTPException (402 Payment Required).
    """
    if feature not in FEATURE_MAP:
        raise ValueError(f"Unknown feature: {feature}")

    bucket_key = FEATURE_MAP[feature]

    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Ensure structure exists
    if "subscription" not in student:
        student["subscription"] = {"current_tier": "basic", "last_recharge_date": None}
    
    if "usage_buckets" not in student:
        student["usage_buckets"] = {
            "exam_balance": 1,
            "voice_balance_mins": 2,
            "tutor_balance_qs": 5,
            "class_balance": 2
        }

    tier = student["subscription"].get("current_tier", "basic")
    buckets = student["usage_buckets"]

    # Handle Basic Tier Daily Reset for Tutor
    if tier == "basic" and feature == "tutor":
        # Check last reset date
        last_reset = student["subscription"].get("last_tutor_reset_date")
        today = datetime.now(timezone.utc).date()
        
        needs_reset = False
        if not last_reset:
            needs_reset = True
        else:
            if isinstance(last_reset, str):
                last_reset_dt = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
            else:
                last_reset_dt = last_reset
            
            if last_reset_dt.date() < today:
                needs_reset = True
                
        if needs_reset:
            buckets["tutor_balance_qs"] = 5
            await db.students.update_one(
                {"_id": s_oid},
                {"$set": {
                    "usage_buckets.tutor_balance_qs": 5,
                    "subscription.last_tutor_reset_date": datetime.now(timezone.utc)
                }}
            )

    # Check Balance
    current_balance = buckets.get(bucket_key, 0)
    
    if current_balance < cost:
        raise HTTPException(
            status_code=402, # Payment Required
            detail=f"Insufficient quota for {feature}. Please recharge your account."
        )

    # Decrement Balance
    await db.students.update_one(
        {"_id": s_oid},
        {"$inc": {f"usage_buckets.{bucket_key}": -cost}}
    )

    return True

async def has_premium_access(student_id: str):
    """
    Checks if a student has Plus or Pro status.
    This is true if they have any paid balance > 0 and are on the right tier.
    """
    try:
        student = None
        if ObjectId.is_valid(student_id):
            student = await db.students.find_one({"_id": ObjectId(student_id)})
        if not student:
            student = await db.students.find_one({"student_id": student_id})
        if not student:
            return False
            
        tier = student.get("subscription", {}).get("current_tier", "basic")
        if tier in ["plus", "pro"]:
            buckets = student.get("usage_buckets", {})
            # Check if they have ANY balance
            if (buckets.get("exam_balance", 0) > 0 or 
                buckets.get("voice_balance_mins", 0) > 0 or 
                buckets.get("tutor_balance_qs", 0) > 0 or
                buckets.get("class_balance", 0) > 0):
                return True
                
            # If all balances are 0, they revert to basic
            await db.students.update_one(
                {"_id": student["_id"]},
                {"$set": {"subscription.current_tier": "basic"}}
            )
            return False
            
        return False
    except Exception as e:
        print(f"Error in has_premium_access: {e}")
        return False
