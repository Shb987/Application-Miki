from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.core.database import db
from app.models.social_models import SocialContentCreate, SocialContentInDB
from app.utils.admin_auth import verify_password
from bson import ObjectId
router = APIRouter()
templates = Jinja2Templates(directory="app/templates/contributor")

# --- UI ROUTES ---
@router.get("/login-page", response_class=HTMLResponse)
async def contributor_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/dashboard-page", response_class=HTMLResponse)
async def contributor_dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# --- API ROUTES ---
class ContributorLogin(BaseModel):

    username: str
    password: str

@router.post("/login")
async def login(credentials: ContributorLogin):
    contributor = await db.contributors.find_one({"username": credentials.username})
    if not contributor or not verify_password(credentials.password, contributor["password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # In a real app, generate a JWT token here.
    # For now, returning the _id to simulate session token.
    return {"message": "Login successful", "contributor_id": contributor["_id"]}

@router.post("/content", response_model=SocialContentInDB)
async def create_content(content: SocialContentCreate, contributor_id: str):
    # Verify contributor exists
    contributor = await db.contributors.find_one({"_id": contributor_id})
    if not contributor:
        raise HTTPException(status_code=404, detail="Contributor not found")
        
    content_db = SocialContentInDB(
        **content.model_dump(),
        contributor_id=contributor_id
    )
    
    content_dict = content_db.model_dump()
    
    result = await db.social_content.insert_one(content_dict)
    
    # Return the dictionary with the string ID to avoid serialization issues
    content_dict["_id"] = str(result.inserted_id)
    return content_dict

@router.get("/content", response_model=list[SocialContentInDB])
async def list_contributor_content(contributor_id: str, skip: int = 0, limit: int = 20):
    cursor = db.social_content.find({"contributor_id": contributor_id}).sort("created_at", -1).skip(skip).limit(limit)
    contents = await cursor.to_list(length=limit)
    for c in contents:
        c["_id"] = str(c["_id"])
    return contents

@router.put("/content/{content_id}", response_model=SocialContentInDB)
async def update_content(content_id: str, content: SocialContentCreate, contributor_id: str):
    # Verify contributor exists
    contributor = await db.contributors.find_one({"_id": contributor_id})
    if not contributor:
        raise HTTPException(status_code=404, detail="Contributor not found")
        
    try:
        obj_id = ObjectId(content_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid content ID format")

    # Check if content exists and belongs to contributor
    existing = await db.social_content.find_one({"_id": obj_id, "contributor_id": contributor_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Content not found or unauthorized")

    update_data = content.model_dump()
    
    await db.social_content.update_one(
        {"_id": obj_id},
        {"$set": update_data}
    )
    
    updated_content = await db.social_content.find_one({"_id": obj_id})
    updated_content["_id"] = str(updated_content["_id"])
    return updated_content

@router.delete("/content/{content_id}")
async def delete_content(content_id: str, contributor_id: str):
    try:
        obj_id = ObjectId(content_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid content ID format")

    # Verify content belongs to contributor
    existing = await db.social_content.find_one({"_id": obj_id, "contributor_id": contributor_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Content not found or unauthorized")
        
    await db.social_content.delete_one({"_id": obj_id})
    return {"message": "Content deleted successfully"}
