from fastapi import APIRouter, Form, HTTPException, Depends, File, UploadFile, Query
from app.models.user_models import UserCreate, Student, UserTypeRequest, StudentUpdate, MobileChangeRequest
from app.models.answer_models import AnswerRequest
from app.models.career_models import CareerAnalyzer
from app.core.database import db
from datetime import datetime, timezone
from bson import ObjectId
from typing import Dict, List, Optional, Union
import re
import os
import random
import shutil
import uuid
from app.utils.user_auth import get_current_user, admin_or_user, create_user_token
from app.utils.admin_auth import get_current_admin, require_permission
from fastapi import HTTPException
from datetime import datetime, timezone
from fastapi import BackgroundTasks
from app.services.future_study_service import generate_and_store_future_study


router = APIRouter(tags=["User"])

UPLOAD_DIR = "app/static/uploads/student_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --------------------- Student Registration -------------------------
@router.post("/register-student")
async def register_student(
    student_name: str = Form(...),
    dob: str = Form(...),
    student_class: str = Form(...),
    age: str = Form(...),
    address: str = Form(...),
    guardian_name: str = Form(...),
    parent_mobile: str = Query(...),
    profile_image: Union[UploadFile, str, None] = File(None),
    school_id: Optional[str] = Form(None),
    syllabus: Optional[str] = Form(None),
    syllabus_spaced: Optional[str] = Form(None, alias="syllabus "),
    current=Depends(admin_or_user)
):
    actual_syllabus = syllabus or syllabus_spaced
    if not actual_syllabus:
        raise HTTPException(status_code=400, detail="Syllabus is required")
        
    if actual_syllabus.upper() not in ["NCERT", "SCERT"]:
        raise HTTPException(status_code=400, detail="Syllabus must be either NCERT or SCERT")
        
    usertype = current.get("usertype")
    # 🔑 Decide is_user
    is_user = usertype == "student"

    image_url = None
    if profile_image and not isinstance(profile_image, str):
        file_extension = os.path.splitext(profile_image.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)
        
        image_url = f"uploads/student_images/{file_name}"

    basic_plan = await db.subscription_plans.find_one({"_id": "basic"})
    initial_buckets = basic_plan.get("buckets", {}) if basic_plan else {
        "exam_balance": 1,
        "voice_balance_mins": 2,
        "tutor_balance_qs": 5,
        "class_balance": 0
    }

    # 1️⃣ Create student document
    student_doc = {
        "student_name": student_name,
        "dob": dob,
        "student_class": student_class,
        "age": age,
        "address": address,
        "guardian_name": guardian_name,
        "image_url": image_url,
        "created_at": datetime.now(timezone.utc),
        "subscription": {"current_tier": "basic", "last_recharge_date": None},
        "usage_buckets": initial_buckets,
        "is_user": is_user,
        "is_new_user": True,
        "school_id": school_id,
        "syllabus": actual_syllabus.upper()
    }

    # ✅ INSERT STUDENT ONCE
    result = await db.students.insert_one(student_doc)
    student_oid = result.inserted_id

    # 2️⃣ Parent registers student
    if usertype == "parent":
        await db.usertable.update_one(
            {"mobile_number": parent_mobile},
            {
                "$setOnInsert": {
                    "usertype": "parent",
                    "created_at": datetime.now(timezone.utc)
                },
                "$addToSet": {
                    "student_ids": student_oid
                }
            },
            upsert=True
        )

    # 3️⃣ Student self-registers
    elif usertype == "student":
        await db.usertable.update_one(
            {"mobile_number": current["sub"]},
            {
                "$set": {
                    "student_id": student_oid,
                    "updated_at": datetime.now(timezone.utc)
                },
                "$setOnInsert": {
                    "usertype": "student",
                    "created_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )

    # 4️⃣ Admin case (optional)
    elif usertype == "admin":
        pass

    return {
        "status_code": 200,
        "message": "Student registered successfully",
        "student_id": str(student_oid),
        "is_user": is_user
    }


# --------------------- Public Student Registration (No Auth) -------------------------
@router.post("/register-student-public")
async def register_student_public(
    student_name: str = Form(...),
    dob: str = Form(...),
    student_class: str = Form(...),
    age: str = Form(...),
    address: str = Form(...),
    guardian_name: str = Form(...),
    parent_mobile: str = Form(...),  # Required for public registration
    profile_image: Union[UploadFile, str, None] = File(None),
    school_id: Optional[str] = Form(None),
    syllabus: Optional[str] = Form(None),
    syllabus_spaced: Optional[str] = Form(None, alias="syllabus ")
):
    """
    Public endpoint for parents to register students without logging in first.
    """
    
    actual_syllabus = syllabus or syllabus_spaced
    if not actual_syllabus:
        raise HTTPException(status_code=400, detail="Syllabus is required")
        
    if actual_syllabus.upper() not in ["NCERT", "SCERT"]:
        raise HTTPException(status_code=400, detail="Syllabus must be either NCERT or SCERT")

    # 1️⃣ Handle Image Upload
    image_url = None
    if profile_image and not isinstance(profile_image, str):
        file_extension = os.path.splitext(profile_image.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)
        
        image_url = f"uploads/student_images/{file_name}"

    basic_plan = await db.subscription_plans.find_one({"_id": "basic"})
    initial_buckets = basic_plan.get("buckets", {}) if basic_plan else {
        "exam_balance": 1,
        "voice_balance_mins": 2,
        "tutor_balance_qs": 5,
        "class_balance": 0
    }

    # 2️⃣ Create Student Document
    student_doc = {
        "student_name": student_name,
        "dob": dob,
        "student_class": student_class,
        "age": age,
        "address": address,
        "guardian_name": guardian_name,
        "image_url": image_url,
        "created_at": datetime.now(timezone.utc),
        "subscription": {"current_tier": "basic", "last_recharge_date": None},
        "usage_buckets": initial_buckets,
        "is_user": False,  # Child is not the user
        "is_new_user": True,
        "school_id": school_id,
        "syllabus": actual_syllabus.upper()
    }

    # Insert into DB
    result = await db.students.insert_one(student_doc)
    student_oid = result.inserted_id

    # 3️⃣ Create or Link Parent Account
    # Upsert parent record based on mobile number
    await db.usertable.update_one(
        {"mobile_number": parent_mobile},
        {
            "$setOnInsert": {
                "usertype": "parent",
                "created_at": datetime.now(timezone.utc)
            },
            "$addToSet": {
                "student_ids": student_oid
            }
        },
        upsert=True
    )

    return {
        "status_code": 200,
        "message": "Student registered successfully (Public)",
        "student_id": str(student_oid),
        "parent_mobile": parent_mobile
    }



@router.put("/update-student/{student_id}")
async def update_student(
    student_id: str,
    student_name: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    student_class: Optional[str] = Form(None),
    age: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    guardian_name: Optional[str] = Form(None),
    school_id: Optional[str] = Form(None),
    syllabus: Optional[str] = Form(None),
    syllabus_spaced: Optional[str] = Form(None, alias="syllabus "),
    profile_image: Union[UploadFile, str, None] = File(None),
    current=Depends(admin_or_user)
):
    # 🔐 Validate student_id
    try:
        student_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id")

    # 🔄 Extract only provided fields
    update_data = {}
    if student_name is not None: update_data["student_name"] = student_name
    if dob is not None: update_data["dob"] = dob
    if student_class is not None: update_data["student_class"] = student_class
    if age is not None: 
        if not age.isdigit():
            raise HTTPException(status_code=400, detail="Age must be numeric")
        update_data["age"] = age
    if address is not None: update_data["address"] = address
    if guardian_name is not None: update_data["guardian_name"] = guardian_name
    if school_id is not None: update_data["school_id"] = school_id
    
    actual_syllabus = syllabus or syllabus_spaced
    if actual_syllabus is not None: 
        if actual_syllabus.upper() not in ["NCERT", "SCERT"]:
            raise HTTPException(status_code=400, detail="Syllabus must be either NCERT or SCERT")
        update_data["syllabus"] = actual_syllabus.upper()

    if profile_image and not isinstance(profile_image, str):
        file_extension = os.path.splitext(profile_image.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)
        
        update_data["image_url"] = f"uploads/student_images/{file_name}"

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    update_data["updated_at"] = datetime.now(timezone.utc)

    result = await db.students.update_one(
        {"_id": student_oid},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "status_code": 200,
        "message": "Student details updated successfully",
        "student_id": student_id
    }

def serialize_mongo_doc(doc):
    """
    Recursively convert ObjectId to str in a document (dict) or list.
    """
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    if isinstance(doc, dict):
        return {k: serialize_mongo_doc(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        # 🕒 Ensure aware datetimes are serialized with UTC indicator 'Z'
        if doc.tzinfo:
            return doc.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        else:
            # 🕒 If naive, assume it was intended as UTC and add 'Z'
            return doc.isoformat() + "Z"
    return doc

# --------------------- Fetch Parent Details -------------------------
@router.get("/parent")
async def get_parent_details(
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch details for the currently logged-in parent.
    Mobile number is extracted from the JWT token.
    """
    mobile_number = current_user.get("sub")
    
    user_record = await db.usertable.find_one({"mobile_number": mobile_number})
    if not user_record:
        return {"status_code": 404, "message": "Parent not found"}

    student_ids = user_record.get("student_ids", [])
    students = []
    if student_ids:
        # student_ids is now a list of ObjectIds
        cursor = db.students.find({"_id": {"$in": student_ids}})
        students = [serialize_mongo_doc(doc) for doc in await cursor.to_list(length=None)]

    return {"status_code": 200, "parent_number": mobile_number, "students": students}


@router.post("/change-mobile")
async def change_mobile(
    data: MobileChangeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Change the parent's mobile number after OTP verification.
    """
    old_mobile = current_user.get("sub")
    new_mobile = data.new_mobile_number

    if old_mobile == new_mobile:
        raise HTTPException(status_code=400, detail="New mobile number must be different from the old one")

    # 1️⃣ Verify OTP for the NEW mobile number
    otp_record = await db.otps.find_one({"mobile_number": new_mobile})
    if not otp_record:
        raise HTTPException(status_code=400, detail="OTP not found for the new mobile number")

    if otp_record.get("otp") != data.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    expiry_time = otp_record.get("expiry")
    if expiry_time.tzinfo is None:
        expiry_time = expiry_time.replace(tzinfo=timezone.utc)

    if expiry_time < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OTP expired")

    # 2️⃣ Check if the new mobile number is already in use
    existing_user = await db.usertable.find_one({"mobile_number": new_mobile})
    if existing_user:
        raise HTTPException(status_code=400, detail="New mobile number is already registered")

    # 3️⃣ Update usertable
    result = await db.usertable.update_one(
        {"mobile_number": old_mobile},
        {"$set": {
            "mobile_number": new_mobile,
            "updated_at": datetime.now(timezone.utc)
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User record not found")

    # 4️⃣ Update OTP table (optional, but keep things clean)
    await db.otps.delete_one({"mobile_number": new_mobile}) # OTP is used
    await db.otps.update_one(
        {"mobile_number": old_mobile},
        {"$set": {"mobile_number": new_mobile}}
    )

    # 5️⃣ Generate NEW access token
    usertype = current_user.get("usertype", "parent")
    new_token = create_user_token(mobile_number=new_mobile, usertype=usertype)

    return {
        "status_code": 200,
        "message": "Mobile number updated successfully",
        "new_mobile_number": new_mobile,
        "access_token": new_token,
        "token_type": "bearer"
    }


@router.post("/set-usertype")
async def set_usertype(
    data: UserTypeRequest,
    current_user: dict = Depends(get_current_user)
):
    # 1️⃣ Check OTP record
    record = await db.otps.find_one({"mobile_number": data.mobile_number})
    if not record:
        return {"status_code": 400, "message": "User not found"}

    # 2️⃣ Update OTP table
    await db.otps.update_one(
        {"mobile_number": data.mobile_number},
        {"$set": {"usertype": data.usertype}}
    )

    # 3️⃣ Update usertable
    await db.usertable.update_one(
        {"mobile_number": data.mobile_number},
        {
            "$set": {
                "usertype": data.usertype,
                "created_at": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    # 4️⃣ 🔑 CREATE NEW ACCESS TOKEN
    access_token = create_user_token(
        mobile_number=data.mobile_number,
        usertype=data.usertype
    )



    return {
        "status_code": 200,
        "message": f"Usertype set to {data.usertype}",
        "usertype": data.usertype,
        "access_token": access_token,
        "token_type": "bearer"
    }


# --------------------- Questions by Age -------------------------
@router.get("/student_questions")
async def get_questions_by_age(age: int = Query(...)):
    # Determine max questions per category based on age (Universal Model)
    if age <= 6:
        max_questions = 5
    elif age <= 11:
        max_questions = 7
    elif age <= 14:
        max_questions = 10
    else:
        max_questions = 12

    # Find questions where age_min <= age <= age_max
    query = {
        "$and": [
            {"age_min": {"$lte": age}},
            {"age_max": {"$gte": age}}
        ]
    }

    cursor = db.questions.find(query)
    questions = [serialize_mongo_doc(doc) for doc in await cursor.to_list(length=None)]

    # Group by category first
    category_map: Dict[str, List[dict]] = {}
    for q in questions:
        cat = q.get("category", "uncategorized")
        category_map.setdefault(cat, []).append(q)

    final_grouped: Dict[str, List[dict]] = {}

    # Rating question limit per category:
    # Minimum / Junior class (age <= 11): Max 1 rating question
    # Higher class (age > 11): Max 3 rating questions
    max_rating_allowed = 1 if age <= 11 else 3

    for cat, cat_questions in category_map.items():
        rating_qs = [q for q in cat_questions if q.get("type") == "rating"]
        non_rating_qs = [q for q in cat_questions if q.get("type") != "rating"]

        random.shuffle(rating_qs)
        random.shuffle(non_rating_qs)

        selected_rating = rating_qs[:max_rating_allowed]
        needed_non_rating = max_questions - len(selected_rating)
        selected_non_rating = non_rating_qs[:needed_non_rating]

        selected_questions = selected_rating + selected_non_rating

        if len(selected_questions) < max_questions and len(rating_qs) > len(selected_rating):
            extra_needed = max_questions - len(selected_questions)
            selected_questions.extend(rating_qs[len(selected_rating):len(selected_rating) + extra_needed])

        random.shuffle(selected_questions)
        
        for q in selected_questions:
            # Build question payload (as per original logic)
            question_data = {
                "id": q["_id"],
                "text": q.get("text"),
            }

            if q.get("type") == "image":
                question_data["type"] = "image"
                img_opts = q.get("image_options", [])
                c_idx = q.get("correct_index")
                question_data["options"] = img_opts
                question_data["correct_index"] = c_idx
                
                correct_ans = q.get("correct_answer")
                if not correct_ans and c_idx is not None and img_opts:
                    try:
                        c_i = int(c_idx)
                        if 0 <= c_i < len(img_opts):
                            correct_ans = img_opts[c_i]
                        elif 1 <= c_i <= len(img_opts):
                            correct_ans = img_opts[c_i - 1]
                    except (ValueError, TypeError):
                        pass
                question_data["correct_answer"] = correct_ans
            elif q.get("type") == "rating":
                question_data["type"] = "rating"
                question_data["age_min"] = q.get("age_min")
                question_data["age_max"] = q.get("age_max")
            else:
                question_data["type"] = "text"
                question_data["options"] = q.get("options", [])
                question_data["correct_answer"] = q.get("correct_answer")

            final_grouped.setdefault(cat, []).append(question_data)

    return {
        "status_code": 200,
        "age": age,
        "categories": final_grouped
    }

# --------------------- Save Answer -------------------------
 



@router.post("/answers")
async def save_answers(payload: AnswerRequest,current_user: dict = Depends(get_current_user)):

    answers_list = []
    total_marks = 0
    rating_values = []

    # Process each question + answer
    for qid, ans in zip(payload.question_ids, payload.answers):
        q_candidates = [qid, str(qid)]
        if ObjectId.is_valid(str(qid)):
            q_candidates.append(ObjectId(str(qid)))

        question = await db.questions.find_one({"_id": {"$in": q_candidates}})
        if not question:
            continue

        q_type = question.get("type")
        correct_index = question.get("correct_index")
        options = question.get("options") or question.get("image_options") or []

        correct_ans_val = question.get("correct_answer")
        if not correct_ans_val and correct_index is not None and options:
            try:
                c_idx = int(correct_index)
                if 0 <= c_idx < len(options):
                    correct_ans_val = options[c_idx]
                elif 1 <= c_idx <= len(options):
                    correct_ans_val = options[c_idx - 1]
            except (ValueError, TypeError):
                pass

        if q_type == "rating":
            rating_values.append(ans)
            mark = 0
        else:
            ans_s = str(ans).strip() if ans is not None else None
            ci_s = str(correct_index).strip() if correct_index is not None else None
            is_correct = (ans_s == ci_s) or (ans_s is not None and ans_s == str(correct_ans_val))
            mark = 1 if is_correct else 0
            total_marks += mark

        answers_list.append({
            "question_id": str(qid),
            "question_text": question.get("text"),
            "options": options,
            "answer_value": ans,
            "correct_index": correct_index,
            "correct_answer": correct_ans_val,
            "type": q_type,
            "mark": mark
        })

    # Compute rating avg + add to total marks
    rating_avg = sum(rating_values) / len(rating_values) if rating_values else 0
    total_marks += rating_avg

    # ---------------------------------------
    # AUTO ATTEMPT & STATUS LOGIC
    # ---------------------------------------
    try:
        s_oid = ObjectId(payload.student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format (must be 24-char hex)")

    existing_doc = await db.answers.find_one({"student_id": s_oid})

    if not existing_doc:
        # 🟢 First ever record for student
        attempt = 1
        new_doc = {
            "student_id": s_oid,
            "attempts": [
                {
                    "attempt": attempt,
                    "status": "in-progress",
                    "timestamp_utc": datetime.now(timezone.utc),
                    "categories": [{
                        "category": payload.category,
                        "total_marks": total_marks,
                        "answers": answers_list
                    }]
                }
            ]
        }
        await db.answers.insert_one(new_doc)

    else:
        # 🟡 Student already exists
        attempts = existing_doc.get("attempts", [])
        if not attempts:
            attempt = 1
        else:
            last_attempt = attempts[-1]
            attempt = last_attempt["attempt"]

            # If last attempt is completed → new attempt
            if last_attempt["status"] == "completed":
                attempt += 1
                await db.answers.update_one(
                    {"student_id": s_oid},
                    {"$push": {
                        "attempts": {
                            "attempt": attempt,
                            "status": "in-progress",
                            "timestamp_utc": datetime.now(timezone.utc),
                            "categories": []
                        }
                    }}
                )

        # Fetch latest document again after potential new attempt creation
        student_doc = await db.answers.find_one({"student_id": s_oid})
        active_attempt = next(
            (a for a in student_doc["attempts"] if a["attempt"] == attempt),
            None
        )

        if not active_attempt:
            raise HTTPException(status_code=500, detail="Attempt not found after update.")

        # Remove existing category if re-submitted
        updated_categories = [
            c for c in active_attempt.get("categories", [])
            if c["category"] != payload.category
        ]
        updated_categories.append({
            "category": payload.category,
            "total_marks": total_marks,
            "answers": answers_list
        })

        # Update DB
        await db.answers.update_one(
            {"student_id": s_oid, "attempts.attempt": attempt},
            {"$set": {"attempts.$.categories": updated_categories}}
        )

        # ---------------------------------------
        # AUTO MARK ATTEMPT AS COMPLETED
        # ---------------------------------------
        total_category_count = len(updated_categories)
        if total_category_count >= 8:  # if all 8 intelligence types answered
            await db.answers.update_one(
                {"student_id": s_oid, "attempts.attempt": attempt},
                {"$set": {"attempts.$.status": "completed"}}
            )
            pass

    return {
        "status_code": 200,
        "message": f"Answers saved for category '{payload.category}' (Attempt {attempt})",
        "rating_average": rating_avg,
        "total_marks": total_marks
    }



@router.get("/get_students")
async def get_students(admin=Depends(require_permission("User Management", "read"))):
    cursor = db.students.find({})
    students = await cursor.to_list(length=None)
    serialized_students = [serialize_mongo_doc(doc) for doc in students]
    return {
        "status_code": 200,
        "students": serialized_students
    }




@router.get("/student-detail/{student_id}")
async def get_student_detail(student_id: str, current=Depends(admin_or_user)):
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    serialized_student = serialize_mongo_doc(student)
    return {
        "status_code": 200,
        "student": serialized_student
    }




# ✅ Get all Users (Parents table)
@router.get("/get_users")
async def get_users(admin=Depends(require_permission("User Management", "read"))):
    cursor = db.usertable.find({})
    users = await cursor.to_list(length=None)
    serialized_users = [serialize_mongo_doc(doc) for doc in users]
    return {
        "status_code": 200,
        "users": serialized_users
    }


# ✅ Get all Login Attempts (OTP table)
@router.get("/get_logins")
async def get_logins(admin=Depends(require_permission("User Management", "read"))):
    cursor = db.otps.find({})
    logins = await cursor.to_list(length=None)
    serialized_logins = [serialize_mongo_doc(doc) for doc in logins]
    return {
        "status_code": 200,
        "logins": serialized_logins
    }


# --------------------- Career Analyzer Logic -------------------------


career_map = {
    "musical": "Musician, Composer, Singer, Sound Engineer",
    
    "logical-mathematical": "Scientist, Engineer, Mathematician, Data Analyst",
    "logical_mathematical": "Scientist, Engineer, Mathematician, Data Analyst",
    "logical mathematical": "Scientist, Engineer, Mathematician, Data Analyst",
    "logical": "Scientist, Engineer, Mathematician, Data Analyst",
    "logical-math": "Scientist, Engineer, Mathematician, Data Analyst",
    
    "verbal-linguistic": "Writer, Journalist, Teacher, Lawyer",
    "verbal_linguistic": "Writer, Journalist, Teacher, Lawyer",
    "verbal linguistic": "Writer, Journalist, Teacher, Lawyer",
    "verbal": "Writer, Journalist, Teacher, Lawyer",
    
    "bodily-kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    "bodily_kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    "bodily kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    "bodily": "Athlete, Dancer, Physical Therapist, Surgeon",
    "kinesthetic": "Athlete, Dancer, Physical Therapist, Surgeon",
    
    "visual-spatial": "Architect, Designer, Artist, Pilot",
    "visual_spatial": "Architect, Designer, Artist, Pilot",
    "visual spatial": "Architect, Designer, Artist, Pilot",
    "visual": "Architect, Designer, Artist, Pilot",
    
    "interpersonal": "Teacher, Counselor, Manager, Salesperson",
    "inter-personal": "Teacher, Counselor, Manager, Salesperson",
    "inter_personal": "Teacher, Counselor, Manager, Salesperson",
    
    "intrapersonal": "Psychologist, Philosopher, Writer",
    "intra-personal": "Psychologist, Philosopher, Writer",
    "intra_personal": "Psychologist, Philosopher, Writer",
    
    "naturalist": "Biologist, Environmentalist, Farmer, Veterinarian"
}

def get_recommended_career(category_name: str) -> str:
    if not category_name:
        return "Scientist, Engineer, Mathematician, Data Analyst"
    
    cat_clean = str(category_name).strip().lower()
    
    if cat_clean in career_map:
        return career_map[cat_clean]
        
    norm_hyphen = cat_clean.replace("_", "-").replace(" ", "-")
    if norm_hyphen in career_map:
        return career_map[norm_hyphen]
        
    norm_underscore = cat_clean.replace("-", "_").replace(" ", "_")
    if norm_underscore in career_map:
        return career_map[norm_underscore]

    if "logical" in cat_clean or "math" in cat_clean:
        return career_map["logical-mathematical"]
    if "verbal" in cat_clean or "linguistic" in cat_clean:
        return career_map["verbal-linguistic"]
    if "bodily" in cat_clean or "kinesthetic" in cat_clean:
        return career_map["bodily-kinesthetic"]
    if "visual" in cat_clean or "spatial" in cat_clean:
        return career_map["visual-spatial"]
    if "interpersonal" in cat_clean or "inter-personal" in cat_clean:
        return career_map["interpersonal"]
    if "intrapersonal" in cat_clean or "intra-personal" in cat_clean:
        return career_map["intrapersonal"]
    if "musical" in cat_clean or "music" in cat_clean:
        return career_map["musical"]
    if "naturalist" in cat_clean or "nature" in cat_clean:
        return career_map["naturalist"]

    return "Scientist, Engineer, Mathematician, Data Analyst"


def generate_insights_and_suggestions(scores: dict):
    if not scores:
        return [], []
    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_3 = sorted_cats[:3]
    insights = [
        f"{cat}: Strong inclination towards {cat.lower()} intelligence."
        for cat, _ in top_3
    ]
    career_suggestions = [
        f"{cat} ➔ {get_recommended_career(cat)}"
        for cat, _ in top_3
    ]
    return insights, career_suggestions


import base64
from io import BytesIO
from datetime import datetime, timezone
import math
from fastapi import HTTPException
def normalize_percentages(scores: dict) -> dict:
    total = sum(scores.values())

    # If total is 0 → return all zeros
    if total == 0:
        return {k: 0 for k in scores}

    # 1️⃣ Exact percentages
    exact = {k: (v / total) * 100 for k, v in scores.items()}

    # 2️⃣ Floor values
    floor_pct = {k: math.floor(p) for k, p in exact.items()}

    # 3️⃣ Remaining percentage points to distribute
    remaining = 100 - sum(floor_pct.values())

    # 4️⃣ Sort categories by fractional remainder descending
    remainders = [(k, exact[k] - floor_pct[k], scores[k]) for k in scores]
    remainders.sort(key=lambda x: (-x[1], -x[2]))

    # 5️⃣ Distribute remaining points
    result = floor_pct.copy()
    for i in range(remaining):
        key = remainders[i][0]
        result[key] += 1

    return result



@router.post("/analyze-career/{student_id}")

async def analyze_career(
    student_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Automatically analyze the latest completed attempt for a student"""

    # 1️⃣ Fetch student answers
    student_doc = await db.answers.find_one({"student_id": ObjectId(student_id)})
    if not student_doc:
        raise HTTPException(status_code=404, detail="No answers found")

    attempts = student_doc.get("attempts", [])
    completed_attempts = [a for a in attempts if a.get("status") == "completed"]

    if not completed_attempts:
        raise HTTPException(
            status_code=400,
            detail="No completed attempt found"
        )

    latest_attempt = max(completed_attempts, key=lambda a: a["attempt"])
    attempt_num = latest_attempt["attempt"]

    # 2️⃣ Scores & Tie Handling
    categories = latest_attempt.get("categories", [])
    scores = {c["category"]: c.get("total_marks", 0) for c in categories}
    percentages = normalize_percentages(scores)

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if sorted_cats:
        max_score = sorted_cats[0][1]
        tied_top_cats = [cat for cat, val in sorted_cats if val == max_score and max_score > 0]
        if not tied_top_cats:
            tied_top_cats = [sorted_cats[0][0]]
    else:
        tied_top_cats = ["logical-mathematical"]

    top_cat = " & ".join(cat.title() for cat in tied_top_cats)

    combined_careers = []
    for cat in tied_top_cats:
        c_str = get_recommended_career(cat)
        for c in c_str.split(","):
            c_clean = c.strip()
            if c_clean and c_clean not in combined_careers:
                combined_careers.append(c_clean)

    recommended_career = ", ".join(combined_careers) if combined_careers else get_recommended_career(tied_top_cats[0])

    top_3 = sorted_cats[:3]
    insights = [
        f"{cat}: Strong inclination towards {cat.lower()} intelligence."
        for cat, _ in top_3
    ]

    career_suggestions = [
        f"{cat} ➔ {get_recommended_career(cat)}"
        for cat, _ in top_3
    ]

    # 3️⃣ Save career analysis
    await db.career_analyzer.update_one(
        {"student_id": student_id, "attempt": attempt_num},
        {
            "$set": {
                "scores": scores,
                "overall_score": sum(scores.values()),
                "percentages": percentages,
                "top_category": top_cat,
                "recommended_career": recommended_career,
                "personality_insights": insights,
                "career_suggestions": career_suggestions,
                "timestamp": datetime.now(timezone.utc)
            }
        },
        upsert=True
    )

    # 4️⃣ Fetch student class & Trigger Future study
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    student_class = student.get("student_class") if student else None

    if student_class:
        background_tasks.add_task(
            generate_and_store_future_study,
            db,
            student_id,
            student_class,
            recommended_career,
            top_cat
        )

    # 6️⃣ Immediate response
    return {
        "status_code": 200,
        "student_id": student_id,
        "analyzed_attempt": attempt_num,
        "scores": scores,
        "overall_score": sum(scores.values()),
        "percentages": percentages,
        "top_category": top_cat,
        "recommended_career": recommended_career,
        "personality_insights": insights,
        "career_suggestions": career_suggestions,
        "future_study_status": "processing"
    }



@router.get("/future-study/{student_id}")
async def get_future_study(
    student_id: str,
    current=Depends(admin_or_user)
):
    record = await db.future_study.find_one(
        {"student_id": student_id},
        sort=[("created_at", -1)]
    )

    if not record:
        raise HTTPException(
            status_code=200,
            detail="Future study guidance not generated yet"
        )

    return {
        "status_code": 200,
        "student_id": student_id,
        "recommended_career": record.get("recommended_career"),
        "top_category": record.get("top_category"),
        "student_class": record.get("student_class"),
        "future_study": record.get("resources"),
        "created_at": record.get("created_at")
    }

 




@router.get("/career-analysis/{student_id}")
@router.get("/career-analysis/{student_id}/{attempt}")
async def get_career_analysis(
    student_id: str,
    attempt: Optional[int] = None,
    current=Depends(admin_or_user)
):
    """
    Fetch career analysis for a specific student and optional attempt number (defaults to latest completed attempt).
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    s_candidates = [student_id, str(s_oid)]
    if ObjectId.is_valid(student_id):
        s_candidates.append(ObjectId(student_id))

    query = {"student_id": {"$in": s_candidates}}
    if attempt is not None:
        query["attempt"] = attempt

    record = await db.career_analyzer.find_one(
        query,
        {"_id": 0},
        sort=[("attempt", -1)]
    )

    if not record:
        answers_doc = await db.answers.find_one({"student_id": {"$in": s_candidates}})
        if answers_doc and answers_doc.get("attempts"):
            completed = [a for a in answers_doc["attempts"] if a.get("status") == "completed"]
            target_attempt = max(completed, key=lambda x: x["attempt"]) if completed else max(answers_doc["attempts"], key=lambda x: x.get("attempt", 1))
            att_no = target_attempt["attempt"]
            categories = target_attempt.get("categories", [])
            scores = {c["category"]: c.get("total_marks", 0) for c in categories}
            percentages = normalize_percentages(scores)
            sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top_cat = sorted_cats[0][0].title() if sorted_cats else "Logical-Mathematical"
            rec_career = get_recommended_career(top_cat)
            insights, suggestions = generate_insights_and_suggestions(scores)

            record = {
                "student_id": student_id,
                "attempt": att_no,
                "scores": scores,
                "overall_score": sum(scores.values()),
                "percentages": percentages,
                "top_category": top_cat,
                "recommended_career": rec_career,
                "personality_insights": insights,
                "career_suggestions": suggestions,
                "timestamp": target_attempt.get("timestamp_utc") or datetime.now(timezone.utc)
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No career analysis found for student {student_id}" + (f" in attempt {attempt}" if attempt else "")
            )

    record = serialize_mongo_doc(record)
    scores = record.get("scores", {})
    insights = record.get("personality_insights")
    suggestions = record.get("career_suggestions")
    if not insights or not suggestions:
        gen_insights, gen_suggestions = generate_insights_and_suggestions(scores)
        insights = insights or gen_insights
        suggestions = suggestions or gen_suggestions
        record["personality_insights"] = insights
        record["career_suggestions"] = suggestions

    att_num = record.get("attempt", attempt or 1)
    top_cat = record.get("top_category", "")
    rec_career = record.get("recommended_career", "")
    overall_score = record.get("overall_score", sum(scores.values()))
    percentages = record.get("percentages", normalize_percentages(scores))

    return {
        "status_code": 200,
        "student_id": student_id,
        "attempt": att_num,
        "analyzed_attempt": att_num,
        "top_category": top_cat,
        "recommended_career": rec_career,
        "overall_score": overall_score,
        "percentages": percentages,
        "scores": scores,
        "personality_insights": insights,
        "career_suggestions": suggestions,
        "career_analysis": record,
        "data": record
    }


@router.get("/career-history/{student_id}")
async def get_career_history(
    student_id: str,
    include_answers: bool = Query(True, description="Include detailed question-by-question answers"),
    current=Depends(admin_or_user)
):
    """
    Fetch historical career analysis attempts for a student.
    Returns full career analysis statistics, scores, personality insights, suggestions, and question answer details.
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    s_candidates = [student_id, str(s_oid)]
    if ObjectId.is_valid(student_id):
        s_candidates.append(ObjectId(student_id))

    career_records = await db.career_analyzer.find({"student_id": {"$in": s_candidates}}).sort("attempt", -1).to_list(None)
    career_map_by_attempt = {c.get("attempt"): c for c in career_records if c.get("attempt") is not None}

    answers_doc = await db.answers.find_one({"student_id": {"$in": s_candidates}})
    attempts = answers_doc.get("attempts", []) if answers_doc else []

    if not attempts and not career_records:
        return {
            "status_code": 200,
            "student_id": student_id,
            "total_attempts": 0,
            "career_history": [],
            "history": [],
            "data": []
        }

    full_attempts = []
    for attempt in attempts:
        categories_detailed = []

        for cat in attempt.get("categories", []):
            answers_detailed = []

            for ans in cat.get("answers", []):
                qid = ans.get("question_id")
                if not qid:
                    continue

                q_candidates = [qid, str(qid)]
                if ObjectId.is_valid(str(qid)):
                    q_candidates.append(ObjectId(str(qid)))

                question = await db.questions.find_one(
                    {"_id": {"$in": q_candidates}},
                    {"text": 1, "type": 1, "options": 1, "image_options": 1,
                     "correct_index": 1, "correct_answer": 1}
                )

                if not question:
                    st_ans = ans.get("answer_value")
                    c_ans = ans.get("correct_answer")
                    c_idx = ans.get("correct_index")
                    q_txt = ans.get("question_text") or ans.get("text") or "Question"
                    qtype = ans.get("type", "text")
                    opts = ans.get("options") or []
                    
                    if not c_ans and c_idx is not None and opts:
                        try:
                            ci = int(c_idx)
                            if 0 <= ci < len(opts):
                                c_ans = opts[ci]
                            elif 1 <= ci <= len(opts):
                                c_ans = opts[ci - 1]
                        except (ValueError, TypeError):
                            pass

                    answers_detailed.append({
                        "question_id": str(qid),
                        "question_text": q_txt,
                        "options": opts,
                        "image_options": opts if qtype == "image" else [],
                        "student_answer": st_ans,
                        "user_answer": st_ans,
                        "student_answer_url": st_ans,
                        "user_answer_url": st_ans,
                        "type": qtype,
                        "correct_index": c_idx,
                        "correct_answer_index": c_idx,
                        "correct_answer": c_ans or "N/A",
                        "correct_answer_url": c_ans,
                        "correct_option": c_ans or "N/A",
                        "is_correct": bool(ans.get("mark", 0) > 0)
                    })
                    continue

                qtype = question.get("type")
                student_answer = ans.get("answer_value")
                correct_index = question.get("correct_index")
                raw_correct_ans = question.get("correct_answer")
                options = question.get("options") or question.get("image_options") or []
                image_options = question.get("image_options") or (options if qtype == "image" else [])

                student_answer_s = str(student_answer).strip() if student_answer is not None else None
                correct_index_s = str(correct_index).strip() if correct_index is not None else None

                correct_ans_val = raw_correct_ans
                target_opts = image_options if qtype == "image" else options
                
                if qtype == "image" or not correct_ans_val or (isinstance(correct_ans_val, (int, str)) and str(correct_ans_val).strip().isdigit()):
                    idx_to_check = None
                    if correct_index is not None:
                        try:
                            idx_to_check = int(correct_index)
                        except (ValueError, TypeError):
                            pass
                    elif raw_correct_ans is not None:
                        try:
                            idx_to_check = int(raw_correct_ans)
                        except (ValueError, TypeError):
                            pass
                    
                    if idx_to_check is not None and target_opts:
                        if 0 <= idx_to_check < len(target_opts):
                            correct_ans_val = target_opts[idx_to_check]
                        elif 1 <= idx_to_check <= len(target_opts):
                            correct_ans_val = target_opts[idx_to_check - 1]

                student_answer_url = None
                if qtype == "image":
                    if isinstance(student_answer, str) and (student_answer.startswith("/") or student_answer.startswith("http")):
                        student_answer_url = student_answer
                    elif student_answer is not None and image_options:
                        try:
                            s_idx = int(student_answer)
                            if 0 <= s_idx < len(image_options):
                                student_answer_url = image_options[s_idx]
                            elif 1 <= s_idx <= len(image_options):
                                student_answer_url = image_options[s_idx - 1]
                        except (ValueError, TypeError):
                            pass
                    if not student_answer_url and isinstance(student_answer, str):
                        student_answer_url = student_answer

                if qtype == "rating":
                    is_correct = True
                else:
                    is_correct = (student_answer_s == correct_index_s) or (student_answer_s is not None and student_answer_s == str(correct_ans_val))

                answers_detailed.append({
                    "question_id": str(qid),
                    "question_text": question.get("text") or ans.get("question_text") or "Question",
                    "question": question.get("text") or ans.get("question_text") or "Question",
                    "text": question.get("text") or ans.get("question_text") or "Question",
                    "options": options,
                    "image_options": image_options,
                    "student_answer": student_answer_url or student_answer,
                    "user_answer": student_answer_url or student_answer,
                    "your_answer": student_answer_url or student_answer,
                    "your_answers": student_answer_url or student_answer,
                    "answer": student_answer_url or student_answer,
                    "answer_value": student_answer_url or student_answer,
                    "student_answer_url": student_answer_url or student_answer,
                    "user_answer_url": student_answer_url or student_answer,
                    "type": qtype,
                    "correct_index": correct_index,
                    "correct_answer_index": correct_index,
                    "correct_answer": correct_ans_val or "N/A",
                    "correct_answer_url": correct_ans_val if qtype == "image" else None,
                    "correct_option": correct_ans_val or "N/A",
                    "is_correct": is_correct
                })

            categories_detailed.append({
                "category": cat["category"],
                "total_marks": cat["total_marks"],
                "answers": answers_detailed
            })

        full_attempts.append({
            "attempt": attempt["attempt"],
            "timestamp_utc": attempt.get("timestamp_utc") or datetime.now(timezone.utc),
            "status": attempt.get("status", "in-progress"),
            "categories": categories_detailed
        })

    attempt_numbers = set([a["attempt"] for a in attempts] + list(career_map_by_attempt.keys()))
    combined_history = []

    for att_num in sorted(attempt_numbers, reverse=True):
        matching_attempt = next((a for a in full_attempts if a["attempt"] == att_num), None)
        c_record = career_map_by_attempt.get(att_num, {})

        scores = c_record.get("scores")
        if not scores and matching_attempt:
            scores = {cat["category"]: cat.get("total_marks", 0) for cat in matching_attempt.get("categories", [])}

        insights = c_record.get("personality_insights")
        suggestions = c_record.get("career_suggestions")
        if not insights or not suggestions:
            gen_insights, gen_suggestions = generate_insights_and_suggestions(scores or {})
            insights = insights or gen_insights
            suggestions = suggestions or gen_suggestions

        top_cat = c_record.get("top_category")
        rec_career = c_record.get("recommended_career")
        if not top_cat and scores:
            sorted_s = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top_cat = sorted_s[0][0].title() if sorted_s else "Logical-Mathematical"
            rec_career = get_recommended_career(top_cat)

        flat_answers = [a for cat in (matching_attempt.get("categories", []) if matching_attempt else []) for a in cat.get("answers", [])]

        item = {
            "attempt": att_num,
            "timestamp": c_record.get("timestamp") or (matching_attempt.get("timestamp_utc") if matching_attempt else None),
            "top_category": top_cat,
            "recommended_career": rec_career,
            "overall_score": c_record.get("overall_score", sum((scores or {}).values())),
            "percentages": c_record.get("percentages") or normalize_percentages(scores or {}),
            "personality_insights": insights,
            "career_suggestions": suggestions,
            "scores": scores or {},
            "answers_detail": matching_attempt,
            "categories": matching_attempt.get("categories", []) if matching_attempt else [],
            "answers": flat_answers,
            "questions": flat_answers,
            "your_answers": flat_answers
        }

        combined_history.append(item)

    return {
        "status_code": 200,
        "student_id": student_id,
        "total_attempts": len(combined_history),
        "career_history": combined_history,
        "history": combined_history,
        "data": combined_history
    }


@router.get("/onboarding-history/{student_id}")
async def get_onboarding_history(
    student_id: str,
    current=Depends(admin_or_user)
):
    """
    Fetch detailed onboarding test answers history for a student.
    Returns question-by-question answer breakdown per attempt.
    """
    return await get_career_history(student_id=student_id, include_answers=True, current=current)




# --------------------- New User Status Update -------------------------

@router.post("/update-user-status/{student_id}")
async def update_user_status(
    student_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Sets is_new_user to False for a specific student.
    Called when the student first opens their dashboard.
    """

    # 🔐 Optional: Authorization check
    user_student_id = current_user.get("student_id")
    if user_student_id and user_student_id != student_id:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    # ✅ Validate ObjectId
    try:
        s_oid = ObjectId(student_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    # ✅ Update student
    result = await db.students.update_one(
        {"_id": s_oid},
        {"$set": {"is_new_user": False}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "status_code": 200,
        "message": "User status updated to 'not new'",
        "student_id": student_id,
        "is_new_user": False
    }

