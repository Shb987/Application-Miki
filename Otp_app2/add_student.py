import asyncio
from datetime import datetime
from bson import ObjectId
from app.core.database import db

async def insert():
    s_oid = ObjectId()
    student = {
        "_id": s_oid,
        "student_name": "John",
        "student_class": "10",
        "guardian_name": "Jacob",
        "dob": "2008-05-12",
        "is_active": True,
        "created_at": datetime.utcnow()
    }
    
    parent = {
        "mobile_number": "+1234567890",
        "usertype": "parent",
        "student_ids": [s_oid],
        "created_at": datetime.utcnow()
    }
    
    await db.students.insert_one(student)
    await db.usertable.insert_one(parent)
    print("Inserted successfully!")

asyncio.run(insert())
