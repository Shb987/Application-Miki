import pytest
from app.routes.ai_tutor_routes import is_realtime_or_web_query, classify_intent, search_web, rank_source


@pytest.mark.asyncio
async def test_realtime_query_detection():
    # Questions about current leaders or officeholders must be detected as realtime/web
    current_queries = [
        "who is the chief minister of kerala",
        "who is the current prime minister of India",
        "who is the governor of Kerala",
        "who won the latest election",
        "kerala cm today",
        "current president of USA"
    ]
    for q in current_queries:
        assert is_realtime_or_web_query(q) is True, f"Failed to detect web query: {q}"

    # Historical and conceptual questions must NOT be detected as realtime
    historical_conceptual_queries = [
        "Who was the first Chief Minister of Kerala?",
        "What is the role of a Chief Minister?",
        "Explain the process of photosynthesis",
        "What is Newton's second law of motion?"
    ]
    for q in historical_conceptual_queries:
        assert is_realtime_or_web_query(q) is False, f"Expected non-realtime query, got True for: {q}"


def test_source_priority_ranking():
    # Official government sources have highest priority (Rank 1)
    assert rank_source("https://kerala.gov.in/chief-minister") == 1
    assert rank_source("https://eci.gov.in/election-results") == 1

    # Reputable news media have high priority (Rank 2)
    assert rank_source("https://www.thehindu.com/news/national/kerala/new-cm") == 2
    assert rank_source("https://indianexpress.com/article/india/satheesan-sworn-in") == 2

    # Forum and spam sites are penalized (Rank 99)
    assert rank_source("https://brainly.in/question/12345") == 99
    assert rank_source("https://www.pinterest.com/pin/12345") == 99


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


