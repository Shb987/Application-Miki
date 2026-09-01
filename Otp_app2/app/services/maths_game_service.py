import random
import string
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.core.database import db
from app.models.maths_game_models import MathOperationEnum, GameModeEnum

class MathsGameService:

    @staticmethod
    def generate_token(length: int = 6) -> str:
        """Generates a random 6-character uppercase token."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return ''.join(random.choices(alphabet, k=length))

    @classmethod
    async def get_unique_token(cls) -> str:
        """Generates a collision-free token for active waiting rooms."""
        for _ in range(10):
            token = cls.generate_token()
            existing = await db.maths_game_sessions.find_one({"token": token, "status": "WAITING"})
            if not existing:
                return token
        return cls.generate_token(8)

    @staticmethod
    def generate_distractors(correct_val: float, operation: MathOperationEnum, operand1: float, operand2: float) -> List[float]:
        """Generates 3 realistic wrong option choices alongside correct_val."""
        distractors = set()
        correct_int = round(correct_val, 2)
        
        candidates = [
            correct_val + 1, correct_val - 1,
            correct_val + 2, correct_val - 2,
            correct_val + 5, correct_val - 5,
            correct_val + 10, correct_val - 10,
            operand1 + operand2 if operation != MathOperationEnum.ADDITION else operand1 * operand2,
            operand1 - operand2 if operation != MathOperationEnum.SUBTRACTION else operand1 + operand2,
            correct_val * 2 if correct_val != 0 else 5,
            abs(correct_val - 3),
        ]
        
        for cand in candidates:
            cand_round = round(cand, 2)
            if cand_round != correct_int and cand_round >= -1000:
                distractors.add(cand_round)
            if len(distractors) >= 3:
                break
                
        attempts = 0
        while len(distractors) < 3 and attempts < 20:
            attempts += 1
            delta = random.choice([-15, -12, -8, -4, -3, 3, 4, 8, 12, 15, 20])
            rand_val = round(correct_val + delta, 2)
            if rand_val != correct_int and rand_val >= -1000:
                distractors.add(rand_val)

        options = list(distractors)[:3] + [correct_int]
        random.shuffle(options)
        return options

    @classmethod
    def generate_question(cls, grade: int, operation: MathOperationEnum) -> Dict[str, Any]:
        """Generates a single math problem based on grade."""
        q_id = str(uuid.uuid4())[:8]

        if grade in [1, 2]:
            if operation == MathOperationEnum.ADDITION:
                op1 = random.randint(1, 15)
                op2 = random.randint(1, 15)
                correct = float(op1 + op2)
                symbol = "+"
            elif operation == MathOperationEnum.SUBTRACTION:
                op1 = random.randint(3, 20)
                op2 = random.randint(1, op1)
                correct = float(op1 - op2)
                symbol = "-"
            elif operation == MathOperationEnum.MULTIPLICATION:
                op1 = random.randint(1, 5)
                op2 = random.randint(1, 5)
                correct = float(op1 * op2)
                symbol = "*"
            else: # DIVISION
                op2 = random.randint(1, 5)
                correct = float(random.randint(1, 5))
                op1 = int(op2 * correct)
                symbol = "/"

        elif grade in [3, 4, 5]:
            if operation == MathOperationEnum.ADDITION:
                op1 = random.randint(10, 200)
                op2 = random.randint(10, 200)
                correct = float(op1 + op2)
                symbol = "+"
            elif operation == MathOperationEnum.SUBTRACTION:
                op1 = random.randint(30, 300)
                op2 = random.randint(10, op1)
                correct = float(op1 - op2)
                symbol = "-"
            elif operation == MathOperationEnum.MULTIPLICATION:
                op1 = random.randint(3, 12)
                op2 = random.randint(3, 15)
                correct = float(op1 * op2)
                symbol = "*"
            else: # DIVISION
                op2 = random.randint(2, 12)
                correct = float(random.randint(2, 15))
                op1 = int(op2 * correct)
                symbol = "/"

        elif grade in [6, 7, 8]:
            if operation == MathOperationEnum.ADDITION:
                op1 = random.randint(50, 1000)
                op2 = random.randint(50, 1000)
                correct = float(op1 + op2)
                symbol = "+"
            elif operation == MathOperationEnum.SUBTRACTION:
                op1 = random.randint(100, 1500)
                op2 = random.randint(20, op1)
                correct = float(op1 - op2)
                symbol = "-"
            elif operation == MathOperationEnum.MULTIPLICATION:
                op1 = random.randint(8, 25)
                op2 = random.randint(6, 30)
                correct = float(op1 * op2)
                symbol = "*"
            else: # DIVISION
                op2 = random.randint(4, 20)
                correct = float(random.randint(5, 30))
                op1 = int(op2 * correct)
                symbol = "/"

        else: # Grades 9, 10, 11, 12
            if operation == MathOperationEnum.ADDITION:
                op1 = random.randint(100, 5000)
                op2 = random.randint(100, 5000)
                correct = float(op1 + op2)
                symbol = "+"
            elif operation == MathOperationEnum.SUBTRACTION:
                op1 = random.randint(200, 3000)
                op2 = random.randint(-500, 2000)
                correct = float(op1 - op2)
                symbol = "-"
            elif operation == MathOperationEnum.MULTIPLICATION:
                op1 = random.randint(12, 50)
                op2 = random.randint(10, 40)
                correct = float(op1 * op2)
                symbol = "*"
            else: # DIVISION
                op2 = random.randint(6, 35)
                correct = float(random.randint(10, 50))
                op1 = int(op2 * correct)
                symbol = "/"

        expression = f"{op1} {symbol} {op2}" if op2 >= 0 else f"{op1} {symbol} ({op2})"
        options = cls.generate_distractors(correct, operation, float(op1), float(op2))

        return {
            "id": q_id,
            "operand1": float(op1),
            "operand2": float(op2),
            "operation": operation.value,
            "expression": expression,
            "correct_answer": round(correct, 2),
            "options": options,
            "solution": f"{expression} = {round(correct, 2)}"
        }

    @classmethod
    def generate_questions(cls, grade: int, operations: List[MathOperationEnum], count: int) -> List[Dict[str, Any]]:
        """Generates list of questions."""
        if not operations:
            operations = [
                MathOperationEnum.ADDITION,
                MathOperationEnum.SUBTRACTION,
                MathOperationEnum.MULTIPLICATION,
                MathOperationEnum.DIVISION
            ]
            
        questions = []
        for i in range(count):
            op = operations[i % len(operations)]
            q = cls.generate_question(grade, op)
            questions.append(q)
            
        random.shuffle(questions)
        return questions

    @classmethod
    async def start_game(
        cls,
        user_id: str,
        user_name: str,
        mode: GameModeEnum = GameModeEnum.SOLO,
        grade: int = 5,
        operations: Optional[List[MathOperationEnum]] = None,
        num_questions: int = 10,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified endpoint logic to start solo game, create multiplayer room, or join multiplayer room.
        """
        ops = operations or [
            MathOperationEnum.ADDITION,
            MathOperationEnum.SUBTRACTION,
            MathOperationEnum.MULTIPLICATION,
            MathOperationEnum.DIVISION
        ]

        # Case 1: Join Multiplayer Room using Token
        if mode == GameModeEnum.MULTIPLAYER and token:
            clean_token = token.strip().upper()
            session = await db.maths_game_sessions.find_one({"token": clean_token, "mode": "multiplayer"})

            if not session:
                return {"error": "Invalid token or room not found"}

            if session.get("status") != "WAITING":
                return {"error": f"Game session is already {session.get('status').lower()}"}

            if session["player1"]["user_id"] == user_id:
                return {"error": "Player 1 cannot join as Player 2 in the same room"}

            player2_data = {
                "user_id": user_id,
                "name": user_name,
                "is_submitted": False,
                "answers": [],
                "correct_count": 0,
                "total_score": 0,
                "time_taken_seconds": 0.0
            }

            await db.maths_game_sessions.update_one(
                {"session_id": session["session_id"]},
                {
                    "$set": {
                        "player2": player2_data,
                        "status": "IN_PROGRESS",
                        "updated_at": datetime.now(timezone.utc)
                    }
                }
            )

            public_q = [
                {
                    "id": q["id"],
                    "expression": q["expression"],
                    "operation": q["operation"],
                    "options": q["options"]
                } for q in session["questions"]
            ]

            return {
                "session_id": session["session_id"],
                "mode": GameModeEnum.MULTIPLAYER,
                "token": clean_token,
                "grade": session["grade"],
                "operations": session["operations"],
                "status": "IN_PROGRESS",
                "player1_name": session["player1"]["name"],
                "player2_name": user_name,
                "questions": public_q
            }

        # Case 2: Create Multiplayer Room
        elif mode == GameModeEnum.MULTIPLAYER:
            questions = cls.generate_questions(grade, ops, num_questions)
            game_token = await cls.get_unique_token()
            session_id = str(uuid.uuid4())

            doc = {
                "session_id": session_id,
                "token": game_token,
                "mode": "multiplayer",
                "grade": grade,
                "operations": [o.value if isinstance(o, MathOperationEnum) else o for o in ops],
                "num_questions": num_questions,
                "questions": questions,
                "status": "WAITING",
                "player1": {
                    "user_id": user_id,
                    "name": user_name,
                    "is_submitted": False,
                    "answers": [],
                    "correct_count": 0,
                    "total_score": 0,
                    "time_taken_seconds": 0.0
                },
                "player2": None,
                "winner": None,
                "winner_name": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }

            await db.maths_game_sessions.insert_one(doc)

            public_q = [
                {
                    "id": q["id"],
                    "expression": q["expression"],
                    "operation": q["operation"],
                    "options": q["options"]
                } for q in questions
            ]

            return {
                "session_id": session_id,
                "mode": GameModeEnum.MULTIPLAYER,
                "token": game_token,
                "grade": grade,
                "operations": doc["operations"],
                "status": "WAITING",
                "player1_name": user_name,
                "player2_name": None,
                "questions": public_q
            }

        # Case 3: Solo Game
        else:
            questions = cls.generate_questions(grade, ops, num_questions)
            session_id = str(uuid.uuid4())

            doc = {
                "session_id": session_id,
                "mode": "solo",
                "grade": grade,
                "operations": [o.value if isinstance(o, MathOperationEnum) else o for o in ops],
                "num_questions": num_questions,
                "questions": questions,
                "status": "IN_PROGRESS",
                "player1": {
                    "user_id": user_id,
                    "name": user_name,
                    "is_submitted": False,
                    "answers": [],
                    "correct_count": 0,
                    "total_score": 0,
                    "time_taken_seconds": 0.0
                },
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }

            await db.maths_game_sessions.insert_one(doc)

            public_q = [
                {
                    "id": q["id"],
                    "expression": q["expression"],
                    "operation": q["operation"],
                    "options": q["options"]
                } for q in questions
            ]

            return {
                "session_id": session_id,
                "mode": GameModeEnum.SOLO,
                "token": None,
                "grade": grade,
                "operations": doc["operations"],
                "status": "IN_PROGRESS",
                "player1_name": user_name,
                "player2_name": None,
                "questions": public_q
            }

    @classmethod
    async def submit_game(
        cls,
        session_id: str,
        user_id: str,
        answers: List[Dict[str, Any]],
        total_time_seconds: float
    ) -> Dict[str, Any]:
        """Unified endpoint to submit answers for both Solo and Multiplayer games."""
        session = await db.maths_game_sessions.find_one({"session_id": session_id})
        if not session:
            return {"error": "Game session not found"}

        mode = session.get("mode", "solo")
        p1 = session.get("player1", {})
        p2 = session.get("player2") or {}

        # ----------------------------------------------------
        # SOLO SUBMISSION
        # ----------------------------------------------------
        if mode == "solo":
            if session.get("status") == "COMPLETED":
                return {"error": "Solo session is already completed"}

            questions_map = {q["id"]: q for q in session["questions"]}
            correct_count = 0
            details = []
            user_ans_dict = {a["question_id"]: a["selected_option"] for a in answers}

            for q_id, q_data in questions_map.items():
                user_val = user_ans_dict.get(q_id)
                correct_val = q_data["correct_answer"]
                is_correct = (user_val is not None) and (abs(round(user_val, 2) - round(correct_val, 2)) < 0.01)
                if is_correct:
                    correct_count += 1
                details.append({
                    "question_id": q_id,
                    "expression": q_data["expression"],
                    "user_answer": user_val if user_val is not None else 0.0,
                    "correct_answer": correct_val,
                    "is_correct": is_correct
                })

            total_q = len(session["questions"])
            base_score = correct_count * 10
            speed_bonus = max(0, int((300 - total_time_seconds) / 10)) if correct_count > 0 else 0
            total_score = base_score + speed_bonus
            accuracy = round((correct_count / total_q) * 100, 2) if total_q > 0 else 0.0

            update_fields = {
                "status": "COMPLETED",
                "player1.is_submitted": True,
                "player1.answers": answers,
                "player1.correct_count": correct_count,
                "player1.total_score": total_score,
                "player1.time_taken_seconds": total_time_seconds,
                "player1_details": details,
                "updated_at": datetime.now(timezone.utc)
            }

            await db.maths_game_sessions.update_one({"session_id": session_id}, {"$set": update_fields})

            return {
                "session_id": session_id,
                "mode": GameModeEnum.SOLO,
                "status": "COMPLETED",
                "total_questions": total_q,
                "user_correct_count": correct_count,
                "user_accuracy_percentage": accuracy,
                "user_total_score": total_score,
                "time_taken_seconds": total_time_seconds,
                "details": details
            }

        # ----------------------------------------------------
        # MULTIPLAYER SUBMISSION
        # ----------------------------------------------------
        is_p1 = (p1.get("user_id") == user_id)
        is_p2 = (p2.get("user_id") == user_id)

        if not is_p1 and not is_p2:
            return {"error": "User is not a participant in this game session"}

        if session.get("status") == "COMPLETED":
            # Already completed, return session summary
            return await cls.get_session(session_id)

        questions_map = {q["id"]: q for q in session["questions"]}
        correct_count = 0
        details = []
        user_ans_dict = {a["question_id"]: a["selected_option"] for a in answers}

        for q_id, q_data in questions_map.items():
            user_val = user_ans_dict.get(q_id)
            correct_val = q_data["correct_answer"]
            is_correct = (user_val is not None) and (abs(round(user_val, 2) - round(correct_val, 2)) < 0.01)
            if is_correct:
                correct_count += 1
            details.append({
                "question_id": q_id,
                "expression": q_data["expression"],
                "user_answer": user_val if user_val is not None else 0.0,
                "correct_answer": correct_val,
                "is_correct": is_correct
            })

        base_score = correct_count * 10
        speed_bonus = max(0, int((300 - total_time_seconds) / 10)) if correct_count > 0 else 0
        total_score = base_score + speed_bonus

        player_key = "player1" if is_p1 else "player2"
        details_key = "player1_details" if is_p1 else "player2_details"

        update_fields = {
            f"{player_key}.is_submitted": True,
            f"{player_key}.answers": answers,
            f"{player_key}.correct_count": correct_count,
            f"{player_key}.total_score": total_score,
            f"{player_key}.time_taken_seconds": total_time_seconds,
            details_key: details,
            "updated_at": datetime.now(timezone.utc)
        }

        other_submitted = p2.get("is_submitted") if is_p1 else p1.get("is_submitted")

        if other_submitted:
            update_fields["status"] = "COMPLETED"
            p1_score = total_score if is_p1 else p1.get("total_score", 0)
            p2_score = total_score if is_p2 else p2.get("total_score", 0)
            p1_time = total_time_seconds if is_p1 else p1.get("time_taken_seconds", 0.0)
            p2_time = total_time_seconds if is_p2 else p2.get("time_taken_seconds", 0.0)

            if p1_score > p2_score:
                winner = "player1"
                winner_name = p1.get("name")
            elif p2_score > p1_score:
                winner = "player2"
                winner_name = p2.get("name")
            else:
                if p1_time < p2_time:
                    winner = "player1"
                    winner_name = p1.get("name")
                elif p2_time < p1_time:
                    winner = "player2"
                    winner_name = p2.get("name")
                else:
                    winner = "draw"
                    winner_name = "Draw"

            update_fields["winner"] = winner
            update_fields["winner_name"] = winner_name

        await db.maths_game_sessions.update_one({"session_id": session_id}, {"$set": update_fields})
        return await cls.get_session(session_id)

    @classmethod
    async def get_session(cls, session_id: str) -> Dict[str, Any]:
        """Retrieves session details, questions, status, player scores, and results."""
        session = await db.maths_game_sessions.find_one({"session_id": session_id})
        if not session:
            return {"error": "Session not found"}

        public_q = [
            {
                "id": q["id"],
                "expression": q["expression"],
                "operation": q["operation"],
                "options": q["options"]
            } for q in session.get("questions", [])
        ]

        p1 = session.get("player1", {})
        p2 = session.get("player2")

        return {
            "session_id": session["session_id"],
            "mode": session.get("mode", "solo"),
            "token": session.get("token"),
            "status": session.get("status", "IN_PROGRESS"),
            "total_questions": len(session.get("questions", [])),
            "winner": session.get("winner"),
            "winner_name": session.get("winner_name"),
            "player1": {
                "user_id": p1.get("user_id"),
                "name": p1.get("name"),
                "is_submitted": p1.get("is_submitted", False),
                "correct_count": p1.get("correct_count", 0),
                "total_score": p1.get("total_score", 0),
                "time_taken_seconds": p1.get("time_taken_seconds", 0.0)
            },
            "player2": {
                "user_id": p2.get("user_id"),
                "name": p2.get("name"),
                "is_submitted": p2.get("is_submitted", False),
                "correct_count": p2.get("correct_count", 0),
                "total_score": p2.get("total_score", 0),
                "time_taken_seconds": p2.get("time_taken_seconds", 0.0)
            } if p2 else None,
            "questions": public_q,
            "details": session.get("player1_details", []) or session.get("player2_details", [])
        }
