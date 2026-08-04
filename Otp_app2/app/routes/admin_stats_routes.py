from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import asyncio

from app.core.database import db
from app.utils.admin_auth import require_permission
from bson import ObjectId

router = APIRouter(tags=["Admin Stats"])


@router.get("/stats/summary", response_model=Dict[str, Any])
async def get_dashboard_summary(current_admin: dict = Depends(require_permission("Analytics", "read"))):
    """
    Returns aggregated KPI stats for the admin dashboard.
    All 6 queries run in parallel for performance.
    """
    try:
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        thirty_days_ago = now - timedelta(days=30)

        async def count_students():
            return await db.students.count_documents({})

        async def count_parents():
            return await db.usertable.count_documents({"usertype": "parent"})

        async def count_active_users():
            # Users who have an OTP record updated in last 30 days (proxy for logins)
            return await db.otps.count_documents({
                "created_at": {"$gte": thirty_days_ago}
            })

        async def count_exams_generated():
            return await db.generated_papers.count_documents({})

        async def count_quiz_questions():
            return await db.quiz_questions.count_documents({"is_active": True})

        async def get_ai_cost_this_month():
            pipeline = [
                {"$match": {"timestamp": {"$gte": start_of_month}}},
                {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return round(result[0]["total"], 4) if result else 0.0

        # Run all queries in parallel
        (
            total_students,
            total_parents,
            active_users_30d,
            total_exams_generated,
            total_quiz_questions,
            ai_cost_this_month_usd
        ) = await asyncio.gather(
            count_students(),
            count_parents(),
            count_active_users(),
            count_exams_generated(),
            count_quiz_questions(),
            get_ai_cost_this_month()
        )

        return {
            "status": "success",
            "data": {
                "total_students": total_students,
                "total_parents": total_parents,
                "active_users_30d": active_users_30d,
                "total_exams_generated": total_exams_generated,
                "total_quiz_questions": total_quiz_questions,
                "ai_cost_this_month_usd": ai_cost_this_month_usd
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/ai-stats/student/{student_id}", response_model=Dict[str, Any])
async def get_student_ai_summary(
    student_id: str,
    current_admin: dict = Depends(require_permission("Analytics", "read"))
):
    """
    Returns AI usage analytics for a single student (last 30 days)
    """

    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        base_match = {
            "student_id": student_id,
            "timestamp": {"$gte": thirty_days_ago}
        }

        # -----------------------------
        # TOTAL TOKENS
        # -----------------------------
        async def total_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return result[0]["total"] if result else 0

        # -----------------------------
        # TOTAL CALLS
        # -----------------------------
        async def total_calls():
            return await db.ai_usage_logs.count_documents(base_match)

        # -----------------------------
        # TOTAL COST
        # -----------------------------
        async def total_cost():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None,
                            "total": {"$sum": "$estimated_cost_usd"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return round(result[0]["total"], 4) if result else 0.0

        # -----------------------------
        # COST BY MODULE
        # -----------------------------
        async def module_costs():
            pipeline = [
                {"$match": base_match},
                {
                    "$group": {
                        "_id": "$action_type",
                        "cost": {"$sum": "$estimated_cost_usd"}
                    }
                }
            ]

            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)

            return {
                "labels": [r["_id"] if r["_id"] else "Other" for r in results],
                "costs": [round(r["cost"], 4) for r in results]
            }

        # -----------------------------
        # TOKENS BY MODEL
        # -----------------------------
        async def model_tokens():
            pipeline = [
                {"$match": base_match},
                {
                    "$group": {
                        "_id": "$model_used",
                        "tokens": {"$sum": "$total_tokens"}
                    }
                }
            ]

            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)

            return {
                "labels": [r["_id"] for r in results],
                "tokens": [r["tokens"] for r in results]
            }

        # -----------------------------
        # STUDENT INFO
        # -----------------------------
        async def student_info():
            try:
                return await db.students.find_one(
                    {"_id": ObjectId(student_id)},
                    {"student_name": 1}
                )
            except:
                return None

        (
            tokens,
            calls,
            cost,
            module_data,
            model_data,
            student
        ) = await asyncio.gather(
            total_tokens(),
            total_calls(),
            total_cost(),
            module_costs(),
            model_tokens(),
            student_info()
        )

        return {
            "status": "success",
            "data": {
                "student_id": student_id,
                "student_name": student.get("student_name", "Unknown")
                if student else "Unknown",
                "total_tokens": tokens,
                "total_calls": calls,
                "total_cost_usd": cost,
                "module_costs": module_data,
                "model_tokens": model_data
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





@router.get("/ai-stats/class/{class_name}", response_model=Dict[str, Any])
async def get_class_ai_summary(
    class_name: str,
    current_admin: dict = Depends(require_permission("Analytics", "read"))
):
    """
    Returns AI usage analytics for all students in a specific class (last 30 days)
    """
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # 1. Get all student IDs in this class
        cursor = db.students.find({"student_class": class_name}, {"_id": 1})
        students = await cursor.to_list(length=None)
        student_ids = [str(s["_id"]) for s in students]

        if not student_ids:
            return {
                "status": "success",
                "data": {
                    "total_tokens": 0, "total_calls": 0, "total_cost_usd": 0.0,
                    "module_costs": {"labels": [], "costs": []},
                    "model_tokens": {"labels": [], "tokens": []}
                }
            }

        base_match = {
            "student_id": {"$in": student_ids},
            "timestamp": {"$gte": thirty_days_ago}
        }

        # Aggregation logic (same as summary but filtered by class)
        async def total_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return result[0]["total"] if result else 0

        async def total_calls():
            return await db.ai_usage_logs.count_documents(base_match)

        async def total_cost():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return round(result[0]["total"], 4) if result else 0.0

        async def module_costs():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$action_type", "cost": {"$sum": "$estimated_cost_usd"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            return {
                "labels": [r["_id"] if r["_id"] else "Other" for r in results],
                "costs": [round(r["cost"], 4) for r in results]
            }

        async def model_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$model_used", "tokens": {"$sum": "$total_tokens"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            return {
                "labels": [r["_id"] if r["_id"] else "Other" for r in results],
                "tokens": [r["tokens"] for r in results]
            }

        (tokens, calls, cost, module_data, model_data) = await asyncio.gather(
            total_tokens(),
            total_calls(),
            total_cost(),
            module_costs(),
            model_tokens()
        )

        return {
            "status": "success",
            "data": {
                "class_name": class_name,
                "total_tokens": tokens,
                "total_calls": calls,
                "total_cost_usd": cost,
                "module_costs": module_data,
                "model_tokens": model_data
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-stats/summary", response_model=Dict[str, Any])
async def get_platform_ai_usage_summary(current_admin: dict = Depends(require_permission("Analytics", "read"))):
    """
    Returns platform-wide AI usage analytics (last 30 days)
    """
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        base_match = {
            "timestamp": {"$gte": thirty_days_ago}
        }

        # -----------------------------
        # TOTAL TOKENS
        # -----------------------------
        async def total_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return result[0]["total"] if result else 0

        # -----------------------------
        # TOTAL CALLS
        # -----------------------------
        async def total_calls():
            return await db.ai_usage_logs.count_documents(base_match)

        # -----------------------------
        # TOTAL COST
        # -----------------------------
        async def total_cost():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return round(result[0]["total"], 4) if result else 0.0

        async def module_costs():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$action_type", "cost": {"$sum": "$estimated_cost_usd"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            labels = [r["_id"] if r["_id"] else "Other" for r in results]
            costs = [round(r["cost"], 4) for r in results]
            return {"labels": labels, "costs": costs}

        # -----------------------------
        # TOKENS BY MODEL
        # -----------------------------
        async def model_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$model_used", "tokens": {"$sum": "$total_tokens"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            labels = [r["_id"] if r["_id"] else "Other" for r in results]
            tokens = [r["tokens"] for r in results]
            return {"labels": labels, "tokens": tokens}

        (tokens, calls, cost, module_data, model_data) = await asyncio.gather(
            total_tokens(),
            total_calls(),
            total_cost(),
            module_costs(),
            model_tokens()
        )

        return {
            "status": "success",
            "data": {
                "total_tokens": tokens,
                "total_calls": calls,
                "total_cost_usd": cost,
                "module_costs": module_data,
                "model_tokens": model_data
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def serialize_student(doc):
    return {
        "id": str(doc["_id"]),
        "name": doc.get("student_name", "Unnamed Student"),
        "class": doc.get("student_class"),
        "image_url": doc.get("image_url")
    }


@router.get("/ai-stats/get_students")
async def get_students(admin=Depends(require_permission("Analytics", "read"))):

    cursor = db.students.find({})
    students = await cursor.to_list(length=None)

    serialized_students = [
        serialize_student(student)
        for student in students
    ]

    return {
        "status": "success",
        "students": serialized_students
    }


@router.get("/ai-stats/summary", response_model=Dict[str, Any])
async def get_platform_ai_usage_summary(current_admin: dict = Depends(require_permission("Analytics", "read"))):
    """
    Returns platform-wide AI usage analytics (last 30 days)
    """
    try:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        base_match = {
            "timestamp": {"$gte": thirty_days_ago}
        }

        # -----------------------------
        # TOTAL TOKENS
        # -----------------------------
        async def total_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$total_tokens"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return result[0]["total"] if result else 0

        # -----------------------------
        # TOTAL CALLS
        # -----------------------------
        async def total_calls():
            return await db.ai_usage_logs.count_documents(base_match)

        # -----------------------------
        # TOTAL COST
        # -----------------------------
        async def total_cost():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}}
            ]
            result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
            return round(result[0]["total"], 4) if result else 0.0

        async def module_costs():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$action_type", "cost": {"$sum": "$estimated_cost_usd"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            labels = [r["_id"] if r["_id"] else "Other" for r in results]
            costs = [round(r["cost"], 4) for r in results]
            return {"labels": labels, "costs": costs}

        # -----------------------------
        # TOKENS BY MODEL
        # -----------------------------
        async def model_tokens():
            pipeline = [
                {"$match": base_match},
                {"$group": {"_id": "$model_used", "tokens": {"$sum": "$total_tokens"}}}
            ]
            results = await db.ai_usage_logs.aggregate(pipeline).to_list(None)
            labels = [r["_id"] if r["_id"] else "Other" for r in results]
            tokens = [r["tokens"] for r in results]
            return {"labels": labels, "tokens": tokens}

        (tokens, calls, cost, module_data, model_data) = await asyncio.gather(
            total_tokens(),
            total_calls(),
            total_cost(),
            module_costs(),
            model_tokens()
        )

        return {
            "status": "success",
            "data": {
                "total_tokens": tokens,
                "total_calls": calls,
                "total_cost_usd": cost,
                "module_costs": module_data,
                "model_tokens": model_data
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def serialize_student(doc):
    return {
        "id": str(doc["_id"]),
        "name": doc.get("student_name", "Unnamed Student"),
        "class": doc.get("student_class"),
        "image_url": doc.get("image_url")
    }


@router.get("/ai-stats/get_students")
async def get_students(admin=Depends(require_permission("Analytics", "read"))):

    cursor = db.students.find({})
    students = await cursor.to_list(length=None)

    serialized_students = [
        serialize_student(student)
        for student in students
    ]

    return {
        "status": "success",
        "students": serialized_students
    }


@router.get("/stats/staff-activity")
async def get_staff_activity(current_admin: dict = Depends(require_permission("Analytics", "read"))):
    """
    Returns aggregated staff data-entry activity logs, including a leaderboard,
    daily activity volume trend, and recent raw logs.
    """
    try:
        # 1. Leaderboard - Count all staff activity (any status except 'processing')
        leaderboard_pipeline = [
            {"$match": {"status": {"$nin": ["processing"]}}},
            {"$group": {"_id": "$username", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]
        leaderboard_cursor = db.admin_activity_logs.aggregate(leaderboard_pipeline)
        leaderboard = await leaderboard_cursor.to_list(length=10)
        
        # 2. Daily Trend (last 30 days) - All statuses, group by date
        # Use a simple date string group to avoid timezone comparison issues
        daily_pipeline = [
            {"$match": {"status": {"$nin": ["processing"]}}},
            {"$project": {
                "date_str": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$timestamp"
                    }
                }
            }},
            {"$group": {
                "_id": "$date_str",
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}},
            {"$limit": 30}
        ]
        daily_cursor = db.admin_activity_logs.aggregate(daily_pipeline)
        daily_trend = await daily_cursor.to_list(length=30)
        
        # 3. Recent logs (show all, including failures)
        recent_cursor = db.admin_activity_logs.find({}).sort("timestamp", -1).limit(50)
        recent_logs = await recent_cursor.to_list(length=50)
        
        # Helper to serialize log docs
        def serialize_log(log):
            ts = log.get("timestamp")
            if hasattr(ts, "isoformat"):
                ts_str = ts.isoformat()
            elif ts is not None:
                ts_str = str(ts)
            else:
                ts_str = None
            return {
                "id": str(log["_id"]),
                "username": log.get("username"),
                "role": log.get("role"),
                "action": log.get("action"),
                "status": log.get("status", "success"),
                "details": log.get("details"),
                "task_id": log.get("task_id"),
                "timestamp": ts_str
            }
            
        return {
            "status": "success",
            "data": {
                "leaderboard": [{"username": item["_id"], "count": item["count"]} for item in leaderboard],
                "daily_trend": [{"date": item["_id"], "count": item["count"]} for item in daily_trend],
                "recent_logs": [serialize_log(log) for log in recent_logs]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/staff-profile/{username}", response_model=Dict[str, Any])
async def get_staff_profile(
    username: str,
    current_admin: dict = Depends(require_permission("Analytics", "read"))
):
    """
    Returns a detailed productivity profile for a single staff member.
    Includes all-time KPIs, action breakdown by type, and recent logs.
    """
    try:
        base_match = {"username": username}

        # ── 1. Total events ────────────────────────────────────────
        async def total_events():
            return await db.admin_activity_logs.count_documents(base_match)

        # ── 2. Success count ───────────────────────────────────────
        async def success_count():
            return await db.admin_activity_logs.count_documents(
                {**base_match, "status": {"$in": ["success", "completed"]}}
            )

        # ── 3. Failed count ────────────────────────────────────────
        async def failed_count():
            return await db.admin_activity_logs.count_documents(
                {**base_match, "status": "failed"}
            )

        # ── 4. Action breakdown (group by action type) ─────────────
        async def action_breakdown():
            pipeline = [
                {"$match": {**base_match, "status": {"$nin": ["processing"]}}},
                {
                    "$group": {
                        "_id": "$action",
                        "total": {"$sum": 1},
                        "success": {
                            "$sum": {
                                "$cond": [
                                    {"$in": ["$status", ["success", "completed"]]},
                                    1, 0
                                ]
                            }
                        },
                        "failed": {
                            "$sum": {
                                "$cond": [{"$eq": ["$status", "failed"]}, 1, 0]
                            }
                        },
                        "last_done": {"$max": "$timestamp"}
                    }
                },
                {"$sort": {"total": -1}}
            ]
            results = await db.admin_activity_logs.aggregate(pipeline).to_list(None)
            return [
                {
                    "action": r["_id"] or "Unknown",
                    "total": r["total"],
                    "success": r["success"],
                    "failed": r["failed"],
                    "last_done": r["last_done"].isoformat() if r.get("last_done") else None
                }
                for r in results
            ]

        # ── 5. Recent logs (last 25) ───────────────────────────────
        async def recent_logs():
            cursor = db.admin_activity_logs.find(base_match).sort("timestamp", -1).limit(25)
            logs = await cursor.to_list(length=25)

            def serialize(log):
                ts = log.get("timestamp")
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
                return {
                    "id": str(log["_id"]),
                    "action": log.get("action", ""),
                    "status": log.get("status", "success"),
                    "details": log.get("details", ""),
                    "timestamp": ts_str
                }

            return [serialize(l) for l in logs]

        # ── 6. Last active timestamp ───────────────────────────────
        async def last_active():
            doc = await db.admin_activity_logs.find_one(
                base_match,
                sort=[("timestamp", -1)]
            )
            if doc and doc.get("timestamp"):
                return doc["timestamp"].isoformat()
            return None

        # ── Run all in parallel ────────────────────────────────────
        (total, success, failed, breakdown, logs, last_ts) = await asyncio.gather(
            total_events(),
            success_count(),
            failed_count(),
            action_breakdown(),
            recent_logs(),
            last_active()
        )

        return {
            "status": "success",
            "data": {
                "username": username,
                "total_events": total,
                "success_count": success,
                "failed_count": failed,
                "action_breakdown": breakdown,
                "recent_logs": logs,
                "last_active": last_ts
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
