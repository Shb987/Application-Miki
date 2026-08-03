from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends
from typing import Optional
from bson import ObjectId
import os
import json
from datetime import datetime, timezone

# Local imports
from app.core.database import db
from app.utils.admin_auth import (
    verify_password,
    create_access_token,
    get_password_hash,
    get_current_admin,
    require_permission,
)
from app.models.admin_models import AdminLogin, AdminCreate, AdminUpdate
from app.models.question_models import Question

# Router setup
router = APIRouter(tags=["Admin"])

# Upload directory
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def log_admin_activity(username: str, role: str, action: str, details: str, status: str = "success"):
    await db.admin_activity_logs.insert_one({
        "username": username,
        "role": role,
        "action": action,
        "status": status,
        "details": details,
        "timestamp": datetime.now(timezone.utc),
    })


# ✅ Register new admin
@router.post("/register")
async def register_admin(
    admin: AdminCreate,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        # Only superadmins can create new admins, or we let the first superadmin be created manually.
        # For now, require superadmin to create others.
        if current_admin.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Only superadmins can create admins")

        existing = await db.admins.find_one({"username": admin.username})
        if existing:
            raise HTTPException(status_code=400, detail="Admin already exists")

        hashed_pw = get_password_hash(admin.password)
        admin_dict = admin.model_dump()
        admin_dict["password"] = hashed_pw
        await db.admins.insert_one(admin_dict)
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_admin",
            f"Created admin staff account '{admin.username}' with role '{admin.role_name}'",
        )
        return {"message": "Admin registered successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_admin",
            f"Failed to create admin staff account '{admin.username}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_admin",
            f"Failed to create admin staff account '{admin.username}': {exc}",
            status="failed",
        )
        raise


# ✅ Login
@router.post("/login")
async def login(admin: AdminLogin):
    record = await db.admins.find_one({"username": admin.username})
    if not record or not verify_password(admin.password, record["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": record["username"], "role": record.get("role_name", "superadmin")})
    return {"access_token": token, "token_type": "bearer"}


# ✅ Get admin details
@router.get("/get_details")
async def get_admin_me(current_admin: dict = Depends(get_current_admin)):
    username = current_admin["sub"]
    role_name = current_admin["role"]
    
    # Defaults
    permissions = {}
    is_superadmin = False
    
    if role_name == "superadmin":
        is_superadmin = True
    else:
        role_doc = await db.roles.find_one({"role_name": role_name})
        if role_doc:
            permissions = role_doc.get("permissions", {})
            
    return {
        "username": username,
        "role": role_name,
        "is_superadmin": is_superadmin,
        "permissions": permissions
    }


# ✅ List all admins
@router.get("/admins")
async def list_admins(current_admin: dict = Depends(get_current_admin)):
    if current_admin.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmins can view admin list")
    
    cursor = db.admins.find({}, {"password": 0})
    admins = await cursor.to_list(length=100)
    for a in admins:
        a["_id"] = str(a["_id"])
        # Fallback for older admin accounts created before RBAC
        if not a.get("role_name"):
            a["role_name"] = "superadmin"
    return admins


@router.put("/admins/{username}")
async def update_admin(
    username: str,
    admin_update: AdminUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    try:
        if current_admin.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Only superadmins can edit admins")

        existing = await db.admins.find_one({"username": username})
        if not existing:
            raise HTTPException(status_code=404, detail="Admin user not found")

        update_data = admin_update.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")

        new_username = update_data.get("username")
        if new_username is not None:
            new_username = new_username.strip()
            if not new_username:
                raise HTTPException(status_code=400, detail="Username cannot be empty")
            update_data["username"] = new_username

        if new_username and new_username != username:
            username_conflict = await db.admins.find_one({"username": new_username})
            if username_conflict:
                raise HTTPException(status_code=400, detail="Username already exists")

        if "password" in update_data:
            update_data["password"] = get_password_hash(update_data["password"])

        await db.admins.update_one({"username": username}, {"$set": update_data})
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_admin",
            f"Updated admin staff account '{username}'" + (f" to '{new_username}'" if new_username and new_username != username else ""),
        )
        return {"message": "Admin updated successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_admin",
            f"Failed to update admin staff account '{username}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_admin",
            f"Failed to update admin staff account '{username}': {exc}",
            status="failed",
        )
        raise


# ✅ Delete an admin
@router.delete("/admins/{username}")
async def delete_admin(username: str, current_admin: dict = Depends(get_current_admin)):
    try:
        if current_admin.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Only superadmins can delete admins")

        if username == current_admin["sub"]:
            raise HTTPException(status_code=400, detail="You cannot delete yourself")

        result = await db.admins.delete_one({"username": username})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Admin user not found")

        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_admin",
            f"Deleted admin staff account '{username}'",
        )
        return {"message": "Admin deleted successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_admin",
            f"Failed to delete admin staff account '{username}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_admin",
            f"Failed to delete admin staff account '{username}': {exc}",
            status="failed",
        )
        raise


# ✅ Create Question (supports text & image-based MCQs)
@router.post("/questions")
async def create_question(
    category: str = Form(...),
    text: str = Form(...),
    type: Optional[str] = Form("text"),
    options: Optional[str] = Form(None),
    correct_answer: Optional[str] = Form(None),
    correct_index: Optional[int] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    option1: UploadFile | None = File(None),
    option2: UploadFile | None = File(None),
    option3: UploadFile | None = File(None),
    option4: UploadFile | None = File(None),
    current_admin: dict = Depends(require_permission("Questions Base", "create"))  # 🔐 Protection added
):
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        image_files = [option1, option2, option3, option4]
        is_image_question = type == "image" or any(file for file in image_files)
        image_options = []

        # 🖼️ IMAGE QUESTION
        if is_image_question:
            for file in image_files:
                if file:
                    filename = f"{ObjectId()}_{file.filename}"
                    file_path = os.path.join(UPLOAD_DIR, filename)
                    with open(file_path, "wb") as buffer:
                        buffer.write(await file.read())
                    image_options.append(f"/uploads/{filename}")
                else:
                    image_options.append(None)

            if correct_index is None:
                raise HTTPException(status_code=400, detail="Missing correct_index for image question")

            question_data = Question(
                category=category,
                text=text,
                type="image",
                image_options=image_options,
                correct_index=correct_index,
                age_min=age_min,
                age_max=age_max,
            )

        # ⭐ RATING-TYPE QUESTION
        elif type == "rating":
            if options or any(file for file in image_files):
                raise HTTPException(status_code=400, detail="Rating questions should not include options or images")

            question_data = Question(
                category=category,
                text=text,
                type="rating",
                age_min=age_min,
                age_max=age_max,
            )

        # 📝 TEXT QUESTION
        else:
            if not options:
                raise HTTPException(status_code=400, detail="Missing options for text question")

            try:
                options_list = json.loads(options)
                if not isinstance(options_list, list):
                    raise ValueError
            except:
                raise HTTPException(status_code=400, detail="Options must be a valid JSON list")

            question_data = Question(
                category=category,
                text=text,
                type="text",
                options=options_list,
                correct_index=int(correct_answer) - 1,
                age_min=age_min,
                age_max=age_max,
            )

        result = await db.questions.insert_one(question_data.dict())

        # Log activity
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_question",
            f"Created question in category '{category}' of type '{question_data.type}'",
        )

        return {
            "message": "Question added successfully",
            "id": str(result.inserted_id),
            "type": question_data.type,
        }
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_question",
            f"Failed to create question in category '{category}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "create_question",
            f"Failed to create question in category '{category}': {exc}",
            status="failed",
        )
        raise



# ✅ Update Question (supports text & image-based MCQs)
@router.put("/questions/{question_id}")
async def update_question(
    question_id: str,
    category: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    options: Optional[str] = Form(None),
    correct_answer: Optional[str] = Form(None),
    correct_index: Optional[int] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    option1: UploadFile | None = File(None),
    option2: UploadFile | None = File(None),
    option3: UploadFile | None = File(None),
    option4: UploadFile | None = File(None),
    current_admin: dict = Depends(require_permission("Questions Base", "update")),
):
    """Update a question (text or image-based)"""
    try:
        existing = await db.questions.find_one({"_id": ObjectId(question_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Question not found")

        update_data = {}

        if text:
            update_data["text"] = text
        if category:
            update_data["category"] = category
        if age_min is not None:
            update_data["age_min"] = age_min
        if age_max is not None:
            update_data["age_max"] = age_max

        # 🧠 If new image files are uploaded, replace old image options
        image_files = [option1, option2, option3, option4]
        if any(image_files):
            image_options = []
            for file in image_files:
                if file:
                    filename = f"{ObjectId()}_{file.filename}"
                    file_path = os.path.join(UPLOAD_DIR, filename)
                    with open(file_path, "wb") as buffer:
                        buffer.write(await file.read())
                    image_options.append(f"/uploads/{filename}")
                else:
                    image_options.append(None)
            update_data["image_options"] = image_options
            if correct_index is not None:
                update_data["correct_index"] = correct_index

        # 📝 Otherwise, allow text updates
        elif options:
            try:
                options_list = json.loads(options)
                update_data["options"] = options_list
            except:
                pass
            if correct_answer:
                update_data["correct_answer"] = correct_answer

        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")

        await db.questions.update_one({"_id": ObjectId(question_id)}, {"$set": update_data})
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_question",
            f"Updated question '{question_id}' in category '{update_data.get('category', existing.get('category', 'Unknown'))}'",
        )
        return {"message": "Question updated successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_question",
            f"Failed to update question '{question_id}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "update_question",
            f"Failed to update question '{question_id}': {exc}",
            status="failed",
        )
        raise

# ✅ Delete Question (also removes uploaded image files)
@router.delete("/questions/{question_id}")
async def delete_question(
    question_id: str,
    current_admin: dict = Depends(require_permission("Questions Base", "delete")),
):
    try:
        existing = await db.questions.find_one({"_id": ObjectId(question_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Question not found")

        # 🧹 Delete associated image files if exist
        if "image_options" in existing and existing["image_options"]:
            for path in existing["image_options"]:
                if not path:
                    continue
                # Resolve disk path relative to static mount
                filename = os.path.basename(path)
                disk_path = os.path.join(UPLOAD_DIR, filename)
                if os.path.exists(disk_path):
                    os.remove(disk_path)

        await db.questions.delete_one({"_id": ObjectId(question_id)})
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_question",
            f"Deleted question '{question_id}' from category '{existing.get('category', 'Unknown')}'",
        )
        return {"message": "Question deleted successfully"}
    except HTTPException as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_question",
            f"Failed to delete question '{question_id}': {exc.detail}",
            status="failed",
        )
        raise
    except Exception as exc:
        await log_admin_activity(
            current_admin["sub"],
            current_admin["role"],
            "delete_question",
            f"Failed to delete question '{question_id}': {exc}",
            status="failed",
        )
        raise

