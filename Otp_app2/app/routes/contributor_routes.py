from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.core.database import db
from app.models.social_models import SocialContentCreate, SocialContentInDB
from app.utils.admin_auth import verify_password
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
async def list_contributor_content(contributor_id: str):
    cursor = db.social_content.find({"contributor_id": contributor_id})
    contents = await cursor.to_list(length=100)
    for c in contents:
        c["_id"] = str(c["_id"])
    return contents
