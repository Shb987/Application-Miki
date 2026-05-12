# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Depends, Body
from app.core.database import db
from app.utils.admin_auth import get_current_admin
from datetime import datetime, timezone
from typing import Optional, Dict, Any
# pyrefly: ignore [missing-import]
from bson import ObjectId

from app.utils.user_auth import admin_or_user

router = APIRouter(tags=["Admin Plan Management"])

def serialize_doc(doc: dict) -> dict:
    if not doc: return {}
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId): result[k] = str(v)
        elif isinstance(v, datetime): result[k] = v.isoformat() + "Z" if v.tzinfo is None else v.isoformat()
        else: result[k] = v
    return result

@router.get("/plans")
async def get_all_plans():
    """Fetch all subscription plans"""
    cursor = db.subscription_plans.find({})
    plans = await cursor.to_list(length=None)
    
    # Sort so basic is first, then plus, then pro if possible
    order = {"basic": 1, "plus": 2, "pro": 3}
    plans.sort(key=lambda x: order.get(x["_id"], 99))
    
    return {"status_code": 200, "plans": plans}

@router.put("/plans/{tier_id}")
async def update_plan(
    tier_id: str,
    name: Optional[str] = Body(None),
    price_inr: Optional[int] = Body(None),
    buckets: Optional[Dict] = Body(None),
    is_active: Optional[bool] = Body(None),
    current_admin: dict = Depends(get_current_admin)
):
    """Update a specific subscription plan"""
    plan = await db.subscription_plans.find_one({"_id": tier_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    update_data = {}
    if name is not None: update_data["name"] = name
    if price_inr is not None: update_data["price_inr"] = price_inr
    if buckets is not None: update_data["buckets"] = buckets
    if is_active is not None: update_data["is_active"] = is_active
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
        
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    await db.subscription_plans.update_one(
        {"_id": tier_id},
        {"$set": update_data}
    )
    
    return {"status_code": 200, "message": f"Plan '{tier_id}' updated successfully"}

@router.post("/plans")
async def create_plan(
    tier_id: str = Body(...),
    name: str = Body(...),
    price_inr: int = Body(...),
    buckets: Dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Create a new subscription plan"""
    existing_plan = await db.subscription_plans.find_one({"_id": tier_id})
    if existing_plan:
        raise HTTPException(status_code=400, detail="Plan with this ID already exists")
        
    new_plan = {
        "_id": tier_id,
        "name": name,
        "price_inr": price_inr,
        "buckets": buckets,
        "is_active": True,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db.subscription_plans.insert_one(new_plan)
    return {"status_code": 200, "message": f"Plan '{tier_id}' created successfully"}

@router.get("/transactions")
async def get_all_transactions(
    skip: int = 0,
    limit: int = 100,
    current_admin: dict = Depends(get_current_admin)
):
    """Fetch all payment transactions for the global revenue dashboard"""
    total_count = await db.payment_orders.count_documents({})
    
    # Calculate some quick stats
    pipeline = [
        {"$match": {"status": "success"}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$amount"}}}
    ]
    stats_cursor = db.payment_orders.aggregate(pipeline)
    stats_list = await stats_cursor.to_list(length=1)
    total_revenue = stats_list[0]["total_revenue"] if stats_list else 0
    
    # Fetch actual transactions
    cursor = db.payment_orders.find({}).sort("created_at", -1).skip(skip).limit(limit)
    transactions = await cursor.to_list(length=limit)
    
    # Resolve student names
    student_ids = list(set([t.get("student_id") for t in transactions if t.get("student_id")]))
    s_oids = [ObjectId(sid) for sid in student_ids if isinstance(sid, str) and len(sid) == 24]
    
    student_map = {}
    if s_oids:
        s_cursor = db.students.find({"_id": {"$in": s_oids}}, {"student_name": 1})
        async for s in s_cursor:
            student_map[str(s["_id"])] = s.get("student_name", "Unknown")
            
    result = []
    for t in transactions:
        t_doc = serialize_doc(t)
        sid = str(t.get("student_id", ""))
        t_doc["student_name"] = student_map.get(sid, "Unknown")
        result.append(t_doc)
        
    return {
        "status_code": 200,
        "total_revenue": total_revenue / 100, # Assuming Razorpay amount is in paise
        "total_transactions": total_count,
        "transactions": result
    }

@router.get("/transactions/student/{student_id}")
async def get_student_transactions(
    student_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Fetch transactions for a specific student profile"""
    cursor = db.payment_orders.find({"student_id": student_id}).sort("created_at", -1)
    transactions = await cursor.to_list(length=None)
    
    return {
        "status_code": 200,
        "transactions": [serialize_doc(t) for t in transactions]
    }
