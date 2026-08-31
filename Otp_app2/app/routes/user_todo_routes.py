import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId

from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile, Request, status
from app.core.database import db
from app.utils.user_auth import get_current_user, admin_or_user

router = APIRouter(prefix="/todos", tags=["User To-Do Module"])

UPLOAD_DIR = os.path.join("app", "static", "uploads", "todos")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def extract_student_id(current_user: dict, explicit_student_id: Optional[str] = None) -> str:
    if explicit_student_id and str(explicit_student_id).strip():
        return str(explicit_student_id).strip()
    sid = current_user.get("student_id") or current_user.get("_id") or current_user.get("sub")
    if not sid:
        raise HTTPException(status_code=400, detail="Student ID could not be resolved from auth token or query")
    return str(sid)


def build_student_id_filter(current_user: dict, explicit_student_id: Optional[str] = None) -> dict:
    if explicit_student_id and str(explicit_student_id).strip():
        sid_str = str(explicit_student_id).strip()
        candidates: List[Any] = [sid_str]
        if ObjectId.is_valid(sid_str):
            candidates.append(ObjectId(sid_str))
        return {"student_id": {"$in": candidates}}

    if current_user.get("role") == "admin":
        return {}

    raw_candidates = [
        current_user.get("student_id"),
        current_user.get("_id"),
        current_user.get("sub"),
        "string"
    ]
    candidates: List[Any] = []
    for val in raw_candidates:
        if val and str(val).strip():
            s = str(val).strip()
            if s not in candidates:
                candidates.append(s)
            if ObjectId.is_valid(s):
                oid = ObjectId(s)
                if oid not in candidates:
                    candidates.append(oid)

    if not candidates:
        raise HTTPException(status_code=400, detail="Student ID could not be resolved from auth token or query")

    return {"student_id": {"$in": candidates}}


def format_todo_item(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]) if doc.get("_id") else "",
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
    category_name = (doc.get("category") or "general").strip()
    return {
        "todo": item,
        "item": item,
        category_name: item
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


@router.post("", status_code=status.HTTP_200_OK)
async def create_todo(
    request: Request,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form("general"),
    due_date: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(False),
    status: Optional[str] = Form("pending"),
    reminder_time: Optional[str] = Form(None),
    is_reminder_enabled: Optional[bool] = Form(None),
    student_id: Optional[str] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
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

            target_student_id = extract_student_id(current_user, body_data.get("student_id"))
            
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

        target_student_id = extract_student_id(current_user, student_id)
        uploaded_images = images or []

    if not todo_title:
        raise HTTPException(status_code=400, detail="Field 'title' is required")

    is_completed = (str(todo_status).lower() == "completed")

    if uploaded_images:
        valid_files = [f for f in uploaded_images if f and hasattr(f, "filename") and f.filename]
        if valid_files:
            file_urls = save_upload_images(valid_files)
            image_urls.extend(file_urls)

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


@router.get("")
async def list_todos(
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
    query_filter: Dict[str, Any] = build_student_id_filter(current_user, student_id)

    if category and category.strip():
        cat_regex = {"$regex": f"^{category.strip()}$", "$options": "i"}
        query_filter["category"] = cat_regex

    offset = skip if skip is not None else (page - 1) * limit
    total_count = await db.user_todos.count_documents(query_filter)

    if total_count == 0 and not student_id:
        fallback_filter: Dict[str, Any] = {}
        if category and category.strip():
            fallback_filter["category"] = cat_regex
        fallback_count = await db.user_todos.count_documents(fallback_filter)
        if fallback_count > 0:
            query_filter = fallback_filter
            total_count = fallback_count

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
        "page": page,
        "limit": limit,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "todo": items[0] if items else {},
        "todos": items,
        "items": items,
        "categories": categories_map,
        **categories_map
    }


@router.put("/{todo_id}")
async def update_todo(
    todo_id: str,
    request: Request,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    due_date: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(None),
    is_completed: Optional[bool] = Form(None),
    status: Optional[str] = Form(None),
    reminder_time: Optional[str] = Form(None),
    is_reminder_enabled: Optional[bool] = Form(None),
    delete_image_urls: Optional[List[str]] = Form(None),
    images: Optional[List[UploadFile]] = File(None),
    current_user: dict = Depends(admin_or_user)
):
    """
    Edit a To-Do item by todo_id and return the updated task formatted inside its category object.
    Consolidates status updates, uploading new image attachments, and deleting specified images.
    """
    doc = await fetch_todo_by_id(todo_id)
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

        if delete_image_urls:
            urls_to_delete.extend(delete_image_urls)

        uploaded_images = images or []

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
        if valid_files:
            new_urls = save_upload_images(valid_files)
            existing_urls.extend(new_urls)

    update_fields["image_urls"] = existing_urls
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.user_todos.update_one({"_id": oid}, {"$set": update_fields})
    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_response(updated_doc)


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """
    Delete a To-Do item permanently by todo_id.
    """
    doc = await fetch_todo_by_id(todo_id)
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
