import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from app.models.otp_models import OTPRequest, OTPVerify
from app.core.database import db
from app.core.settings import settings
from app.utils.user_auth import get_current_user, create_user_token
from bson import ObjectId

router = APIRouter(tags=["OTP"])

OTP_EXPIRY_MINUTES = settings.OTP_EXPIRY_MINUTES
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


@router.post("/send")
async def send_otp(data: OTPRequest):
    otp = str(random.randint(100000, 999999))

    now = datetime.now(timezone.utc)  # âœ… explicit UTC
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    record = await db.otps.find_one({"mobile_number": data.mobile_number})

    update_data = {
        "otp": otp,
        "created_at": now,
        "expiry": expiry_time,
    }

    if not record:
        update_data["usertype"] = None

    # Sync usertype from usertable if it exists (for externally registered users)
    user_record = await db.usertable.find_one({"mobile_number": data.mobile_number})
    if user_record and user_record.get("usertype"):
        update_data["usertype"] = user_record.get("usertype")

    await db.otps.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": update_data},
        upsert=True
    )

    return {"status_code": 200, "message": "OTP generated", "otp": otp}


from datetime import datetime, timezone
from bson import ObjectId


@router.post("/verify")
async def verify_otp(data: OTPVerify):
    record = await db.otps.find_one({"mobile_number": data.mobile_number})

    if not record:
        return {"status_code": 400, "message": "OTP not found"}

    expiry_time = record.get("expiry")

    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)

    if expiry_time < datetime.now(timezone.utc):
        return {"status_code": 400, "message": "OTP expired"}

    if record.get("otp") != data.otp:
        return {"status_code": 400, "message": "Invalid OTP"}

    # Get usertype
    usertype = record.get("usertype")
    
    # If usertype is missing in otps (e.g. registered via external API), fetch from usertable
    if not usertype or usertype == "null":
        user_record = await db.usertable.find_one({"mobile_number": data.mobile_number})
        if user_record and user_record.get("usertype"):
            usertype = user_record.get("usertype")
            # Sync it back to otps table
            await db.otps.update_one(
                {"mobile_number": data.mobile_number},
                {"$set": {"usertype": usertype}}
            )
        else:
            usertype = "null"

    # Defaults
    is_user = False
    student_id = None
    is_new_user = False # Default
    student_subscription = None
    student_usage_buckets = None

    # âœ… Only if student
    if usertype == "student":
        user_record = await db.usertable.find_one(
            {"mobile_number": data.mobile_number},
            {"student_id": 1}
        )

        if user_record:
            student_id = user_record.get("student_id")

            if student_id:
                student = await db.students.find_one(
                    {"_id": ObjectId(student_id)}
                )

                if student:
                    if student.get("is_user") is True:
                        is_user = True
                    
                    # âœ… Check if student is "new"
                    is_new_user = student.get("is_new_user", False)
                    
                    # Grab subscription and usage_buckets
                    student_subscription = student.get("subscription")
                    student_usage_buckets = student.get("usage_buckets")

    access_token = create_user_token(data.mobile_number, usertype)

    response_payload = {
        "status_code": 200,
        "message": "OTP verified successfully",
        "usertype": usertype,
        "is_user": is_user,

        # âœ… Return student_id only for students
        "student_id": str(student_id) if student_id else None,

        "access_token": access_token,
        "token_type": "bearer",
        "is_new_user": is_new_user  # ðŸ†• Return new user status
    }

    if usertype == "student" and student_subscription is not None:
        from app.routes.user_routes import serialize_mongo_doc
        response_payload["subscription"] = serialize_mongo_doc(student_subscription)
        response_payload["usage_buckets"] = student_usage_buckets

    return response_payload


# ðŸ” PROTECTED â€” must be a LOGGED IN USER (parent)
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



# ðŸ” PROTECTED â€” must be a LOGGED IN USER (parent)
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
    except:
        return {"status_code": 400, "message": "Invalid student ID format (must be 24-char hex)"}

    student_doc = await db.students.find_one({"_id": s_oid})
    if not student_doc:
        return {"status_code": 404, "message": "Student not found"}

    parent_record = await db.usertable.find_one({
        "student_ids": {"$in": [s_oid]},
        "usertype": "parent"
    })

    if not parent_record:
        return {
            "status_code": 403,
            "message": "This student is not linked to any parent account"
        }

    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},
        {
            "$set": {
                "usertype": "student",
                "student_id": s_oid,
                "created_at": datetime.now().astimezone()
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

    # âœ… Return is_new_user status
    is_new_user = student_doc.get("is_new_user", False)

    response_payload = {
        "status_code": 200,
        "message": "Switched to student successfully",
        "usertype": "student",
        "student_id": str(s_oid),
        "access_token": new_token,
        "token_type": "bearer",
        "is_new_user": is_new_user  # ðŸ†• Return new user status
    }

    student_subscription = student_doc.get("subscription")
    student_usage_buckets = student_doc.get("usage_buckets")

    if student_subscription is not None:
        from app.routes.user_routes import serialize_mongo_doc
        response_payload["subscription"] = serialize_mongo_doc(student_subscription)
        response_payload["usage_buckets"] = student_usage_buckets

    return response_payload