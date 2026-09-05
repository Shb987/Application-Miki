import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from bson import ObjectId

from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile, Request, status
from app.core.database import db
from app.utils.user_auth import get_current_user, admin_or_user

router = APIRouter(tags=["User To-Do Module"])

UPLOAD_DIR = os.path.join("app", "static", "uploads", "todos")
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def extract_student_id(current_user: dict, explicit_student_id: Optional[str] = None) -> str:
    if explicit_student_id and str(explicit_student_id).strip() and str(explicit_student_id).strip().lower() != "string":
        return str(explicit_student_id).strip()

    sid = current_user.get("student_id") or current_user.get("_id")
    if sid and str(sid).strip() and str(sid).strip().lower() != "string":
        return str(sid).strip()

    sub = current_user.get("sub")
    if sub and str(sub).strip():
        sub_str = str(sub).strip()
        digits = "".join([c for c in sub_str if c.isdigit()])
        if len(digits) >= 10:
            last_10 = digits[-10:]
            regex_pattern = {"$regex": f"{last_10}$"}
            
            user_rec = await db.usertable.find_one({"mobile_number": regex_pattern})
            if user_rec:
                if user_rec.get("student_id"):
                    return str(user_rec["student_id"])
                st_ids = user_rec.get("student_ids", [])
                if st_ids:
                    return str(st_ids[0])

            st_rec = await db.students.find_one({"mobile_number": regex_pattern})
            if st_rec:
                return str(st_rec["_id"])

        return sub_str

    raise HTTPException(status_code=400, detail="Student ID could not be resolved from auth token or query")


async def build_student_id_filter(current_user: dict, explicit_student_id: Optional[str] = None) -> dict:
    candidates: List[Any] = []

    def add_candidate(val):
        if val is None:
            return
        s = str(val).strip()
        if not s or s.lower() == "string":
            return
        if s not in candidates:
            candidates.append(s)
        if ObjectId.is_valid(s):
            oid = ObjectId(s)
            if oid not in candidates:
                candidates.append(oid)

    if explicit_student_id:
        add_candidate(explicit_student_id)

    add_candidate(current_user.get("student_id"))
    add_candidate(current_user.get("_id"))
    add_candidate(current_user.get("sub"))

    sub = current_user.get("sub")
    if sub and str(sub).strip():
        sub_str = str(sub).strip()
        add_candidate(sub_str)
        
        digits = "".join([c for c in sub_str if c.isdigit()])
        if len(digits) >= 10:
            last_10 = digits[-10:]
            add_candidate(last_10)
            add_candidate(f"+91{last_10}")
            
            regex_pattern = {"$regex": f"{last_10}$"}

            user_cursor = db.usertable.find({"mobile_number": regex_pattern})
            user_recs = await user_cursor.to_list(length=10)
            for urec in user_recs:
                add_candidate(urec.get("student_id"))
                for sid in urec.get("student_ids", []):
                    add_candidate(sid)

            st_cursor = db.students.find({"mobile_number": regex_pattern})
            st_recs = await st_cursor.to_list(length=10)
            for srec in st_recs:
                add_candidate(srec.get("_id"))

    if explicit_student_id and ObjectId.is_valid(str(explicit_student_id).strip()):
        try:
            st_doc = await db.students.find_one({"_id": ObjectId(str(explicit_student_id).strip())})
            if st_doc and st_doc.get("mobile_number"):
                st_mob = str(st_doc["mobile_number"]).strip()
                add_candidate(st_mob)
                st_digits = "".join([c for c in st_mob if c.isdigit()])
                if len(st_digits) >= 10:
                    add_candidate(st_digits[-10:])
                    add_candidate(f"+91{st_digits[-10:]}")
        except Exception:
            pass

    if current_user.get("role") == "admin" and not explicit_student_id:
        return {}

    if not candidates:
        raise HTTPException(status_code=400, detail="Student ID could not be resolved from auth token or query")

    return {"student_id": {"$in": candidates}}


async def verify_todo_ownership(doc: dict, current_user: dict, explicit_student_id: Optional[str] = None):
    if current_user.get("role") == "admin":
        return

    filter_dict = await build_student_id_filter(current_user, explicit_student_id)
    allowed_ids = filter_dict.get("student_id", {}).get("$in", [])
    allowed_strs = [str(x) for x in allowed_ids if x is not None]

    doc_sid = doc.get("student_id")
    if doc_sid is not None and str(doc_sid) not in allowed_strs:
        raise HTTPException(status_code=403, detail="You do not have permission to access or modify this to-do task")


def format_todo_item(doc: dict) -> dict:
    todo_id = str(doc["_id"]) if doc.get("_id") else ""
    return {
        "id": todo_id,
        "todo_id": todo_id,
        "student_id": str(doc.get("student_id", "")),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "category": doc.get("category", "general"),
        "status": doc.get("status", "pending"),
        "is_completed": doc.get("is_completed", False),
        "is_important": doc.get("is_important", False),
        "due_date": doc.get("due_date", ""),
        "reminder_time": doc.get("reminder_time", ""),
        "is_reminder_enabled": doc.get("is_reminder_enabled", False),
        "reminder_sent": doc.get("reminder_sent", False),
        "image_urls": doc.get("image_urls", []),
        "created_at": doc.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": doc.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }


def format_todo_response(doc: dict) -> dict:
    item = format_todo_item(doc)
    return {
        "status": "success",
        "todo": item
    }


def save_upload_images(files: List[UploadFile]) -> List[str]:
    saved_urls = []
    for file_obj in files:
        if not file_obj or not file_obj.filename:
            continue
        ext = os.path.splitext(file_obj.filename)[1]
        filename = f"{uuid.uuid4()}{ext if ext else '.jpg'}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file_obj.file, buffer)
        saved_urls.append(f"uploads/todos/{filename}")
    return saved_urls


async def fetch_todo_by_id(todo_id: str) -> dict:
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")
    return doc


@router.post("/add-todos", summary="Add To-Do", status_code=status.HTTP_200_OK)
@router.post("/todos", summary="Add To-Do", status_code=status.HTTP_200_OK, include_in_schema=False)
async def create_todo(
    request: Request,
    student_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    due_date: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(False),
    status: Optional[str] = Form("pending"),
    reminder_time: Optional[str] = Form(None),
    is_reminder_enabled: Optional[bool] = Form(None),
    images: Union[List[UploadFile], List[str], UploadFile, str, None] = File(None),
    current_user: dict = Depends(admin_or_user)
):
    """
    Create a new To-Do task for a student.
    Supports optional `reminder_time` and `is_reminder_enabled` for OneSignal push notifications.
    Image upload (`images`) is fully optional.
    Returns the task wrapped inside its category object.
    """
    content_type = request.headers.get("content-type", "")
    image_urls = []

    if "application/json" in content_type:
        try:
            body_data = await request.json()
            todo_title = body_data.get("title")
            todo_desc = body_data.get("description", "")
            todo_cat = body_data.get("category", "general")
            todo_due = body_data.get("due_date", "")
            todo_imp = bool(body_data.get("is_important", False))
            todo_status = body_data.get("status", "pending")
            todo_rem_time = body_data.get("reminder_time", "")
            if "is_reminder_enabled" in body_data:
                todo_rem_enabled = bool(body_data["is_reminder_enabled"])
            else:
                todo_rem_enabled = bool(todo_rem_time)

            target_student_id = await extract_student_id(current_user, body_data.get("student_id"))
            
            json_imgs = body_data.get("images") or body_data.get("image_urls") or []
            if isinstance(json_imgs, str):
                json_imgs = [json_imgs]
            image_urls = [str(img) for img in json_imgs if img]
            uploaded_images = []
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    else:
        todo_title = title
        todo_desc = description or ""
        todo_cat = category or "general"
        todo_due = due_date or ""
        todo_imp = bool(is_important) if is_important is not None else False
        todo_status = status or "pending"
        todo_rem_time = reminder_time or ""
        if is_reminder_enabled is not None:
            todo_rem_enabled = bool(is_reminder_enabled)
        else:
            todo_rem_enabled = bool(todo_rem_time)

        target_student_id = await extract_student_id(current_user, student_id)
        uploaded_images = images or []
        if isinstance(uploaded_images, (UploadFile, str)):
            uploaded_images = [uploaded_images]
        elif not isinstance(uploaded_images, (list, tuple)):
            uploaded_images = []

    if not todo_title:
        raise HTTPException(status_code=400, detail="Field 'title' is required")

    is_completed = (str(todo_status).lower() == "completed")

    if uploaded_images:
        valid_files = [f for f in uploaded_images if hasattr(f, "filename") and f.filename]
        string_urls = [str(f) for f in uploaded_images if isinstance(f, str) and f.strip() and f.strip().lower() != "string"]
        if valid_files:
            file_urls = save_upload_images(valid_files)
            image_urls.extend(file_urls)
        if string_urls:
            image_urls.extend(string_urls)

    now_iso = datetime.now(timezone.utc).isoformat()
    todo_doc = {
        "student_id": target_student_id,
        "title": todo_title,
        "description": todo_desc,
        "status": "completed" if is_completed else "pending",
        "is_completed": is_completed,
        "is_important": todo_imp,
        "category": todo_cat,
        "due_date": todo_due,
        "reminder_time": todo_rem_time,
        "is_reminder_enabled": todo_rem_enabled,
        "reminder_sent": False,
        "image_urls": image_urls,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    res = await db.user_todos.insert_one(todo_doc)
    return {
        "status": "success",
        "message": "To-do item created successfully"
    }


@router.get("/view-todos", summary="View To-Do List")
@router.get("/todos", summary="View To-Do List", include_in_schema=False)
@router.get("/get-todos", summary="View To-Do List", include_in_schema=False)
@router.get("/list-todos", summary="View To-Do List", include_in_schema=False)
@router.post("/view-todos", summary="View To-Do List (POST)", include_in_schema=False)
@router.post("/get-todos", summary="View To-Do List (POST)", include_in_schema=False)
async def list_todos(
    request: Request,
    student_id: Optional[str] = Query(None, description="Student ID to fetch to-dos for"),
    category: Optional[str] = Query(None, description="Optional category to filter to-dos"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    skip: Optional[int] = Query(None, ge=0, description="Optional offset skip count"),
    current_user: dict = Depends(admin_or_user)
):
    """
    List all To-Do items for a student ID with pagination.
    Supports optional `category` query parameter filter (`?category=homework`).
    Sorted by is_important descending (True comes first) and created_at descending (latest comes top).
    """
    target_student_id = student_id
    target_category = category

    if request.method == "POST":
        try:
            body_data = await request.json()
            if not target_student_id and body_data.get("student_id"):
                target_student_id = str(body_data.get("student_id"))
            if not target_category and body_data.get("category"):
                target_category = str(body_data.get("category"))
        except Exception:
            pass

    query_filter: Dict[str, Any] = await build_student_id_filter(current_user, target_student_id)

    if target_category and target_category.strip():
        cat_regex = {"$regex": f"^{target_category.strip()}$", "$options": "i"}
        query_filter["category"] = cat_regex

    offset = skip if skip is not None else (page - 1) * limit
    total_count = await db.user_todos.count_documents(query_filter)

    cursor = (
        db.user_todos.find(query_filter)
        .sort([("is_important", -1), ("created_at", -1)])
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)

    items = [format_todo_item(doc) for doc in docs]

    categories_map: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        cat_name = (item.get("category") or "general").strip()
        if cat_name not in categories_map:
            categories_map[cat_name] = []
        categories_map[cat_name].append(item)

    if not categories_map and total_count == 0:
        categories_map["general"] = []

    total_pages = (total_count + limit - 1) // limit if limit > 0 else 0

    return {
        "status_code": 200,
        "status": "success",
        "todos": items,
        "page": page,
        "limit": limit,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }


@router.put("/update-todos/{todo_id}", summary="Update To-Do")
@router.put("/todos/{todo_id}", summary="Update To-Do", include_in_schema=False)
async def update_todo(
    todo_id: str,
    request: Request,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(None),
    status: Optional[str] = Form(None),
    reminder_time: Optional[str] = Form(None),
    is_reminder_enabled: Optional[bool] = Form(None),
    images: Union[List[UploadFile], List[str], UploadFile, str, None] = File(None),
    current_user: dict = Depends(admin_or_user)
):
    """
    Edit a To-Do item by todo_id and return the updated task formatted inside its category object.
    Consolidates status updates, uploading new image attachments, and deleting specified images.
    """
    doc = await fetch_todo_by_id(todo_id)
    await verify_todo_ownership(doc, current_user)
    oid = doc["_id"]

    content_type = request.headers.get("content-type", "")
    update_fields = {}
    existing_urls = list(doc.get("image_urls", []))
    urls_to_delete = []

    if "application/json" in content_type:
        try:
            body_data = await request.json()
            if "title" in body_data:
                update_fields["title"] = body_data["title"]
            if "description" in body_data:
                update_fields["description"] = body_data["description"]
            if "category" in body_data:
                update_fields["category"] = body_data["category"]
            if "due_date" in body_data:
                update_fields["due_date"] = body_data["due_date"]
            if "is_important" in body_data:
                update_fields["is_important"] = bool(body_data["is_important"])
            if "is_completed" in body_data:
                comp = bool(body_data["is_completed"])
                update_fields["is_completed"] = comp
                update_fields["status"] = "completed" if comp else "pending"
            elif "status" in body_data:
                st = str(body_data["status"]).lower()
                update_fields["status"] = st
                update_fields["is_completed"] = (st == "completed")

            if "reminder_time" in body_data:
                update_fields["reminder_time"] = body_data["reminder_time"]
                update_fields["reminder_sent"] = False
                if "is_reminder_enabled" not in body_data:
                    update_fields["is_reminder_enabled"] = bool(body_data["reminder_time"])

            if "is_reminder_enabled" in body_data:
                update_fields["is_reminder_enabled"] = bool(body_data["is_reminder_enabled"])

            del_imgs = body_data.get("delete_image_urls") or body_data.get("delete_images") or []
            if isinstance(del_imgs, str):
                del_imgs = [del_imgs]
            urls_to_delete.extend([str(u) for u in del_imgs if u])

            if "image_urls" in body_data and isinstance(body_data["image_urls"], list):
                existing_urls = [str(u) for u in body_data["image_urls"] if u]

            uploaded_images = []
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    else:
        if title is not None:
            update_fields["title"] = title
        if description is not None:
            update_fields["description"] = description
        if category is not None:
            update_fields["category"] = category
        if due_date is not None:
            update_fields["due_date"] = due_date
        if is_important is not None:
            update_fields["is_important"] = is_important
        if is_completed is not None:
            update_fields["is_completed"] = is_completed
            update_fields["status"] = "completed" if is_completed else "pending"
        elif status is not None:
            st = status.lower()
            update_fields["status"] = st
            update_fields["is_completed"] = (st == "completed")

        if reminder_time is not None:
            update_fields["reminder_time"] = reminder_time
            update_fields["reminder_sent"] = False
            if is_reminder_enabled is None:
                update_fields["is_reminder_enabled"] = bool(reminder_time)

        if is_reminder_enabled is not None:
            update_fields["is_reminder_enabled"] = bool(is_reminder_enabled)

        delete_imgs = request.query_params.get("delete_image_urls")
        if delete_imgs:
            urls_to_delete.append(delete_imgs)

        uploaded_images = images or []
        if isinstance(uploaded_images, (UploadFile, str)):
            uploaded_images = [uploaded_images]
        elif not isinstance(uploaded_images, (list, tuple)):
            uploaded_images = []

    if urls_to_delete:
        for img_url in urls_to_delete:
            if img_url in existing_urls:
                existing_urls.remove(img_url)
                local_path = os.path.join("app", "static", img_url.replace("/", os.sep))
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                    except Exception:
                        pass

    if uploaded_images:
        valid_files = [f for f in uploaded_images if hasattr(f, "filename") and f.filename]
        string_urls = [str(f) for f in uploaded_images if isinstance(f, str) and f.strip() and f.strip().lower() != "string"]
        if valid_files:
            new_urls = save_upload_images(valid_files)
            existing_urls.extend(new_urls)
        if string_urls:
            existing_urls.extend(string_urls)

    update_fields["image_urls"] = existing_urls
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.user_todos.update_one({"_id": oid}, {"$set": update_fields})
    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_response(updated_doc)


@router.delete("/delete-todos/{todo_id}", summary="Delete To-Do")
@router.delete("/todos/{todo_id}", summary="Delete To-Do", include_in_schema=False)
async def delete_todo(
    todo_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """
    Delete a To-Do item permanently by todo_id.
    """
    doc = await fetch_todo_by_id(todo_id)
    await verify_todo_ownership(doc, current_user)
    oid = doc["_id"]

    for img_url in doc.get("image_urls", []):
        local_path = os.path.join("app", "static", img_url.replace("/", os.sep))
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    await db.user_todos.delete_one({"_id": oid})
    return {
        "status": "success",
        "message": f"To-do item '{todo_id}' deleted successfully",
        **format_todo_response(doc)
    }


@router.post("/complete-todos/{todo_id}", summary="Complete To-Do", status_code=status.HTTP_200_OK)
@router.post("/todos/{todo_id}/complete", summary="Complete To-Do", status_code=status.HTTP_200_OK, include_in_schema=False)
async def mark_todo_completed(
    todo_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """
    Mark a To-Do item as completed.
    Changes status from 'pending' to 'completed' and sets is_completed to True.
    """
    doc = await fetch_todo_by_id(todo_id)
    await verify_todo_ownership(doc, current_user)
    oid = doc["_id"]

    update_fields = {
        "status": "completed",
        "is_completed": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    await db.user_todos.update_one({"_id": oid}, {"$set": update_fields})
    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_response(updated_doc)
