import random
from datetime import datetime, timezone
from bson import ObjectId
from app.core.database import db
from typing import Dict, Any, List, Optional
from app.models.wordle_models import WordleSessionResponse, WordleGuessResponse

class WordleService:
    @staticmethod
    def get_class_range(std: int) -> str:
        if 1 <= std <= 3: return "1-3"
        elif 4 <= std <= 5: return "3-5"
        elif 6 <= std <= 8: return "6-8"
        elif 9 <= std <= 10: return "9-10"
        elif 11 <= std <= 12: return "11-12"
        return "6-8" # Default to Middle School if unknown

    @staticmethod
    async def get_available_levels(student_id: str) -> Dict[str, Any]:
        """Get list of all levels with their status (locked/unlocked/completed)"""
        try:
            s_oid = ObjectId(student_id)
            student = await db.students.find_one({"_id": s_oid})
        except:
            return {"error": "Invalid student ID"}
        
        if not student:
            return {"error": "Student not found"}
        
        student_class = student.get("student_class", 8)
        try:
            student_class = int(student_class)
        except:
            student_class = 8
        
        class_range = WordleService.get_class_range(student_class)
        
        # Determine highest level reached
        latest_session = await db.wordle_sessions.find_one(
            {"student_id": student_id},
            sort=[("updated_at", -1)]
        )
        
        highest_level_reached = 1
        if latest_session:
            highest_level_reached = latest_session.get("current_level", 1)
        
        # Get total levels for this class range
        level_config = {
            "1-3": 15, "3-5": 25, "6-8": 50, "9-10": 50, "11-12": 50
        }
        total_levels = level_config.get(class_range, 50)
        
        # Build level list
        levels = []
        for level_num in range(1, total_levels + 1):
            if level_num < highest_level_reached:
                status = "completed"
                playable = True
            elif level_num == highest_level_reached:
                status = "unlocked"
                playable = True
            else:
                status = "locked"
                playable = False
            
            levels.append({
                "level": level_num,
                "status": status,
                "playable": playable
            })
        
        return {
            "student_id": student_id,
            "class_range": class_range,
            "highest_level_reached": highest_level_reached,
            "total_levels": total_levels,
            "levels": levels
        }

    @staticmethod
    async def start_game(student_id: str, selected_level: Optional[int] = None) -> Dict[str, Any]:
        # 1. Get Student Class and Level
        try:
            s_oid = ObjectId(student_id)
            student = await db.students.find_one({"_id": s_oid})
        except:
            return {"error": "Invalid student ID"}
        
        if not student:
            return {"error": "Student not found"}
            
        student_class = student.get("student_class", 8)
        try:
            student_class = int(student_class)
        except:
            student_class = 8
        class_range = WordleService.get_class_range(student_class)
        
        # 2. Determine Level from Session History
        latest_session = await db.wordle_sessions.find_one(
            {"student_id": student_id},
            sort=[("updated_at", -1)]
        )
        
        current_student_level = 1
        if latest_session:
            current_student_level = latest_session.get("current_level", 1)
        
        # 3. Determine Total Max Levels
        level_config = {
            "1-3": 15, "3-5": 25, "6-8": 50, "9-10": 50, "11-12": 50
        }
        total_max_levels = level_config.get(class_range, 50)
        
        # 4. Handle Level Selection (Practice vs Progression Mode)
        mode = "progression"
        level_to_play = current_student_level
        
        if selected_level is not None:
            if selected_level < 1 or selected_level > total_max_levels:
                return {"error": f"Invalid level. Must be between 1 and {total_max_levels}"}
            
            if selected_level > current_student_level:
                return {"error": f"Level {selected_level} is locked. You can only play up to level {current_student_level}"}
            
            level_to_play = selected_level
            
            # Only practice if user chooses a PREVIOUS level
            if selected_level < current_student_level:
                mode = "practice"
            else:
                mode = "progression"
        
        if level_to_play > total_max_levels:
            level_to_play = total_max_levels

        # 5. Fetch ONLY the selected level question
        question = await db.wordle_questions.find_one({
            "class_range": class_range,
            "level": level_to_play
        })
        if not question:
             return {"error": f"Level {level_to_play} not found for class range {class_range}"}

        # 6. Create Session (Clean schema)
        await db.wordle_sessions.delete_many({"student_id": student_id, "status": "playing"})
        
        session_doc = {
            "student_id": student_id,
            "class_range": class_range,
            "current_level": current_student_level,  # Student's actual progression level
            "selected_level": level_to_play,  # The level being played
            "mode": mode,  # "progression" or "practice"
            "total_levels": total_max_levels,
            "levels_passed": 0,
            
            # Current Word State
            "current_word_id": question["_id"],
            "secret_word": question["word"],
            "hints": question["hints"],
            "guesses": [],
            "revealed_pattern": "_" * len(question["word"]),
            "remaining_attempts": 5,
            
            "status": "playing",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        result = await db.wordle_sessions.insert_one(session_doc)
        
        return {
            "session_id": str(result.inserted_id),
            "current_round": level_to_play, 
            "level": level_to_play,
            "total_rounds": total_max_levels,
            "current_word_length": len(question["word"]),
            "revealed_pattern": session_doc["revealed_pattern"],
            "hint": question["hints"][0] if question["hints"] else "No hint available",
            "remaining_attempts": 5,
            "levels_passed": 0,
            "status": "playing",
            "mode": mode
        }

    @staticmethod
    async def process_guess(session_id: str, guess: str) -> Dict[str, Any]:
        try:
            s_oid = ObjectId(session_id)
        except:
            return {"error": "Invalid session ID"}

        session = await db.wordle_sessions.find_one({"_id": s_oid})
        if not session:
            return {"error": "Session not found"}
        
        if session["status"] != "playing":
            return {"error": "Game already finished"}

        guess = guess.upper().strip()
        secret_word = session["secret_word"]
        word_length = len(secret_word)
        
        if len(guess) != word_length:
            return {"error": f"Guess must be {word_length} letters"}

        # --- Wordle Feedback Logic ---
        new_revealed_pattern = list(session["revealed_pattern"])
        word_counts = {}
        for char in secret_word:
            word_counts[char] = word_counts.get(char, 0) + 1

        temp_feedback = [None] * word_length
        for i in range(word_length):
            if guess[i] == secret_word[i]:
                temp_feedback[i] = "CORRECT"
                word_counts[guess[i]] -= 1
                new_revealed_pattern[i] = guess[i]

        for i in range(word_length):
            if temp_feedback[i] is None:
                if guess[i] in word_counts and word_counts[guess[i]] > 0:
                    temp_feedback[i] = "PRESENT"
                    word_counts[guess[i]] -= 1
                else:
                    temp_feedback[i] = "ABSENT"
        
        feedback = temp_feedback
        new_revealed_pattern_str = "".join(new_revealed_pattern)
        
        guesses = session["guesses"]
        guesses.append({"guess": guess, "feedback": feedback})
        remaining_attempts = session["remaining_attempts"] - 1
        
        # --- Check Outcome ---
        word_status = "playing"
        if guess == secret_word:
            word_status = "won"
        elif remaining_attempts <= 0:
            word_status = "lost"
            
        update_data = {}
        message = "Keep going!"
        word_revealed = None
        status_response = "playing"
        
        current_level = session["current_level"]
        total_max_levels = session["total_levels"]
        levels_passed = session.get("levels_passed", 0)
        mode = session.get("mode", "progression")
        selected_level = session.get("selected_level", current_level)
        
        if word_status in ["won", "lost"]:
            word_revealed = secret_word 
            result_entry = {
                "word": secret_word,
                "status": word_status,
                "attempts_used": len(guesses),
            }
            
            if word_status == "lost":
                # FAIL = Game Over. No level change.
                update_data = {
                    "guesses": guesses,
                    "revealed_pattern": new_revealed_pattern_str,
                    "remaining_attempts": remaining_attempts,
                    "status": "completed",
                    "updated_at": datetime.now(timezone.utc),
                    "$push": {"results": result_entry}
                }
                if mode == "practice":
                    message = f"Level {selected_level} Failed! (Practice Mode)"
                else:
                    message = f"Level Failed! You are still on Level {current_level}. Try again!"
                status_response = "game_over"
                next_level_to_show = selected_level
            else:
                # WON
                levels_passed += 1
                
                if mode == "practice":
                    # Practice mode: Don't advance, just complete
                    update_data = {
                        "guesses": guesses,
                        "revealed_pattern": new_revealed_pattern_str,
                        "remaining_attempts": remaining_attempts,
                        "levels_passed": levels_passed,
                        "status": "completed",
                        "updated_at": datetime.now(timezone.utc),
                        "$push": {"results": result_entry}
                    }
                    message = f"Level {selected_level} completed! (Practice Mode)"
                    status_response = "game_over"
                    next_level_to_show = selected_level
                else:
                    # Progression mode: Advance to next level
                    next_level = current_level + 1
                    if next_level > total_max_levels:
                        # Final Completion
                        update_data = {
                            "guesses": guesses,
                            "revealed_pattern": new_revealed_pattern_str,
                            "remaining_attempts": remaining_attempts,
                            "levels_passed": levels_passed,
                            "status": "completed",
                            "updated_at": datetime.now(timezone.utc),
                            "$push": {"results": result_entry}
                        }
                        message = "Congratulations! You've passed all levels for your category!"
                        status_response = "game_over"
                        next_level_to_show = current_level
                    else:
                        # Fetch NEXT word on-demand
                        next_q = await db.wordle_questions.find_one({
                            "class_range": session["class_range"],
                            "level": next_level
                        })
                        
                        if not next_q:
                            update_data = {"status": "completed", "updated_at": datetime.now(timezone.utc)}
                            status_response = "game_over"
                            message = "Error loading next level data."
                            next_level_to_show = current_level
                        else:
                            update_data = {
                                "current_level": next_level,
                                "selected_level": next_level,
                                "levels_passed": levels_passed,
                                "current_word_id": next_q["_id"],
                                "secret_word": next_q["word"],
                                "hints": next_q["hints"],
                                "guesses": [],
                                "revealed_pattern": "_" * len(next_q["word"]),
                                "remaining_attempts": 5,
                                "updated_at": datetime.now(timezone.utc),
                                "$push": {"results": result_entry}
                            }
                            message = f"Correct! Level {next_level} unlocked!"
                            status_response = "won"
                            next_level_to_show = next_level
        else:
            # Still playing
            update_data = {
                "guesses": guesses,
                "revealed_pattern": new_revealed_pattern_str,
                "remaining_attempts": remaining_attempts,
                "updated_at": datetime.now(timezone.utc)
            }
            next_level_to_show = current_level

        # MongoDB Update
        update_query = {}
        if "$push" in update_data:
            update_query["$push"] = update_data.pop("$push")
        if update_data:
            update_query["$set"] = update_data
        await db.wordle_sessions.update_one({"_id": s_oid}, update_query)
        
        # Prepare Response
        next_hint = None
        if status_response == "playing":
             hint_idx = len(guesses)
             all_hints = session["hints"]
             next_hint = all_hints[hint_idx] if hint_idx < len(all_hints) else all_hints[-1]

        # Word length for next word or current
        if status_response == "playing":
            output_word_length = word_length
        elif status_response == "won" and next_level <= total_max_levels and next_q:
            output_word_length = len(next_q["word"])
        else:
            output_word_length = 0

        return {
            "feedback": feedback,
            "next_hint": next_hint,
            "revealed_pattern": new_revealed_pattern_str,
            "remaining_attempts": remaining_attempts,
            "status": status_response,
            "message": message,
            "current_round": next_level_to_show,
            "level": next_level_to_show,
            "total_rounds": total_max_levels,
            "levels_passed": levels_passed,
            "word_revealed": word_revealed,
            "current_word_length": output_word_length,
            "mode": mode
        }

    @staticmethod
    async def get_status(student_id: str) -> Dict[str, Any]:
        # 1. Search for active session
        session = await db.wordle_sessions.find_one(
            {"student_id": student_id, "status": "playing"},
            sort=[("updated_at", -1)]
        )
        print('check1')
        if session:
            print('check2')
            # Active Session Found
            hint_index = len(session["guesses"])
            hints = session["hints"]
            current_hint = hints[hint_index] if hint_index < len(hints) else hints[-1]
            
            return {
                "session_id": str(session["_id"]),
                "current_round": session["current_level"],
                "level": session["current_level"],
                "total_rounds": session["total_levels"],
                "current_word_length": len(session["secret_word"]),
                "revealed_pattern": session["revealed_pattern"],
                "hint": current_hint,
                "remaining_attempts": session["remaining_attempts"],
                "levels_passed": session.get("levels_passed", 0),
                "status": "playing"
            }
        
        # 2. No Active Session: Fallback to History
        latest_session = await db.wordle_sessions.find_one(
            {"student_id": student_id},
            sort=[("updated_at", -1)]
        )
        
        current_student_level = 1
        lifetime_passed = 0
        
        if latest_session:
            current_student_level = latest_session.get("current_level", 1)
            # Rough estimate of passed levels from history
            lifetime_passed = current_student_level - 1
            if current_student_level > latest_session.get("total_levels", 50):
                lifetime_passed = latest_session.get("total_levels", 50)

        # Still need class for total_rounds
        try:
            s_oid = ObjectId(student_id)
            student = await db.students.find_one({"_id": s_oid})
            student_class = int(student.get("student_class", 8))
        except:
            student_class = 8
            
        class_range = WordleService.get_class_range(student_class)
        level_config = {"1-3": 15, "3-5": 25, "6-8": 50, "9-10": 50, "11-12": 50}
        total_max_levels = level_config.get(class_range, 50)

        return {
            "session_id": None,
            "current_round": current_student_level,
            "level": current_student_level,
            "total_rounds": total_max_levels,
            "current_word_length": None,
            "revealed_pattern": None,
            "hint": None,
            "remaining_attempts": None,
            "levels_passed": lifetime_passed,
            "status": "idle"
        }
