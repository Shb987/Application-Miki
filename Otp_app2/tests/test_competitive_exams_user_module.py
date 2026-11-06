import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


@pytest.fixture
def mock_db():
    with patch("app.routes.user_competitive_exam_routes.db") as mock_database:
        yield mock_database


def test_list_categories_structure(mock_db):
    """Verify list_categories returns categories dynamically with counts."""
    from app.routes.user_competitive_exam_routes import list_categories
    import asyncio

    sample_cat_id = ObjectId("672900000000000000000001")
    sample_categories = [
        {
            "_id": sample_cat_id,
            "category_name": "Kerala PSC",
            "description": "Kerala Public Service Commission examinations",
            "icon": "fa-certificate",
            "is_active": True
        },
        {
            "_id": ObjectId("672900000000000000000002"),
            "category_name": "UPSC Civil Services",
            "description": "Union Public Service Commission examinations",
            "icon": "fa-university",
            "is_active": True
        }
    ]

    mock_db.competitive_exam_categories.count_documents = AsyncMock(return_value=2)
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=sample_categories)
    mock_db.competitive_exam_categories.find.return_value = mock_cursor

    mock_db.competitive_exams.count_documents = AsyncMock(return_value=5)
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=3)
    mock_db.textbook.count_documents = AsyncMock(return_value=4)

    res = asyncio.run(list_categories())

    assert res["status"] == "success"
    assert res["total_categories"] == 2
    cats = res["categories"]
    assert len(cats) == 2
    assert cats[0]["category_name"] == "Kerala PSC"
    assert cats[0]["_id"] == str(sample_cat_id)
    assert cats[0]["exam_count"] == 5
    assert cats[0]["tutorial_count"] == 3
    assert cats[0]["textbook_count"] == 4


def test_get_competitive_tutorials_with_category_name(mock_db):
    """
    Verify get_competitive_tutorials returns both tutorials and textbooks
    when passing category name from list_categories API.
    """
    from app.routes.user_competitive_exam_routes import get_competitive_tutorials
    import asyncio

    # Mock category resolution lookup
    mock_db.competitive_exam_categories.find_one = AsyncMock(return_value={
        "_id": ObjectId("672900000000000000000001"),
        "category_name": "Kerala PSC"
    })

    # Mock tutorials
    sample_tutorial = {
        "_id": ObjectId("672900000000000000000010"),
        "title": "Kerala PSC - Indian History",
        "category_name": "Kerala PSC",
        "exam_name": "KAS",
        "subject": "History",
        "topic": "Freedom Movement",
        "youtube_url": "https://www.youtube.com/playlist?list=PL123",
        "video_links": [
            {"title": "Part 1", "link": "https://www.youtube.com/watch?v=abc12345678", "thumbnail": ""}
        ],
        "is_active": True,
        "created_at": "2026-11-05T10:00:00+05:30"
    }
    tut_cursor = MagicMock()
    tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[sample_tutorial])
    mock_db.competitive_tutorials.find.return_value = tut_cursor
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=1)

    # Mock textbooks
    sample_textbook = {
        "_id": ObjectId("672900000000000000000020"),
        "textbook_title": "Kerala History & Culture",
        "exam_category": "Kerala PSC",
        "exam_name": "KAS",
        "subject": "History",
        "total_pages": 240,
        "chapters": ["Chapter 1: Ancient Kerala", "Chapter 2: Modern Era"],
        "created_at": "2026-11-05T10:00:00+05:30"
    }
    tb_cursor = MagicMock()
    tb_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[sample_textbook])
    mock_db.textbook.find.return_value = tb_cursor
    mock_db.textbook.count_documents = AsyncMock(return_value=1)

    res = asyncio.run(get_competitive_tutorials(category="Kerala PSC"))

    assert res["status"] == "success"
    assert res["category"] == "Kerala PSC"
    assert res["total_tutorials"] == 1
    assert res["total_textbooks"] == 1

    # Validate tutorials payload
    assert len(res["tutorials"]) == 1
    tut = res["tutorials"][0]
    assert tut["_id"] == "672900000000000000000010"
    assert tut["title"] == "Kerala PSC - Indian History"
    assert tut["exam_name"] == "KAS"
    assert len(tut["video_links"]) == 1

    # Validate textbooks payload
    assert len(res["textbooks"]) == 1
    tb = res["textbooks"][0]
    assert tb["_id"] == "672900000000000000000020"
    assert tb["textbook_title"] == "Kerala History & Culture"
    assert tb["chapters_count"] == 2


def test_get_competitive_tutorials_with_category_id(mock_db):
    """
    Verify get_competitive_tutorials resolves category_id passed from list_categories API.
    """
    from app.routes.user_competitive_exam_routes import get_competitive_tutorials
    import asyncio

    cat_oid_str = "672900000000000000000001"
    mock_db.competitive_exam_categories.find_one = AsyncMock(return_value={
        "_id": ObjectId(cat_oid_str),
        "category_name": "Kerala PSC"
    })

    tut_cursor = MagicMock()
    tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    mock_db.competitive_tutorials.find.return_value = tut_cursor
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=0)

    tb_cursor = MagicMock()
    tb_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    mock_db.textbook.find.return_value = tb_cursor
    mock_db.textbook.count_documents = AsyncMock(return_value=0)

    res = asyncio.run(get_competitive_tutorials(category_id=cat_oid_str))

    assert res["status"] == "success"
    assert res["category"] == "Kerala PSC"
    assert res["category_id"] == cat_oid_str
    assert res["total_tutorials"] == 0
    assert res["total_textbooks"] == 0
    assert res["tutorials"] == []
    assert res["textbooks"] == []


def test_openapi_schema_only_two_competitive_user_endpoints():
    """
    Verify that in OpenAPI / Swagger documentation:
    1. ONLY 2 endpoints exist under 'Competitive Exams - User' tag.
    2. Endpoint 1: GET /user/competitive-exams/categories
    3. Endpoint 2: GET /user/competitive-exams/tutorials
    4. Separate Exams, Textbooks, Papers, Download Paper endpoints are NOT present.
    """
    from main import app

    schema = app.openapi()
    paths = schema.get("paths", {})

    comp_endpoints = []
    for path, methods in paths.items():
        for method, op in methods.items():
            if "Competitive Exams - User" in op.get("tags", []):
                comp_endpoints.append((method.upper(), path, op.get("summary")))

    assert len(comp_endpoints) == 2, f"Expected exactly 2 endpoints under Competitive Exams - User, got {len(comp_endpoints)}: {comp_endpoints}"
    endpoints_dict = {(m, p): s for m, p, s in comp_endpoints}

    assert ("GET", "/user/competitive-exams/categories") in endpoints_dict
    assert endpoints_dict[("GET", "/user/competitive-exams/categories")] == "List Exam Categories"

    assert ("GET", "/user/competitive-exams/tutorials") in endpoints_dict
    assert endpoints_dict[("GET", "/user/competitive-exams/tutorials")] == "Get Competitive Tutorials"

    # Ensure separate obsolete endpoints are NOT present
    assert ("/user/competitive-exams/exams") not in [p for _, p, _ in comp_endpoints]
    assert ("/user/competitive-exams/textbooks") not in [p for _, p, _ in comp_endpoints]
    assert ("/user/competitive-exams/papers") not in [p for _, p, _ in comp_endpoints]

