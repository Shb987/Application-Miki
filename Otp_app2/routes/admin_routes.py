from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends
from typing import Optional
from bson import ObjectId
import os
import json

# Local imports
from core.database import db
from utils.admin_auth import (
    verify_password,
    create_access_token,
    get_password_hash,
    get_current_admin,
)
from models.admin_models import AdminLogin
from models.question_models import Question

# Router setup
router = APIRouter(tags=["Admin"])

# Upload directory
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ✅ Register new admin
@router.post("/register")
async def register_admin(
    admin: AdminLogin
):
    existing = await db.admins.find_one({"username": admin.username})
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")

    hashed_pw = get_password_hash(admin.password)
    await db.admins.insert_one({"username": admin.username, "password": hashed_pw})
    return {"message": "Admin registered successfully"}


# ✅ Login
@router.post("/login")
async def login(admin: AdminLogin):
    record = await db.admins.find_one({"username": admin.username})
    if not record or not verify_password(admin.password, record["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": record["username"], "role": "admin"})
    return {"access_token": token, "token_type": "bearer"}


# ✅ Get admin details
@router.get("/get_details")
async def get_admin_me(current_admin: dict = Depends(get_current_admin)):
    return {"username": current_admin["sub"]}


# ✅ Create Question (supports text & image-based MCQs)

# ✅ Create Question (PROTECTED NOW)
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
    current_admin: dict = Depends(get_current_admin)  # 🔐 Protection added
):
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

    return {
        "message": "Question added successfully",
        "id": str(result.inserted_id),
        "type": question_data.type,
    }



# ✅ Update Question
# ✅ Flexible update endpoint for both text & image MCQs
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
    current_admin: dict = Depends(get_current_admin),
):
    """Update a question (text or image-based)"""
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
                image_options.append(file_path)
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
    return {"message": "Question updated successfully"}

# ✅ Delete Question
# ✅ Delete Question (also removes uploaded image files)
@router.delete("/questions/{question_id}")
async def delete_question(
    question_id: str,
    current_admin: dict = Depends(get_current_admin),
):
    existing = await db.questions.find_one({"_id": ObjectId(question_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    # 🧹 Delete associated image files if exist
    if "image_options" in existing and existing["image_options"]:
        for path in existing["image_options"]:
            if path and os.path.exists(path):
                os.remove(path)

    await db.questions.delete_one({"_id": ObjectId(question_id)})
    return {"message": "Question deleted successfully"}

