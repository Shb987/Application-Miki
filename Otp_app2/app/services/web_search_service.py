import logging
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 1. Browser Impersonation Stability Configuration
# -----------------------------------------------------------------------------
# Configure ddgs and duckduckgo_search to use supported Chrome profile
# and prevent random generation of invalid browser targets (chrome_107, chrome_133, safari_18, etc.)
STABLE_PRIMP_PROFILE = ("chrome_120",)
STABLE_PRIMP_OS = ("windows",)
CURL_CFFI_GENERIC_PROFILE = "chrome"

def patch_ddgs_impersonate():
    """Ensure ddgs / duckduckgo_search HttpClient does not use invalid random profiles."""
    patched = False
    try:
        import ddgs.http_client
        ddgs.http_client.HttpClient._impersonates = STABLE_PRIMP_PROFILE
        ddgs.http_client.HttpClient._impersonates_os = STABLE_PRIMP_OS
        patched = True
    except Exception as e:
        logger.debug(f"Could not patch ddgs.http_client: {e}")

    try:
        import duckduckgo_search.http_client
        duckduckgo_search.http_client.HttpClient._impersonates = STABLE_PRIMP_PROFILE
        duckduckgo_search.http_client.HttpClient._impersonates_os = STABLE_PRIMP_OS
        patched = True
    except Exception as e:
        logger.debug(f"Could not patch duckduckgo_search.http_client: {e}")

    return patched

# Apply patch immediately upon import
patch_ddgs_impersonate()

# Import DDGS after patch
try:
    from duckduckgo_search import DDGS
except ImportError:
    try:
        from ddgs import DDGS
    except ImportError:
        DDGS = None

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

try:
    import httpx
except ImportError:
    httpx = None


def rank_source(url_or_title: str) -> int:
    """
    Ranks sources according to Section 4 Source Priority:
    1. Official government portals and ECI (.gov.in, .nic.in, eci.gov.in)
    2. Reputable national & international news media
    3. General reliable sources
    99. Outdated SEO/forum sites (Pinterest, Brainly, Quora)
    """
    s = url_or_title.lower()
    if any(d in s for d in [".gov.in", ".nic.in", "eci.gov.in", "pib.gov.in", "india.gov.in", "kerala.gov.in"]):
        return 1
    if any(d in s for d in [
        "thehindu", "indianexpress", "ndtv", "timesofindia", "hindustantimes",
        "bbc", "reuters", "pti", "ani", "onmanorama", "mathrubhumi", "livemint",
        "economictimes", "tribuneindia", "deccanherald", "business-standard"
    ]):
        return 2
    if any(d in s for d in ["pinterest", "brainly", "quora"]):
        return 99
    return 3


def search_provider_ddgs_news(query: str, max_results: int = 5) -> list[dict]:
    """Provider 1: DuckDuckGo News via DDGS for live events, elections & appointments."""
    provider_name = "DDGS_NEWS"
    if DDGS is None:
        logger.warning(f"[{provider_name}] DDGS not available.")
        return []
    try:
        patch_ddgs_impersonate()
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
            items = []
            for r in results:
                title = r.get("title", "").strip()
                body = r.get("body", r.get("snippet", "")).strip()
                url = r.get("url", r.get("href", "")).strip()
                date = r.get("date", "").strip()
                source = r.get("source", "").strip()
                if title and body:
                    items.append({
                        "title": f"{title} ({source})" if source else title,
                        "body": f"Date: {date}\n{body}" if date else body,
                        "url": url,
                        "provider": provider_name
                    })
            logger.info(f"[{provider_name}] Successfully retrieved {len(items)} news items for query: '{query}'")
            return items
    except Exception as e:
        logger.error(f"[{provider_name}] Search error: {type(e).__name__}: {e}")
        return []


def search_provider_ddgs_text(query: str, max_results: int = 6, timelimit: str = "y") -> list[dict]:
    """Provider 2: DuckDuckGo Text via DDGS with recency filtering ('y' = past 12 months)."""
    provider_name = "DDGS_TEXT"
    if DDGS is None:
        logger.warning(f"[{provider_name}] DDGS not available.")
        return []
    try:
        patch_ddgs_impersonate()
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, timelimit=timelimit))
            items = []
            for r in results:
                title = r.get("title", "").strip()
                body = r.get("body", r.get("snippet", "")).strip()
                url = r.get("href", r.get("url", "")).strip()
                if title and body:
                    items.append({
                        "title": title,
                        "body": body,
                        "url": url,
                        "provider": provider_name
                    })
            logger.info(f"[{provider_name}] Successfully retrieved {len(items)} text items for query: '{query}'")
            return items
    except Exception as e:
        logger.error(f"[{provider_name}] Search error: {type(e).__name__}: {e}")
        return []


def search_provider_curl_cffi(query: str, max_results: int = 5) -> list[dict]:
    """Provider 3: Direct DuckDuckGo HTML search using curl_cffi with generic 'chrome' profile."""
    provider_name = "CURL_CFFI"
    if curl_requests is None:
        logger.warning(f"[{provider_name}] curl_cffi not installed.")
        return []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Use supported generic 'chrome' impersonation
        r = curl_requests.get(url, headers=headers, impersonate=CURL_CFFI_GENERIC_PROFILE, timeout=10)
        if r.status_code != 200:
            logger.warning(f"[{provider_name}] HTTP status {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for el in soup.select(".result"):
            title_el = el.select_one(".result__title")
            snippet_el = el.select_one(".result__snippet")
            url_el = el.select_one(".result__url")
            if title_el and snippet_el:
                items.append({
                    "title": title_el.get_text(strip=True),
                    "body": snippet_el.get_text(strip=True),
                    "url": url_el.get_text(strip=True) if url_el else "",
                    "provider": provider_name
                })
                if len(items) >= max_results:
                    break

        logger.info(f"[{provider_name}] Successfully retrieved {len(items)} items for query: '{query}'")
        return items
    except Exception as e:
        logger.error(f"[{provider_name}] Search error: {type(e).__name__}: {e}")
        return []


def search_provider_httpx_ddg(query: str, max_results: int = 5) -> list[dict]:
    """Provider 4: Fallback DuckDuckGo HTML search via httpx with desktop User-Agent."""
    provider_name = "HTTPX_DDG"
    if httpx is None:
        logger.warning(f"[{provider_name}] httpx not available.")
        return []
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        data = {"q": query}
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.post(url, headers=headers, data=data)
            if resp.status_code != 200:
                logger.warning(f"[{provider_name}] HTTP status {resp.status_code}")
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            items = []
            for el in soup.select(".result"):
                title_el = el.select_one(".result__title")
                snippet_el = el.select_one(".result__snippet")
                url_el = el.select_one(".result__url")
                if title_el and snippet_el:
                    items.append({
                        "title": title_el.get_text(strip=True),
                        "body": snippet_el.get_text(strip=True),
                        "url": url_el.get_text(strip=True) if url_el else "",
                        "provider": provider_name
                    })
                    if len(items) >= max_results:
                        break
            logger.info(f"[{provider_name}] Successfully retrieved {len(items)} items for query: '{query}'")
            return items
    except Exception as e:
        logger.error(f"[{provider_name}] Search error: {type(e).__name__}: {e}")
        return []


async def execute_web_search(query: str, max_results: int = 6) -> str:
    """
    Executes a resilient multi-provider web search.
    - Isolates provider exceptions so a failure in one provider never stops others.
    - Ranks and prioritizes official government portals and reputable news sources.
    - Filters out spam sites.
    - Returns formatted source context strings, or empty string if all fail.
    """
    logger.info(f"🌐 Initiating Multi-Provider Web Search for query: '{query}'")
    raw_items = []

    # 1. Execute News search (time-sensitive breaking news, leadership changes)
    try:
        news_items = search_provider_ddgs_news(query, max_results=4)
        raw_items.extend(news_items)
    except Exception as e:
        logger.error(f"[SEARCH_ORCHESTRATOR] Unexpected error in DDGS_NEWS: {e}")

    # 2. Execute Recency-filtered Text search
    try:
        text_items = search_provider_ddgs_text(query, max_results=6, timelimit="y")
        raw_items.extend(text_items)
    except Exception as e:
        logger.error(f"[SEARCH_ORCHESTRATOR] Unexpected error in DDGS_TEXT: {e}")

    # 3. Fallback to curl_cffi direct search if fewer than 3 results obtained
    if len(raw_items) < 3:
        try:
            curl_items = search_provider_curl_cffi(query, max_results=5)
            raw_items.extend(curl_items)
        except Exception as e:
            logger.error(f"[SEARCH_ORCHESTRATOR] Unexpected error in CURL_CFFI: {e}")

    # 4. Fallback to DDGS text search without timelimit if still empty
    if not raw_items:
        try:
            std_items = search_provider_ddgs_text(query, max_results=5, timelimit="")
            raw_items.extend(std_items)
        except Exception as e:
            logger.error(f"[SEARCH_ORCHESTRATOR] Unexpected error in DDGS_STANDARD: {e}")

    # 5. Final fallback to httpx HTML search if still empty
    if not raw_items:
        try:
            httpx_items = search_provider_httpx_ddg(query, max_results=5)
            raw_items.extend(httpx_items)
        except Exception as e:
            logger.error(f"[SEARCH_ORCHESTRATOR] Unexpected error in HTTPX_DDG: {e}")

    # Filter spam and duplicates
    filtered = [
        item for item in raw_items
        if not any(spam in (item.get("title", "") + " " + item.get("url", "")).lower() for spam in ["pinterest", "brainly", "quora"])
    ]

    # Sort according to Section 4 Source Priority
    filtered.sort(key=lambda r: rank_source(r.get("title", "") + " " + r.get("url", "")))

    context_items = []
    seen_titles = set()
    for r in filtered:
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()
        url = r.get("url", "").strip()
        if not body or title in seen_titles:
            continue
        seen_titles.add(title)
        source_header = f"[SOURCE: {title}" + (f" | URL: {url}]" if url else "]")
        context_items.append(f"{source_header}\n{body}")
        if len(context_items) >= max_results:
            break

    if not context_items:
        logger.warning(f"[SEARCH_ORCHESTRATOR] No verified search results found across all providers for: '{query}'")
        return ""

    logger.info(f"[SEARCH_ORCHESTRATOR] Returning {len(context_items)} ranked search context blocks for: '{query}'")
    return "\n\n".join(context_items)
