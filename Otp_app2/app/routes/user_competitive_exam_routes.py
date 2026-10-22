from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Optional, Dict, Any, Union
from bson import ObjectId
from datetime import datetime, timezone
import os
import re
import json

from app.core.database import db
from app.utils.user_auth import get_current_user
from app.report.competitive_exam_pdf import save_competitive_exam_paper
from app.models.competitive_exam_models import (
    ExamSubmitRequest, ExamAnswerSubmission,
    ExamResultResponse, ExamSubmissionSummary, QuestionReviewItem,
    ExamAttemptItem, CompetitiveAnalyticsResponse
)

router = APIRouter(tags=["Competitive Exams - User"])

GENERATED_PDF_DIR = "app/static/generated_papers"
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# DEFAULT SEEDS (Identical to Admin configuration)
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES = [
    {"category_name": "UPSC Civil Services", "description": "Union Public Service Commission examinations (IAS, IPS, IFS, Prelims, Mains)", "icon": "fa-university", "is_active": True},
    {"category_name": "Kerala PSC", "description": "Kerala Public Service Commission examinations (KAS, Degree Level, 10th/12th Level)", "icon": "fa-certificate", "is_active": True},
    {"category_name": "SSC", "description": "Staff Selection Commission examinations (CGL, CHSL, MTS, CPO)", "icon": "fa-id-card", "is_active": True},
    {"category_name": "Banking & Insurance", "description": "IBPS, SBI PO, Clerk, RBI Grade B, LIC AAO examinations", "icon": "fa-money", "is_active": True},
    {"category_name": "Railway Recruitment", "description": "RRB NTPC, Group D, ALP, JE examinations", "icon": "fa-train", "is_active": True},
    {"category_name": "Other State PSCs", "description": "TNPSC, APPSC, KPSC, MPSC, UPPSC and other State Public Service examinations", "icon": "fa-map", "is_active": True},
    {"category_name": "Defence Examinations", "description": "NDA, CDS, AFCAT, CAPF, Territorial Army", "icon": "fa-shield", "is_active": True},
    {"category_name": "Teaching & Eligibility", "description": "CTET, KTET, NET / SET, PRT, TGT, PGT examinations", "icon": "fa-graduation-cap", "is_active": True},
    {"category_name": "NEET / JEE & Entrance", "description": "Medical, Engineering, and Higher Education Entrance examinations", "icon": "fa-flask", "is_active": True},
    {"category_name": "Other Competitive Exams", "description": "General recruitment and skill-based competitive assessments", "icon": "fa-briefcase", "is_active": True}
]

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def natural_sort_key(s):
    if not s:
        return []
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

async def resolve_student(current_user: dict, explicit_student_id: Optional[str] = None) -> Optional[dict]:
    """
    Intelligently resolves the student record from:
    1. Explicit student_id param
    2. current_user token payload ('student_id')
    3. current_user mobile number / sub via usertable or students collection
    """
    target_id = explicit_student_id or current_user.get("student_id")
    if target_id and str(target_id).strip():
        s_clean = str(target_id).strip()
        try:
            if ObjectId.is_valid(s_clean):
                st = await db.students.find_one({"_id": ObjectId(s_clean)})
                if st: return st
        except Exception:
            pass
        st = await db.students.find_one({"_id": s_clean})
        if st: return st
        st = await db.students.find_one({"student_id": s_clean})
        if st: return st
        st = await db.students.find_one({"id": s_clean})
        if st: return st

    # Fallback to mobile lookup
    mobile = current_user.get("sub")
    if mobile:
        user_doc = await db.usertable.find_one({"mobile_number": mobile})
        if user_doc and user_doc.get("student_ids"):
            first_sid = user_doc["student_ids"][0]
            try:
                if ObjectId.is_valid(str(first_sid)):
                    st = await db.students.find_one({"_id": ObjectId(str(first_sid))})
                    if st: return st
            except Exception:
                pass
            st = await db.students.find_one({"_id": str(first_sid)})
            if st: return st

        st = await db.students.find_one({"parent_mobile": mobile})
        if st: return st
        st = await db.students.find_one({"mobile_number": mobile})
        if st: return st

    return None

def ensure_pdf_file(paper_doc: dict) -> str:
    """
    Checks if PDF exists on disk; if missing, re-renders via save_competitive_exam_paper.
    Returns relative web path (e.g., '/generated_papers/comp_...pdf').
    """
    paper_data = paper_doc.get("paper", {})
    paper_oid = str(paper_doc.get("_id", "comp_paper"))
    task_id = str(paper_doc.get("task_id", paper_oid))
    paper_idx = paper_doc.get("paper_index", 1)

    pdf_filename = f"comp_{task_id}_{paper_idx}.pdf"
    disk_path = os.path.abspath(os.path.join(GENERATED_PDF_DIR, pdf_filename))

    if not os.path.exists(disk_path):
        try:
            save_competitive_exam_paper(paper_data, disk_path)
        except Exception as e:
            print(f"[USER-COMP-PDF] PDF render warning: {e}")

    return f"/generated_papers/{pdf_filename}"


# ===========================================================================
# 1. CATEGORIES & EXAMS DISCOVERY
# ===========================================================================

@router.get("/competitive-exams/categories")
async def list_categories():
    """
    Retrieve all competitive exam categories (UPSC, Kerala PSC, SSC, Banking, Railways, Defence, etc.).
    Includes active exam count for each category.
    """
    count = await db.competitive_exam_categories.count_documents({})
    if count == 0:
        now = datetime.now(timezone.utc)
        docs = [{**cat, "created_at": now, "updated_at": now} for cat in DEFAULT_CATEGORIES]
        await db.competitive_exam_categories.insert_many(docs)

    categories = await db.competitive_exam_categories.find({"is_active": {"$ne": False}}).sort("category_name", 1).to_list(None)

    for cat in categories:
        cat["_id"] = str(cat["_id"])
        c_name = cat.get("category_name")
        c_id = cat["_id"]
        # Count available exams under this category
        cat["exam_count"] = await db.competitive_exams.count_documents({
            "$or": [{"category_id": c_id}, {"category_name": c_name}],
            "is_active": {"$ne": False}
        })

    return {
        "status": "success",
        "total_categories": len(categories),
        "categories": categories
    }


@router.get("/competitive-exams/exams")
async def list_exams(
    category_id: Optional[str] = Query(None, description="Filter by Category ID or Category Name"),
    search: Optional[str] = Query(None, description="Search keyword for exam title or conducting authority"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    List available competitive exams with pattern, subjects, duration, and question count.
    Filterable by category and search keyword.
    """
    query: Dict[str, Any] = {"is_active": {"$ne": False}}
    if category_id and category_id.strip():
        cid = category_id.strip()
        query["$or"] = [{"category_id": cid}, {"category_name": cid}]

    if search and search.strip():
        term = re.escape(search.strip())
        search_filter = {
            "$or": [
                {"exam_name": {"$regex": term, "$options": "i"}},
                {"conducting_authority": {"$regex": term, "$options": "i"}},
                {"subjects": {"$regex": term, "$options": "i"}}
            ]
        }
        if "$or" in query:
            query = {"$and": [query, search_filter]}
        else:
            query.update(search_filter)

    total_count = await db.competitive_exams.count_documents(query)
    exams = await db.competitive_exams.find(query).sort("exam_name", 1).skip(skip).limit(limit).to_list(None)

    for exam in exams:
        exam["_id"] = str(exam["_id"])
        e_name = exam.get("exam_name")
        e_id = exam["_id"]

        # Count available generated papers for this exam
        paper_count = await db.generated_papers.count_documents({
            "module_type": "competitive_exam",
            "$or": [
                {"exam_id": e_id},
                {"exam_name": e_name},
                {"paper.exam_name": e_name}
            ]
        })
        exam["available_papers_count"] = paper_count

        # Count available textbooks for this exam
        tb_count = await db.textbook.count_documents({
            "$or": [
                {"exam_name": e_name},
                {"standard": e_name}
            ]
        })
        exam["available_textbooks_count"] = tb_count

    return {
        "status": "success",
        "total_count": total_count,
        "returned_count": len(exams),
        "exams": exams
    }


@router.get("/competitive-exams/exams/{exam_id}")
async def get_exam_details(exam_id: str = Path(..., description="Competitive Exam ID or Name")):
    """
    Get detailed blueprint and syllabus specifications for a specific competitive exam.
    """
    exam = None
    if ObjectId.is_valid(exam_id):
        exam = await db.competitive_exams.find_one({"_id": ObjectId(exam_id)})
    if not exam:
        exam = await db.competitive_exams.find_one({"exam_name": exam_id})

    if not exam:
        raise HTTPException(status_code=404, detail="Competitive Exam not found")

    exam["_id"] = str(exam["_id"])
    e_name = exam.get("exam_name")

    # Fetch available question papers count
    paper_count = await db.generated_papers.count_documents({
        "module_type": "competitive_exam",
        "$or": [{"exam_id": exam["_id"]}, {"exam_name": e_name}, {"paper.exam_name": e_name}]
    })
    exam["available_papers_count"] = paper_count

    # Fetch available textbooks
    textbooks = await db.textbook.find({
        "$or": [{"exam_name": e_name}, {"standard": e_name}],
        "status": {"$in": ["completed", "cleanup_failed"]}
    }).to_list(None)

    for tb in textbooks:
        tb["_id"] = str(tb["_id"])
        if isinstance(tb.get("chapters"), list):
            tb["chapters"] = sorted(tb["chapters"], key=natural_sort_key)

    exam["textbooks"] = textbooks

    return {
        "status": "success",
        "exam": exam
    }


# ===========================================================================
# 2. TEXTBOOKS & CHAPTERS (STUDY MATERIALS)
# ===========================================================================

@router.get("/competitive-exams/textbooks")
async def list_textbooks(
    category: Optional[str] = Query(None, description="Category filter"),
    exam_name: Optional[str] = Query(None, description="Exam Name filter"),
    subject: Optional[str] = Query(None, description="Subject filter")
):
    """
    Retrieve ingested competitive exam textbooks and chapter syllabi.
    """
    query: Dict[str, Any] = {
        "$or": [
            {"module_type": "competitive_exam"},
            {"exam_name": {"$exists": True, "$ne": None, "$ne": ""}},
            {"exam_category": {"$exists": True, "$ne": None, "$ne": ""}}
        ]
    }
    and_clauses = []
    if category:
        and_clauses.append({"$or": [{"exam_category": category}, {"board": category}, {"state": category}]})
    if exam_name:
        and_clauses.append({"$or": [{"exam_name": exam_name}, {"standard": exam_name}]})
    if subject:
        and_clauses.append({"subject": subject})
    if and_clauses:
        query = {"$and": [query] + and_clauses}

    textbooks = await db.textbook.find(query).sort("created_at", -1).to_list(None)

    clean_tbs = []
    for t in textbooks:
        t_id = str(t["_id"])
        ch_list = t.get("chapters", [])
        if isinstance(ch_list, list):
            ch_list = sorted(ch_list, key=natural_sort_key)
        else:
            ch_list = []

        clean_tbs.append({
            "_id": t_id,
            "textbook_id": t_id,
            "textbook_title": t.get("textbook_title") or t.get("textbook_name") or f"{t.get('subject', 'General')} Textbook",
            "exam_name": t.get("exam_name") or t.get("standard") or "Competitive Exam",
            "exam_category": t.get("exam_category") or t.get("board") or "Competitive Exams",
            "subject": t.get("subject", "General"),
            "language": t.get("language", "en"),
            "chapters_count": len(ch_list),
            "chapters": ch_list,
            "stored_chunk_count": t.get("stored_chunk_count", 0),
            "created_at": t.get("created_at").isoformat() if isinstance(t.get("created_at"), datetime) else str(t.get("created_at", ""))
        })

    return {
        "status": "success",
        "total_textbooks": len(clean_tbs),
        "textbooks": clean_tbs
    }


@router.get("/competitive-exams/textbooks/{textbook_id}/chapters")
async def get_textbook_chapters(textbook_id: str = Path(..., description="Textbook ID")):
    """
    Get detailed chapter syllabus, page ranges, and detected topic metadata for a textbook.
    """
    if not ObjectId.is_valid(textbook_id):
        raise HTTPException(status_code=400, detail="Invalid textbook ID format")

    tb = await db.textbook.find_one({"_id": ObjectId(textbook_id)})
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")

    chapter_metadata = tb.get("chapter_metadata", [])
    raw_chapters = tb.get("chapters", [])
    if isinstance(raw_chapters, list):
        sorted_chapters = sorted(raw_chapters, key=natural_sort_key)
    else:
        sorted_chapters = []

    return {
        "status": "success",
        "textbook_id": textbook_id,
        "textbook_title": tb.get("textbook_title") or tb.get("textbook_name"),
        "exam_name": tb.get("exam_name") or tb.get("standard"),
        "subject": tb.get("subject"),
        "chapters_count": len(sorted_chapters),
        "chapters": sorted_chapters,
        "chapter_metadata": chapter_metadata
    }


# ===========================================================================
# 3. QUESTION PAPERS & MOCK TESTS
# ===========================================================================

@router.get("/competitive-exams/papers")
async def list_papers(
    exam_id: Optional[str] = Query(None, description="Filter by Exam ID"),
    exam_name: Optional[str] = Query(None, description="Filter by Exam Name"),
    subject: Optional[str] = Query(None, description="Filter by Subject"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """
    List generated practice question papers for competitive exams.
    """
    query: Dict[str, Any] = {"module_type": "competitive_exam"}

    if exam_id and exam_id.strip():
        query["exam_id"] = exam_id.strip()

    if exam_name and exam_name.strip():
        term = exam_name.strip()
        query["$or"] = [{"exam_name": term}, {"paper.exam_name": term}]

    if subject and subject.strip():
        term = subject.strip()
        query["$or"] = [{"paper.subject": term}, {"subject": term}]

    total_count = await db.generated_papers.count_documents(query)
    papers_cursor = db.generated_papers.find(query).sort("created_at", -1).skip(skip).limit(limit)
    papers = await papers_cursor.to_list(None)

    clean_papers = []
    for p in papers:
        p_id = str(p["_id"])
        paper_obj = p.get("paper", {})
        task_id = p.get("task_id", p_id)
        paper_idx = p.get("paper_index", 1)

        # Count total questions across sections
        total_q = 0
        for sec in paper_obj.get("sections", []):
            total_q += len(sec.get("questions", []))

        pdf_filename = f"comp_{task_id}_{paper_idx}.pdf"
        has_pdf = os.path.exists(os.path.join(GENERATED_PDF_DIR, pdf_filename)) or bool(p.get("pdf_path"))

        clean_papers.append({
            "paper_id": p_id,
            "task_id": task_id,
            "exam_id": p.get("exam_id"),
            "exam_name": p.get("exam_name") or paper_obj.get("exam_name", "Competitive Exam"),
            "subject": paper_obj.get("subject") or p.get("subject", "General Studies"),
            "paper_title": paper_obj.get("paper_title") or f"{p.get('exam_name', 'Competitive Exam')} Practice Paper",
            "total_marks": paper_obj.get("total_marks", 100),
            "time_limit": paper_obj.get("time_limit", "120 MINUTES"),
            "total_questions": total_q,
            "negative_marking_rule": paper_obj.get("negative_marking_rule", "Negative penalty applies"),
            "has_pdf": has_pdf,
            "pdf_url": f"/generated_papers/{pdf_filename}",
            "created_at": p.get("created_at").isoformat() if isinstance(p.get("created_at"), datetime) else str(p.get("created_at", ""))
        })

    return {
        "status": "success",
        "total_count": total_count,
        "returned_count": len(clean_papers),
        "papers": clean_papers
    }


@router.get("/competitive-exams/papers/{paper_id}")
async def get_paper_detail(
    paper_id: str = Path(..., description="Question Paper ID"),
    mode: str = Query("test", description="'test' hides answers and explanations; 'practice' returns answers & explanations")
):
    """
    Retrieve question paper for test taking or practice study.
    - When `mode=test`: Omits `correct_answer`, `answer_key`, and `explanation` so students can take the exam securely.
    - When `mode=practice`: Includes complete solutions, answer key, and chapter citations.
    """
    if not ObjectId.is_valid(paper_id):
        raise HTTPException(status_code=400, detail="Invalid paper ID format")

    paper_doc = await db.generated_papers.find_one({"_id": ObjectId(paper_id)})
    if not paper_doc:
        raise HTTPException(status_code=404, detail="Question paper not found")

    paper_obj = paper_doc.get("paper", {})
    raw_sections = paper_obj.get("sections", [])

    is_test_mode = (mode.lower() == "test")
    sanitized_sections = []
    total_q = 0

    for sec in raw_sections:
        sanitized_questions = []
        for q in sec.get("questions", []):
            total_q += 1
            q_clean = {
                "question_number": q.get("question_number", total_q),
                "question": q.get("question", ""),
                "type": q.get("type", "MCQ"),
                "options": q.get("options", {}),
                "marks": q.get("marks", 1.0),
                "negative_marks": q.get("negative_marks", 0.33),
                "difficulty": q.get("difficulty", "Medium"),
                "chapter_reference": q.get("chapter_reference")
            }

            if not is_test_mode:
                # In practice mode, include answers and explanations
                q_clean["correct_answer"] = q.get("correct_answer")
                q_clean["explanation"] = q.get("explanation")

            sanitized_questions.append(q_clean)

        sanitized_sections.append({
            "section_title": sec.get("section_title", "Section"),
            "questions": sanitized_questions
        })

    # Ensure PDF exists on disk
    pdf_url = ensure_pdf_file(paper_doc)

    response_data = {
        "paper_id": str(paper_doc["_id"]),
        "exam_id": paper_doc.get("exam_id"),
        "exam_name": paper_doc.get("exam_name") or paper_obj.get("exam_name", "Competitive Exam"),
        "subject": paper_obj.get("subject", "General Studies"),
        "paper_title": paper_obj.get("paper_title", "Competitive Exam Practice Paper"),
        "total_marks": paper_obj.get("total_marks", 100),
        "time_limit": paper_obj.get("time_limit", "120 MINUTES"),
        "negative_marking_rule": paper_obj.get("negative_marking_rule", "0.33 mark deducted for each incorrect response"),
        "total_questions": total_q,
        "mode": "test" if is_test_mode else "practice",
        "sections": sanitized_sections,
        "pdf_url": pdf_url,
        "download_url": f"/user/competitive-exams/papers/{paper_id}/download"
    }

    if not is_test_mode:
        response_data["answer_key"] = paper_obj.get("answer_key", {})

    return {
        "status": "success",
        "paper": response_data
    }


@router.get("/competitive-exams/papers/{paper_id}/download")
async def download_paper_pdf(paper_id: str = Path(..., description="Question Paper ID")):
    """
    Download the printable PDF question paper. Auto-renders on the fly if missing.
    """
    if not ObjectId.is_valid(paper_id):
        raise HTTPException(status_code=400, detail="Invalid paper ID format")

    paper_doc = await db.generated_papers.find_one({"_id": ObjectId(paper_id)})
    if not paper_doc:
        raise HTTPException(status_code=404, detail="Question paper not found")

    pdf_url = ensure_pdf_file(paper_doc)
    pdf_filename = os.path.basename(pdf_url)
    disk_path = os.path.abspath(os.path.join(GENERATED_PDF_DIR, pdf_filename))

    if not os.path.exists(disk_path):
        raise HTTPException(status_code=500, detail="Failed to render paper PDF file on server storage.")

    exam_title = (paper_doc.get("paper", {}).get("paper_title") or f"competitive_exam_{paper_id}").replace(" ", "_")
    download_filename = f"{exam_title}.pdf"

    return FileResponse(
        path=disk_path,
        filename=download_filename,
        media_type="application/pdf"
    )


# ===========================================================================
# 4. EXAM SUBMISSION & AUTO-EVALUATION
# ===========================================================================

@router.post("/competitive-exams/papers/{paper_id}/submit", response_model=ExamResultResponse)
async def submit_exam_paper(
    paper_id: str = Path(..., description="Question Paper ID"),
    payload: ExamSubmitRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Submit answers for a competitive exam paper.
    Calculates instant marks with negative marking penalty, stores attempt,
    and returns comprehensive score breakdown with question explanations.
    """
    if not ObjectId.is_valid(paper_id):
        raise HTTPException(status_code=400, detail="Invalid paper ID format")

    paper_doc = await db.generated_papers.find_one({"_id": ObjectId(paper_id)})
    if not paper_doc:
        raise HTTPException(status_code=404, detail="Question paper not found")

    # Resolve student
    student = await resolve_student(current_user, payload.student_id)
    student_id_str = str(student["_id"]) if student else str(payload.student_id or current_user.get("sub", "student"))
    student_name_str = student.get("student_name", "Learner") if student else "Learner"

    paper_obj = paper_doc.get("paper", {})
    raw_sections = paper_obj.get("sections", [])

    # Index paper questions by question_number
    questions_map: Dict[int, dict] = {}
    for sec in raw_sections:
        for q in sec.get("questions", []):
            q_num = int(q.get("question_number", 0))
            if q_num:
                questions_map[q_num] = q

    # Index user's answers
    user_answers_map: Dict[int, str] = {}
    for ans in payload.answers:
        if ans.selected_option and str(ans.selected_option).strip():
            user_answers_map[ans.question_number] = str(ans.selected_option).strip().upper()

    # Evaluation variables
    total_q = len(questions_map)
    attempted_count = 0
    correct_count = 0
    incorrect_count = 0
    unattempted_count = 0

    total_possible_marks = 0.0
    positive_marks = 0.0
    negative_marks_deducted = 0.0
    evaluated_results: List[QuestionReviewItem] = []

    for q_num in sorted(questions_map.keys()):
        q = questions_map[q_num]
        q_marks = float(q.get("marks", 1.0))
        q_negative = float(q.get("negative_marks", 0.33))
        total_possible_marks += q_marks

        correct_opt = str(q.get("correct_answer", "")).strip().upper()
        user_opt = user_answers_map.get(q_num)

        if not user_opt:
            # Unattempted question
            unattempted_count += 1
            status = "unattempted"
            marks_awarded = 0.0
        else:
            attempted_count += 1
            if user_opt == correct_opt:
                correct_count += 1
                status = "correct"
                marks_awarded = q_marks
                positive_marks += q_marks
            else:
                incorrect_count += 1
                status = "incorrect"
                marks_awarded = -q_negative
                negative_marks_deducted += q_negative

        evaluated_results.append(QuestionReviewItem(
            question_number=q_num,
            question=q.get("question", ""),
            options=q.get("options"),
            selected_option=user_opt,
            correct_answer=correct_opt,
            status=status,
            marks_awarded=round(marks_awarded, 2),
            explanation=q.get("explanation"),
            chapter_reference=q.get("chapter_reference")
        ))

    net_score = max(0.0, round(positive_marks - negative_marks_deducted, 2))
    total_possible_marks = round(total_possible_marks, 2) if total_possible_marks > 0 else 100.0
    percentage = round((net_score / total_possible_marks) * 100, 2)
    accuracy = round((correct_count / attempted_count) * 100, 2) if attempted_count > 0 else 0.0

    now_utc = datetime.now(timezone.utc)

    # Persist submission document
    submission_doc = {
        "user_id": current_user.get("sub"),
        "student_id": student_id_str,
        "student_name": student_name_str,
        "paper_id": str(paper_doc["_id"]),
        "task_id": paper_doc.get("task_id"),
        "paper_title": paper_obj.get("paper_title") or f"{paper_doc.get('exam_name')} Paper",
        "exam_name": paper_doc.get("exam_name") or paper_obj.get("exam_name", "Competitive Exam"),
        "subject": paper_obj.get("subject", "General Studies"),
        "total_questions": total_q,
        "attempted_count": attempted_count,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "unattempted_count": unattempted_count,
        "total_marks": total_possible_marks,
        "score": net_score,
        "positive_marks": round(positive_marks, 2),
        "negative_marks_deducted": round(negative_marks_deducted, 2),
        "percentage": percentage,
        "accuracy": accuracy,
        "time_taken_seconds": payload.time_taken_seconds,
        "submitted_at": now_utc,
        "user_answers": {str(k): v for k, v in user_answers_map.items()},
        "results": [r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in evaluated_results]
    }

    sub_res = await db.competitive_exam_submissions.insert_one(submission_doc)
    submission_id = str(sub_res.inserted_id)

    summary = ExamSubmissionSummary(
        submission_id=submission_id,
        paper_id=str(paper_doc["_id"]),
        paper_title=submission_doc["paper_title"],
        exam_name=submission_doc["exam_name"],
        subject=submission_doc["subject"],
        total_questions=total_q,
        attempted_count=attempted_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unattempted_count=unattempted_count,
        total_marks=total_possible_marks,
        net_score=net_score,
        positive_marks=round(positive_marks, 2),
        negative_marks_deducted=round(negative_marks_deducted, 2),
        percentage=percentage,
        accuracy=accuracy,
        time_taken_seconds=payload.time_taken_seconds,
        submitted_at=now_utc.isoformat()
    )

    return ExamResultResponse(
        status="success",
        message="Exam submitted and evaluated successfully.",
        summary=summary,
        results=evaluated_results
    )


# ===========================================================================
# 5. ATTEMPT HISTORY & ANALYTICS
# ===========================================================================

@router.get("/competitive-exams/attempts")
async def get_user_attempts(
    student_id: Optional[str] = Query(None, description="Optional target Student ID"),
    exam_name: Optional[str] = Query(None, description="Filter by Exam Name"),
    limit: int = Query(20, ge=1, le=50),
    skip: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of past exam attempts for the student.
    """
    student = await resolve_student(current_user, student_id)
    sid = str(student["_id"]) if student else str(student_id or current_user.get("sub", ""))

    query: Dict[str, Any] = {
        "$or": [
            {"student_id": sid},
            {"user_id": current_user.get("sub")}
        ]
    }
    if exam_name and exam_name.strip():
        query["exam_name"] = exam_name.strip()

    total_count = await db.competitive_exam_submissions.count_documents(query)
    submissions = await db.competitive_exam_submissions.find(
        query,
        {"results": 0}  # Exclude heavy question arrays in list view
    ).sort("submitted_at", -1).skip(skip).limit(limit).to_list(None)

    clean_attempts = []
    for s in submissions:
        clean_attempts.append({
            "submission_id": str(s["_id"]),
            "paper_id": s.get("paper_id"),
            "paper_title": s.get("paper_title"),
            "exam_name": s.get("exam_name"),
            "subject": s.get("subject"),
            "score": s.get("score", 0.0),
            "total_marks": s.get("total_marks", 100),
            "percentage": s.get("percentage", 0.0),
            "accuracy": s.get("accuracy", 0.0),
            "attempted_count": s.get("attempted_count", 0),
            "total_questions": s.get("total_questions", 0),
            "time_taken_seconds": s.get("time_taken_seconds"),
            "submitted_at": s.get("submitted_at").isoformat() if isinstance(s.get("submitted_at"), datetime) else str(s.get("submitted_at", ""))
        })

    return {
        "status": "success",
        "total_attempts": total_count,
        "returned_count": len(clean_attempts),
        "attempts": clean_attempts
    }


@router.get("/competitive-exams/attempts/{submission_id}")
async def get_attempt_detail(
    submission_id: str = Path(..., description="Submission ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve full question-by-question review of a previously completed test attempt.
    """
    if not ObjectId.is_valid(submission_id):
        raise HTTPException(status_code=400, detail="Invalid submission ID format")

    sub = await db.competitive_exam_submissions.find_one({"_id": ObjectId(submission_id)})
    if not sub:
        raise HTTPException(status_code=404, detail="Exam submission attempt not found")

    sub["_id"] = str(sub["_id"])
    if isinstance(sub.get("submitted_at"), datetime):
        sub["submitted_at"] = sub["submitted_at"].isoformat()

    return {
        "status": "success",
        "attempt": sub
    }


@router.get("/competitive-exams/analytics", response_model=CompetitiveAnalyticsResponse)
async def get_competitive_analytics(
    student_id: Optional[str] = Query(None, description="Optional target Student ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Aggregated performance analytics for the student across all competitive exams.
    Includes average scores, accuracy rate, subject-wise strengths, and recent progress.
    """
    student = await resolve_student(current_user, student_id)
    sid = str(student["_id"]) if student else str(student_id or current_user.get("sub", "learner"))
    sname = student.get("student_name", "Learner") if student else "Learner"

    query = {
        "$or": [
            {"student_id": sid},
            {"user_id": current_user.get("sub")}
        ]
    }

    submissions = await db.competitive_exam_submissions.find(query).sort("submitted_at", -1).to_list(100)

    total_tests = len(submissions)
    if total_tests == 0:
        return CompetitiveAnalyticsResponse(
            status="success",
            student_id=sid,
            student_name=sname,
            total_tests_taken=0,
            average_score=0.0,
            average_percentage=0.0,
            average_accuracy=0.0,
            total_questions_attempted=0,
            total_correct=0,
            total_incorrect=0,
            subject_performance={},
            recent_attempts=[]
        )

    total_score = sum(s.get("score", 0.0) for s in submissions)
    total_percentage = sum(s.get("percentage", 0.0) for s in submissions)
    total_accuracy = sum(s.get("accuracy", 0.0) for s in submissions)
    total_attempted_q = sum(s.get("attempted_count", 0) for s in submissions)
    total_correct_q = sum(s.get("correct_count", 0) for s in submissions)
    total_incorrect_q = sum(s.get("incorrect_count", 0) for s in submissions)

    # Subject-wise analysis
    subject_map: Dict[str, Dict[str, Any]] = {}
    for s in submissions:
        subj = s.get("subject", "General Studies")
        if subj not in subject_map:
            subject_map[subj] = {
                "tests_taken": 0,
                "total_score": 0.0,
                "total_possible": 0.0,
                "correct": 0,
                "attempted": 0
            }
        subject_map[subj]["tests_taken"] += 1
        subject_map[subj]["total_score"] += s.get("score", 0.0)
        subject_map[subj]["total_possible"] += s.get("total_marks", 100.0)
        subject_map[subj]["correct"] += s.get("correct_count", 0)
        subject_map[subj]["attempted"] += s.get("attempted_count", 0)

    clean_subj_perf = {}
    for subj, data in subject_map.items():
        avg_pct = round((data["total_score"] / data["total_possible"] * 100), 2) if data["total_possible"] > 0 else 0.0
        acc = round((data["correct"] / data["attempted"] * 100), 2) if data["attempted"] > 0 else 0.0
        clean_subj_perf[subj] = {
            "tests_taken": data["tests_taken"],
            "average_percentage": avg_pct,
            "accuracy": acc
        }

    recent_summary = []
    for s in submissions[:10]:
        recent_summary.append({
            "submission_id": str(s["_id"]),
            "paper_title": s.get("paper_title"),
            "exam_name": s.get("exam_name"),
            "subject": s.get("subject"),
            "score": s.get("score"),
            "total_marks": s.get("total_marks"),
            "percentage": s.get("percentage"),
            "accuracy": s.get("accuracy"),
            "submitted_at": s.get("submitted_at").isoformat() if isinstance(s.get("submitted_at"), datetime) else str(s.get("submitted_at", ""))
        })

    return CompetitiveAnalyticsResponse(
        status="success",
        student_id=sid,
        student_name=sname,
        total_tests_taken=total_tests,
        average_score=round(total_score / total_tests, 2),
        average_percentage=round(total_percentage / total_tests, 2),
        average_accuracy=round(total_accuracy / total_tests, 2),
        total_questions_attempted=total_attempted_q,
        total_correct=total_correct_q,
        total_incorrect=total_incorrect_q,
        subject_performance=clean_subj_perf,
        recent_attempts=recent_summary
    )
