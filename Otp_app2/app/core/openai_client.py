import os
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI, OpenAIError
import logging

logger = logging.getLogger(__name__)

def get_openai_api_key() -> str:
    # Refresh env from .env file if available
    load_dotenv(override=False)
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return key

def get_async_openai_client() -> AsyncOpenAI:
    key = get_openai_api_key()
    if not key or key == "sk-placeholder":
        # Return client with placeholder so instantiation succeeds, but log clear warning
        return AsyncOpenAI(api_key="sk-placeholder")
    return AsyncOpenAI(api_key=key)

def get_sync_openai_client() -> OpenAI:
    key = get_openai_api_key()
    if not key or key == "sk-placeholder":
        return OpenAI(api_key="sk-placeholder")
    return OpenAI(api_key=key)
