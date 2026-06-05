from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db
from typing import Dict, Any, List

class PuzzleService:
    @staticmethod
    def get_difficulty(std: int) -> str:
        """Map student class to puzzle difficulty"""
        if 1 <= std <= 6:
            return "Beginner"
        elif 7 <= std <= 10:
            return "Intermediate"
        elif 11 <= std <= 12:
            return "Advanced"
        return "Beginner"  # Default

    @staticmethod
    async def get_available_levels(student_id: str) -> Dict[str, Any]:
        """Get list of all puzzle levels with their status for a student"""
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student:
                return {"error": "Student not found"}
            
            std_class = int(student.get("student_class", 1))
            difficulty = PuzzleService.get_difficulty(std_class)
            
            # Fetch progress
            progress = await db.puzzle_progress.find_one({
                "student_id": student_id, 
                "difficulty": difficulty
            })
            highest_level = progress.get("highest_level", 1) if progress else 1
            
            # Get total levels available for this difficulty
            total_levels_count = await db.puzzle_levels.count_documents({"difficulty": difficulty})
            # Ensure at least 1 level is shown if none exist yet to avoid completely empty UI
            if total_levels_count == 0:
                total_levels_count = 0
            
            levels = []
            for i in range(1, total_levels_count + 1):
                if i < highest_level:
                    status, playable = "completed", True
                elif i == highest_level:
                    status, playable = "unlocked", True
                else:
                    status, playable = "locked", False
                
                levels.append({
                    "level": i,
                    "status": status,
                    "playable": playable
                })
                
            return {
                "student_id": student_id,
                "difficulty": difficulty,
                "highest_level_reached": highest_level,
                "total_levels": total_levels_count,
                "levels": levels
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def start_game(student_id: str, level: int) -> Dict[str, Any]:
        """Fetch the puzzle configuration for a specific level"""
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student:
                return {"error": "Student not found"}
                
            std_class = int(student.get("student_class", 1))
            difficulty = PuzzleService.get_difficulty(std_class)
            
            # Verify level is unlocked
            progress = await db.puzzle_progress.find_one({
                "student_id": student_id, 
                "difficulty": difficulty
            })
            highest_level = progress.get("highest_level", 1) if progress else 1
            
            if level > highest_level:
                return {"error": f"Level {level} is locked. Highest level reached is {highest_level}."}
            
            # Fetch level config
            puzzle_level = await db.puzzle_levels.find_one({
                "difficulty": difficulty,
                "level": level
            })
            
            if not puzzle_level:
                return {"error": f"Puzzle configuration not found for difficulty '{difficulty}' and level {level}."}
                
            return {
                "level": level,
                "difficulty": difficulty,
                "image_url": puzzle_level.get("image_url", ""),
                "grid_size": puzzle_level.get("grid_size", 3),
                "mode": "practice" if level < highest_level else "progression"
            }
            
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def complete_level(student_id: str, level: int) -> Dict[str, Any]:
        """Mark a puzzle level as completed and unlock the next one"""
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student:
                return {"error": "Student not found"}
                
            std_class = int(student.get("student_class", 1))
            difficulty = PuzzleService.get_difficulty(std_class)
            
            progress = await db.puzzle_progress.find_one({
                "student_id": student_id, 
                "difficulty": difficulty
            })
            highest_level = progress.get("highest_level", 1) if progress else 1
            
            next_unlocked = False
            # Only increment highest_level if they are playing their current highest progression level
            if level == highest_level:
                total_levels_count = await db.puzzle_levels.count_documents({"difficulty": difficulty})
                
                # Check if there's a next level to unlock
                if highest_level < total_levels_count:
                    highest_level += 1
                    next_unlocked = True
                
                await db.puzzle_progress.update_one(
                    {"student_id": student_id, "difficulty": difficulty},
                    {
                        "$set": {
                            "highest_level": highest_level,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            
            return {
                "status": "success",
                "message": f"Level {level} completed successfully!",
                "next_level_unlocked": next_unlocked,
                "highest_level_reached": highest_level
            }
            
        except Exception as e:
            return {"error": str(e)}
