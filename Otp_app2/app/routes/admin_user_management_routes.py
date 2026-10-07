from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any
from bson import ObjectId
from datetime import datetime, timezone

from app.core.database import db
from app.utils.admin_auth import require_permission

router = APIRouter(tags=["User Management - Admin"])


def serialize(doc: dict) -> dict:
    """Convert MongoDB ObjectId and datetime fields to JSON-safe types."""
    if not doc:
        return {}
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, list):
            result[k] = [str(i) if isinstance(i, ObjectId) else i for i in v]
        elif isinstance(v, datetime):
            result[k] = v.isoformat() + "Z" if v.tzinfo is None else v.isoformat()
        else:
            result[k] = v
    return result


# ──────────────────────────────────────────────────────────────
# STUDENTS
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/students")
async def search_students(
    name: Optional[str] = Query(None, description="Filter by student name (partial match)"),
    student_class: Optional[str] = Query(None, description="Filter by class (e.g. '5')"),
    school_id: Optional[str] = Query(None, description="Filter by school ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(require_permission("User Management", "read"))
):
    """Search/list all students with optional filters."""
    query: Dict[str, Any] = {}
    if name:
        query["student_name"] = {"$regex": name, "$options": "i"}
    if student_class:
        import re
        raw_cls = str(student_class).strip()
        clean_cls = re.sub(r'^(class|std|grade)\s*', '', raw_cls, flags=re.I).strip()
        or_cls = [
            {"student_class": raw_cls},
            {"student_class": clean_cls},
            {"student_class": f"Class {clean_cls}"},
            {"student_class": f"class {clean_cls}"},
            {"student_class_raw": raw_cls}
        ]
        if clean_cls.isdigit():
            or_cls.append({"student_class": int(clean_cls)})
        query["$or"] = or_cls
    if school_id:
        query["school_id"] = school_id

    total = await db.students.count_documents(query)
    cursor = db.students.find(query).sort("created_at", -1).skip(skip).limit(limit)
    students = await cursor.to_list(length=limit)

    school_ids = list(set([s.get("school_id") for s in students if s.get("school_id")]))
    school_map = {}
    if school_ids:
        valid_school_ids = []
        for sid in school_ids:
            try:
                valid_school_ids.append(ObjectId(sid))
            except:
                pass
        if valid_school_ids:
            s_cursor = db.schools.find({"_id": {"$in": valid_school_ids}})
            async for school in s_cursor:
                school_map[str(school["_id"])] = school.get("name")

    # Batch lookup student mobile numbers from usertable if not directly on student doc
    missing_mobile_sids = [s["_id"] for s in students if not (s.get("student_phone") or s.get("mobile_number") or s.get("phone_number") or s.get("mobileno") or s.get("mobile_no") or s.get("phone") or s.get("mobile"))]
    mobile_map = {}
    guardian_phone_map = {}
    if missing_mobile_sids:
        sid_str_list = [str(x) for x in missing_mobile_sids]
        u_cursor = db.usertable.find({
            "$or": [
                {"student_ids": {"$in": missing_mobile_sids}},
                {"student_ids": {"$in": sid_str_list}},
                {"student_id": {"$in": missing_mobile_sids}},
                {"student_id": {"$in": sid_str_list}}
            ]
        })
        async for u in u_cursor:
            m_num = u.get("mobile_number")
            u_type = u.get("usertype")
            if m_num:
                st_ids = u.get("student_ids", [])
                if not isinstance(st_ids, list):
                    st_ids = [st_ids]
                if u.get("student_id"):
                    st_ids.append(u.get("student_id"))
                for st_id in st_ids:
                    key = str(st_id)
                    if u_type == "parent":
                        guardian_phone_map[key] = m_num
                    else:
                        mobile_map[key] = m_num

    for s in students:
        sid = s.get("school_id")
        if sid and sid in school_map:
            s["school_name"] = school_map[sid]
        
        st_id_str = str(s["_id"])

        # Populate guardian phone cleanly
        g_phone = s.get("guardian_phone") or s.get("parent_mobile") or guardian_phone_map.get(st_id_str)
        if g_phone:
            s["guardian_phone"] = g_phone

        # Ensure student age is calculated from DOB if missing
        if not s.get("age") and s.get("dob"):
            from app.routes.external_registration_routes import calculate_age_from_dob
            s["age"] = calculate_age_from_dob(s.get("dob"))

        # Resolve student's own phone number
        explicit_st_phone = (
            s.get("student_phone") or
            s.get("phone_number") or
            s.get("mobileno") or
            s.get("mobile_no") or
            s.get("mobile_number") or
            s.get("phone") or
            s.get("mobile") or
            s.get("contact_no") or
            s.get("mob_no")
        )
        raw_st_phone = explicit_st_phone or mobile_map.get(st_id_str)

        resolved_st_num = str(raw_st_phone).strip() if raw_st_phone else None
        s["mobile_number"] = resolved_st_num
        s["student_phone"] = resolved_st_num
        s["phone_number"] = resolved_st_num
        s["mobileno"] = resolved_st_num
        s["mobile_no"] = resolved_st_num

    return {
        "status": "success",
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [serialize(s) for s in students]
    }


@router.get("/admin-panel/users/student/{student_id}")
async def get_student_profile(
    student_id: str,
    current_admin: dict = Depends(require_permission("User Management", "read"))
):
    """
    Fetch a full student profile including:
    - Basic info (name, class, DOB, guardian)
    - Latest career analysis
    - Quiz attempt count
    - Intelligence test completion status
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if not student.get("age") and student.get("dob"):
        from app.routes.external_registration_routes import calculate_age_from_dob
        student["age"] = calculate_age_from_dob(student.get("dob"))

    g_phone = student.get("guardian_phone")
    if not g_phone:
        parent = await db.usertable.find_one({
            "usertype": "parent",
            "$or": [
                {"student_ids": s_oid},
                {"student_ids": student_id},
                {"student_id": s_oid},
                {"student_id": student_id}
            ]
        })
        if parent and parent.get("mobile_number"):
            g_phone = parent.get("mobile_number")
            student["guardian_phone"] = g_phone

    explicit_st_phone = (
        student.get("student_phone") or
        student.get("phone_number") or
        student.get("mobileno") or
        student.get("mobile_no") or
        student.get("mobile_number") or
        student.get("phone") or
        student.get("mobile") or
        student.get("contact_no") or
        student.get("mob_no")
    )
    raw_st_phone = explicit_st_phone
    if not raw_st_phone:
        st_user = await db.usertable.find_one({
            "usertype": {"$ne": "parent"},
            "$or": [
                {"student_ids": s_oid},
                {"student_ids": student_id},
                {"student_id": s_oid},
                {"student_id": student_id}
            ]
        })
        if st_user and st_user.get("mobile_number"):
            raw_st_phone = st_user.get("mobile_number")

    resolved_st_num = str(raw_st_phone).strip() if raw_st_phone else None
    student["mobile_number"] = resolved_st_num
    student["student_phone"] = resolved_st_num
    student["phone_number"] = resolved_st_num
    student["mobileno"] = resolved_st_num
    student["mobile_no"] = resolved_st_num

    if not student.get("guardian_phone"):
        parent = await db.usertable.find_one({
            "usertype": "parent",
            "$or": [
                {"student_ids": s_oid},
                {"student_ids": student_id},
                {"student_id": s_oid},
                {"student_id": student_id}
            ]
        })
        if parent and parent.get("mobile_number"):
            student["guardian_phone"] = parent.get("mobile_number")

    # Career analysis (latest)
    career = await db.career_analyzer.find_one(
        {"student_id": student_id},
        sort=[("attempt", -1)]
    )

    # Quiz submissions count
    quiz_count = await db.quiz_submissions.count_documents({"student_id": student_id})

    # Intelligence answers (latest attempt)
    answers_doc = await db.answers.find_one({"student_id": s_oid})
    latest_attempt = None
    if answers_doc:
        attempts = answers_doc.get("attempts", [])
        if attempts:
            latest_attempt = attempts[-1]
            # Remove heavy answers list from response to keep it light
            for cat in latest_attempt.get("categories", []):
                cat.pop("answers", None)

    career_data = None
    if career:
        scores = career.get("scores", {})
        percentages = career.get("percentages", {})
        top_5_items = career.get("top_5_careers")
        top_5_str = career.get("recommended_career")
        if not top_5_items or not top_5_str:
            from app.routes.user_routes import get_top_5_careers_with_scores
            top_5_items, top_5_str, _ = get_top_5_careers_with_scores(scores, percentages)

        career_data = {
            "top_category": career.get("top_category"),
            "recommended_career": top_5_str,
            "top_5_careers": top_5_items,
            "percentages": percentages,
            "scores": scores,
            "attempt": career.get("attempt"),
        }

    return {
        "status": "success",
        "data": {
            "student": serialize(student),
            "career": career_data or {},
            "quiz_attempts": quiz_count,
            "intelligence_test": latest_attempt
        }
    }


@router.delete("/admin-panel/users/student/{student_id}")
async def delete_student(
    student_id: str,
    current_admin: dict = Depends(require_permission("User Management", "delete"))
):
    """
    Permanently delete a student record and unlink from parent.
    Also removes answers, career analysis data for this student.
    """
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Unlink from parents
    await db.usertable.update_many(
        {"student_ids": s_oid},
        {"$pull": {"student_ids": s_oid}}
    )
    # Unlink from student-type users
    await db.usertable.update_many(
        {"student_id": s_oid},
        {"$unset": {"student_id": ""}}
    )

    # Remove associated data
    await db.answers.delete_many({"student_id": s_oid})
    await db.career_analyzer.delete_many({"student_id": student_id})
    await db.notifications.delete_many({"student_id": student_id})

    # Delete the student
    await db.students.delete_one({"_id": s_oid})

    return {"status": "success", "message": f"Student {student_id} deleted successfully"}


@router.patch("/admin-panel/users/student/{student_id}/deactivate")
async def deactivate_student(
    student_id: str,
    current_admin: dict = Depends(require_permission("User Management", "update"))
):
    """Soft-deactivate a student (sets is_active=False)."""
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    result = await db.students.update_one(
        {"_id": s_oid},
        {"$set": {"is_active": False, "deactivated_at": datetime.now(timezone.utc)}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"status": "success", "message": "Student deactivated"}


class QuotaUpdate(BaseModel):
    bucket: str
    new_value: int

@router.patch("/admin-panel/users/student/{student_id}/quotas")
async def update_student_quotas(
    student_id: str,
    payload: QuotaUpdate,
    current_admin: dict = Depends(require_permission("User Management", "update"))
):
    """Manually update a student's usage quota."""
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")
        
    allowed_buckets = ["tutor_balance_qs", "exam_balance", "class_balance", "voice_balance_mins"]
    if payload.bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail="Invalid bucket name")
        
    if payload.new_value < 0:
        raise HTTPException(status_code=400, detail="Quota cannot be negative")

    result = await db.students.update_one(
        {"_id": s_oid},
        {"$set": {f"usage_buckets.{payload.bucket}": payload.new_value}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")
        
    return {"status": "success", "message": f"Updated {payload.bucket} to {payload.new_value}"}


class StudentPhoneUpdate(BaseModel):
    student_phone: Optional[str] = None
    guardian_phone: Optional[str] = None
    guardian_name: Optional[str] = None


@router.patch("/admin-panel/users/student/{student_id}/phone")
@router.put("/admin-panel/users/student/{student_id}/phone")
async def update_student_phone(
    student_id: str,
    payload: StudentPhoneUpdate,
    current_admin: dict = Depends(require_permission("User Management", "update"))
):
    """
    Update student and/or guardian phone number on an existing student record.
    Preserves all existing IDs, answers, quizzes, and subscriptions.
    NEVER creates duplicate user/student records.
    """
    import re
    try:
        s_oid = ObjectId(student_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid student_id format")

    student = await db.students.find_one({"_id": s_oid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student_update = {"updated_at": datetime.now(timezone.utc)}

    # 1. Update Student Phone
    if payload.student_phone is not None:
        raw_st = str(payload.student_phone).strip()
        clean_st = re.sub(r'\D', '', raw_st)
        new_st_phone = clean_st[-10:] if len(clean_st) >= 10 else (clean_st if clean_st else None)

        old_st_phone = (
            student.get("student_phone") or
            student.get("mobile_number") or
            student.get("phone_number") or
            student.get("phone") or
            student.get("mobile")
        )

        student_update["student_phone"] = new_st_phone
        student_update["mobile_number"] = new_st_phone
        student_update["phone_number"] = new_st_phone
        student_update["phone"] = new_st_phone
        student_update["mobile"] = new_st_phone
        student_update["mobileno"] = new_st_phone
        student_update["mobile_no"] = new_st_phone

        if new_st_phone:
            # Update existing student record in usertable
            old_user = await db.usertable.find_one({
                "$or": [
                    {"student_id": s_oid},
                    {"student_id": student_id},
                    {"mobile_number": old_st_phone}
                ],
                "usertype": {"$ne": "parent"}
            })
            if old_user:
                await db.usertable.update_one(
                    {"_id": old_user["_id"]},
                    {
                        "$set": {
                            "mobile_number": new_st_phone,
                            "student_id": s_oid,
                            "student_name": student.get("student_name"),
                            "usertype": "student",
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )
            else:
                await db.usertable.update_one(
                    {"mobile_number": new_st_phone},
                    {
                        "$set": {
                            "usertype": "student",
                            "student_id": s_oid,
                            "student_name": student.get("student_name"),
                            "updated_at": datetime.now(timezone.utc)
                        },
                        "$setOnInsert": {
                            "created_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )

            # Update OTP record if needed
            if old_st_phone and old_st_phone != new_st_phone:
                await db.otps.update_many(
                    {"mobile_number": old_st_phone},
                    {"$set": {"mobile_number": new_st_phone, "usertype": "student"}}
                )

    # 2. Update Guardian Phone / Name
    if payload.guardian_phone is not None:
        raw_g = str(payload.guardian_phone).strip()
        clean_g = re.sub(r'\D', '', raw_g)
        new_g_phone = clean_g[-10:] if len(clean_g) >= 10 else (clean_g if clean_g else None)

        old_g_phone = student.get("guardian_phone") or student.get("parent_mobile")

        student_update["guardian_phone"] = new_g_phone
        student_update["parent_mobile"] = new_g_phone
        student_update["father_phone"] = new_g_phone
        student_update["parent_phone"] = new_g_phone

        if new_g_phone:
            # If old guardian exists and is different, remove student from old parent
            if old_g_phone and old_g_phone != new_g_phone:
                await db.usertable.update_one(
                    {"mobile_number": old_g_phone, "usertype": "parent"},
                    {"$pull": {"student_ids": s_oid}}
                )

            # Add student to new guardian account
            await db.usertable.update_one(
                {"mobile_number": new_g_phone},
                {
                    "$set": {
                        "usertype": "parent",
                        "updated_at": datetime.now(timezone.utc)
                    },
                    "$addToSet": {
                        "student_ids": s_oid
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )

    if payload.guardian_name is not None:
        student_update["guardian_name"] = payload.guardian_name

    # Apply update to student doc
    await db.students.update_one({"_id": s_oid}, {"$set": student_update})

    # Fetch updated student doc
    updated_student = await db.students.find_one({"_id": s_oid})

    return {
        "status": "success",
        "message": "Student phone details updated successfully",
        "student_id": student_id,
        "data": serialize(updated_student)
    }


# ──────────────────────────────────────────────────────────────
# PARENTS
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/parents")
async def list_parents(
    search: Optional[str] = Query(None, description="Search by parent mobile"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(require_permission("User Management", "read"))
):
    """List all parents with their linked student names and join dates."""
    # Ensure all guardians in db.students are synced to usertable
    students_with_guardians = await db.students.find({
        "$or": [
            {"guardian_phone": {"$exists": True, "$ne": None, "$nin": ["", "0000000000"]}},
            {"parent_mobile": {"$exists": True, "$ne": None, "$nin": ["", "0000000000"]}}
        ]
    }).to_list(length=None)

    for st in students_with_guardians:
        g_phone = st.get("guardian_phone") or st.get("parent_mobile")
        if g_phone and str(g_phone).strip() and str(g_phone).strip() != "0000000000":
            await db.usertable.update_one(
                {"mobile_number": str(g_phone).strip()},
                {
                    "$setOnInsert": {
                        "usertype": "parent",
                        "created_at": st.get("created_at", datetime.now(timezone.utc))
                    },
                    "$addToSet": {
                        "student_ids": st["_id"]
                    }
                },
                upsert=True
            )

    query = {"usertype": "parent"}
    if search:
        query["mobile_number"] = {"$regex": search, "$options": "i"}

    total = await db.usertable.count_documents(query)
    cursor = db.usertable.find(query).sort("created_at", -1).skip(skip).limit(limit)
    parents = await cursor.to_list(length=limit)

    # 1️⃣ Collect all student IDs for bulk fetch
    all_student_ids = []
    for p in parents:
        all_student_ids.extend(p.get("student_ids", []))
    
    # Remove duplicates
    all_student_ids = list(set(all_student_ids))

    # 2️⃣ Fetch student names and guardian names
    student_map = {}
    guardian_map = {}
    if all_student_ids:
        s_cursor = db.students.find({"_id": {"$in": all_student_ids}}, {"_id": 1, "student_name": 1, "guardian_name": 1})
        async for s in s_cursor:
            student_map[str(s["_id"])] = s.get("student_name", "Unknown")
            guardian_map[str(s["_id"])] = s.get("guardian_name", "Unknown")

    # 3️⃣ Build result
    result = []
    for p in parents:
        p_data = serialize(p)
        
        # Resolve student names
        s_ids = p.get("student_ids", [])
        p_data["student_names"] = [student_map.get(str(sid), "Unknown") for sid in s_ids]
        
        # Get guardian name from the first linked student, if available
        p_data["guardian_name"] = guardian_map.get(str(s_ids[0]), "Guardian") if s_ids else "Guardian"
        
        p_data["student_count"] = len(s_ids)
        result.append(p_data)

    return {
        "status": "success",
        "total": total,
        "data": result
    }


class ParentPhoneUpdate(BaseModel):
    new_mobile: str
    guardian_name: Optional[str] = None


@router.patch("/admin-panel/users/parent/{mobile}/phone")
@router.put("/admin-panel/users/parent/{mobile}/phone")
async def update_parent_phone(
    mobile: str,
    payload: ParentPhoneUpdate,
    current_admin: dict = Depends(require_permission("User Management", "update"))
):
    """
    Update a parent/guardian mobile number and sync all connected students.
    Preserves all existing student links and IDs.
    """
    import re
    clean_old = re.sub(r'\D', '', str(mobile).strip())
    old_cands = list(filter(None, {mobile, clean_old, clean_old[-10:] if len(clean_old) >= 10 else None}))

    clean_new = re.sub(r'\D', '', str(payload.new_mobile).strip())
    new_mobile = clean_new[-10:] if len(clean_new) >= 10 else clean_new
    if not new_mobile:
        raise HTTPException(status_code=400, detail="Invalid new mobile number")

    # 1. Find existing parent record
    parent = await db.usertable.find_one({"mobile_number": {"$in": old_cands}, "usertype": "parent"})

    # 2. Find all students linked to this guardian phone
    linked_students = await db.students.find({
        "$or": [
            {"guardian_phone": {"$in": old_cands}},
            {"parent_mobile": {"$in": old_cands}},
            {"father_phone": {"$in": old_cands}},
            {"parent_phone": {"$in": old_cands}},
            {"_id": {"$in": parent.get("student_ids", []) if parent else []}}
        ]
    }).to_list(length=None)

    s_oids = [s["_id"] for s in linked_students]

    # 3. Update parent record in usertable
    if parent:
        await db.usertable.update_one(
            {"_id": parent["_id"]},
            {
                "$set": {
                    "mobile_number": new_mobile,
                    "updated_at": datetime.now(timezone.utc)
                },
                "$addToSet": {
                    "student_ids": {"$each": s_oids}
                }
            }
        )
    else:
        await db.usertable.update_one(
            {"mobile_number": new_mobile},
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

    # 4. Update all linked students in db.students
    st_update = {
        "guardian_phone": new_mobile,
        "parent_mobile": new_mobile,
        "father_phone": new_mobile,
        "parent_phone": new_mobile,
        "updated_at": datetime.now(timezone.utc)
    }
    if payload.guardian_name:
        st_update["guardian_name"] = payload.guardian_name

    if s_oids:
        await db.students.update_many(
            {"_id": {"$in": s_oids}},
            {"$set": st_update}
        )

    # 5. Update OTP record
    await db.otps.update_many(
        {"mobile_number": {"$in": old_cands}},
        {"$set": {"mobile_number": new_mobile}}
    )

    return {
        "status": "success",
        "message": f"Guardian phone updated to {new_mobile}",
        "old_mobile": mobile,
        "new_mobile": new_mobile,
        "affected_students": len(s_oids)
    }


@router.delete("/admin-panel/users/parent/{mobile}")
async def delete_parent(
    mobile: str,
    current_admin: dict = Depends(require_permission("User Management", "delete"))
):
    """Remove a parent record from usertable."""
    existing = await db.usertable.find_one({"mobile_number": mobile})
    if not existing:
        raise HTTPException(status_code=404, detail="Parent not found")
    await db.usertable.delete_one({"mobile_number": mobile})
    return {"status": "success", "message": f"Parent {mobile} removed"}


# ──────────────────────────────────────────────────────────────
# DISTINCT CLASS LIST (for filters)
# ──────────────────────────────────────────────────────────────

@router.get("/admin-panel/users/classes")
async def get_available_classes(current_admin: dict = Depends(require_permission("User Management", "read"))):
    """Returns the distinct student classes present in DB (for filter dropdowns)."""
    classes = await db.students.distinct("student_class")
    try:
        classes_sorted = sorted(classes, key=lambda x: int(str(x)))
    except Exception:
        classes_sorted = sorted(classes)
    return {"status": "success", "classes": classes_sorted}
