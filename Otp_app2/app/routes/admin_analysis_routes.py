from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from app.core.database import db
from app.utils.admin_auth import require_permission

router = APIRouter(prefix="/ai-stats", tags=["Admin AI Analytics"])

@router.get("/summary", response_model=Dict[str, Any])
async def get_ai_usage_summary(days: int = 30, current_admin: dict = Depends(require_permission("Analytics", "read"))):
    """
    Returns an aggregated summary of AI usage and costs over the last `days` days.
    """
    try:
        # Calculate the date boundary
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Aggregation Pipeline for Total Usage
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff_date}}},
            {"$group": {
                "_id": None,
                "total_tokens": {"$sum": "$total_tokens"},
                "total_cost_usd": {"$sum": "$estimated_cost_usd"},
                "total_calls": {"$sum": 1}
            }}
        ]
        
        summary_result = await db.ai_usage_logs.aggregate(pipeline).to_list(1)
        
        # Aggregation Pipeline for Module Breakdown (Bar Chart)
        module_pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff_date}}},
            {"$group": {
                "_id": "$action_type",
                "cost": {"$sum": "$estimated_cost_usd"}
            }},
            {"$sort": {"cost": -1}}
        ]
        module_results = await db.ai_usage_logs.aggregate(module_pipeline).to_list(100)
        
        # Aggregation Pipeline for Model Usage (Doughnut Chart)
        model_pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff_date}}},
            {"$group": {
                "_id": "$model_used",
                "tokens": {"$sum": "$total_tokens"}
            }},
            {"$sort": {"tokens": -1}}
        ]
        model_results = await db.ai_usage_logs.aggregate(model_pipeline).to_list(100)
        
        # Format the data for the frontend
        summary = summary_result[0] if summary_result else {"total_tokens": 0, "total_cost_usd": 0.0, "total_calls": 0}
        
        module_labels = [m["_id"] for m in module_results]
        module_costs = [m["cost"] for m in module_results]
        
        model_labels = [m["_id"] for m in model_results]
        model_tokens = [m["tokens"] for m in model_results]
        
        return {
            "status": "success",
            "data": {
                "total_tokens": summary.get("total_tokens", 0),
                "total_calls": summary.get("total_calls", 0),
                "total_cost_usd": summary.get("total_cost_usd", 0.0),
                "module_costs": {
                    "labels": module_labels,
                    "costs": module_costs
                },
                "model_tokens": {
                    "labels": model_labels,
                    "tokens": model_tokens
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
