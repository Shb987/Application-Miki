import logging
from datetime import datetime, timezone
from app.core.database import db

logger = logging.getLogger(__name__)

# Standardized OpenAI Pricing (Per 1M Tokens in USD)
# Note: Always keep this updated with current OpenAI pricing
PRICING = {
    "gpt-4o": {
        "prompt": 5.00,
        "completion": 15.00
    },
    "gpt-4o-2024-08-06": {   # Specific model version fallback
        "prompt": 2.50,
        "completion": 10.00
    },
    "gpt-4o-mini": {
        "prompt": 0.150,
        "completion": 0.600
    },
    "text-embedding-3-large": {
        "prompt": 0.130,
        "completion": 0.000
    },
    "text-embedding-3-small": {
        "prompt": 0.020,
        "completion": 0.000
    },
    "gpt-4o-realtime-preview": {
        "prompt": 5.00,       # Text input
        "completion": 20.00,  # Text output
        "audio_prompt": 40.00, 
        "audio_completion": 80.00
    }
}

async def log_ai_usage(student_id: str, action_type: str, model: str, usage_obj) -> None:
    """
    Logs AI API token usage to the database asynchronously.
    
    Args:
        student_id (str): The ID of the student making the request, or "ADMIN" if system-level.
        action_type (str): The feature being used (e.g., 'ai_tutor_chat', 'voice_assistant', 'exam_evaluation').
        model (str): The model name used (e.g., 'gpt-4o', 'gpt-4o-mini').
        usage_obj: The usage object returned by the OpenAI API.
    """
    try:
        if not usage_obj:
            logger.warning(f"No usage object provided for {action_type} using {model}")
            return
            
        # Extract tokens gracefully from the object (handles both object attributes and dicts)
        if isinstance(usage_obj, dict):
            prompt_tokens = usage_obj.get("prompt_tokens", 0)
            completion_tokens = usage_obj.get("completion_tokens", 0)
            total_tokens = usage_obj.get("total_tokens", prompt_tokens + completion_tokens)
        else:
            prompt_tokens = getattr(usage_obj, "prompt_tokens", 0)
            completion_tokens = getattr(usage_obj, "completion_tokens", 0)
            total_tokens = getattr(usage_obj, "total_tokens", prompt_tokens + completion_tokens)
            
        # Calculate Estimated Cost in USD
        # Default to 0 if model is not in pricing table
        rates = PRICING.get(model, {"prompt": 0, "completion": 0})
        
        # Calculate cost (price is per 1 million tokens)
        prompt_cost = (prompt_tokens / 1000000) * rates.get("prompt", 0)
        completion_cost = (completion_tokens / 1000000) * rates.get("completion", 0)
        total_cost_usd = prompt_cost + completion_cost
        
        # Insert into MongoDB
        log_entry = {
            "student_id": student_id,
            "action_type": action_type,
            "model_used": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": total_cost_usd,
            "timestamp": datetime.now(timezone.utc)
        }
        
        await db.ai_usage_logs.insert_one(log_entry)
        logger.info(f"Logged AI Usage: {action_type} | {model} | {total_tokens} tokens | ${total_cost_usd:.5f}")
        
    except Exception as e:
        logger.error(f"Failed to log AI usage for {action_type}: {str(e)}")
