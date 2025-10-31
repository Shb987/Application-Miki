from fastapi import APIRouter, Form, File, UploadFile, HTTPException,Depends
from models.admin_models import AdminLogin
from core.database import db
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from utils.auth import verify_password, create_access_token, get_password_hash,get_current_admin
from models.question_models import Question
from bson import ObjectId
import os, json
from typing import List, Optional



router = APIRouter(tags=["Admin"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ✅ Register new admin (for testing, later can restrict)
@router.post("/register")
async def register_admin(admin: AdminLogin):
    existing = await db.admins.find_one({"username": admin.username})
    if existing:
        raise HTTPException(status_code=400, detail="Admin already exists")

    hashed_pw = get_password_hash(admin.password)
    await db.admins.insert_one({"username": admin.username, "password": hashed_pw})
    return {"message": "Admin registered"}

# ✅ Login
@router.post("/login")
async def login(admin: AdminLogin):
    record = await db.admins.find_one({"username": admin.username})
    if not record:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(admin.password, record["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": record["username"], "role": "admin"})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/get_details")
async def get_admin_me(current_admin: dict = Depends(get_current_admin)):
    return {"username": current_admin["sub"]}

# # ✅ Create Question
# @router.post("/create-questions")
# async def create_question(question: Question, current_admin: dict = Depends(get_current_admin)):
#     print("Received Question:", question.dict())  # 👈 debug
#     new_q = question.dict()
#     result = await db.questions.insert_one(new_q)
#     return {"message": "Question added", "id": str(result.inserted_id)}


# ✅ Get All Questions
@router.post("/questions")
async def create_question(
    category: str = Form(...),
    text: str = Form(...),
    # optional fields for normal MCQs
    options: Optional[str] = Form(None),   # send as JSON string if using form-data
    correct_answer: Optional[str] = Form(None),
    # optional fields for image-based MCQs
    correct_index: Optional[int] = Form(None),
    age_min: Optional[int] = Form(None),
    age_max: Optional[int] = Form(None),
    option1: UploadFile | None = File(None),
    option2: UploadFile | None = File(None),
    option3: UploadFile | None = File(None),
    option4: UploadFile | None = File(None)
):
    image_files = [option1, option2, option3, option4]
    image_options = []

    # Check if any image is uploaded
    is_image_question = any(file is not None for file in image_files)

    if is_image_question:
        # Handle image-based question
        for file in image_files:
            if file:
                filename = f"{ObjectId()}_{file.filename}"
                file_path = os.path.join(UPLOAD_DIR, filename)
                with open(file_path, "wb") as buffer:
                    buffer.write(await file.read())
                image_options.append(file_path)
            else:
                image_options.append(None)

        if correct_index is None:
            raise HTTPException(status_code=400, detail="Missing correct_index for image question")

        question_data = Question(
            category=category,
            text=text,
            image_options=image_options,
            correct_index=correct_index,
            age_min=age_min,
            age_max=age_max
        )

    else:
        # Handle normal text-based question
        if not options:
            raise HTTPException(status_code=400, detail="Missing options for text question")
        try:
            options_list = json.loads(options)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Options must be valid JSON list")

        question_data = Question(
            category=category,
            text=text,
            options=options_list,
            correct_answer=correct_answer,
            age_min=age_min,
            age_max=age_max
        )

    # Save to MongoDB
    result = await db.questions.insert_one(question_data.dict())

    return {
        "message": "Question added successfully",
        "id": str(result.inserted_id),
        "type": "image" if is_image_question else "text"
    }


# ✅ Update Question
@router.put("/questions/{question_id}")
async def update_question(question_id: str, question: Question, current_admin: dict = Depends(get_current_admin)):
    result = await db.questions.update_one(
        {"_id": ObjectId(question_id)},
        {"$set": question.dict()}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Question not found or no changes made")
    return {"message": "Question updated"}

# ✅ Delete Question
@router.delete("/questions/{question_id}")
async def delete_question(question_id: str, current_admin: dict = Depends(get_current_admin)):
    result = await db.questions.delete_one({"_id": ObjectId(question_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Question deleted"}

# # Dynamic admin panel route
# @router.get("/admin-panel", response_class=HTMLResponse)
# async def admin_panel(request: Request):
#     return templates.TemplateResponse("index.html", {"request": request})