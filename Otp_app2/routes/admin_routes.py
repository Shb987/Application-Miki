from fastapi import APIRouter, Depends, HTTPException
from models.admin_models import AdminLogin
from core.database import db
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from utils.auth import verify_password, create_access_token, get_password_hash,get_current_admin
from models.question_models import Question
from bson import ObjectId

router = APIRouter(tags=["Admin"])

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

# ✅ Create Question
@router.post("/questions")
async def create_question(question: Question, current_admin: dict = Depends(get_current_admin)):
    print("Received Question:", question.dict())  # 👈 debug
    new_q = question.dict()
    result = await db.questions.insert_one(new_q)
    return {"message": "Question added", "id": str(result.inserted_id)}


# ✅ Get All Questions
@router.post("/questions")
async def create_question(question: Question):  # removed current_admin
    print("Received Question:", question.dict())
    new_q = question.dict()
    result = await db.questions.insert_one(new_q)
    return {"message": "Question added", "id": str(result.inserted_id)}

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