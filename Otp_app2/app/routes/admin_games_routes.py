from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from bson import ObjectId
from datetime import datetime

from app.core.database import db
from app.utils.admin_auth import require_permission

router = APIRouter(tags=["Games - Admin"])

CLASS_RANGES = ["1-3", "3-5", "6-8", "9-10", "11-12"]


def serialize_doc(doc: dict) -> dict:
    if not doc:
        return {}
    doc["id"] = str(doc.pop("_id"))
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat() + "Z"
    return doc


# ══════════════════════════════════════════════
# WORDLE — Word Management
# ══════════════════════════════════════════════

@router.get("/admin-panel/games/wordle/words")
async def list_wordle_words(
    class_range: Optional[str] = Query(None, description="Filter by class range e.g. '6-8'"),
    search: Optional[str] = Query(None, description="Search by word"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(require_permission("Games", "read"))
):
    """List all Wordle questions with optional filters."""
    query: Dict[str, Any] = {}
    if class_range:
        query["class_range"] = class_range
    if search:
        query["word"] = {"$regex": search, "$options": "i"}

    total = await db.wordle_questions.count_documents(query)
    cursor = db.wordle_questions.find(query).sort("level", 1).skip(skip).limit(limit)
    words = await cursor.to_list(length=limit)

    return {
        "status": "success",
        "total": total,
        "data": [serialize_doc(w) for w in words]
    }


@router.post("/admin-panel/games/wordle/words")
async def add_wordle_word(
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(require_permission("Games", "create"))
):
    """
    Add a new Wordle word/level.
    Body: { word, hints, difficulty, level, class_range }
    """
    word = payload.get("word", "").strip().upper()
    hints = payload.get("hints", []) # Expecting a list
    difficulty = payload.get("difficulty", "Easy").strip()
    level = payload.get("level")
    class_range = payload.get("class_range", "").strip()

    if not word or not hints or level is None or not class_range:
        raise HTTPException(status_code=400, detail="word, hints, level, and class_range are required")

    if class_range not in CLASS_RANGES:
        raise HTTPException(status_code=400, detail=f"class_range must be one of {CLASS_RANGES}")

    # Check duplicate word in same class range
    existing = await db.wordle_questions.find_one({"word": word, "class_range": class_range})
    if existing:
        raise HTTPException(status_code=400, detail=f"Word '{word}' already exists in class range '{class_range}'")

    doc = {
        "word": word,
        "hints": [h.strip() for h in hints if h.strip()],
        "difficulty": difficulty,
        "level": int(level),
        "class_range": class_range,
        "created_at": datetime.utcnow(),
        "created_by": current_admin.get("sub", "admin")
    }
    result = await db.wordle_questions.insert_one(doc)

    return {
        "status": "success",
        "message": "Wordle word added successfully",
        "id": str(result.inserted_id)
    }


@router.put("/admin-panel/games/wordle/words/{word_id}")
async def update_wordle_word(
    word_id: str,
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(require_permission("Games", "update"))
):
    """Update an existing Wordle word."""
    try:
        oid = ObjectId(word_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid word_id")

    existing = await db.wordle_questions.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Word not found")

    update_data: Dict[str, Any] = {}
    if "word" in payload and payload["word"]:
        update_data["word"] = payload["word"].strip().upper()
    if "hints" in payload:
        update_data["hints"] = [h.strip() for h in payload["hints"] if h.strip()]
    if "difficulty" in payload:
        update_data["difficulty"] = payload["difficulty"].strip()
    if "level" in payload:
        update_data["level"] = int(payload["level"])
    if "class_range" in payload:
        if payload["class_range"] not in CLASS_RANGES:
            raise HTTPException(status_code=400, detail=f"class_range must be one of {CLASS_RANGES}")
        update_data["class_range"] = payload["class_range"]

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.utcnow()
    await db.wordle_questions.update_one({"_id": oid}, {"$set": update_data})

    return {"status": "success", "message": "Word updated successfully"}


@router.delete("/admin-panel/games/wordle/words/{word_id}")
async def delete_wordle_word(
    word_id: str,
    current_admin: dict = Depends(require_permission("Games", "delete"))
):
    """Delete a Wordle word by ID."""
    try:
        oid = ObjectId(word_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid word_id")

    result = await db.wordle_questions.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Word not found")

    return {"status": "success", "message": "Word deleted successfully"}


@router.get("/admin-panel/games/wordle/stats")
async def get_wordle_stats(current_admin: dict = Depends(require_permission("Games", "read"))):
    """Returns total Wordle words per class range + total sessions."""
    pipeline = [
        {"$group": {"_id": "$class_range", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    by_range = await db.wordle_questions.aggregate(pipeline).to_list(None)
    total_words = await db.wordle_questions.count_documents({})
    total_sessions = await db.wordle_sessions.count_documents({})

    return {
        "status": "success",
        "data": {
            "total_words": total_words,
            "total_sessions": total_sessions,
            "by_class_range": {item["_id"]: item["count"] for item in by_range}
        }
    }


# ══════════════════════════════════════════════
# SQUARES — Level Management
# ══════════════════════════════════════════════

@router.get("/admin-panel/games/squares/levels")
async def list_squares_levels(
    class_range: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(require_permission("Games", "read"))
):
    """List all Squares levels with optional class_range filter."""
    query: Dict[str, Any] = {}
    if class_range:
        query["class_range"] = class_range

    total = await db.squares_questions.count_documents(query)
    cursor = db.squares_questions.find(query).sort("level", 1).skip(skip).limit(limit)
    levels = await cursor.to_list(length=limit)

    result = []
    for lv in levels:
        d = serialize_doc(lv)
        # Add word count for quick overview
        d["word_count"] = len(d.get("words", []))
        result.append(d)

    return {"status": "success", "total": total, "data": result}


@router.post("/admin-panel/games/squares/levels")
async def add_squares_level(
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(require_permission("Games", "create"))
):
    """
    Add a new Squares level.
    Body: { level, class_range, main_words: [...], bonus_words: [...], grid: [[...]], hint }
    """
    level = payload.get("level")
    class_range = payload.get("class_range", "").strip()
    main_words = payload.get("main_words", [])
    bonus_words = payload.get("bonus_words", [])
    grid = payload.get("grid", [])
    hint = payload.get("hint", "").strip()

    if level is None or not class_range or not main_words or not grid:
        raise HTTPException(status_code=400, detail="level, class_range, main_words, and grid are required")

    if class_range not in CLASS_RANGES:
        raise HTTPException(status_code=400, detail=f"class_range must be one of {CLASS_RANGES}")

    existing = await db.squares_questions.find_one({"level": int(level), "class_range": class_range})
    if existing:
        raise HTTPException(status_code=400, detail=f"Level {level} already exists for class range '{class_range}'")

    doc = {
        "level": int(level),
        "class_range": class_range,
        "main_words": [w.strip().upper() for w in main_words if w.strip()],
        "bonus_words": [w.strip().upper() for w in bonus_words if w.strip()],
        "grid": grid,
        "hint": hint,
        "created_at": datetime.utcnow(),
        "created_by": current_admin.get("sub", "admin")
    }
    result = await db.squares_questions.insert_one(doc)

    return {
        "status": "success",
        "message": "Squares level added successfully",
        "id": str(result.inserted_id)
    }


@router.put("/admin-panel/games/squares/levels/{level_id}")
async def update_squares_level(
    level_id: str,
    payload: Dict[str, Any] = Body(...),
    current_admin: dict = Depends(require_permission("Games", "update"))
):
    """Update an existing Squares level."""
    try:
        oid = ObjectId(level_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid level_id")

    existing = await db.squares_questions.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Level not found")

    update_data: Dict[str, Any] = {}
    if "main_words" in payload:
        update_data["main_words"] = [w.strip().upper() for w in payload["main_words"] if w.strip()]
    if "bonus_words" in payload:
        update_data["bonus_words"] = [w.strip().upper() for w in payload["bonus_words"] if w.strip()]
    if "grid" in payload:
        update_data["grid"] = payload["grid"]
    if "level" in payload:
        update_data["level"] = int(payload["level"])
    if "class_range" in payload:
        if payload["class_range"] not in CLASS_RANGES:
            raise HTTPException(status_code=400, detail=f"class_range must be one of {CLASS_RANGES}")
        update_data["class_range"] = payload["class_range"]
    if "hint" in payload:
        update_data["hint"] = payload["hint"].strip()

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.utcnow()
    await db.squares_questions.update_one({"_id": oid}, {"$set": update_data})

    return {"status": "success", "message": "Level updated successfully"}


@router.delete("/admin-panel/games/squares/levels/{level_id}")
async def delete_squares_level(
    level_id: str,
    current_admin: dict = Depends(require_permission("Games", "delete"))
):
    """Delete a Squares level by ID."""
    try:
        oid = ObjectId(level_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid level_id")

    result = await db.squares_questions.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Level not found")

    return {"status": "success", "message": "Level deleted successfully"}


@router.get("/admin-panel/games/squares/stats")
async def get_squares_stats(current_admin: dict = Depends(require_permission("Games", "read"))):
    """Returns total Squares levels per class range + total sessions."""
    pipeline = [
        {"$group": {"_id": "$class_range", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    by_range = await db.squares_questions.aggregate(pipeline).to_list(None)
    total_levels = await db.squares_questions.count_documents({})
    total_sessions = await db.squares_sessions.count_documents({})

    return {
        "status": "success",
        "data": {
            "total_levels": total_levels,
            "total_sessions": total_sessions,
            "by_class_range": {item["_id"]: item["count"] for item in by_range}
        }
    }


# ══════════════════════════════════════════════
# PUZZLE — Level & Image Management
# ══════════════════════════════════════════════

import uuid
import os
from fastapi import UploadFile, File, Form

PUZZLE_DIFFICULTIES = ["Beginner", "Intermediate", "Advanced"]
GRID_SIZE_MAP = {
    "Beginner": 3,
    "Intermediate": 4,
    "Advanced": 5
}

@router.get("/admin-panel/games/puzzle/levels")
async def list_puzzle_levels(
    difficulty: Optional[str] = Query(None, description="Filter by difficulty e.g. 'Beginner'"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_admin: dict = Depends(require_permission("Games", "read"))
):
    """List all Puzzle levels with optional difficulty filter."""
    query: Dict[str, Any] = {}
    if difficulty:
        query["difficulty"] = difficulty.strip().capitalize()

    total = await db.puzzle_levels.count_documents(query)
    cursor = db.puzzle_levels.find(query).sort([("difficulty", 1), ("level", 1)]).skip(skip).limit(limit)
    levels = await cursor.to_list(length=limit)

    return {
        "status": "success",
        "total": total,
        "data": [serialize_doc(lv) for lv in levels]
    }


@router.post("/admin-panel/games/puzzle/levels")
async def add_puzzle_level(
    difficulty: str = Form(...),
    level: int = Form(...),
    title: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    current_admin: dict = Depends(require_permission("Games", "create"))
):
    """
    Add a new Puzzle level with uploaded image file or image URL.
    Saves image under /static/games/puzzle/<Difficulty>/ (Beginner, Intermediate, Advanced)
    Assigns grid_size automatically (Beginner: 3x3, Intermediate: 4x4, Advanced: 5x5).
    """
    diff = difficulty.strip().capitalize()
    if diff not in PUZZLE_DIFFICULTIES:
        raise HTTPException(status_code=400, detail=f"difficulty must be one of {PUZZLE_DIFFICULTIES}")

    # Check duplicate level for same difficulty
    existing = await db.puzzle_levels.find_one({"difficulty": diff, "level": int(level)})
    if existing:
        raise HTTPException(status_code=400, detail=f"Level {level} already exists for difficulty '{diff}'")

    final_image_url = (image_url or "").strip()

    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"
        
        folder_dir = os.path.join("app", "static", "games", "puzzle", diff)
        os.makedirs(folder_dir, exist_ok=True)
        
        file_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(folder_dir, file_name)
        
        content = await image_file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        final_image_url = f"/static/games/puzzle/{diff}/{file_name}"

    if not final_image_url:
        raise HTTPException(status_code=400, detail="Either an image file or an image URL is required")

    grid_size = GRID_SIZE_MAP.get(diff, 3)

    doc = {
        "difficulty": diff,
        "level": int(level),
        "title": title.strip() if title else f"{diff} Level {level}",
        "image_url": final_image_url,
        "grid_size": grid_size,
        "created_at": datetime.utcnow(),
        "created_by": current_admin.get("sub", "admin")
    }
    result = await db.puzzle_levels.insert_one(doc)

    return {
        "status": "success",
        "message": "Puzzle level added successfully",
        "id": str(result.inserted_id)
    }


@router.put("/admin-panel/games/puzzle/levels/{level_id}")
async def update_puzzle_level(
    level_id: str,
    difficulty: Optional[str] = Form(None),
    level: Optional[int] = Form(None),
    title: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    current_admin: dict = Depends(require_permission("Games", "update"))
):
    """Update an existing Puzzle level or replace image."""
    try:
        oid = ObjectId(level_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid level_id")

    existing = await db.puzzle_levels.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Puzzle level not found")

    update_data: Dict[str, Any] = {}

    target_diff = difficulty.strip().capitalize() if difficulty else existing.get("difficulty", "Beginner")
    if target_diff not in PUZZLE_DIFFICULTIES:
        raise HTTPException(status_code=400, detail=f"difficulty must be one of {PUZZLE_DIFFICULTIES}")
        
    update_data["difficulty"] = target_diff
    update_data["grid_size"] = GRID_SIZE_MAP.get(target_diff, 3)

    if level is not None:
        update_data["level"] = int(level)

    if title is not None:
        update_data["title"] = title.strip()

    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"
            
        folder_dir = os.path.join("app", "static", "games", "puzzle", target_diff)
        os.makedirs(folder_dir, exist_ok=True)
        
        file_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(folder_dir, file_name)
        
        content = await image_file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        update_data["image_url"] = f"/static/games/puzzle/{target_diff}/{file_name}"
    elif image_url is not None and image_url.strip():
        update_data["image_url"] = image_url.strip()

    update_data["updated_at"] = datetime.utcnow()
    await db.puzzle_levels.update_one({"_id": oid}, {"$set": update_data})

    return {"status": "success", "message": "Puzzle level updated successfully"}


@router.delete("/admin-panel/games/puzzle/levels/{level_id}")
async def delete_puzzle_level(
    level_id: str,
    current_admin: dict = Depends(require_permission("Games", "delete"))
):
    """Delete a Puzzle level and its local image if stored locally."""
    try:
        oid = ObjectId(level_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid level_id")

    existing = await db.puzzle_levels.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Puzzle level not found")

    # Try removing local image file
    img_url = existing.get("image_url", "")
    if img_url.startswith("/static/games/puzzle/") or img_url.startswith("/games/puzzle/"):
        rel_path = img_url.lstrip("/")
        if rel_path.startswith("static/"):
            local_file = os.path.join("app", rel_path)
        else:
            local_file = os.path.join("app", "static", rel_path)
        if os.path.exists(local_file):
            try:
                os.remove(local_file)
            except Exception:
                pass

    await db.puzzle_levels.delete_one({"_id": oid})
    return {"status": "success", "message": "Puzzle level deleted successfully"}


@router.get("/admin-panel/games/puzzle/stats")
async def get_puzzle_stats(current_admin: dict = Depends(require_permission("Games", "read"))):
    """Returns total Puzzle levels per difficulty + total student progress records."""
    pipeline = [
        {"$group": {"_id": "$difficulty", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    by_diff = await db.puzzle_levels.aggregate(pipeline).to_list(None)
    total_levels = await db.puzzle_levels.count_documents({})
    total_progress_records = await db.puzzle_progress.count_documents({})

    return {
        "status": "success",
        "data": {
            "total_levels": total_levels,
            "total_progress_records": total_progress_records,
            "by_difficulty": {item["_id"]: item["count"] for item in by_diff}
        }
    }
