import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db

async def insert():
    p1_mobile = "7510752568"
    p2_mobile = "7306964987"

    # 1. Parent 1 Student ABCD
    s1_doc = {
        "student_name": "ABCD",
        "student_class": "3",
        "dob": "2015-05-10",
        "age": "8",
        "address": "Kerala, India",
        "guardian_name": "Parent 1",
        "guardian_phone": p1_mobile,
        "parent_mobile": p1_mobile,
        "student_phone": None,
        "image_url": None,
        "created_at": datetime.now(timezone.utc),
        "subscription": {"current_tier": "basic", "last_recharge_date": None},
        "usage_buckets": {
            "exam_balance": 1,
            "voice_balance_mins": 2,
            "tutor_balance_qs": 5,
            "class_balance": 0
        },
        "is_user": False,
        "is_new_user": True,
        "syllabus": "NCERT"
    }
    res1 = await db.students.insert_one(s1_doc)
    s1_id = res1.inserted_id

    # 2. Parent 2 Student ABCD (distinct student record with identical details)
    s2_doc = {
        "student_name": "ABCD",
        "student_class": "3",
        "dob": "2015-05-10",
        "age": "8",
        "address": "Kerala, India",
        "guardian_name": "Parent 2",
        "guardian_phone": p2_mobile,
        "parent_mobile": p2_mobile,
        "student_phone": None,
        "image_url": None,
        "created_at": datetime.now(timezone.utc),
        "subscription": {"current_tier": "basic", "last_recharge_date": None},
        "usage_buckets": {
            "exam_balance": 1,
            "voice_balance_mins": 2,
            "tutor_balance_qs": 5,
            "class_balance": 0
        },
        "is_user": False,
        "is_new_user": True,
        "syllabus": "NCERT"
    }
    res2 = await db.students.insert_one(s2_doc)
    s2_id = res2.inserted_id

    # 3. Parent 1 in usertable
    await db.usertable.update_one(
        {"mobile_number": p1_mobile},
        {
            "$set": {
                "usertype": "parent",
                "updated_at": datetime.now(timezone.utc)
            },
            "$addToSet": {
                "student_ids": s1_id
            },
            "$pull": {
                "student_ids": s2_id
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    # 4. Parent 2 in usertable
    await db.usertable.update_one(
        {"mobile_number": p2_mobile},
        {
            "$set": {
                "usertype": "parent",
                "updated_at": datetime.now(timezone.utc)
            },
            "$addToSet": {
                "student_ids": s2_id
            },
            "$pull": {
                "student_ids": s1_id
            },
            "$setOnInsert": {
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    print(f"Parent 1 ({p1_mobile}) -> Student S1 ID: {s1_id}")
    print(f"Parent 2 ({p2_mobile}) -> Student S2 ID: {s2_id}")
    print("Inserted successfully into local DB!")

if __name__ == "__main__":
    asyncio.run(insert())
