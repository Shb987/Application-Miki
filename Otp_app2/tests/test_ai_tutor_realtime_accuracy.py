import pytest
from app.routes.ai_tutor_routes import is_realtime_or_web_query, classify_intent, search_web


@pytest.mark.asyncio
async def test_realtime_query_detection():
    # Questions about current leaders or officeholders must be detected as realtime/web
    queries = [
        "who is the chief minister of kerala",
        "who is the current prime minister of India",
        "who is the governor of Kerala",
        "who won the latest election",
        "kerala cm today",
        "current president of USA"
    ]
    for q in queries:
        assert is_realtime_or_web_query(q) is True, f"Failed to detect web query: {q}"


@pytest.mark.asyncio
async def test_classify_intent_for_leadership_query():
    intent = await classify_intent("who is the chief minister of kerala")
    assert intent == "WEB", f"Expected intent to be WEB, got {intent}"


@pytest.mark.asyncio
async def test_search_web_retrieves_updated_kerala_cm():
    context = await search_web("current chief minister of kerala")
    assert len(context) > 0, "Expected non-empty search context"
    # Should include reference to current leadership / V. D. Satheesan
    assert "Satheesan" in context or "Chief Minister" in context
