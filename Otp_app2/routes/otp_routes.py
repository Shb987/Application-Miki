import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from models.otp_models import OTPRequest, OTPVerify
from core.database import db
from core.settings import settings
from utils.user_auth import get_current_user,create_user_token  # <-- USERS JWT (parent/student)

router = APIRouter(tags=["OTP"])

OTP_EXPIRY_MINUTES = settings.OTP_EXPIRY_MINUTES

@router.post("/send")
async def send_otp(data: OTPRequest):
    otp = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc)
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    record = await db.otps.find_one({"mobile_number": data.mobile_number})

    update_data = {
        "otp": otp,
        "created_at": now,
        "expiry": expiry_time,
    }

    if not record:
        update_data["usertype"] = None

    await db.otps.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": update_data},
        upsert=True
    )

    return {"status_code": 200, "message": "OTP generated", "otp": otp}


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
    usertype = record.get("usertype") or "null"

    # Default value
    is_user = False

    # ✅ Check only if student
    if usertype == "student":
        print('check1')
        user_record = await db.usertable.find_one(
            {"mobile_number": data.mobile_number}
        )
        print(data.mobile_number)

        if user_record:
            print('check2')
            student_id = user_record.get("student_id")

            if student_id:
                print('check3')

                student = await db.students.find_one(
                    {"_id": (student_id)},
                    {"is_user": 1}
                )

                if student and student.get("is_user") is True:
                    print('check4')
                    is_user = True

    access_token = create_user_token(data.mobile_number, usertype)

    return {
        "status_code": 200,
        "message": "OTP verified successfully",
        "usertype": usertype,
        "is_user": is_user,
        "access_token": access_token,
        "token_type": "bearer"
    }

# 🔐 PROTECTED — must be a LOGGED IN USER (parent)
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


from fastapi import Query

# 🔐 PROTECTED — must be a LOGGED IN USER (parent)
@router.post("/switch-to-student")
async def switch_to_student(
    data: OTPVerify,
    student_id: str = Query(..., description="The ID of the student"),
    current_user: dict = Depends(get_current_user)
):
    verify_result = await verify_otp(data)
    if verify_result["status_code"] != 200:
        return verify_result

    student_doc = await db.students.find_one({"student_id": student_id})
    if not student_doc:
        return {"status_code": 404, "message": "Student not found"}
    print(student_id)
    parent_record = await db.usertable.find_one({
        "student_ids": {"$in": [student_id]},
        "usertype": "parent"
    })
    print(parent_record)
    if not parent_record:
        cursor = db.usertable.find({"usertype": "parent"})
        parent_docs = await cursor.to_list(length=None)

        all_links = [
            {
                "mobile_number": doc["mobile_number"],
                "student_ids": doc.get("student_ids", [])
            }
            for doc in parent_docs
        ]

        return {
            "status_code": 403,
            "message": f"This student ({student_id}) is not linked to any parent account",
            "all_parent_links": all_links
        }

    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},
        {
            "$set": {
                "usertype": "student",
                "student_id": student_id,
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    await db.students.update_one(
        {"student_id": student_id},
        {"$set": {"is_user": True}}
    )

    return {
        "status_code": 200,
        "message": "Switched to student successfully",
        "usertype": "student",
        "student_id": student_id
    }
