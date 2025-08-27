import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from models.otp_models import OTPRequest, OTPVerify
from core.database import db
from core.settings import settings

router = APIRouter(tags=["OTP"])

OTP_EXPIRY_MINUTES = settings.OTP_EXPIRY_MINUTES

@router.post("/send")
async def send_otp(data: OTPRequest):
    otp = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc)  # store UTC
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    # Check if mobile number exists
    record = await db.otps.find_one({"mobile_number": data.mobile_number})

    update_data = {
        "otp": otp,
        "created_at": now,
        "expiry": expiry_time,
    }

    # If user does not exist, add usertype = None
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

    # Force to UTC if Mongo stored as naive
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)

    if expiry_time < datetime.now(timezone.utc):
        return {"status_code": 400, "message": "OTP expired"}

    if record.get("otp") != data.otp:
        return {"status_code": 400, "message": "Invalid OTP"}

    return {"status_code": 200, 
            "message": "OTP verified successfully",
            "usertype": record.get("usertype")  # 👈 include in response
}


@router.post("/switch-user/send-otp")
async def switch_user_send_otp(data: OTPRequest):
    """
    Step 1: Send OTP for switching/login as Student
    """
    otp = str(random.randint(100000, 999999))
    now = datetime.now(timezone.utc)
    expiry_time = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    update_data = {"otp": otp, "created_at": now, "expiry": expiry_time, "usertype": "student"}
    await db.otps.update_one({"mobile_number": data.mobile_number}, {"$set": update_data}, upsert=True)

    return {"status_code": 200, "message": "OTP sent for student login", "otp": otp}
from fastapi import Query

@router.post("/switch-to-student")
async def switch_to_student(
    data: OTPVerify,
    student_id: str = Query(..., description="The ID of the student")
):
    """
    Verify OTP and switch to student account using student's own mobile number.
    """
    # Step 1: Verify OTP
    verify_result = await verify_otp(data)
    if verify_result["status_code"] != 200:
        return verify_result

    # Step 2: Check that student exists
    student_doc = await db.students.find_one({"student_id": student_id})
    if not student_doc:
        return {"status_code": 404, "message": "Student not found"}
    print(student_id)
    # Step 3: Ensure student_id belongs to some parent
    parent_record = await db.usertable.find_one({
        "student_ids": {"$in": [student_id]},
        "usertype": "parent"
    })    
    print(parent_record)
    if not parent_record:
        # DEBUG: print all parent records that have student_ids
        cursor = db.usertable.find({"usertype": "parent"})
        parent_docs = await cursor.to_list(length=None)

        all_links = [
            {
                "mobile_number": doc["mobile_number"],
                "student_ids": doc.get("student_ids", [])
            }
            for doc in parent_docs
        ]
        print("DEBUG: Parent records with student_ids:", all_links)

        return {
            "status_code": 403,
            "message": f"This student ({student_id}) is not linked to any parent account",
            "all_parent_links": all_links   # 👈 optional: send back in API response too
        }

    # Step 4: Create/Update student user account with their own mobile
    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},   # student logs in with their own number
        {
            "$set": {
                "usertype": "student",
                "student_id": student_id,
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )
    # Step 5: Mark student as user
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
