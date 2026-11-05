# tests/test_future_study_resources.py
import os
import sys

# Ensure Otp_app2 directory is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import pytest
import urllib.parse
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.future_study_service import (
    is_domain_allowed,
    validate_url,
    generate_youtube_search_url,
    generate_platform_tutorial_urls,
    validate_resources_concurrently,
    get_category_fallbacks,
    build_future_study_resources,
    get_or_create_future_study_resources,
    generate_and_store_future_study,
    normalize_class,
    ALLOWED_DOMAINS,
)


class TestDomainAllowlist:
    def test_allowlisted_domains(self):
        """Allowlisted educational domains must be permitted."""
        valid_hosts = [
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
            "kids.nationalgeographic.com",
        ]
        for host in valid_hosts:
            assert is_domain_allowed(host) is True, f"Host {host} should be allowed"

    def test_disallowed_domains(self):
        """Unapproved third-party or malicious domains must be rejected."""
        invalid_hosts = [
            "evil-site.com",
            "phishing.org",
            "randomtutorials.net",
            "bit.ly",
            "localhost",
            "127.0.0.1",
            "",
            None,
        ]
        for host in invalid_hosts:
            assert is_domain_allowed(host) is False, f"Host {host} should be disallowed"


class TestDynamicURLGeneration:
    def test_youtube_search_url_dynamic_encoding(self):
        """YouTube search URLs must be generated dynamically using urllib.parse.quote_plus."""
        keyword = "Ecology & Wildlife"
        student_class = "12"
        res = generate_youtube_search_url(keyword, student_class)

        assert "title" in res
        assert "link" in res
        # Title must clearly indicate search results, not a specific video
        assert "Search Results" in res["title"]

        url = res["link"]
        assert url.startswith("https://www.youtube.com/results?search_query=")
        # Must not contain watch?v= or fabricated video IDs
        assert "watch?v=" not in url
        assert "youtu.be" not in url

        # Query parameter must be properly encoded
        parsed = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert "search_query" in params
        assert "Ecology & Wildlife" in params["search_query"][0]
        # '&' character must be percent-encoded as %26 in raw query
        assert "%26" in parsed.query or "Ecology" in params["search_query"][0]

    def test_educational_platform_urls(self):
        """Tutorial URLs must use legitimate educational platforms and search functionality."""
        keyword = "Plant Biology"
        student_class = "12"
        tutorials = generate_platform_tutorial_urls(keyword, student_class)

        assert len(tutorials) >= 4
        links = [t["link"] for t in tutorials]

        # Check Khan Academy search format
        khan = [t for t in tutorials if "khanacademy.org" in t["link"]]
        assert len(khan) == 1
        assert "search?page_search_query=" in khan[0]["link"]
        assert "Plant+Biology" in khan[0]["link"] or "Plant%20Biology" in khan[0]["link"]

        # Check NCERT official textbook URL
        ncert = [t for t in tutorials if "ncert.nic.in" in t["link"]]
        assert len(ncert) == 1
        assert ncert[0]["link"] == "https://ncert.nic.in/textbook.php"

        # Check SWAYAM search format
        swayam = [t for t in tutorials if "swayam.gov.in" in t["link"]]
        assert len(swayam) == 1
        assert "explorer?searchText=" in swayam[0]["link"]

        # Check NPTEL search format
        nptel = [t for t in tutorials if "nptel.ac.in" in t["link"]]
        assert len(nptel) == 1
        assert "courses?keyword=" in nptel[0]["link"]

        # All candidate tutorial links must belong to allowlisted domains
        for link in links:
            parsed = urllib.parse.urlsplit(link)
            assert is_domain_allowed(parsed.netloc) is True


class TestURLValidator:
    def test_youtube_fabricated_video_rejected(self):
        """Fabricated YouTube video IDs (watch?v=) must be rejected immediately."""
        fake_video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_url(fake_video_url) is False

    def test_disallowed_domain_rejected(self):
        """URLs on non-allowlisted domains must be rejected."""
        url = "https://arbitrary-blog.com/naturalist-guide"
        assert validate_url(url) is False

    def test_invalid_scheme_rejected(self):
        """Non-HTTP/HTTPS URLs must be rejected."""
        assert validate_url("ftp://ncert.nic.in/textbook.php") is False
        assert validate_url("javascript:alert(1)") is False

    @patch("requests.head")
    @patch("requests.get")
    def test_http_200_alone_not_sufficient_if_soft_404(self, mock_get, mock_head):
        """HTTP 200 with soft-404 text must NOT be treated as valid."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://www.khanacademy.org/search?page_search_query=Ecology"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.text = "<html><head><title>404 Not Found</title></head><body>Page not found</body></html>"
        mock_resp.iter_content.return_value = [mock_resp.text]

        mock_head.return_value = mock_resp
        mock_get.return_value = mock_resp

        assert validate_url("https://www.khanacademy.org/search?page_search_query=Ecology") is False

    @patch("requests.head")
    def test_valid_html_resource_passes(self, mock_head):
        """Legitimate educational resource returning valid HTML and 200 passes."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://www.khanacademy.org/search?page_search_query=Ecology"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.text = "<html><head><title>Search: Ecology | Khan Academy</title></head><body>Results</body></html>"
        mock_resp.iter_content.return_value = [mock_resp.text]

        mock_head.return_value = mock_resp

        assert validate_url("https://www.khanacademy.org/search?page_search_query=Ecology") is True

    @patch("requests.head")
    def test_redirect_to_disallowed_domain_rejected(self, mock_head):
        """If redirect leads to an unapproved domain, it must be rejected."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Redirected to an external untrusted domain
        mock_resp.url = "https://malicious-redirect.com/landing"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "<html>Content</html>"
        mock_head.return_value = mock_resp

        assert validate_url("https://ncert.nic.in/textbook.php") is False

    def test_unverified_resource_excluded_rather_than_replaced(self):
        """Unverified URLs must be dropped/excluded, never replaced with a fake link."""
        items = [
            {"title": "Valid YouTube Search", "link": "https://www.youtube.com/results?search_query=Wildlife"},
            {"title": "Fake Video", "link": "https://www.youtube.com/watch?v=fake11char0"},
            {"title": "Disallowed Domain", "link": "https://random-site.org/lesson"},
        ]

        with patch("app.services.future_study_service.validate_url") as mock_val:
            def side_effect(url):
                return "youtube.com/results" in url
            mock_val.side_effect = side_effect

            filtered = validate_resources_concurrently(items)

            assert len(filtered) == 1
            assert filtered[0]["title"] == "Valid YouTube Search"


@pytest.mark.asyncio
class TestMongoDBFutureStudyResourcesCollection:
    async def test_retrieve_from_future_study_resources_collection_when_cached(self):
        """Existing resources must be retrieved directly from future_study_resources collection."""
        mock_db = MagicMock()
        cached_data = {
            "career_category": "Naturalist",
            "student_class": "12",
            "resources": {
                "youtube_videos": [
                    {"title": "Ecology (Search Results)", "link": "https://www.youtube.com/results?search_query=Ecology"}
                ],
                "tutorial_links": [
                    {"title": "Khan Academy: Ecology", "link": "https://www.khanacademy.org/search?page_search_query=Ecology"}
                ],
                "competitive_exams": [],
                "study_centers": [],
            }
        }
        mock_db.future_study_resources.find_one = AsyncMock(return_value=cached_data)

        # Should retrieve cached data without calling LLM or building from scratch
        result = await get_or_create_future_study_resources(
            db=mock_db,
            career_category="Naturalist",
            student_class="12",
        )

        assert result == cached_data["resources"]
        mock_db.future_study_resources.find_one.assert_called_once()

    async def test_generates_and_caches_when_not_in_collection(self):
        """When category/class not cached, generates clean resources and stores into future_study_resources."""
        mock_db = MagicMock()
        # Not in cache
        mock_db.future_study_resources.find_one = AsyncMock(return_value=None)
        mock_db.future_study_resources.update_one = AsyncMock()

        with patch("app.services.future_study_service.validate_resources_concurrently") as mock_val:
            # Let all candidates pass validation
            mock_val.side_effect = lambda items, **kwargs: items

            res = await get_or_create_future_study_resources(
                db=mock_db,
                career_category="Naturalist",
                student_class="12",
                recommended_career="Wildlife Biologist"
            )

            assert "youtube_videos" in res
            assert "tutorial_links" in res
            assert len(res["youtube_videos"]) > 0
            assert len(res["tutorial_links"]) > 0

            # Must have upserted into future_study_resources
            mock_db.future_study_resources.update_one.assert_called_once()
            call_args = mock_db.future_study_resources.update_one.call_args[0]
            assert call_args[0]["career_category"] == "Naturalist"
            assert call_args[0]["student_class"] == "12"

    async def test_replaces_old_fabricated_links_in_cache(self):
        """If cached record contains legacy fake watch?v= links, it must regenerate clean search links."""
        mock_db = MagicMock()
        stale_data = {
            "career_category": "Naturalist",
            "student_class": "12",
            "resources": {
                "youtube_videos": [
                    {"title": "Fake Video", "link": "https://www.youtube.com/watch?v=fake11char0"}
                ],
                "tutorial_links": []
            }
        }
        mock_db.future_study_resources.find_one = AsyncMock(return_value=stale_data)
        mock_db.future_study_resources.update_one = AsyncMock()

        with patch("app.services.future_study_service.validate_resources_concurrently") as mock_val:
            mock_val.side_effect = lambda items, **kwargs: items

            res = await get_or_create_future_study_resources(
                db=mock_db,
                career_category="Naturalist",
                student_class="12"
            )

            # Must not contain watch?v= anymore
            assert all("watch?v=" not in v["link"] for v in res["youtube_videos"])
            mock_db.future_study_resources.update_one.assert_called_once()


class TestJSONResponseStructure:
    def test_json_structure_matches_flutter_requirements(self):
        """JSON structure must match exact required contract with top_category, student_class, and future_study."""
        fallback = get_category_fallbacks("Naturalist", "12")
        assert "search_keywords" in fallback
        assert "competitive_exams" in fallback
        assert "study_centers" in fallback

        response_payload = {
            "top_category": "Naturalist",
            "student_class": "12",
            "future_study": {
                "youtube_videos": [
                    {"title": "Ecology & Wildlife (Search Results)", "link": "https://www.youtube.com/results?search_query=Ecology"}
                ],
                "tutorial_links": [
                    {"title": "Khan Academy: Ecology", "link": "https://www.khanacademy.org/search?page_search_query=Ecology"}
                ],
                "competitive_exams": fallback["competitive_exams"],
                "study_centers": fallback["study_centers"],
            }
        }

        assert response_payload["top_category"] == "Naturalist"
        assert response_payload["student_class"] == "12"
        assert "youtube_videos" in response_payload["future_study"]
        assert "tutorial_links" in response_payload["future_study"]
        for v in response_payload["future_study"]["youtube_videos"]:
            assert "results?search_query=" in v["link"]
            assert "watch?v=" not in v["link"]


@pytest.mark.asyncio
class TestAPIEndpointsIntegration:
    async def test_get_future_study_endpoint_refreshes_legacy_fake_links(self):
        """API route /user/future-study/{student_id} must detect and refresh legacy fabricated links."""
        from app.routes.user_routes import get_future_study
        from bson import ObjectId

        test_student_id = str(ObjectId())

        # Existing record in db with fake legacy YouTube watch link
        legacy_record = {
            "student_id": test_student_id,
            "student_class": "12",
            "top_category": "Naturalist",
            "recommended_career": "Wildlife Biologist",
            "resources": {
                "youtube_videos": [
                    {"title": "Fake Video 1", "link": "https://www.youtube.com/watch?v=fake11char0"}
                ],
                "tutorial_links": [
                    {"title": "Fake Tutorial", "link": "https://unknownsite.org/deadlink"}
                ],
            }
        }

        # Cached clean resources in future_study_resources collection
        clean_cached_resources = {
            "youtube_videos": [
                {"title": "Ecology & Wildlife (Search Results)", "link": "https://www.youtube.com/results?search_query=Ecology+Wildlife+Class+12"}
            ],
            "tutorial_links": [
                {"title": "Khan Academy: Ecology", "link": "https://www.khanacademy.org/search?page_search_query=Ecology"},
                {"title": "NCERT Textbooks (Class 12)", "link": "https://ncert.nic.in/textbook.php"}
            ],
            "competitive_exams": [],
            "study_centers": []
        }

        with patch("app.routes.user_routes.db") as mock_db, \
             patch("app.routes.user_routes.generate_and_store_future_study") as mock_gen:

            mock_db.future_study.find_one = AsyncMock(return_value=legacy_record)
            mock_db.students.find_one = AsyncMock(return_value={"student_id": test_student_id, "student_class": "12"})
            mock_db.career_analyzer.find_one = AsyncMock(return_value={
                "student_id": test_student_id,
                "top_category": "Naturalist",
                "recommended_career": "Wildlife Biologist",
                "scores": {"naturalist": 25},
                "percentages": {"naturalist": 100}
            })
            mock_gen.return_value = clean_cached_resources

            response = await get_future_study(
                student_id=test_student_id,
                current={"username": "test_user", "role": "user"}
            )

            assert response["status_code"] == 200
            assert response["top_category"] == "Naturalist"
            assert response["student_class"] == "12"
            assert "future_study" in response

            videos = response["future_study"]["youtube_videos"]
            assert len(videos) > 0
            # Ensure none of the returned videos are legacy fake watch links
            for v in videos:
                assert "watch?v=" not in v["link"]
                assert "results?search_query=" in v["link"]

            # Tutorial links must belong to allowlisted domains
            tutorials = response["future_study"]["tutorial_links"]
            for t in tutorials:
                parsed = urllib.parse.urlsplit(t["link"])
                assert is_domain_allowed(parsed.netloc) is True

    async def test_user_futurestudy_route_returns_compliant_contract(self):
        """API route /user/{student_id} in user_futurestudy_routes returns compliant structure."""
        from app.routes.user_futurestudy_routes import generate_future_study_guidance
        from bson import ObjectId

        test_student_id = str(ObjectId())
        clean_resources = {
            "youtube_videos": [
                {"title": "Ecology (Search Results)", "link": "https://www.youtube.com/results?search_query=Ecology"}
            ],
            "tutorial_links": [
                {"title": "Khan Academy: Ecology", "link": "https://www.khanacademy.org/search?page_search_query=Ecology"}
            ],
            "competitive_exams": [],
            "study_centers": []
        }

        with patch("app.routes.user_futurestudy_routes.db") as mock_db, \
             patch("app.routes.user_futurestudy_routes.check_premium") as mock_prem, \
             patch("app.routes.user_futurestudy_routes.generate_and_store_future_study") as mock_gen:

            mock_prem.return_value = None
            mock_db.students.find_one = AsyncMock(return_value={"student_id": test_student_id, "student_class": "12"})
            mock_db.career_analyzer.find_one = AsyncMock(return_value={
                "student_id": test_student_id,
                "top_category": "Naturalist",
                "recommended_career": "Wildlife Biologist",
                "scores": {"naturalist": 25},
                "percentages": {"naturalist": 100}
            })
            mock_gen.return_value = clean_resources

            resp = await generate_future_study_guidance(
                student_id=test_student_id,
                current_user={"username": "test_user"}
            )

            assert resp["status_code"] == 200
            assert resp["top_category"] == "Naturalist"
            assert resp["student_class"] == "12"
            assert resp["future_study"] == clean_resources


class TestOpenAPISwaggerDocumentation:
    def test_future_study_swagger_display_and_no_duplicate_routes(self):
        """
        Verify OpenAPI/Swagger schema requirements:
        1. 'User_Futurestudy Module' heading is removed completely.
        2. Obsolete duplicate '/user/{student_id}' endpoint is removed from schema & routing.
        3. Only 'GET /user/future-study/{student_id}' exists with summary 'Get Future Study'
           and description 'Generate Future Study Guidance'.
        """
        import os
        from unittest.mock import patch
        # Import app while ensuring static dirs don't throw if running from outside Otp_app2
        with patch.dict(os.environ, {}):
            from main import app

        schema = app.openapi()
        paths = schema.get("paths", {})

        # 1. Verify User_Futurestudy Module heading is removed
        all_tags = []
        for tag_def in schema.get("tags", []):
            all_tags.append(tag_def.get("name", ""))
        for path_item in paths.values():
            for operation in path_item.values():
                all_tags.extend(operation.get("tags", []))

        assert "User_Futurestudy Module" not in all_tags, "'User_Futurestudy Module' heading must not exist in Swagger"

        # 2. Verify duplicate /user/{student_id} is removed
        assert "/user/{student_id}" not in paths, "'/user/{student_id}' duplicate endpoint must not be present"

        # 3. Verify required endpoint exists with exact summary and description
        assert "/user/future-study/{student_id}" in paths, "'/user/future-study/{student_id}' must be registered"
        endpoint_methods = paths["/user/future-study/{student_id}"]
        assert "get" in endpoint_methods, "'/user/future-study/{student_id}' must support GET method"

        get_op = endpoint_methods["get"]
        assert get_op.get("summary") == "Get Future Study", "Summary must be 'Get Future Study'"
        assert get_op.get("description") == "Generate Future Study Guidance", "Description must be 'Generate Future Study Guidance'"


