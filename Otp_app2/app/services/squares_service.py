import random
from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db
from typing import Dict, Any, List, Optional
from app.models.squares_models import SquaresLevelsResponse, SquaresSessionResponse, SquaresWordResponse

class SquaresService:
    @staticmethod
    def get_class_range(std: int) -> str:
        if 1 <= std <= 3: return "1-3"
        elif 4 <= std <= 5: return "4-5"
        elif 6 <= std <= 8: return "6-8"
        elif 9 <= std <= 10: return "9-10"
        elif 11 <= std <= 12: return "11-12"
        return "6-8" # Default

    @staticmethod
    async def get_available_levels(student_id: str) -> Dict[str, Any]:
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student: return {"error": "Student not found"}
            
            std_class = int(student.get("student_class", 8))
            class_range = SquaresService.get_class_range(std_class)
            
            # Find progress
            progress = await db.squares_progress.find_one({"student_id": student_id, "class_range": class_range})
            highest_level = progress.get("highest_level", 1) if progress else 1
            
            # Map total levels
            level_config = {"1-3": 20, "4-5": 30, "6-8": 50, "9-10": 50, "11-12": 50}
            total_levels = level_config.get(class_range, 50)
            
            levels = []
            for i in range(1, total_levels + 1):
                if i < highest_level:
                    status, playable = "completed", True
                elif i == highest_level:
                    status, playable = "unlocked", True
                else:
                    status, playable = "locked", False
                levels.append({"level": i, "status": status, "playable": playable})
                
            return {
                "student_id": student_id,
                "class_range": class_range,
                "highest_level_reached": highest_level,
                "total_levels": total_levels,
                "levels": levels
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def start_game(student_id: str, level: int) -> Dict[str, Any]:
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student: return {"error": "Student not found"}
            
            std_class = int(student.get("student_class", 8))
            class_range = SquaresService.get_class_range(std_class)
            
            # Verify if level is unlocked
            progress = await db.squares_progress.find_one({"student_id": student_id, "class_range": class_range})
            highest_level = progress.get("highest_level", 1) if progress else 1
            
            if level > highest_level:
                return {"error": "Level locked"}
            
            # Fetch puzzle
            puzzle = await db.squares_questions.find_one({"class_range": class_range, "level": level})
            if not puzzle:
                return {"error": "Puzzle level not found"}
            
            # Create/Update session
            active_session = {
                "student_id": student_id,
                "class_range": class_range,
                "level": level,
                "grid": puzzle["grid"],
                "main_words": puzzle["main_words"],
                "bonus_words": puzzle.get("bonus_words", []),
                "found_words": [],
                "found_bonus_words": [],
                "status": "playing",
                "mode": "practice" if level < highest_level else "progression",
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Delete any old playing session for this student
            await db.squares_sessions.delete_many({"student_id": student_id, "status": "playing"})
            result = await db.squares_sessions.insert_one(active_session)
            
            return {
                "session_id": str(result.inserted_id),
                "level": level,
                "class_range": class_range,
                "grid": puzzle["grid"],
                "found_words": [],
                "found_bonus_words": [],
                "main_words_count": len(puzzle["main_words"]),
                "bonus_words_count": len(puzzle.get("bonus_words", [])),
                "status": "playing",
                "mode": active_session["mode"]
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def process_word(session_id: str, word: str) -> Dict[str, Any]:
        try:
            s_oid = ObjectId(session_id)
            session = await db.squares_sessions.find_one({"_id": s_oid})
            if not session: return {"error": "Session not found"}
            if session["status"] != "playing": return {"error": "Game already finished"}
            
            word = word.upper().strip()
            if len(word) < 4:
                return {"error": "Word must be at least 4 letters"}
            
            main_words = [w.upper() for w in session["main_words"]]
            bonus_words = [w.upper() for w in session["bonus_words"]]
            found_words = session["found_words"]
            found_bonus_words = session["found_bonus_words"]
            
            is_valid = False
            is_main = False
            is_bonus = False
            is_new = False
            message = "Word not found in this grid."
            
            if word in main_words:
                is_valid = True
                is_main = True
                if word not in found_words:
                    is_new = True
                    found_words.append(word)
                    message = "Great! You found a main word!"
                else:
                    message = "You already found this word."
            elif word in bonus_words:
                is_valid = True
                is_bonus = True
                if word not in found_bonus_words:
                    is_new = True
                    found_bonus_words.append(word)
                    message = "Awesome! You found a bonus word!"
                else:
                    message = "You already found this bonus word."
            
            # Update session
            status = "playing"
            if len(found_words) == len(main_words):
                status = "level_cleared"
                message = "Congratulations! Level Cleared!"
            
            await db.squares_sessions.update_one(
                {"_id": s_oid},
                {
                    "$set": {
                        "found_words": found_words,
                        "found_bonus_words": found_bonus_words,
                        "status": "completed" if status == "level_cleared" else "playing",
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )
            
            # Progression logic
            next_unlocked = False
            if status == "level_cleared" and session["mode"] == "progression":
                current_level = session["level"]
                class_range = session["class_range"]
                student_id = session["student_id"]
                
                # Increment highest level
                await db.squares_progress.update_one(
                    {"student_id": student_id, "class_range": class_range},
                    {"$set": {"highest_level": current_level + 1}},
                    upsert=True
                )
                next_unlocked = True

            return {
                "is_valid": is_valid,
                "is_main": is_main,
                "is_bonus": is_bonus,
                "is_new": is_new,
                "message": message,
                "found_words": found_words,
                "found_bonus_words": found_bonus_words,
                "main_words_remaining": len(main_words) - len(found_words),
                "status": status,
                "level": session["level"],
                "next_level_unlocked": next_unlocked
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_status(student_id: str) -> Dict[str, Any]:
        try:
            session = await db.squares_sessions.find_one(
                {"student_id": student_id, "status": "playing"},
                sort=[("updated_at", -1)]
            )
            if session:
                return {
                    "session_id": str(session["_id"]),
                    "level": session["level"],
                    "class_range": session["class_range"],
                    "grid": session["grid"],
                    "found_words": session["found_words"],
                    "found_bonus_words": session["found_bonus_words"],
                    "main_words_count": len(session["main_words"]),
                    "bonus_words_count": len(session["bonus_words"]),
                    "status": "playing",
                    "mode": session["mode"]
                }
            return {"status": "idle"}
        except Exception as e:
            return {"error": str(e)}
