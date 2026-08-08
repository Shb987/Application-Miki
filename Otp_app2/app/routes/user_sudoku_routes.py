from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.core.database import db
from app.utils.user_auth import get_current_user
from app.services.sudoku_service import get_level_config, SudokuGenerator
import uuid
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter()

class SudokuSubmit(BaseModel):
    current_board: List[List[int]]
    time_spent_seconds: int
    is_completed: bool

@router.get("/levels")
async def get_levels(current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    cursor = db.sudoku_progress.find({"user_id": user_id})
    progress = await cursor.to_list(length=None)
    
    progress_map = {p["level"]: p for p in progress}
    
    highest_completed = 0
    for lvl in progress_map.values():
        if lvl.get("is_completed", False):
            if lvl["level"] > highest_completed:
                highest_completed = lvl["level"]
                
    levels = []
    for i in range(1, 51):
        config = get_level_config(i)
        is_unlocked = i <= highest_completed + 1
        
        if i == 1:
            is_unlocked = True
            
        lvl_progress = progress_map.get(i, {})
        
        levels.append({
            "id": str(lvl_progress.get("_id", uuid.uuid4())),
            "level": i,
            "grid_size": config["grid_size"],
            "block_rows": config["block_rows"],
            "block_cols": config["block_cols"],
            "difficulty": config["difficulty"],
            "is_unlocked": is_unlocked,
            "is_completed": lvl_progress.get("is_completed", False),
            "stars": lvl_progress.get("stars", 0)
        })
        
    return {"levels": levels}

@router.get("/play/{level}")
async def play_sudoku(level: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    config = get_level_config(level)
    
    if not config:
        raise HTTPException(status_code=404, detail="Level not found")
        
    progress = await db.sudoku_progress.find_one({"user_id": user_id, "level": level})
    
    if progress:
        return {
            "level": level,
            "config": config,
            "original_board": progress["original_board"],
            "current_board": progress["current_board"],
            "solution_board": progress["solution_board"],
            "is_completed": progress["is_completed"],
            "time_spent_seconds": progress.get("time_spent_seconds", 0)
        }
        
    generator = SudokuGenerator(config["grid_size"], config["block_rows"], config["block_cols"])
    puzzle, solution = generator.generate(config["difficulty"])
    
    new_progress = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "level": level,
        "original_board": puzzle,
        "current_board": puzzle,
        "solution_board": solution,
        "is_completed": False,
        "stars": 0,
        "time_spent_seconds": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    await db.sudoku_progress.insert_one(new_progress)
    
    return {
        "level": level,
        "config": config,
        "original_board": puzzle,
        "current_board": puzzle,
        "solution_board": solution,
        "is_completed": False,
        "time_spent_seconds": 0
    }

@router.post("/submit/{level}")
async def submit_sudoku(
    level: int, 
    data: SudokuSubmit,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    progress = await db.sudoku_progress.find_one({"user_id": user_id, "level": level})
    
    if not progress:
        raise HTTPException(status_code=404, detail="Progress not found for this level")
        
    if progress.get("is_completed") and data.is_completed:
        return {"message": "Level already completed", "stars": progress.get("stars", 0)}
        
    stars = progress.get("stars", 0)
    if data.is_completed:
        if data.current_board == progress["solution_board"]:
            if data.time_spent_seconds < 120:
                stars = 3
            elif data.time_spent_seconds < 300:
                stars = 2
            else:
                stars = 1
        else:
            raise HTTPException(status_code=400, detail="Board is incorrect or incomplete")
            
    await db.sudoku_progress.update_one(
        {"_id": progress["_id"]},
        {"$set": {
            "current_board": data.current_board,
            "time_spent_seconds": data.time_spent_seconds,
            "is_completed": data.is_completed or progress.get("is_completed", False),
            "stars": max(stars, progress.get("stars", 0)),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "message": "Progress saved successfully",
        "is_completed": data.is_completed,
        "stars": stars
    }
