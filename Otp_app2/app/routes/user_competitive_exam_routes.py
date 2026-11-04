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
from app.services.youtube_service import youtube_service
from app.models.competitive_exam_models import (
    CompetitiveVideoLink,
    CompetitiveTutorialCreateRequest,
    CompetitiveTutorialResponse
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
            print(f"[USER-COMP-PDF] Generated on-the-fly PDF: {disk_path}")
        except Exception as e:
            print(f"[USER-COMP-PDF] PDF render warning: {e}")

    return f"/generated_papers/{pdf_filename}"

def fetch_youtube_videos_for_tutorial(youtube_url: str, title: Optional[str] = None) -> List[dict]:
    """
    Fetches videos from YouTube URL (supports playlist, channel, and single video links).
    Falls back gracefully if YouTube API key is missing or quota exceeded.
    """
    if not youtube_url or not youtube_url.strip():
        return []

    url = youtube_url.strip()

    # 1. Single Video Link (e.g., watch?v=..., youtu.be/..., /embed/...)
    v_match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})", url)
    if v_match and "list=" not in url:
        vid = v_match.group(1)
        video_link = f"https://www.youtube.com/watch?v={vid}"
        fallback_item = {
            "title": title or "Video Tutorial",
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "link": video_link,
            "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
        }
        try:
            if hasattr(youtube_service, "youtube") and youtube_service.youtube:
                res = youtube_service.youtube.videos().list(part="snippet", id=vid).execute()
                items = res.get("items", [])
                if items:
                    snip = items[0].get("snippet", {})
                    thumb = (snip.get("thumbnails", {}).get("high", {}).get("url")
                             or snip.get("thumbnails", {}).get("default", {}).get("url")
                             or fallback_item["thumbnail"])
                    return [{
                        "title": snip.get("title") or title or "Video Tutorial",
                        "published_at": snip.get("publishedAt", "")[:10],
                        "link": video_link,
                        "thumbnail": thumb
                    }]
        except Exception as e:
            print(f"[Tutorial] Single video fetch warning: {e}")
        return [fallback_item]

    # 2. Playlist / Channel / Search
    try:
        extracted_id, id_type = youtube_service.extract_id(url)
        target_playlist_id = None
        if id_type == "playlist":
            target_playlist_id = extracted_id
        elif id_type == "channel":
            target_playlist_id = youtube_service.get_uploads_id(extracted_id)
        else:
            target_playlist_id, _ = youtube_service.search_playlist_by_name(url)

        if target_playlist_id:
            videos = youtube_service.fetch_videos(target_playlist_id)
            if videos:
                results = []
                for v in videos:
                    results.append({
                        "title": v.get("title") or "Tutorial Video",
                        "published_at": v.get("published_at", ""),
                        "link": v.get("link", ""),
                        "thumbnail": v.get("thumbnail") or ""
                    })
                return results
    except Exception as e:
        print(f"[Tutorial] YouTube playlist/channel fetch warning: {e}")

    # Fallback to single entry
    return [{
        "title": title or "Video Tutorial",
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "link": url,
        "thumbnail": ""
    }]


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


# ===========================================================================
# 2. TEXTBOOKS (STUDY MATERIALS)
# ===========================================================================

@router.get("/competitive-exams/textbooks")
async def list_textbooks(
    category: Optional[str] = Query(None, description="Category filter"),
    exam_name: Optional[str] = Query(None, description="Exam filter (e.g., 'KAS', 'UPSC Prelims')"),
    subject: Optional[str] = Query(None, description="Subject filter"),
    search: Optional[str] = Query(None, description="Search keyword for title, subject, or exam")
):
    """
    Browse ingested textbooks and study materials tailored for competitive exam prep.
    """
    query: Dict[str, Any] = {
        "$or": [
            {"module_type": "competitive_exam"},
            {"board": "Competitive Exams"},
            {"exam_name": {"$exists": True, "$ne": None, "$ne": ""}}
        ],
        "status": {"$in": ["completed", "cleanup_failed"]}
    }

    if category and category.strip():
        cat_term = category.strip()
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"exam_category": {"$regex": re.escape(cat_term), "$options": "i"}},
                {"category": {"$regex": re.escape(cat_term), "$options": "i"}}
            ]
        }]

    if exam_name and exam_name.strip():
        exam_term = exam_name.strip()
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"exam_name": {"$regex": re.escape(exam_term), "$options": "i"}},
                {"standard": {"$regex": re.escape(exam_term), "$options": "i"}}
            ]
        }]

    if subject and subject.strip():
        query["subject"] = {"$regex": re.escape(subject.strip()), "$options": "i"}

    if search and search.strip():
        s_term = re.escape(search.strip())
        query["$and"] = query.get("$and", []) + [{
            "$or": [
                {"textbook_title": {"$regex": s_term, "$options": "i"}},
                {"textbook_name": {"$regex": s_term, "$options": "i"}},
                {"subject": {"$regex": s_term, "$options": "i"}},
                {"exam_name": {"$regex": s_term, "$options": "i"}}
            ]
        }]

    textbooks = await db.textbook.find(query).sort("created_at", -1).to_list(100)

    clean_tbs = []
    for tb in textbooks:
        tb_id = str(tb["_id"])
        raw_chapters = tb.get("chapters", [])
        if isinstance(raw_chapters, list):
            sorted_chapters = sorted(raw_chapters, key=natural_sort_key)
        else:
            sorted_chapters = []

        total_pages = tb.get("total_pages", 0)
        chunks_count = await db.textbook_chunks.count_documents({"textbook_id": tb_id})

        clean_tbs.append({
            "textbook_id": tb_id,
            "textbook_title": tb.get("textbook_title") or tb.get("textbook_name", "Competitive Textbook"),
            "exam_category": tb.get("exam_category") or tb.get("board", "Competitive Exams"),
            "exam_name": tb.get("exam_name") or tb.get("standard", "Competitive Exam"),
            "subject": tb.get("subject", "General Studies"),
            "total_pages": total_pages,
            "chapters_count": len(sorted_chapters),
            "chapters": sorted_chapters,
            "vector_chunks_indexed": chunks_count,
            "uploaded_at": tb.get("created_at").isoformat() if isinstance(tb.get("created_at"), datetime) else str(tb.get("created_at", ""))
        })

    return {
        "status": "success",
        "total_textbooks": len(clean_tbs),
        "textbooks": clean_tbs
    }


# ===========================================================================
# 3. QUESTION PAPERS
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
# ===========================================================================
# 4. COMPETITIVE EXAMS TUTORIALS (READ-ONLY FOR USERS)
# ===========================================================================

@router.get("/competitive-exams/tutorials")
async def get_competitive_tutorials(
    category: Optional[str] = Query(None, description="Filter by Category"),
    exam_name: Optional[str] = Query(None, description="Filter by Exam Name"),
    subject: Optional[str] = Query(None, description="Filter by Subject"),
    topic: Optional[str] = Query(None, description="Filter by Topic"),
    search: Optional[str] = Query(None, description="Keyword search in title/topic/subject"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0)
):
    """
    Get tutorials for competitive exams with flexible filtering.
    """
    query: Dict[str, Any] = {"is_active": {"$ne": False}}

    if category and category.strip():
        query["$or"] = [
            {"category_name": {"$regex": re.escape(category.strip()), "$options": "i"}},
            {"exam_category": {"$regex": re.escape(category.strip()), "$options": "i"}}
        ]
    if exam_name and exam_name.strip():
        query["exam_name"] = {"$regex": re.escape(exam_name.strip()), "$options": "i"}
    if subject and subject.strip():
        query["subject"] = {"$regex": re.escape(subject.strip()), "$options": "i"}
    if topic and topic.strip():
        query["topic"] = {"$regex": re.escape(topic.strip()), "$options": "i"}
    if search and search.strip():
        s = re.escape(search.strip())
        query["$or"] = [
            {"title": {"$regex": s, "$options": "i"}},
            {"subject": {"$regex": s, "$options": "i"}},
            {"topic": {"$regex": s, "$options": "i"}},
            {"exam_name": {"$regex": s, "$options": "i"}}
        ]

    total = await db.competitive_tutorials.count_documents(query)
    cursor = db.competitive_tutorials.find(query).sort("_id", -1).skip(skip).limit(limit)
    items = await cursor.to_list(length=limit)

    for item in items:
        item["_id"] = str(item["_id"])
        if isinstance(item.get("created_at"), datetime):
            item["created_at"] = item["created_at"].isoformat()
        if isinstance(item.get("updated_at"), datetime):
            item["updated_at"] = item["updated_at"].isoformat()
        item["videos_count"] = len(item.get("video_links", []))

    return {
        "status": "success",
        "total_count": total,
        "returned_count": len(items),
        "tutorials": items
    }
