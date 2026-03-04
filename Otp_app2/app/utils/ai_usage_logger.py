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
    },
    "gpt-4o-mini-realtime-preview": {
        "prompt": 0.60,       # Text input
        "completion": 2.40,   # Text output
        "audio_prompt": 10.00, 
        "audio_completion": 20.00
    },
    "gpt-4.1-mini": { # Custom/Legacy model name
        "prompt": 0.150,
        "completion": 0.600
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
        rates = PRICING.get(model, {"prompt": 0, "completion": 0})
        
        # 1. Standard Text Costs (Usage object usually has prompt_tokens and completion_tokens)
        prompt_cost = (prompt_tokens / 1000000) * rates.get("prompt", 0)
        completion_cost = (completion_tokens / 1000000) * rates.get("completion", 0)
        
        # 2. Realtime Audio Specific Costs (if usage object contains audio breakdown)
        # Note: Some OpenAI SDK versions put these in 'prompt_tokens_details' or similar sub-objects
        audio_prompt_tokens = 0
        audio_completion_tokens = 0
        
        if not isinstance(usage_obj, dict):
            # Try to find audio token counts in response details (SDK specific)
            prompt_details = getattr(usage_obj, "prompt_tokens_details", None)
            if prompt_details:
                audio_prompt_tokens = getattr(prompt_details, "audio_tokens", 0)
            
            comp_details = getattr(usage_obj, "completion_tokens_details", None)
            if comp_details:
                audio_completion_tokens = getattr(comp_details, "audio_tokens", 0)
        
        audio_prompt_cost = (audio_prompt_tokens / 1000000) * rates.get("audio_prompt", 0)
        audio_comp_cost = (audio_completion_tokens / 1000000) * rates.get("audio_completion", 0)
        
        total_cost_usd = prompt_cost + completion_cost + audio_prompt_cost + audio_comp_cost
        
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
