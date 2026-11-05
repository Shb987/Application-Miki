# services/future_study_service.py
import os
import re
import json
import urllib.parse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import requests
import urllib3
from openai import AsyncOpenAI

# Suppress insecure request warnings for official Indian government portals with local NIC root certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Async OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "sk-placeholder")

# Set of strictly allowed educational domains
ALLOWED_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "khanacademy.org",
    "www.khanacademy.org",
    "swayam.gov.in",
    "www.swayam.gov.in",
    "nptel.ac.in",
    "www.nptel.ac.in",
    "ncert.nic.in",
    "www.ncert.nic.in",
    "openstax.org",
    "www.openstax.org",
    "coursera.org",
    "www.coursera.org",
    "edx.org",
    "www.edx.org",
    "mit.edu",
    "ocw.mit.edu",
    "geeksforgeeks.org",
    "www.geeksforgeeks.org",
    "nationalgeographic.com",
    "kids.nationalgeographic.com",
}


def normalize_class(student_class: str) -> str:
    """Normalize student class string to digits if possible (e.g., 'Class 12' -> '12')."""
    if not student_class:
        return "10"
    s = str(student_class).strip()
    match = re.search(r"\b([1-9]|1[0-2])\b", s)
    if match:
        return match.group(1)
    digits = re.findall(r"\d+", s)
    if digits:
        return digits[0]
    return s


def is_domain_allowed(host: str) -> bool:
    """Check if the hostname belongs to the allowlisted educational domains."""
    if not host:
        return False
    host = host.lower().split(":")[0].strip()
    if host in ALLOWED_DOMAINS:
        return True
    for d in ALLOWED_DOMAINS:
        if host.endswith("." + d):
            return True
    return False


def validate_url(url: str, timeout: int = 5) -> bool:
    """
    Validate educational URL using format checks, domain allowlisting, and HTTP verification.
    Does not treat HTTP 200 alone as proof of validity.
    Excludes invalid or fabricated links.
    """
    try:
        if not url or not isinstance(url, str):
            return False

        parsed = urllib.parse.urlsplit(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        if not parsed.netloc or not is_domain_allowed(parsed.netloc):
            return False

        # YouTube format rule: Must be a search query URL, never a fabricated video ID or channel
        if "youtube.com" in parsed.netloc.lower():
            if not parsed.path.startswith("/results"):
                return False
            query_params = urllib.parse.parse_qs(parsed.query)
            if "search_query" not in query_params or not query_params["search_query"][0].strip():
                return False

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        # Check for Indian government domains requiring custom/permissive TLS
        is_gov_domain = parsed.netloc.lower().endswith((".gov.in", ".nic.in"))
        verify_ssl = not is_gov_domain

        resp = None
        # Attempt lightweight HEAD first
        try:
            resp = requests.head(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                verify=verify_ssl,
            )
            # Some platforms return 403/405 for HEAD, fallback to GET
            if resp.status_code in (403, 405):
                resp = None
        except Exception:
            resp = None

        # Fallback to streaming GET if HEAD wasn't supported
        if resp is None:
            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    stream=True,
                    allow_redirects=True,
                    verify=verify_ssl,
                )
            except Exception:
                return False

        # Post-redirect security check: verify final destination is still allowlisted
        final_parsed = urllib.parse.urlsplit(resp.url)
        if not is_domain_allowed(final_parsed.netloc):
            return False

        # Status code check
        if resp.status_code < 200 or resp.status_code >= 400:
            return False

        # Content-Type check (must be HTML/web text, not binary or empty)
        content_type = resp.headers.get("Content-Type", "").lower()
        if not any(t in content_type for t in ("text/html", "application/xhtml", "text/plain", "text/xml")):
            return False

        # Read first snippet to check for soft-404 indicators
        content_chunk = ""
        try:
            if hasattr(resp, "iter_content"):
                for chunk in resp.iter_content(chunk_size=4096, decode_unicode=True):
                    if chunk:
                        content_chunk = chunk
                        break
            elif hasattr(resp, "text"):
                content_chunk = resp.text[:4096]
        except Exception:
            pass

        lower_chunk = content_chunk.lower()
        soft_404_indicators = [
            "<title>404",
            "404 not found",
            "page not found",
            "video unavailable",
            "this video is unavailable",
            "course not found",
        ]
        for indicator in soft_404_indicators:
            if indicator in lower_chunk:
                return False

        return True
    except Exception:
        return False


def generate_youtube_search_url(keyword: str, student_class: str) -> dict:
    """Generate dynamic YouTube search result URL with urllib.parse.quote_plus."""
    norm_cls = normalize_class(student_class)
    try:
        cls_int = int(norm_cls)
    except ValueError:
        cls_int = 10

    if cls_int <= 5:
        search_term = f"{keyword} for kids fun science learning"
    elif cls_int <= 8:
        search_term = f"{keyword} Class {norm_cls} foundation concepts"
    else:
        search_term = f"{keyword} Class {norm_cls} educational lecture"

    encoded = urllib.parse.quote_plus(search_term.strip())
    url = f"https://www.youtube.com/results?search_query={encoded}"
    return {
        "title": f"{keyword} (Search Results)",
        "link": url,
    }


def generate_platform_tutorial_urls(keyword: str, student_class: str) -> list[dict]:
    """
    Generate legitimate educational platform search URLs using each platform's
    actual search query functionality.
    """
    norm_cls = normalize_class(student_class)
    try:
        cls_int = int(norm_cls)
    except ValueError:
        cls_int = 10

    encoded_kw = urllib.parse.quote_plus(keyword.strip())
    candidates = []

    # 1. Khan Academy (Available for all classes)
    candidates.append({
        "title": f"Khan Academy: {keyword}",
        "link": f"https://www.khanacademy.org/search?page_search_query={encoded_kw}",
    })

    # 2. NCERT official curriculum/textbook portal (Class 1-12)
    candidates.append({
        "title": f"NCERT Textbooks & Curriculum (Class {norm_cls})",
        "link": "https://ncert.nic.in/textbook.php",
    })

    # 3. SWAYAM - Ministry of Education, Govt of India (Class 9-12)
    if cls_int >= 9:
        candidates.append({
            "title": f"SWAYAM Courses: {keyword}",
            "link": f"https://swayam.gov.in/explorer?searchText={encoded_kw}",
        })

    # 4. NPTEL - IITs & IISc online education (Class 9-12)
    if cls_int >= 9:
        candidates.append({
            "title": f"NPTEL Courses: {keyword}",
            "link": f"https://nptel.ac.in/courses?keyword={encoded_kw}",
        })

    # 5. OpenStax (Peer-reviewed textbooks for Class 9-12)
    if cls_int >= 9:
        candidates.append({
            "title": f"OpenStax Learning Resources: {keyword}",
            "link": "https://openstax.org/subjects",
        })

    return candidates


def validate_resources_concurrently(items: list[dict], max_workers: int = 8) -> list[dict]:
    """
    Validate a list of resources concurrently using Python requests.
    Excludes any unverified links rather than generating fake replacements.
    """
    if not items:
        return []

    def check_item(item):
        link = item.get("link", "")
        if validate_url(link):
            return item
        return None

    with ThreadPoolExecutor(max_workers=min(len(items), max_workers)) as executor:
        results = list(executor.map(check_item, items))

    # Return only successfully verified items
    return [r for r in results if r is not None]


def extract_json(text: str):
    """Safely extract JSON object from LLM response text."""
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(text[start:end])
    except Exception:
        return None


def get_category_fallbacks(top_category: str, student_class: str) -> dict:
    """
    Curated, verified fallback data for all Multiple Intelligence categories and classes
    in India, used if the LLM is unreachable or fails.
    """
    norm_cls = normalize_class(student_class)
    try:
        cls_int = int(norm_cls)
    except ValueError:
        cls_int = 10

    cat_lower = (top_category or "Naturalist").strip().lower()

    if "natural" in cat_lower:
        keywords = [
            "Ecology & Ecosystems",
            "Wildlife Conservation & Biodiversity",
            "Environmental Science",
            "Botany & Plant Science",
            "Zoology & Animal Behavior",
        ]
        if cls_int <= 8:
            exams = [
                {"exam_name": "Green Olympiad (TERI)", "eligibility": f"Class {norm_cls}", "age_group": "Under 14", "description": "India's premier environmental examination conducted by TERI."},
                {"exam_name": "National Science Olympiad (NSO)", "eligibility": f"Class {norm_cls}", "age_group": "School Students", "description": "National level science competition testing environmental and biological concepts."},
            ]
        else:
            exams = [
                {"exam_name": "ICAR AIEEA (UG)", "eligibility": "Class 12 (PCB/PCMB)", "age_group": "16-20 years", "description": "All India Entrance Examination for Agricultural and Environmental Sciences."},
                {"exam_name": "KVPY / INSPIRE Fellowship", "eligibility": "Class 11-12", "age_group": "16-18 years", "description": "Department of Science & Technology fellowship for basic and natural sciences."},
                {"exam_name": "Indian Forest Service (IFS)", "eligibility": "Graduation in Natural Sciences", "age_group": "Future Goal", "description": "Premier civil service managing wildlife, forestry, and environmental conservation."},
            ]
        study_centers = [
            {"center_name": "Wildlife Institute of India (WII)", "location": "Dehradun, Uttarakhand", "career_focus": "Wildlife Biology & Ecology", "description": "Autonomous institution under the Ministry of Environment, Forest and Climate Change."},
            {"center_name": "Forest Research Institute (FRI)", "location": "Dehradun, Uttarakhand", "career_focus": "Forestry & Environmental Studies", "description": "Premier research center in forestry and natural resources."},
            {"center_name": "National Centre for Biological Sciences (NCBS)", "location": "Bengaluru, Karnataka", "career_focus": "Ecology & Evolutionary Biology", "description": "Research center exploring biodiversity, ecology, and biological systems."},
        ]

    elif "math" in cat_lower or "logical" in cat_lower:
        keywords = [
            "Data Science & Statistical Analysis",
            "Algorithms & Problem Solving",
            "Applied Mathematics & Modeling",
            "Artificial Intelligence Fundamentals",
            "Logical Reasoning & Quantitative Aptitude",
        ]
        if cls_int <= 8:
            exams = [
                {"exam_name": "International Mathematics Olympiad (IMO)", "eligibility": f"Class {norm_cls}", "age_group": "School Students", "description": "Tests mathematical and analytical reasoning skills."},
                {"exam_name": "NMTC (National Mathematics Talent Contests)", "eligibility": f"Class {norm_cls}", "age_group": "Junior Students", "description": "Organized by AMTI to identify mathematical talent."},
            ]
        else:
            exams = [
                {"exam_name": "Regional Mathematical Olympiad (RMO)", "eligibility": "Class 9-12", "age_group": "14-18 years", "description": "First-tier national mathematics competition leading to INMO."},
                {"exam_name": "ISI Admission Test", "eligibility": "Class 12 (Maths)", "age_group": "17-19 years", "description": "Entrance for B.Stat / B.Math at the Indian Statistical Institute."},
                {"exam_name": "JEE (Main & Advanced)", "eligibility": "Class 12 (PCM)", "age_group": "16-19 years", "description": "National entrance exam for premier engineering and technology institutes."},
            ]
        study_centers = [
            {"center_name": "Indian Statistical Institute (ISI)", "location": "Kolkata, West Bengal", "career_focus": "Statistics, Mathematics & Data Science", "description": "Institution of national importance devoted to statistics and mathematical sciences."},
            {"center_name": "Chennai Mathematical Institute (CMI)", "location": "Chennai, Tamil Nadu", "career_focus": "Mathematics & Computer Science", "description": "Premier research institution for mathematics, computer science, and physics."},
            {"center_name": "IIT Bombay - Department of Computer Science", "location": "Mumbai, Maharashtra", "career_focus": "Computing & Applied Mathematics", "description": "Leading technological institution for computational problem solving."},
        ]

    elif "linguistic" in cat_lower or "verbal" in cat_lower:
        keywords = [
            "Creative Writing & Storytelling",
            "Journalism & Investigative Reporting",
            "Linguistics & Communication Skills",
            "Public Speaking & Debating Techniques",
            "Literary Analysis & Media Studies",
        ]
        exams = [
            {"exam_name": "International English Olympiad (IEO)", "eligibility": f"Class {norm_cls}", "age_group": "School Students", "description": "Olympiad assessing English language competence and comprehension."},
            {"exam_name": "CLAT (Common Law Admission Test)", "eligibility": "Class 12", "age_group": "16-20 years", "description": "National entrance exam for 24 National Law Universities in India."},
            {"exam_name": "CUET (English & Mass Communication)", "eligibility": "Class 12", "age_group": "16-19 years", "description": "Central Universities entrance exam for humanities and journalism programs."},
        ]
        study_centers = [
            {"center_name": "Indian Institute of Mass Communication (IIMC)", "location": "New Delhi", "career_focus": "Journalism & Media", "description": "Autonomous journalism school under the Ministry of Information and Broadcasting."},
            {"center_name": "English and Foreign Languages University (EFLU)", "location": "Hyderabad, Telangana", "career_focus": "Linguistics & Languages", "description": "Central university dedicated to language studies and literature."},
            {"center_name": "Asian College of Journalism (ACJ)", "location": "Chennai, Tamil Nadu", "career_focus": "Broadcast & Print Journalism", "description": "Top-tier postgraduate journalism academy in India."},
        ]

    elif "spatial" in cat_lower or "visual" in cat_lower:
        keywords = [
            "Architectural Design Principles",
            "Visual Arts & 3D Modeling",
            "Graphic Design & Typography",
            "Cartography & Geographic Information Systems",
            "Product & Industrial Design",
        ]
        exams = [
            {"exam_name": "UCEED (Undergraduate Common Entrance Examination for Design)", "eligibility": "Class 12", "age_group": "16-19 years", "description": "Conducted by IIT Bombay for admission to B.Des programs."},
            {"exam_name": "NID DAT (Design Aptitude Test)", "eligibility": "Class 12", "age_group": "16-20 years", "description": "Entrance exam for National Institute of Design campuses across India."},
            {"exam_name": "NATA (National Aptitude Test in Architecture)", "eligibility": "Class 12 (PCM)", "age_group": "16-20 years", "description": "National entrance test for 5-year B.Arch degree programs."},
        ]
        study_centers = [
            {"center_name": "National Institute of Design (NID)", "location": "Ahmedabad, Gujarat", "career_focus": "Industrial & Visual Design", "description": "Apex institute for industrial, communication, and textile design."},
            {"center_name": "School of Planning and Architecture (SPA)", "location": "New Delhi", "career_focus": "Architecture & Urban Planning", "description": "Premier institute of national importance for architecture and planning."},
            {"center_name": "IDC School of Design, IIT Bombay", "location": "Mumbai, Maharashtra", "career_focus": "Interaction & Visual Communication Design", "description": "Renowned center for design education and innovation."},
        ]

    else:
        # Default / Interpersonal / Bodily-Kinesthetic / General category
        keywords = [
            f"{top_category} Core Concepts",
            f"{top_category} Foundations & Skills",
            f"{top_category} Practical Applications",
            "Analytical & Research Skills",
            "Communication & Leadership",
        ]
        exams = [
            {"exam_name": "National Talent Search Examination (NTSE)", "eligibility": "Class 10", "age_group": "14-16 years", "description": "Scholarship program conducted by NCERT to identify high academic talent."},
            {"exam_name": "CUET (UG)", "eligibility": "Class 12", "age_group": "16-19 years", "description": "Central Universities entrance exam for diverse undergraduate courses."},
        ]
        study_centers = [
            {"center_name": "Tata Institute of Social Sciences (TISS)", "location": "Mumbai, Maharashtra", "career_focus": "Social Sciences & Development", "description": "Premier institute for interdisciplinary studies and human development."},
            {"center_name": "University of Delhi", "location": "New Delhi", "career_focus": "Higher Education & Research", "description": "Leading collegiate university offering diverse specializations."},
        ]

    return {
        "search_keywords": keywords,
        "competitive_exams": exams,
        "study_centers": study_centers,
    }


async def fetch_keywords_and_guidance_from_llm(
    student_class: str,
    top_category: str,
    recommended_career: str,
    student_id: str = None
) -> dict:
    """
    Call LLM to generate educational search keywords, exams, and study centers.
    STRICT RULE: The LLM is forbidden from generating URLs or YouTube video IDs.
    """
    norm_cls = normalize_class(student_class)

    prompt = f"""
You are an educational curriculum advisor for Indian school students.

STUDENT PROFILE:
- Current class: {norm_cls}
- Top intelligence category: {top_category}
- Recommended career: {recommended_career}

REQUIREMENT:
Generate age-appropriate educational study topics and guidance for this student.
DO NOT generate any website URLs, links, or YouTube video IDs.
Only generate descriptive search topic keywords, competitive exams, and study centers.

CLASS GUIDELINES:
- Class 1–5: Fun exploration, curiosity, foundational nature/science concepts
- Class 6–8: Foundation skills, practical concepts, introductory science & math
- Class 9–10: Structured academic concepts, foundational Olympiads and NTSE/entry exams
- Class 11–12: In-depth subject topics, competitive exams (JEE, NEET, CUET, Olympiads, NDA, etc.)

STRICT RULES:
- DO NOT INCLUDE ANY URLS OR LINKS IN ANY FIELD.
- DO NOT INCLUDE YOUTUBE VIDEO IDS.
- Provide EXACTLY 3 to 5 highly relevant, specific search keywords for educational videos/tutorials.
- Provide EXACTLY 3 to 5 legitimate, age-appropriate India-focused competitive exams.
- Provide EXACTLY 3 to 5 recognized Indian institutions or study centers relevant to this career.

RETURN STRICT JSON ONLY:
{{
  "search_keywords": [
    "Topic 1",
    "Topic 2",
    "Topic 3"
  ],
  "competitive_exams": [
    {{
      "exam_name": "...",
      "eligibility": "...",
      "age_group": "...",
      "description": "..."
    }}
  ],
  "study_centers": [
    {{
      "center_name": "...",
      "location": "...",
      "career_focus": "...",
      "description": "..."
    }}
  ]
}}
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )

        if student_id and hasattr(response, "usage") and response.usage:
            try:
                from app.utils.ai_usage_logger import log_ai_usage
                await log_ai_usage(student_id, "Future Study - Resources", "gpt-4o-mini", response.usage)
            except Exception:
                pass

        content = response.choices[0].message.content
        data = extract_json(content)
        if (
            data
            and isinstance(data.get("search_keywords"), list)
            and len(data["search_keywords"]) > 0
        ):
            return data
    except Exception:
        pass

    # Use curated fallback
    return get_category_fallbacks(top_category, norm_cls)


async def build_future_study_resources(
    top_category: str,
    student_class: str,
    recommended_career: str = None,
    student_id: str = None
) -> dict:
    """
    Builds, generates, and validates learning resources dynamically.
    - Generates dynamic YouTube search URLs (using urllib.parse.quote_plus)
    - Generates legitimate educational platform search URLs (Khan Academy, SWAYAM, NPTEL, NCERT)
    - Concurrently validates all URLs using Python requests
    - Excludes unverified resources rather than fabricating fake URLs
    """
    norm_cls = normalize_class(student_class)
    guidance = await fetch_keywords_and_guidance_from_llm(
        norm_cls, top_category, recommended_career, student_id=student_id
    )

    keywords = guidance.get("search_keywords", [])
    if not keywords:
        fallback = get_category_fallbacks(top_category, norm_cls)
        keywords = fallback.get("search_keywords", [])

    # 1. Generate YouTube search URLs (dynamic urllib.parse.quote_plus)
    candidate_videos = [generate_youtube_search_url(kw, norm_cls) for kw in keywords[:5]]

    # 2. Generate educational platform tutorial search URLs
    candidate_tutorials = []
    for kw in keywords[:3]:
        candidate_tutorials.extend(generate_platform_tutorial_urls(kw, norm_cls))

    # Add general NCERT reference if not already present
    ncert_link = "https://ncert.nic.in/textbook.php"
    if not any(t.get("link") == ncert_link for t in candidate_tutorials):
        candidate_tutorials.append({
            "title": f"NCERT Textbooks & Curriculum (Class {norm_cls})",
            "link": ncert_link,
        })

    # Deduplicate tutorial links by URL
    seen_urls = set()
    deduped_tutorials = []
    for item in candidate_tutorials:
        link = item.get("link", "")
        if link and link not in seen_urls:
            seen_urls.add(link)
            deduped_tutorials.append(item)

    # 3. Concurrently validate candidate URLs with requests
    # Limit validation to candidates; drop any that fail validation
    all_candidates = candidate_videos + deduped_tutorials
    validated_items = validate_resources_concurrently(all_candidates, max_workers=8)

    # Separate into verified videos and verified tutorials
    verified_url_set = {item["link"] for item in validated_items}
    verified_videos = [v for v in candidate_videos if v["link"] in verified_url_set]
    verified_tutorials = [t for t in deduped_tutorials if t["link"] in verified_url_set]

    # Return structured resources matching Flutter contract
    return {
        "youtube_videos": verified_videos,
        "tutorial_links": verified_tutorials,
        "competitive_exams": guidance.get("competitive_exams", []),
        "study_centers": guidance.get("study_centers", []),
    }


async def get_or_create_future_study_resources(
    db,
    career_category: str,
    student_class: str,
    recommended_career: str = None,
    student_id: str = None
) -> dict:
    """
    Retrieve resources from MongoDB collection 'future_study_resources' if available
    for the given career_category and student_class. Otherwise generate, validate,
    cache to MongoDB, and return.
    """
    if not career_category:
        career_category = "General"
    norm_category = career_category.strip()
    norm_cls = normalize_class(student_class)

    # 1. Check MongoDB collection 'future_study_resources'
    if db is not None:
        try:
            cached = await db.future_study_resources.find_one({
                "career_category": {"$regex": f"^{re.escape(norm_category)}$", "$options": "i"},
                "student_class": norm_cls,
            })
            if cached and cached.get("resources"):
                resources = cached["resources"]
                videos = resources.get("youtube_videos", [])
                # Ensure cached resources don't contain old fabricated watch?v= links
                has_fake_links = any("watch?v=" in v.get("link", "") or "youtu.be" in v.get("link", "") for v in videos)
                if not has_fake_links and len(videos) > 0:
                    return resources
        except Exception:
            pass

    # 2. Generate and validate clean resources
    resources = await build_future_study_resources(
        norm_category, norm_cls, recommended_career=recommended_career, student_id=student_id
    )

    # 3. Cache into MongoDB collection 'future_study_resources'
    if db is not None:
        try:
            await db.future_study_resources.update_one(
                {
                    "career_category": norm_category,
                    "student_class": norm_cls,
                },
                {
                    "$set": {
                        "career_category": norm_category,
                        "student_class": norm_cls,
                        "recommended_career": recommended_career,
                        "resources": resources,
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc),
                    },
                },
                upsert=True,
            )
        except Exception:
            pass

    return resources


async def generate_and_store_future_study(
    db,
    student_id: str,
    student_class: str,
    recommended_career,
    top_category: str
):
    """
    Main future study generation entry point.
    Retrieves/generates clean resources from 'future_study_resources' collection
    and updates student-specific 'future_study' document.
    """
    resources = await get_or_create_future_study_resources(
        db,
        career_category=top_category,
        student_class=student_class,
        recommended_career=recommended_career,
        student_id=student_id,
    )

    if db is not None:
        try:
            await db.future_study.update_one(
                {"student_id": str(student_id)},
                {
                    "$set": {
                        "student_class": normalize_class(student_class),
                        "recommended_career": recommended_career,
                        "top_category": top_category,
                        "resources": resources,
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc),
                    },
                },
                upsert=True,
            )
        except Exception:
            pass

    return resources
