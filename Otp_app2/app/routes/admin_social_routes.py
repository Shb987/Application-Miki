from fastapi import APIRouter, HTTPException, Depends
from app.core.database import db
from app.models.social_models import ContributorCreate, ContributorInDB
from app.utils.admin_auth import get_password_hash, require_permission
router = APIRouter()

@router.post("/contributors/register", response_model=ContributorInDB)
async def register_contributor(contributor: ContributorCreate, current_admin: dict = Depends(require_permission("Social Content & Contributors", "create"))):
    # Check if username exists
    existing = await db.contributors.find_one({"username": contributor.username})
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    contributor_db = ContributorInDB(
        **contributor.model_dump(exclude={"password"}),
        password=get_password_hash(contributor.password)
    )
    
    # We let Mongo handle the _id generation
    contributor_dict = contributor_db.model_dump()
    
    result = await db.contributors.insert_one(contributor_dict)
    contributor_dict["_id"] = str(result.inserted_id)
    return contributor_dict

@router.get("/contributors")
async def list_contributors(current_admin: dict = Depends(require_permission("Social Content & Contributors", "read"))):
    cursor = db.contributors.find()
    contributors = await cursor.to_list(length=100)
    # Ensure _id is present
    for c in contributors:
        if "_id" in c:
            c["_id"] = str(c["_id"])
    return contributors

@router.get("/content")
async def list_all_content(current_admin: dict = Depends(require_permission("Social Content & Contributors", "read"))):
    # We fetch content and join it with contributor info to show author name
    cursor = db.social_content.find().sort("created_at", -1)
    contents = await cursor.to_list(length=200)
    
    # Optional: fetch contributor names for each content piece
    contributor_ids = list(set([c["contributor_id"] for c in contents if "contributor_id" in c]))
    contributors = await db.contributors.find({"_id": {"$in": contributor_ids}}).to_list(length=None)
    contributor_map = {c["_id"]: c["name"] for c in contributors}
    
    for c in contents:
        c["contributor_name"] = contributor_map.get(c.get("contributor_id"), "Unknown")
        
    return contents
