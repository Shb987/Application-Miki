from fastapi import APIRouter, HTTPException, Depends, Body
from app.services.payment_service import create_razorpay_order, verify_razorpay_signature
from app.core.database import db
from bson import ObjectId
from datetime import datetime, timezone
from app.utils.user_auth import get_current_user

router = APIRouter(prefix="/payment", tags=["Payment"])



@router.post("/create-order")
async def create_order(
    student_id: str = Body(...),
    tier: str = Body(...), # "plus" or "pro"
    current_user: dict = Depends(get_current_user)
):
    plan = await db.subscription_plans.find_one({"_id": tier, "is_active": True})
    if not plan:
        raise HTTPException(status_code=400, detail=f"Invalid or inactive tier selected: {tier}")
        
    price = plan["price_inr"]
    receipt = f"rcpt_{student_id}_{int(datetime.now().timestamp())}"
    
    order = create_razorpay_order(amount=price, receipt=receipt)
    
    # Store order locally to verify later
    order_doc = {
        "order_id": order["id"],
        "student_id": student_id,
        "tier": tier,
        "amount": price,
        "status": "created",
        "created_at": datetime.now(timezone.utc)
    }
    await db.payment_orders.insert_one(order_doc)
    
    return {
        "status_code": 200,
        "order_id": order["id"],
        "amount": order["amount"], # This is in paise
        "currency": order["currency"],
        "tier": tier
    }

@router.post("/verify")
async def verify_payment(
    razorpay_payment_id: str = Body(...),
    razorpay_order_id: str = Body(...),
    razorpay_signature: str = Body(...),
    current_user: dict = Depends(get_current_user)
):
    # Verify signature
    is_valid = verify_razorpay_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
        
    # Find order
    order = await db.payment_orders.find_one({"order_id": razorpay_order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.get("status") == "paid":
        return {"status_code": 200, "message": "Payment already verified"}
        
    # Update order status
    await db.payment_orders.update_one(
        {"_id": order["_id"]},
        {"$set": {
            "status": "paid",
            "payment_id": razorpay_payment_id,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # REFILL STUDENT BUCKETS
    student_id = order["student_id"]
    tier = order["tier"]
    
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")
        
    plan = await db.subscription_plans.find_one({"_id": tier})
    if not plan:
        raise HTTPException(status_code=400, detail=f"Plan {tier} not found in database.")
        
    new_buckets = plan.get("buckets", {})
    
    update_data = {
        "subscription.current_tier": tier,
        "subscription.last_recharge_date": datetime.now(timezone.utc),
        "usage_buckets.exam_balance": new_buckets["exam_balance"],
        "usage_buckets.voice_balance_mins": new_buckets["voice_balance_mins"],
        "usage_buckets.tutor_balance_qs": new_buckets["tutor_balance_qs"],
        "usage_buckets.class_balance": new_buckets["class_balance"]
    }
    
    # Update student record
    await db.students.update_one(
        {"_id": s_oid},
        {
            "$set": update_data,
            "$inc": {"subscription.total_spend": order["amount"]}
        }
    )
    
    return {
        "status_code": 200,
        "message": f"Successfully upgraded to {tier.capitalize()} Pack. All quotas have been refilled."
    }
