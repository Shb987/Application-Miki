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


def test_get_competitive_tutorials_with_category_id_as_name(mock_db):
    """
    Verify get_competitive_tutorials resolves category_id passed as category name or ID string.
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
        "category_id": "672900000000000000000001",
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
    tut_cursor.sort.return_value.to_list = AsyncMock(return_value=[sample_tutorial])
    tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[sample_tutorial])
    mock_db.competitive_tutorials.find.return_value = tut_cursor
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=1)

    # Mock textbooks
    sample_textbook = {
        "_id": ObjectId("672900000000000000000020"),
        "textbook_title": "Kerala History & Culture",
        "category_id": "672900000000000000000001",
        "exam_category": "Kerala PSC",
        "exam_name": "KAS",
        "subject": "History",
        "total_pages": 240,
        "chapters": ["Chapter 1: Ancient Kerala", "Chapter 2: Modern Era"],
        "created_at": "2026-11-05T10:00:00+05:30"
    }
    tb_cursor = MagicMock()
    tb_cursor.sort.return_value.to_list = AsyncMock(return_value=[sample_textbook])
    tb_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[sample_textbook])
    mock_db.textbook.find.return_value = tb_cursor
    mock_db.textbook.count_documents = AsyncMock(return_value=1)

    res = asyncio.run(get_competitive_tutorials(category_id="Kerala PSC"))

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
    tut_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
    tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    mock_db.competitive_tutorials.find.return_value = tut_cursor
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=0)

    tb_cursor = MagicMock()
    tb_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
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

    # Verify that GET /user/competitive-exams/tutorials uses ONLY category_id as its query parameter
    tut_get_op = paths.get("/user/competitive-exams/tutorials", {}).get("get", {})
    tut_param_names = [p.get("name") for p in tut_get_op.get("parameters", [])]
    assert tut_param_names == ["category_id"], f"Expected ONLY ['category_id'] in parameters, got: {tut_param_names}"
    for removed_param in ["category", "category_name", "exam_name", "subject", "topic", "search", "limit", "skip"]:
        assert removed_param not in tut_param_names, f"{removed_param} should be removed from query parameters"

    # Ensure separate obsolete endpoints are NOT present
    assert ("/user/competitive-exams/exams") not in [p for _, p, _ in comp_endpoints]
    assert ("/user/competitive-exams/textbooks") not in [p for _, p, _ in comp_endpoints]
    assert ("/user/competitive-exams/papers") not in [p for _, p, _ in comp_endpoints]


def test_category_creation_and_tutorials_filter_flow(mock_db):
    """
    End-to-end verification of the user request:
    1. Admin adds a category via add_category.
    2. Category dynamically appears in GET /user/competitive-exams/categories (list_categories).
    3. The category's _id is passed to GET /user/competitive-exams/tutorials (get_competitive_tutorials).
    4. Relevant tutorials and textbooks are filtered and returned based strictly on category_id.
    """
    from app.routes.admin_competitive_exam_routes import add_category
    from app.routes.user_competitive_exam_routes import list_categories, get_competitive_tutorials
    from app.models.competitive_exam_models import CompetitiveCategoryCreateRequest
    import asyncio

    new_cat_id = ObjectId("672900000000000000000055")
    created_doc = None

    async def mock_insert_one(doc):
        nonlocal created_doc
        created_doc = {**doc, "_id": new_cat_id}
        res = MagicMock()
        res.inserted_id = new_cat_id
        return res

    mock_db.competitive_exam_categories.find_one = AsyncMock(return_value=None)
    mock_db.competitive_exam_categories.insert_one = AsyncMock(side_effect=mock_insert_one)

    # 1. Admin adds new category
    req = MagicMock()
    payload = CompetitiveCategoryCreateRequest(
        category_name="GATE",
        description="Graduate Aptitude Test in Engineering",
        icon="fa-flask"
    )
    with patch("app.routes.admin_competitive_exam_routes.db", mock_db):
        admin_res = asyncio.run(add_category(request=req, payload=payload))

    assert admin_res["status"] == "success"
    assert admin_res["category"]["_id"] == str(new_cat_id)
    assert admin_res["category"]["category_name"] == "GATE"

    # 2. list_categories fetches this category
    mock_db.competitive_exam_categories.count_documents = AsyncMock(return_value=1)
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.to_list = AsyncMock(return_value=[created_doc])
    mock_db.competitive_exam_categories.find.return_value = mock_cursor

    mock_db.competitive_exams.count_documents = AsyncMock(return_value=0)
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=1)
    mock_db.textbook.count_documents = AsyncMock(return_value=1)

    cats_res = asyncio.run(list_categories())
    assert cats_res["status"] == "success"
    assert len(cats_res["categories"]) == 1
    retrieved_cat = cats_res["categories"][0]
    assert retrieved_cat["_id"] == str(new_cat_id)
    assert retrieved_cat["category_name"] == "GATE"
    assert retrieved_cat["icon"] == "fa-flask"

    # 3. get_competitive_tutorials called with category_id only
    mock_db.competitive_exam_categories.find_one = AsyncMock(return_value=created_doc)

    gate_tut = {
        "_id": ObjectId("672900000000000000000066"),
        "title": "GATE Computer Science - Data Structures",
        "category_id": str(new_cat_id),
        "category_name": "GATE",
        "exam_name": "GATE CS",
        "subject": "Computer Science",
        "topic": "Trees & Graphs",
        "video_links": [{"title": "Lec 1", "link": "https://youtube.com/watch?v=123"}],
        "is_active": True,
        "created_at": "2026-11-10T10:00:00+05:30"
    }
    tut_cursor = MagicMock()
    tut_cursor.sort.return_value.to_list = AsyncMock(return_value=[gate_tut])
    tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[gate_tut])
    mock_db.competitive_tutorials.find.return_value = tut_cursor
    mock_db.competitive_tutorials.count_documents = AsyncMock(return_value=1)

    gate_tb = {
        "_id": ObjectId("672900000000000000000077"),
        "textbook_title": "Algorithms & Data Structures for GATE",
        "category_id": str(new_cat_id),
        "exam_category": "GATE",
        "exam_name": "GATE CS",
        "subject": "Computer Science",
        "total_pages": 450,
        "chapters": ["Chapter 1: Asymptotic Analysis"],
        "created_at": "2026-11-10T10:00:00+05:30"
    }
    tb_cursor = MagicMock()
    tb_cursor.sort.return_value.to_list = AsyncMock(return_value=[gate_tb])
    tb_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[gate_tb])
    mock_db.textbook.find.return_value = tb_cursor
    mock_db.textbook.count_documents = AsyncMock(return_value=1)

    tut_res = asyncio.run(get_competitive_tutorials(category_id=str(new_cat_id)))

    assert tut_res["status"] == "success"
    assert tut_res["category_id"] == str(new_cat_id)
    assert tut_res["category_name"] == "GATE"
    assert tut_res["total_tutorials"] == 1
    assert tut_res["total_textbooks"] == 1
    assert tut_res["tutorials"][0]["title"] == "GATE Computer Science - Data Structures"
    assert tut_res["textbooks"][0]["textbook_title"] == "Algorithms & Data Structures for GATE"

    """
    Verify admin add_category endpoint validates input, inserts into db.competitive_exam_categories,
    and returns properly serialized category document.
    """
    from app.routes.admin_competitive_exam_routes import add_category
    from app.models.competitive_exam_models import CompetitiveCategoryCreateRequest
    import asyncio

    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db:
        mock_admin_db.competitive_exam_categories.find_one = AsyncMock(return_value=None)
        mock_insert_res = MagicMock()
        mock_insert_res.inserted_id = ObjectId("672900000000000000000099")
        mock_admin_db.competitive_exam_categories.insert_one = AsyncMock(return_value=mock_insert_res)

        mock_req = MagicMock()
        payload = CompetitiveCategoryCreateRequest(
            category_name="Karnataka PSC",
            description="Karnataka Public Service Commission",
            icon="fa-university"
        )

        res = asyncio.run(add_category(request=mock_req, payload=payload))
        assert res["status"] == "success"
        assert "Karnataka PSC" in res["message"]
        cat = res["category"]
        assert cat["_id"] == "672900000000000000000099"
        assert cat["category_name"] == "Karnataka PSC"
        assert cat["icon"] == "fa-university"
        assert cat["is_active"] is True


def test_objectid_serialization_in_fastapi():
    """
    Verify that bson.ObjectId objects anywhere in responses or nested structures
    serialize cleanly to strings via jsonable_encoder without throwing:
    ValueError: [TypeError("'ObjectId' object is not iterable"), TypeError('vars() argument must have __dict__ attribute')]
    """
    import fastapi.encoders
    from bson import ObjectId

    sample_response = {
        "_id": ObjectId("6ad5e500b34330eed859acf5"),
        "category_id": ObjectId("6ad5e500b34330eed859acf6"),
        "tutorials": [
            {
                "_id": ObjectId("6aeaf1c3627ae009c2f48b47"),
                "video_links": [{"vid_id": ObjectId("6aeaf1c3627ae009c2f48b48")}]
            }
        ]
    }

    encoded = fastapi.encoders.jsonable_encoder(sample_response)
    assert encoded["_id"] == "6ad5e500b34330eed859acf5"
    assert encoded["category_id"] == "6ad5e500b34330eed859acf6"
    assert encoded["tutorials"][0]["_id"] == "6aeaf1c3627ae009c2f48b47"
    assert encoded["tutorials"][0]["video_links"][0]["vid_id"] == "6aeaf1c3627ae009c2f48b48"


