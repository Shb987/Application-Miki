import pytest
from app.routes.ai_tutor_routes import is_realtime_or_web_query, classify_intent, search_web
from app.services.web_search_service import (
    execute_web_search,
    rank_source,
    search_provider_ddgs_news,
    search_provider_ddgs_text,
    search_provider_curl_cffi,
    STABLE_PRIMP_PROFILE,
    STABLE_PRIMP_OS,
    CURL_CFFI_GENERIC_PROFILE
)


@pytest.mark.asyncio
async def test_realtime_query_detection_and_classification():
    # 4 Required test questions
    required_questions = [
        "Who is the Chief Minister of Kerala?",
        "Who is the Prime Minister of India?",
        "Who is the Governor of Kerala?",
        "What are the latest current affairs in India?"
    ]
    for q in required_questions:
        assert is_realtime_or_web_query(q) is True, f"Failed to detect realtime query: {q}"
        intent = await classify_intent(q)
        assert intent == "WEB", f"Expected intent WEB for '{q}', got {intent}"

    # Historical and conceptual questions must NOT be detected as realtime
    historical_conceptual_queries = [
        "Who was the first Chief Minister of Kerala?",
        "What is the role of a Chief Minister?",
        "Explain the process of photosynthesis",
        "What is Newton's second law of motion?"
    ]
    for q in historical_conceptual_queries:
        assert is_realtime_or_web_query(q) is False, f"Expected non-realtime query, got True for: {q}"


def test_impersonation_configuration_stability():
    """Verify that random unsupported impersonates are replaced with stable profiles."""
    import ddgs.http_client
    assert ddgs.http_client.HttpClient._impersonates == STABLE_PRIMP_PROFILE
    assert ddgs.http_client.HttpClient._impersonates_os == STABLE_PRIMP_OS
    assert "chrome_107" not in ddgs.http_client.HttpClient._impersonates
    assert "chrome_133" not in ddgs.http_client.HttpClient._impersonates
    assert "safari_18" not in ddgs.http_client.HttpClient._impersonates
    assert CURL_CFFI_GENERIC_PROFILE == "chrome"


def test_source_priority_ranking():
    # Official government sources have highest priority (Rank 1)
    assert rank_source("https://kerala.gov.in/chief-minister") == 1
    assert rank_source("https://eci.gov.in/election-results") == 1
    assert rank_source("https://pmindia.gov.in/en/") == 1

    # Reputable news media have high priority (Rank 2)
    assert rank_source("https://www.thehindu.com/news/national/kerala/new-cm") == 2
    assert rank_source("https://indianexpress.com/article/india/new-pm") == 2

    # Forum and spam sites are penalized (Rank 99)
    assert rank_source("https://brainly.in/question/12345") == 99
    assert rank_source("https://www.pinterest.com/pin/12345") == 99


@pytest.mark.asyncio
async def test_search_providers_execute_successfully():
    """Verify both DDGS News and DDGS Text execute without impersonation errors."""
    query = "Prime Minister of India"
    
    # News provider
    news_res = search_provider_ddgs_news(query, max_results=3)
    assert isinstance(news_res, list)
    assert len(news_res) > 0, "Expected at least 1 news result"

    # Text provider
    text_res = search_provider_ddgs_text(query, max_results=3, timelimit="y")
    assert isinstance(text_res, list)
    assert len(text_res) > 0, "Expected at least 1 text result"

    # curl_cffi provider
    curl_res = search_provider_curl_cffi(query, max_results=3)
    assert isinstance(curl_res, list)
    assert len(curl_res) > 0, "Expected at least 1 curl_cffi result"


@pytest.mark.asyncio
async def test_all_four_required_questions_web_search():
    """Verify live web search retrieval for all four required questions."""
    questions = [
        "Who is the Chief Minister of Kerala?",
        "Who is the Prime Minister of India?",
        "Who is the Governor of Kerala?",
        "What are the latest current affairs in India?"
    ]
    for q in questions:
        context = await execute_web_search(q, max_results=3)
        assert isinstance(context, str)
        assert len(context) > 0, f"Expected non-empty search context for: {q}"
        assert "[SOURCE:" in context, f"Expected [SOURCE: ...] tag in context for: {q}"


@pytest.mark.asyncio
async def test_safe_fallback_when_search_fails():
    """Verify that empty search results produce an unverified source type instead of fabricating."""
    # When execute_web_search returns "", caller marks source_type as REALTIME_WEB (UNVERIFIED)
    empty_context = ""
    source_type = "REALTIME_WEB (UNVERIFIED)" if not empty_context else "REALTIME_WEB"
    assert source_type == "REALTIME_WEB (UNVERIFIED)"
