import os
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List
from bson import ObjectId

from fastapi import APIRouter, Depends, HTTPException, Query, Form, File, UploadFile, Request, status
from app.core.database import db
from app.utils.user_auth import get_current_user, admin_or_user
from app.models.todo_models import TodoCreate, TodoUpdate, TodoStatusUpdate, TodoResponse

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


def format_todo_doc(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "student_id": str(doc.get("student_id", "")),
        "title": doc.get("title", ""),
        "description": doc.get("description"),
        "status": doc.get("status", "pending"),
        "is_completed": doc.get("is_completed", False),
        "is_important": doc.get("is_important", False),
        "category": doc.get("category", "General"),
        "due_date": doc.get("due_date"),
        "image_urls": doc.get("image_urls", []),
        "created_at": doc.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": doc.get("updated_at", datetime.now(timezone.utc).isoformat()),
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


@router.post("", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create_todo(
    request: Request,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form("General"),
    due_date: Optional[str] = Form(None),
    is_important: Optional[bool] = Form(False),
    status: Optional[str] = Form("pending"),
    student_id: Optional[str] = Form(None),
    images: List[UploadFile] = File(None),
    current_user: dict = Depends(admin_or_user)
):
    """
    Create a new To-Do task for a user (student).
    Supports both JSON body and Form-data (with file image uploads).
    """
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body_data = await request.json()
            todo_title = body_data.get("title")
            todo_desc = body_data.get("description")
            todo_cat = body_data.get("category", "General")
            todo_due = body_data.get("due_date")
            todo_imp = bool(body_data.get("is_important", False))
            todo_status = body_data.get("status", "pending")
            target_student_id = extract_student_id(current_user, body_data.get("student_id"))
            uploaded_images = []
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {str(e)}")
    else:
        todo_title = title
        todo_desc = description
        todo_cat = category or "General"
        todo_due = due_date
        todo_imp = bool(is_important) if is_important is not None else False
        todo_status = status or "pending"
        target_student_id = extract_student_id(current_user, student_id)
        uploaded_images = images or []

    if not todo_title:
        raise HTTPException(status_code=400, detail="Field 'title' is required")

    is_completed = (str(todo_status).lower() == "completed")

    # Process uploaded images if provided
    image_urls = []
    if uploaded_images:
        valid_files = [f for f in uploaded_images if f.filename]
        if valid_files:
            image_urls = save_upload_images(valid_files)

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
        "image_urls": image_urls,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    res = await db.user_todos.insert_one(todo_doc)
    todo_doc["_id"] = res.inserted_id
    return format_todo_doc(todo_doc)


@router.get("", response_model=List[TodoResponse])
async def list_todos(
    student_id: Optional[str] = Query(None, description="Optional target student ID"),
    status: Optional[str] = Query(None, description="Filter by status: 'pending', 'completed', or 'all'"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_important: Optional[bool] = Query(None, description="Filter by importance flag"),
    search: Optional[str] = Query(None, description="Search term in title or description"),
    current_user: dict = Depends(admin_or_user)
):
    """
    List all To-Do items for the authenticated student.
    Supports filtering by status ('pending', 'completed', 'all'), category, importance, and text search.
    """
    target_student_id = extract_student_id(current_user, student_id)
    query = {"student_id": target_student_id}

    if status and status.lower() != "all":
        query["status"] = status.lower()

    if category:
        query["category"] = category

    if is_important is not None:
        query["is_important"] = is_important

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]

    cursor = db.user_todos.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [format_todo_doc(d) for d in docs]


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(
    todo_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """
    Fetch details of a single To-Do item by ID.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    return format_todo_doc(doc)


@router.put("/{todo_id}", response_model=TodoResponse)
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
    images: List[UploadFile] = File(None),
    current_user: dict = Depends(admin_or_user)
):
    """
    Update a To-Do item. Supports updating fields and appending new image attachments.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    content_type = request.headers.get("content-type", "")
    update_fields = {}

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
        uploaded_images = images or []

    if uploaded_images:
        valid_files = [f for f in uploaded_images if f.filename]
        if valid_files:
            new_urls = save_upload_images(valid_files)
            existing_urls = doc.get("image_urls", [])
            update_fields["image_urls"] = existing_urls + new_urls

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.user_todos.update_one({"_id": oid}, {"$set": update_fields})
    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_doc(updated_doc)


@router.patch("/{todo_id}/status", response_model=TodoResponse)
async def update_todo_status(
    todo_id: str,
    payload: TodoStatusUpdate,
    current_user: dict = Depends(admin_or_user)
):
    """
    Quick status update endpoint to switch task status between 'pending' and 'completed'.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    new_status = None
    new_completed = None

    if payload.is_completed is not None:
        new_completed = payload.is_completed
        new_status = "completed" if payload.is_completed else "pending"
    elif payload.status is not None:
        new_status = payload.status.lower()
        new_completed = (new_status == "completed")

    if new_status is None:
        raise HTTPException(status_code=400, detail="Must provide either status or is_completed")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.user_todos.update_one(
        {"_id": oid},
        {"$set": {"status": new_status, "is_completed": new_completed, "updated_at": now_iso}}
    )
    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_doc(updated_doc)


@router.post("/{todo_id}/images", response_model=TodoResponse)
async def upload_todo_images(
    todo_id: str,
    images: List[UploadFile] = File(...),
    current_user: dict = Depends(admin_or_user)
):
    """
    Upload one or more image attachments for an existing To-Do task.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    valid_files = [f for f in images if f.filename]
    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid image files provided")

    new_urls = save_upload_images(valid_files)
    existing_urls = doc.get("image_urls", [])
    updated_urls = existing_urls + new_urls

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.user_todos.update_one(
        {"_id": oid},
        {"$set": {"image_urls": updated_urls, "updated_at": now_iso}}
    )

    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_doc(updated_doc)


@router.delete("/{todo_id}/images", response_model=TodoResponse)
async def delete_todo_image(
    todo_id: str,
    image_url: str = Query(..., description="The relative image URL to remove"),
    current_user: dict = Depends(admin_or_user)
):
    """
    Remove an image attachment from a To-Do task.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    existing_urls = doc.get("image_urls", [])
    if image_url not in existing_urls:
        raise HTTPException(status_code=404, detail="Specified image_url not found in task")

    existing_urls.remove(image_url)

    # Attempt to delete file from disk if local
    local_path = os.path.join("app", "static", image_url.replace("/", os.sep))
    if os.path.exists(local_path):
        try:
            os.remove(local_path)
        except Exception:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.user_todos.update_one(
        {"_id": oid},
        {"$set": {"image_urls": existing_urls, "updated_at": now_iso}}
    )

    updated_doc = await db.user_todos.find_one({"_id": oid})
    return format_todo_doc(updated_doc)


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    current_user: dict = Depends(admin_or_user)
):
    """
    Delete a To-Do item permanently along with any associated local upload images.
    """
    try:
        oid = ObjectId(todo_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid to-do ID format")

    doc = await db.user_todos.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="To-do item not found")

    # Clean up associated uploaded images
    for img_url in doc.get("image_urls", []):
        local_path = os.path.join("app", "static", img_url.replace("/", os.sep))
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    await db.user_todos.delete_one({"_id": oid})
    return {"status": "success", "message": f"To-do item '{todo_id}' deleted successfully"}
