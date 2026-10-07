import random
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from bson import ObjectId

from app.models.otp_models import OTPRequest, OTPVerify
from app.core.database import db
from app.core.settings import settings
from app.utils.user_auth import get_current_user, create_user_token

router = APIRouter(tags=["OTP"])

OTP_EXPIRY_MINUTES = settings.OTP_EXPIRY_MINUTES


def get_phone_candidates(mobile: str) -> List[str]:
    """Return all common representations of a phone number (original, cleaned digits, last 10 digits)."""
    if not mobile:
        return []
    raw = str(mobile).strip()
    clean = re.sub(r'\D', '', raw)
    candidates = {raw}
    if clean:
        candidates.add(clean)
        if len(clean) >= 10:
            candidates.add(clean[-10:])
    return list(candidates)


def get_student_phone_query(candidates: List[str]) -> dict:
    """Build a MongoDB query to match a student's own phone number across all alias fields."""
    return {
        "$or": [
            {"student_phone": {"$in": candidates}},
            {"mobile_number": {"$in": candidates}},
            {"phone_number": {"$in": candidates}},
            {"phone": {"$in": candidates}},
            {"mobile": {"$in": candidates}},
            {"mobileno": {"$in": candidates}},
            {"mobile_no": {"$in": candidates}},
            {"contact_no": {"$in": candidates}},
            {"mob_no": {"$in": candidates}},
        ]
    }


def get_guardian_phone_query(candidates: List[str]) -> dict:
    """Build a MongoDB query to match a guardian/parent phone number across all alias fields."""
    return {
        "$or": [
            {"guardian_phone": {"$in": candidates}},
            {"parent_mobile": {"$in": candidates}},
            {"father_phone": {"$in": candidates}},
            {"parent_phone": {"$in": candidates}},
        ]
    }


@router.post("/send")
async def send_otp(data: OTPRequest):
    otp = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc)
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    candidates = get_phone_candidates(data.mobile_number)
    record = await db.otps.find_one({"mobile_number": {"$in": candidates}})

    update_data = {
        "otp": otp,
        "created_at": now,
        "expiry": expiry_time,
    }

    if not record:
        update_data["usertype"] = None

    # 1. Sync usertype from usertable if it exists
    user_record = await db.usertable.find_one({"mobile_number": {"$in": candidates}})
    if user_record and user_record.get("usertype"):
        update_data["usertype"] = user_record.get("usertype")
    else:
        # 2. Automatically detect if this phone belongs to a student or guardian in db.students
        st_match = await db.students.find_one(get_student_phone_query(candidates))
        if st_match:
            update_data["usertype"] = "student"
            # Auto-sync usertable
            await db.usertable.update_one(
                {"mobile_number": data.mobile_number},
                {
                    "$set": {
                        "usertype": "student",
                        "student_id": st_match["_id"],
                        "student_name": st_match.get("student_name"),
                        "updated_at": datetime.now(timezone.utc)
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
        else:
            g_students = await db.students.find(get_guardian_phone_query(candidates)).to_list(length=None)
            if g_students:
                update_data["usertype"] = "parent"
                s_oids = [s["_id"] for s in g_students]
                await db.usertable.update_one(
                    {"mobile_number": data.mobile_number},
                    {
                        "$set": {
                            "usertype": "parent",
                            "updated_at": datetime.now(timezone.utc)
                        },
                        "$addToSet": {
                            "student_ids": {"$each": s_oids}
                        },
                        "$setOnInsert": {
                            "created_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )

    await db.otps.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": update_data},
        upsert=True
    )

    return {"status_code": 200, "message": "OTP generated", "otp": otp}


@router.post("/verify")
async def verify_otp(data: OTPVerify):
    candidates = get_phone_candidates(data.mobile_number)
    record = await db.otps.find_one({"mobile_number": {"$in": candidates}})

    if not record:
        return {"status_code": 400, "message": "OTP not found"}

    expiry_time = record.get("expiry")
    if expiry_time is not None:
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
        if expiry_time < datetime.now(timezone.utc):
            return {"status_code": 400, "message": "OTP expired"}

    if record.get("otp") != data.otp:
        return {"status_code": 400, "message": "Invalid OTP"}

    # Determine usertype
    usertype = record.get("usertype")
    user_record = await db.usertable.find_one({"mobile_number": {"$in": candidates}})
    
    if not usertype or usertype == "null":
        if user_record and user_record.get("usertype"):
            usertype = user_record.get("usertype")
        else:
            # Detect from db.students
            st_match = await db.students.find_one(get_student_phone_query(candidates))
            if st_match:
                usertype = "student"
                await db.usertable.update_one(
                    {"mobile_number": data.mobile_number},
                    {
                        "$set": {
                            "usertype": "student",
                            "student_id": st_match["_id"],
                            "student_name": st_match.get("student_name"),
                            "updated_at": datetime.now(timezone.utc)
                        },
                        "$setOnInsert": {
                            "created_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            else:
                g_students = await db.students.find(get_guardian_phone_query(candidates)).to_list(length=None)
                if g_students:
                    usertype = "parent"
                    s_oids = [s["_id"] for s in g_students]
                    await db.usertable.update_one(
                        {"mobile_number": data.mobile_number},
                        {
                            "$set": {
                                "usertype": "parent",
                                "updated_at": datetime.now(timezone.utc)
                            },
                            "$addToSet": {
                                "student_ids": {"$each": s_oids}
                            },
                            "$setOnInsert": {
                                "created_at": datetime.now(timezone.utc)
                            }
                        },
                        upsert=True
                    )
                else:
                    usertype = "null"

        # Sync resolved usertype back to otps table
        if usertype != "null":
            await db.otps.update_one(
                {"mobile_number": data.mobile_number},
                {"$set": {"usertype": usertype}}
            )

    # Defaults
    is_user = False
    student_id = None
    is_new_user = False
    student_subscription = None
    student_usage_buckets = None
    student_doc = None
    linked_students = []

    # 1. Student Identity Login
    if usertype == "student":
        student_id = user_record.get("student_id") if user_record else None

        if student_id:
            try:
                student_doc = await db.students.find_one({"_id": ObjectId(student_id)})
            except Exception:
                pass
            if not student_doc:
                student_doc = await db.students.find_one({"_id": student_id})

        if not student_doc:
            # Fallback: Look up directly by student phone in db.students
            student_doc = await db.students.find_one(get_student_phone_query(candidates))
            if student_doc:
                student_id = student_doc["_id"]
                # Save link in usertable
                await db.usertable.update_one(
                    {"mobile_number": data.mobile_number},
                    {
                        "$set": {
                            "usertype": "student",
                            "student_id": student_id,
                            "student_name": student_doc.get("student_name"),
                            "updated_at": datetime.now(timezone.utc)
                        },
                        "$setOnInsert": {
                            "created_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )

        if student_doc:
            student_id = student_doc["_id"]
            is_user = True
            is_new_user = student_doc.get("is_new_user", False)
            student_subscription = student_doc.get("subscription")
            student_usage_buckets = student_doc.get("usage_buckets")

            if student_doc.get("is_user") is not True:
                await db.students.update_one(
                    {"_id": student_doc["_id"]},
                    {"$set": {"is_user": True}}
                )

    # 2. Guardian / Parent Identity Login
    elif usertype == "parent":
        is_user = False
        is_new_user = False
        
        # Find all students connected to this guardian phone
        existing_sids = []
        if user_record and user_record.get("student_ids"):
            existing_sids = user_record.get("student_ids")

        student_query = [get_guardian_phone_query(candidates)]
        if existing_sids:
            student_query.append({"_id": {"$in": existing_sids}})

        linked_cursor = db.students.find({"$or": student_query})
        linked_students = await linked_cursor.to_list(length=None)

        if linked_students:
            found_oids = [s["_id"] for s in linked_students]
            await db.usertable.update_one(
                {"mobile_number": data.mobile_number},
                {
                    "$set": {
                        "usertype": "parent",
                        "updated_at": datetime.now(timezone.utc)
                    },
                    "$addToSet": {
                        "student_ids": {"$each": found_oids}
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )

    access_token = create_user_token(
        data.mobile_number,
        usertype,
        student_id=str(student_id) if student_id else None
    )

    response_payload = {
        "status_code": 200,
        "message": "OTP verified successfully",
        "usertype": usertype,
        "is_user": is_user,
        "student_id": str(student_id) if student_id else None,
        "access_token": access_token,
        "token_type": "bearer",
        "is_new_user": is_new_user
    }

    from app.routes.user_routes import serialize_mongo_doc

    if usertype == "student" and student_doc:
        response_payload["student"] = serialize_mongo_doc(student_doc)
        if student_subscription is not None:
            response_payload["subscription"] = serialize_mongo_doc(student_subscription)
            response_payload["usage_buckets"] = student_usage_buckets

    elif usertype == "parent" and linked_students:
        response_payload["student_ids"] = [str(s["_id"]) for s in linked_students]
        response_payload["students"] = [serialize_mongo_doc(s) for s in linked_students]

    return response_payload


# 🔒 PROTECTED — must be a LOGGED IN USER (parent)
@router.post("/switch-user/send-otp")
async def switch_user_send_otp(
    data: OTPRequest,
    current_user: dict = Depends(get_current_user)
):
    otp = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc)
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    update_data = {"otp": otp, "created_at": now, "expiry": expiry_time, "usertype": "student"}
    await db.otps.update_one({"mobile_number": data.mobile_number}, {"$set": update_data}, upsert=True)

    return {"status_code": 200, "message": "OTP sent for student login", "otp": otp}


# 🔒 PROTECTED — must be a LOGGED IN USER (parent)
@router.post("/switch-to-student")
async def switch_to_student(
    data: OTPVerify,
    student_id: str = Query(..., description="The 24-character hex student ObjectID"),
    current_user: dict = Depends(get_current_user)
):
    verify_result = await verify_otp(data)
    if verify_result["status_code"] != 200:
        return verify_result

    try:
        s_oid = ObjectId(student_id)
    except Exception:
        return {"status_code": 400, "message": "Invalid student ID format (must be 24-char hex)"}

    student_doc = await db.students.find_one({"_id": s_oid})
    if not student_doc:
        return {"status_code": 404, "message": "Student not found"}

    parent_mobile = current_user.get("sub")
    parent_candidates = get_phone_candidates(parent_mobile)

    # Check parent link in usertable or by guardian_phone in student record
    parent_record = await db.usertable.find_one({
        "usertype": "parent",
        "$or": [
            {"student_ids": {"$in": [s_oid, student_id]}},
            {"mobile_number": {"$in": parent_candidates}}
        ]
    })

    guardian_match = (
        student_doc.get("guardian_phone") in parent_candidates or
        student_doc.get("parent_mobile") in parent_candidates
    )

    if not parent_record and not guardian_match:
        return {
            "status_code": 403,
            "message": "This student is not linked to this parent account"
        }

    # Ensure student mobile is linked in usertable for student login
    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},
        {
            "$set": {
                "usertype": "student",
                "student_id": s_oid,
                "student_name": student_doc.get("student_name"),
                "updated_at": datetime.now(timezone.utc)
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    await db.students.update_one(
        {"_id": s_oid},
        {"$set": {"is_user": True}}
    )

    # Generate a token for the student session including the ObjectID
    new_token = create_user_token(
        mobile_number=data.mobile_number,
        usertype="student",
        student_id=str(s_oid)
    )

    is_new_user = student_doc.get("is_new_user", False)
    from app.routes.user_routes import serialize_mongo_doc

    response_payload = {
        "status_code": 200,
        "message": "Switched to student successfully",
        "usertype": "student",
        "student_id": str(s_oid),
        "student": serialize_mongo_doc(student_doc),
        "access_token": new_token,
        "token_type": "bearer",
        "is_new_user": is_new_user
    }

    student_subscription = student_doc.get("subscription")
    student_usage_buckets = student_doc.get("usage_buckets")

    if student_subscription is not None:
        response_payload["subscription"] = serialize_mongo_doc(student_subscription)
        response_payload["usage_buckets"] = student_usage_buckets

    return response_payload