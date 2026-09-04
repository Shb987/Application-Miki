from datetime import datetime, timezone
from typing import Dict, List, Optional
from bson import ObjectId
from app.core.database import db
from app.models.analysis_models import (
    VisualCareerAnalytics, CareerScoreItem,
    VisualExamAnalytics, ExamHistoryItem,
    VisualQuizAnalytics, DifficultyStats, QuizHistoryItem,
    VisualCoreDashboard
)

class AnalysisService:
    """Core 3 Visual Analytics Service"""

    @staticmethod
    async def get_visual_career_stats(s_oid: ObjectId) -> Optional[VisualCareerAnalytics]:
        """Formatting latest career scores for UI charts"""
        try:
            career_doc = await db.career_analyzer.find_one(
                {"student_id": {"$in": [str(s_oid), s_oid]}},
                sort=[("timestamp", -1)]
            )
            if not career_doc:
                return None

            scores_dict = career_doc.get("scores", {})
            score_details = [
                CareerScoreItem(label=k, value=float(v)) 
                for k, v in scores_dict.items()
            ]
            top_cat = career_doc.get("top_category", "")

            # Detect ties in scores_dict if top_cat doesn't already contain '&'
            if scores_dict and "&" not in top_cat:
                max_val = max(scores_dict.values())
                tied_cats = [k for k, v in scores_dict.items() if v == max_val and max_val > 0]
                if len(tied_cats) > 1:
                    top_cat = " & ".join(k.title() for k in tied_cats)

            raw_careers = career_doc.get("recommended_career", [])
            if isinstance(raw_careers, str):
                recommended_careers = [c.strip() for c in raw_careers.split(",") if c.strip() and c.strip() != "No career mapped"]
            else:
                recommended_careers = [c for c in raw_careers if c != "No career mapped"]

            if not recommended_careers:
                from app.routes.user_routes import get_recommended_career
                cats_to_check = [c.strip() for c in top_cat.split("&")] if "&" in top_cat else [top_cat]
                combined = []
                for cat in cats_to_check:
                    c_str = get_recommended_career(cat)
                    for c in c_str.split(","):
                        c_clean = c.strip()
                        if c_clean and c_clean not in combined:
                            combined.append(c_clean)
                recommended_careers = combined if combined else [get_recommended_career(top_cat)]

            return VisualCareerAnalytics(
                current_top_category=top_cat or "N/A",
                recommended_careers=recommended_careers,
                score_details=score_details,
                message=f"Your top intelligence is {top_cat}. You are a natural fit for {', '.join(recommended_careers)}."
            )
        except Exception as e:
            print(f"Error in get_visual_career_stats: {e}")
            return None

    @staticmethod
    async def get_visual_exam_stats(s_oid: ObjectId) -> Optional[VisualExamAnalytics]:
        """Historical progression trend for descriptive exams"""
        try:
            # 1. Fetch completed evaluations from 'evaluations' collection
            cursor = db.evaluations.find({
                "student_id": {"$in": [s_oid, str(s_oid)]},
                "status": "COMPLETED"
            }).sort("created_at", 1)
            
            exams = await cursor.to_list(length=100)
            if not exams:
                return None

            history = []
            total_pct = 0
            for e in exams:
                # Use 'max_total' instead of 'total_marks' as per DB structure
                marks = e.get("max_total", 1)
                score = e.get("total_score", 0)
                
                # Avoid division by zero
                if marks == 0: marks = 1
                
                pct = (score / marks) * 100
                total_pct += pct
                
                # completed_at is usually more accurate for "when it was graded"
                date_val = e.get("completed_at") or e.get("created_at") or datetime.now(timezone.utc)
                if isinstance(date_val, str):
                    try:
                        date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                    except Exception:
                        date_val = datetime.now(timezone.utc)
                
                history.append(ExamHistoryItem(
                    date=date_val,
                    score_percentage=round(pct, 1),
                    paper_id=str(e.get("paper_id", "Unknown"))
                ))

            # Trend calculation
            trend = "Stable"
            if len(history) >= 2:
                recent_avg = sum(h.score_percentage for h in history[-2:]) / 2
                
                # Calculate previous average (excluding the last 2)
                prev_records = history[:-2]
                if prev_records:
                    prev_avg = sum(h.score_percentage for h in prev_records) / len(prev_records)
                else:
                    # If only 2 records exist, compare the last one with the first one
                    prev_avg = history[0].score_percentage
                
                if recent_avg > prev_avg + 5: trend = "Improving"
                elif recent_avg < prev_avg - 5: trend = "Declining"

            return VisualExamAnalytics(
                overall_avg_score=round(total_pct / len(exams), 1),
                total_papers_taken=len(exams),
                history=history,
                latest_feedback=exams[-1].get("overall_feedback", "Exam evaluation complete!"),
                trend=trend
            )
        except Exception as e:
            print(f"Error in get_visual_exam_stats: {e}")
            return None

    @staticmethod
    async def get_visual_quiz_stats(s_oid: ObjectId) -> Optional[VisualQuizAnalytics]:
        """Difficulty breakdown and 10-session trend for 'Mixed' quizzes"""
        try:
            # 1. Fetch all Mixed quizzes
            cursor = db.quiz_submissions.find({
                "student_id": {"$in": [s_oid, str(s_oid)]},
            }).sort("submitted_at", 1)
            quizzes = await cursor.to_list(length=200)
            if not quizzes:
                return None

            # 2. Difficulty breakdown
            diff_map: Dict[str, List[float]] = {"Easy": [], "Medium": [], "Hard": []}
            for q in quizzes:
                lvl = q.get("difficulty_level", "Medium")
                pct = q.get("percentage", 0)
                if lvl in diff_map:
                    diff_map[lvl].append(pct)
                else:
                    # Fallback for dynamic levels
                    diff_map[lvl] = [pct]

            breakdown = {}
            total_all_pct = 0
            for lvl, scores in diff_map.items():
                if scores:
                    avg = sum(scores) / len(scores)
                    total_all_pct += sum(scores)
                    breakdown[lvl] = DifficultyStats(
                        total_taken=len(scores),
                        avg_percentage=round(avg, 1)
                    )
                else:
                    breakdown[lvl] = DifficultyStats(total_taken=0, avg_percentage=0.0)

            # 3. Last 10 trend
            recent_10 = quizzes[-10:]
            history = []
            for q in recent_10:
                dt = q.get("submitted_at")
                if dt:
                    if isinstance(dt, str):
                        try:
                            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                        except Exception:
                            dt = datetime.now(timezone.utc)
                    history.append(QuizHistoryItem(
                        date=dt,
                        percentage=float(q.get("percentage", 0))
                    ))

            return VisualQuizAnalytics(
                difficulty_breakdown=breakdown,
                last_10_trend=history,
                overall_accuracy=round(total_all_pct / len(quizzes), 1)
            )
        except Exception as e:
            print(f"Error in get_visual_quiz_stats: {e}")
            return None

    @staticmethod
    async def get_visual_dashboard(student_id: str, student_name: str) -> VisualCoreDashboard:
        """Final Aggregator for the Core 3 Experience"""
        s_oid = ObjectId(student_id) if ObjectId.is_valid(student_id) else None
        if not s_oid:
            return VisualCoreDashboard(
                student_id=student_id, student_name=student_name, generated_at=datetime.now(timezone.utc)
            )

        career = await AnalysisService.get_visual_career_stats(s_oid)
        exams = await AnalysisService.get_visual_exam_stats(s_oid)
        quizzes = await AnalysisService.get_visual_quiz_stats(s_oid)

        return VisualCoreDashboard(
            student_id=student_id,
            student_name=student_name,
            generated_at=datetime.now(timezone.utc),
            career=career,
            exams=exams,
            quizzes=quizzes
        )
