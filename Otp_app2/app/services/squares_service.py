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
    def _parse_class(val: Any) -> int:
        try:
            if not val: return 8
            import re
            m = re.search(r'\d+', str(val))
            if m: return int(m.group())
            return 8
        except Exception:
            return 8

    @staticmethod
    async def get_available_levels(student_id: str) -> Dict[str, Any]:
        try:
            student = await db.students.find_one({"_id": ObjectId(student_id)})
            if not student: return {"error": "Student not found"}
            
            std_class = SquaresService._parse_class(student.get("student_class"))
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
            
            std_class = SquaresService._parse_class(student.get("student_class"))
            print("Parsed class for squares:", std_class)
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
                "hint": puzzle.get("hint"),
                "grid": puzzle["grid"],
                "found_words": [],
                "found_bonus_words": [],
                "main_words": puzzle["main_words"],
                "bonus_words": puzzle.get("bonus_words", []),
                "main_words_count": len(puzzle["main_words"]),
                "bonus_words_count": len(puzzle.get("bonus_words", [])),
                "status": "playing",
                "mode": active_session["mode"]
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def process_words(session_id: str, words_list: List[str]) -> Dict[str, Any]:
        try:
            s_oid = ObjectId(session_id)
            session = await db.squares_sessions.find_one({"_id": s_oid})
            if not session: return {"error": "Session not found"}
            if session["status"] != "playing": return {"error": "Game already finished"}
            
            # Clean words
            input_words = [w.strip().upper() for w in words_list if w.strip()]
            if not input_words:
                return {"error": "No words provided"}
            
            main_words = [w.upper() for w in session["main_words"]]
            bonus_words = [w.upper() for w in session["bonus_words"]]
            found_words = list(session["found_words"])
            found_bonus_words = list(session["found_bonus_words"])
            
            any_valid = False
            any_new = False
            new_main_count = 0
            new_bonus_count = 0
            
            for word in input_words:
                if len(word) < 4:
                    continue
                
                if word in main_words:
                    any_valid = True
                    if word not in found_words:
                        any_new = True
                        new_main_count += 1
                        found_words.append(word)
                elif word in bonus_words:
                    any_valid = True
                    if word not in found_bonus_words:
                        any_new = True
                        new_bonus_count += 1
                        found_bonus_words.append(word)
            
            # Message logic
            if new_main_count > 0 or new_bonus_count > 0:
                msg_parts = []
                if new_main_count > 0: msg_parts.append(f"{new_main_count} main word(s)")
                if new_bonus_count > 0: msg_parts.append(f"{new_bonus_count} bonus word(s)")
                message = f"Found {' and '.join(msg_parts)}!"
            elif any_valid:
                message = "Words already found."
            else:
                message = "No new valid words found in this batch."
            
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
                "is_valid": any_valid,
                "is_main": new_main_count > 0, # True if at least one new main word was found
                "is_bonus": new_bonus_count > 0,
                "is_new": any_new,
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
                # Fetch hint from the puzzle
                puzzle = await db.squares_questions.find_one({
                    "class_range": session["class_range"],
                    "level": session["level"]
                })
                hint = puzzle.get("hint") if puzzle else None
                
                return {
                    "session_id": str(session["_id"]),
                    "level": session["level"],
                    "class_range": session["class_range"],
                    "hint": hint,
                    "grid": session["grid"],
                    "found_words": session["found_words"],
                    "found_bonus_words": session["found_bonus_words"],
                    "main_words": session["main_words"],
                    "bonus_words": session.get("bonus_words", []),
                    "main_words_count": len(session["main_words"]),
                    "bonus_words_count": len(session["bonus_words"]),
                    "status": "playing",
                    "mode": session["mode"]
                }
            return {"status": "idle"}
        except Exception as e:
            return {"error": str(e)}
