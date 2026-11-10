from fastapi import APIRouter, HTTPException, Depends, Query, Path, Body, Request
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any, Union
from bson import ObjectId
from datetime import datetime, timezone
import os
import re
import json

from app.core.database import db
from app.utils.user_auth import get_current_user
from app.services.youtube_service import youtube_service
from app.utils.timezone_utils import get_ist_now, to_ist_iso

router = APIRouter(tags=["Competitive Exams - User"])

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def serialize_mongo(data: Any) -> Any:
    """
    Recursively converts BSON ObjectId, datetime, or any non-JSON-serializable
    Mongo structures into clean serializable primitives (strings/dicts/lists).
    """
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, dict):
        return {k: serialize_mongo(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [serialize_mongo(item) for item in data]
    return data


def natural_sort_key(s):
    if not s:
        return []
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def fetch_youtube_videos_for_tutorial(youtube_url: str, title: Optional[str] = None) -> List[dict]:
    """
    Fetches videos from YouTube URL (supports playlist, channel, and single video links).
    Falls back gracefully if YouTube API key is missing or quota exceeded.
    Used by admin tutorial creation and user views.
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
            "published_at": get_ist_now().strftime("%Y-%m-%d"),
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
        "published_at": get_ist_now().strftime("%Y-%m-%d"),
        "link": url,
        "thumbnail": ""
    }]


# ===========================================================================
# 1. GET – LIST EXAM CATEGORIES
# ===========================================================================

@router.get(
    "/competitive-exams/categories",
    summary="List Exam Categories",
    description="Fetch and display all available competitive exam categories dynamically."
)
async def list_categories():
    """
    Fetch and display all available competitive exam categories.
    Display the categories dynamically in the UI.
    When the user selects a category, pass the selected category object or identifier to the Tutorials API.
    """
    categories = await db.competitive_exam_categories.find({"is_active": {"$ne": False}}).sort("category_name", 1).to_list(None)

    for cat in categories:
        cat["_id"] = str(cat["_id"])
        c_name = cat.get("category_name", "")
        c_id = cat["_id"]

        # Count available exams under this category
        cat["exam_count"] = await db.competitive_exams.count_documents({
            "$or": [{"category_id": c_id}, {"category_name": c_name}],
            "is_active": {"$ne": False}
        })
        # Count available tutorials under this category
        cat["tutorial_count"] = await db.competitive_tutorials.count_documents({
            "$or": [{"category_id": c_id}, {"category_name": c_name}, {"exam_category": c_name}],
            "is_active": {"$ne": False}
        })
        # Count available textbooks under this category
        cat["textbook_count"] = await db.textbook.count_documents({
            "$or": [
                {"category_id": c_id},
                {"exam_category": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}},
                {"category": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}},
                {"state": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}},
                {"board": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}}
            ]
        })

        if "created_at" in cat:
            cat["created_at"] = to_ist_iso(cat["created_at"])
        if "updated_at" in cat:
            cat["updated_at"] = to_ist_iso(cat["updated_at"])

    return serialize_mongo({
        "status": "success",
        "total_categories": len(categories),
        "categories": categories
    })


# ===========================================================================
# 2. GET – GET COMPETITIVE TUTORIALS & TEXTBOOKS
# ===========================================================================

@router.get(
    "/competitive-exams/tutorials",
    summary="Get Competitive Tutorials",
    description="Fetch competitive exam tutorials based on the selected exam category ID, including relevant tutorial links and associated textbooks."
)
async def get_competitive_tutorials(
    category_id: Optional[str] = Query(None, description="Category ID from List Exam Categories API")
):
    """
    Fetch competitive exam tutorials and associated textbooks based on the selected exam category ID.
    Accepts category_id from the Categories API.
    Returns both the relevant tutorial links and the textbooks associated with that category.
    """
    category_id = category_id.strip() if isinstance(category_id, str) else None

    # ── 1. Resolve Category Identifier from category_id ─────────────────────
    target_category_name = None
    target_category_id = None

    if category_id:
        if ObjectId.is_valid(category_id):
            target_category_id = category_id
            cat_doc = await db.competitive_exam_categories.find_one({"_id": ObjectId(category_id)})
            if cat_doc:
                target_category_name = cat_doc.get("category_name")
        else:
            # Fallback if category_id is stored as string ID or was passed as category name
            target_category_id = category_id
            cat_doc = await db.competitive_exam_categories.find_one({
                "$or": [
                    {"category_id": category_id},
                    {"category_name": {"$regex": f"^{re.escape(category_id)}$", "$options": "i"}}
                ]
            })
            if cat_doc:
                target_category_id = str(cat_doc["_id"])
                target_category_name = cat_doc.get("category_name")
            else:
                target_category_name = category_id

    # ── 2. Query Competitive Tutorials ──────────────────────────────────────
    tut_query: Dict[str, Any] = {"is_active": {"$ne": False}}

    if target_category_name or target_category_id:
        cat_or_filters = []
        if target_category_id:
            cat_or_filters.append({"category_id": target_category_id})
        if target_category_name:
            c_escaped = re.escape(target_category_name)
            cat_or_filters.extend([
                {"category_name": {"$regex": c_escaped, "$options": "i"}},
                {"exam_category": {"$regex": c_escaped, "$options": "i"}}
            ])

        if len(cat_or_filters) == 1:
            tut_query.update(cat_or_filters[0])
        elif cat_or_filters:
            tut_query["$or"] = cat_or_filters

    tut_cursor = db.competitive_tutorials.find(tut_query).sort("_id", -1)
    tut_items = await tut_cursor.to_list(length=None)

    clean_tutorials = []
    for item in tut_items:
        t_id = str(item["_id"])
        clean_tutorials.append({
            "_id": t_id,
            "tutorial_id": t_id,
            "title": item.get("title") or f"{item.get('exam_name', '')} - {item.get('subject', '')}",
            "category_id": item.get("category_id") or target_category_id or "",
            "category_name": item.get("category_name") or item.get("exam_category") or target_category_name or "",
            "exam_name": item.get("exam_name", ""),
            "subject": item.get("subject", ""),
            "topic": item.get("topic", ""),
            "description": item.get("description", ""),
            "youtube_url": item.get("youtube_url", ""),
            "video_links": item.get("video_links", []),
            "videos_count": len(item.get("video_links", [])),
            "is_active": item.get("is_active", True),
            "created_at": to_ist_iso(item.get("created_at")),
            "updated_at": to_ist_iso(item.get("updated_at"))
        })

    # ── 3. Query Textbooks Associated with Selected Category ───────────────
    tb_query: Dict[str, Any] = {
        "$or": [
            {"module_type": "competitive_exam"},
            {"board": "Competitive Exams"},
            {"exam_name": {"$exists": True, "$ne": None, "$ne": ""}}
        ]
    }

    if target_category_name or target_category_id:
        tb_cat_or_filters = []
        if target_category_id:
            tb_cat_or_filters.append({"category_id": target_category_id})
        if target_category_name:
            cat_escaped = re.escape(target_category_name)
            tb_cat_or_filters.extend([
                {"exam_category": {"$regex": cat_escaped, "$options": "i"}},
                {"category": {"$regex": cat_escaped, "$options": "i"}},
                {"state": {"$regex": cat_escaped, "$options": "i"}},
                {"board": {"$regex": cat_escaped, "$options": "i"}}
            ])
        tb_query["$and"] = [{"$or": tb_cat_or_filters}]

    tb_cursor = db.textbook.find(tb_query).sort("created_at", -1)
    tb_items = await tb_cursor.to_list(length=None)

    clean_textbooks = []
    for tb in tb_items:
        tb_id = str(tb["_id"])
        raw_chapters = tb.get("chapters", [])
        sorted_chapters = sorted(raw_chapters, key=natural_sort_key) if isinstance(raw_chapters, list) else []

        pdf_url = tb.get("pdf_url") or tb.get("download_url") or tb.get("file_url")
        if not pdf_url:
            filename = tb.get("filename") or f"comp_tb_{tb_id}.pdf"
            pdf_url = f"/static/textbook/{filename}"

        clean_textbooks.append({
            "textbook_id": tb_id,
            "_id": tb_id,
            "textbook_title": tb.get("textbook_title") or tb.get("textbook_name", "Competitive Textbook"),
            "category_id": tb.get("category_id") or target_category_id or "",
            "exam_category": tb.get("exam_category") or tb.get("board", target_category_name or "Competitive Exams"),
            "exam_name": tb.get("exam_name") or tb.get("standard", "Competitive Exam"),
            "subject": tb.get("subject", "General Studies"),
            "total_pages": tb.get("total_pages") or tb.get("page_count", 0),
            "chapters_count": len(sorted_chapters),
            "pdf_url": pdf_url,
            "download_url": pdf_url,
            "file_url": pdf_url,
            "original_filename": tb.get("original_filename", ""),
            "uploaded_at": to_ist_iso(tb.get("created_at")),
            "created_at": to_ist_iso(tb.get("created_at"))
        })

    return serialize_mongo({
        "status": "success",
        "category_id": str(target_category_id) if target_category_id else None,
        "category_name": target_category_name or (str(target_category_id) if target_category_id else ""),
        "category": target_category_name or (str(target_category_id) if target_category_id else "All"),
        "total_tutorials": len(clean_tutorials),
        "total_textbooks": len(clean_textbooks),
        "total_count": len(clean_tutorials),
        "returned_count": len(clean_tutorials),
        "tutorials": clean_tutorials,
        "textbooks": clean_textbooks
    })
