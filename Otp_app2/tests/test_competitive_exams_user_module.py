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
            "cover_image": "/uploads/competitive_categories/kerala_psc.png",
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
    assert cats[0]["cover_image"] == "/uploads/competitive_categories/kerala_psc.png"
    assert cats[1]["cover_image"] == ""
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

    # Validate textbooks payload (full PDF URL, no extracted chapters)
    assert len(res["textbooks"]) == 1
    tb = res["textbooks"][0]
    assert tb["_id"] == "672900000000000000000020"
    assert tb["textbook_title"] == "Kerala History & Culture"
    assert tb["chapters_count"] == 2
    assert "chapters" not in tb
    assert "pdf_url" in tb
    assert tb["pdf_url"].startswith("/static/textbook/")
    assert "download_url" in tb
    assert "file_url" in tb
    assert tb["total_pages"] == 240


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


def test_update_category_cascades_name():
    """Verify updating category name cascades updates across textbooks, tutorials, and exams."""
    from app.routes.admin_competitive_exam_routes import update_category
    import asyncio

    cat_id = ObjectId("672900000000000000000088")
    existing_cat = {
        "_id": cat_id,
        "category_name": "Old Category",
        "description": "Old Description",
        "icon": "fa-university",
        "is_active": True
    }
    updated_cat = {
        "_id": cat_id,
        "category_name": "New Category",
        "description": "Updated Description",
        "icon": "fa-certificate",
        "is_active": True
    }

    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db:
        # 1st find_one is existing, 2nd is duplicate check (None), 3rd is reload updated_doc
        mock_admin_db.competitive_exam_categories.find_one = AsyncMock(side_effect=[
            existing_cat,
            None,
            updated_cat
        ])
        mock_admin_db.competitive_exam_categories.update_one = AsyncMock()
        mock_admin_db.textbook.update_many = AsyncMock()
        mock_admin_db.competitive_tutorials.update_many = AsyncMock()
        mock_admin_db.competitive_exams.update_many = AsyncMock()

        mock_req = MagicMock()
        res = asyncio.run(update_category(
            category_id=str(cat_id),
            request=mock_req,
            payload={
                "category_name": "New Category",
                "description": "Updated Description",
                "icon": "fa-certificate",
                "is_active": True
            }
        ))

        assert res["status"] == "success"
        assert res["category"]["category_name"] == "New Category"
        # Verify cascade calls
        mock_admin_db.textbook.update_many.assert_called_once()
        mock_admin_db.competitive_tutorials.update_many.assert_called_once()
        mock_admin_db.competitive_exams.update_many.assert_called_once()


def test_delete_category():
    """Verify deleting category removes it from DB."""
    from app.routes.admin_competitive_exam_routes import delete_category
    import asyncio

    cat_id = ObjectId("672900000000000000000077")
    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db:
        mock_del_res = MagicMock()
        mock_del_res.deleted_count = 1
        mock_admin_db.competitive_exam_categories.delete_one = AsyncMock(return_value=mock_del_res)

        res = asyncio.run(delete_category(category_id=str(cat_id)))
        assert res["status"] == "success"
        assert "deleted successfully" in res["message"]


def test_sidebar_and_page_routes():
    """Verify sidebar menu order and page template rendering."""
    with open("app/templates/admin/template/sidebar.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Verify menu structure and ordering under Competitive Exams
    sub_menu_idx = content.find('id="competitive-exams-submenu"')
    assert sub_menu_idx != -1

    snippet = content[sub_menu_idx:sub_menu_idx + 1200]
    pos_add_cat = snippet.find('/admin-panel/competitive-exams/manage-categories')
    pos_upload = snippet.find('/admin-panel/competitive-exams/upload-textbook')
    pos_manage = snippet.find('/admin-panel/competitive-exams/manage-exams')
    pos_gen = snippet.find('/admin-panel/competitive-exams/generate-questions')
    pos_tut = snippet.find('/admin-panel/competitive-exams/tutorials')

    assert pos_add_cat != -1
    assert pos_upload != -1
    assert pos_manage != -1
    assert pos_gen != -1
    assert pos_tut != -1

    # Verify ordering: Add Category -> Upload Textbooks -> Manage Exams -> Generate Question Papers -> Tutorials
    assert pos_add_cat < pos_upload < pos_manage < pos_gen < pos_tut

    # Verify individual categories list is removed from sidebar
    assert "id=\"sidebar-dynamic-categories\"" not in snippet


def test_category_cover_image_crud_and_endpoints():
    """Verify add_category, update_category, and get_categories handle cover_image properly."""
    from app.routes.admin_competitive_exam_routes import add_category, update_category, get_categories
    from fastapi import Request
    import asyncio
    import io

    # Mock DB in admin routes
    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db:
        # 1. Test get_categories returns cover_image
        cat_id = ObjectId("672900000000000000000099")
        sample_cat = {
            "_id": cat_id,
            "category_name": "SSC",
            "description": "Staff Selection Commission",
            "icon": "fa-id-card",
            "cover_image": "/uploads/competitive_categories/ssc_banner.png",
            "is_active": True
        }
        cursor = MagicMock()
        cursor.sort.return_value.to_list = AsyncMock(return_value=[sample_cat])
        mock_admin_db.competitive_exam_categories.find.return_value = cursor
        mock_admin_db.textbook.count_documents = AsyncMock(return_value=2)
        mock_admin_db.competitive_tutorials.count_documents = AsyncMock(return_value=1)
        mock_admin_db.competitive_exams.count_documents = AsyncMock(return_value=3)

        get_res = asyncio.run(get_categories())
        assert get_res["status"] == "success"
        assert len(get_res["categories"]) == 1
        assert get_res["categories"][0]["cover_image"] == "/uploads/competitive_categories/ssc_banner.png"

        # 2. Test add_category with JSON payload containing cover_image
        mock_admin_db.competitive_exam_categories.find_one = AsyncMock(return_value=None)
        inserted_id = ObjectId("672900000000000000000100")
        mock_admin_db.competitive_exam_categories.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=inserted_id)
        )

        mock_req = MagicMock(spec=Request)
        mock_req.headers = {"content-type": "application/json"}
        mock_req.json = AsyncMock(return_value={
            "category_name": "Banking & Insurance",
            "description": "IBPS, SBI PO, Clerk exams",
            "icon": "fa-money",
            "cover_image": "/uploads/competitive_categories/banking_cover.jpg",
            "is_active": True
        })

        add_res = asyncio.run(add_category(request=mock_req))
        assert add_res["status"] == "success"
        assert add_res["category"]["category_name"] == "Banking & Insurance"
        assert add_res["category"]["cover_image"] == "/uploads/competitive_categories/banking_cover.jpg"

        # 3. Test update_category updates cover_image
        existing_doc = {
            "_id": inserted_id,
            "category_name": "Banking & Insurance",
            "description": "IBPS, SBI PO, Clerk exams",
            "icon": "fa-money",
            "cover_image": "/uploads/competitive_categories/banking_cover.jpg",
            "is_active": True
        }
        updated_doc = {
            **existing_doc,
            "cover_image": "/uploads/competitive_categories/banking_new.jpg"
        }
        mock_admin_db.competitive_exam_categories.find_one = AsyncMock(
            side_effect=[existing_doc, updated_doc]
        )
        mock_admin_db.competitive_exam_categories.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_admin_db.textbook.update_many = AsyncMock()
        mock_admin_db.competitive_tutorials.update_many = AsyncMock()
        mock_admin_db.competitive_exams.update_many = AsyncMock()

        update_req = MagicMock(spec=Request)
        update_req.headers = {"content-type": "application/json"}
        update_req.json = AsyncMock(return_value={
            "category_name": "Banking & Insurance",
            "cover_image": "/uploads/competitive_categories/banking_new.jpg"
        })

        up_res = asyncio.run(update_category(category_id=str(inserted_id), request=update_req))
        assert up_res["status"] == "success"
        assert up_res["category"]["cover_image"] == "/uploads/competitive_categories/banking_new.jpg"


def test_validate_pdf_file():
    """Verify validate_pdf_file rejects corrupt bytes and accepts valid PDF structures."""
    import pymupdf
    from app.routes.admin_competitive_exam_routes import validate_pdf_file

    # 1. Valid PDF with 2 pages
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Chapter 1: Introduction to Polity")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Chapter 2: Fundamental Rights")
    valid_pdf_bytes = doc.tobytes()
    doc.close()

    is_valid, page_count, err = validate_pdf_file(valid_pdf_bytes)
    assert is_valid is True
    assert page_count == 2
    assert err == ""

    # 2. Corrupt / empty bytes
    is_valid_bad, _, err_bad = validate_pdf_file(b"Corrupted dummy PDF payload")
    assert is_valid_bad is False
    assert err_bad != ""


def test_generate_chapter_mcqs_contract_and_structure():
    """Verify generate_chapter_mcqs produces 4-option MCQs with answers, explanations, and difficulty tags."""
    import asyncio
    from app.routes.admin_competitive_exam_routes import generate_chapter_mcqs

    chapter_text = """
    The Preamble to the Constitution of India is a brief introductory statement that sets out the guiding purpose,
    principles and philosophy of the Constitution. The Constitution of India was adopted on 26 November 1949 by the
    Constituent Assembly and became effective on 26 January 1950. Dr. B. R. Ambedkar was the Chairman of the Drafting
    Committee. The Constitution declares India a sovereign, socialist, secular, and democratic republic.
    """
    seen = set()
    passages = [{"content": chapter_text, "page_range": "1-2", "topics": ["Preamble", "Constitution"]}]
    mcqs = asyncio.run(generate_chapter_mcqs(
        chapter_title="Chapter 1: The Preamble",
        chapter_passages=passages,
        exam_name="SSC CGL",
        subject="Indian Polity",
        target_count=3,
        seen_questions=seen
    ))

    assert len(mcqs) >= 1
    for mcq in mcqs:
        assert "question" in mcq and len(mcq["question"].strip()) > 5
        assert "options" in mcq and len(mcq["options"]) == 4
        # Options format with A, B, C, D
        assert set(mcq["options"].keys()) == {"A", "B", "C", "D"}
        for k in ["A", "B", "C", "D"]:
            assert len(str(mcq["options"][k]).strip()) > 0
        assert mcq.get("correct_answer") in ["A", "B", "C", "D"]
        assert "explanation" in mcq and len(mcq["explanation"].strip()) > 0
        assert mcq["difficulty"] in ["Easy", "Medium", "Hard"]
        assert "chapter_reference" in mcq and "Chapter 1: The Preamble" in mcq["chapter_reference"]


def test_textbook_question_bank_pipeline_and_tutorials_response(tmp_path):
    """
    End-to-end integration test:
    1. Pipeline generates question bank PDF from stored vectors.
    2. Validates generated PDF structure and purges temporary source PDF.
    3. Verifies GET /user/competitive-exams/tutorials returns the exact required JSON structure with pdf_url.
    """
    import asyncio
    import pymupdf
    from app.routes.admin_competitive_exam_routes import generate_textbook_question_bank_pipeline
    from app.routes.user_competitive_exam_routes import get_competitive_tutorials

    tb_id = "6af2bac3162d857fa1495cbc"
    cat_id = "6ae4345bbf329b258a4f41fc"

    # Create dummy source PDF file to test cleanup
    src_pdf = tmp_path / "original_textbook.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Source textbook content")
    doc.save(str(src_pdf))
    doc.close()
    assert os.path.exists(str(src_pdf))

    # Mock stored chapters in textbook_chapters
    stored_chunks = [
        {
            "_id": ObjectId("672900000000000000000501"),
            "textbook_id": tb_id,
            "chapter_title": "Chapter 1: Alphabet or Word Test",
            "content": "The Alphabet Test involves arranging words in alphabetical order based on their initial letters.",
            "page_range": "1-5",
            "topics": ["Reasoning", "Alphabet"]
        },
        {
            "_id": ObjectId("672900000000000000000502"),
            "textbook_id": tb_id,
            "chapter_title": "Chapter 6: Coding Decoding",
            "content": "Coding and decoding tests reasoning ability to decipher hidden patterns or shifted cipher keys.",
            "page_range": "20-25",
            "topics": ["Reasoning", "Coding"]
        }
    ]

    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db, \
         patch("app.routes.user_competitive_exam_routes.db") as mock_user_db:

        # Setup mock DB for admin pipeline
        chunks_cursor = MagicMock()
        chunks_cursor.to_list = AsyncMock(return_value=stored_chunks)
        mock_admin_db.textbook_chapters.find.return_value = chunks_cursor

        mock_admin_db.textbook.find_one = AsyncMock(return_value={
            "_id": ObjectId(tb_id),
            "textbook_id": tb_id,
            "textbook_title": "Smart Question Bank",
            "category_id": cat_id,
            "exam_category": "SSC",
            "exam_name": "SSC CGL (Tier 1 General Studies)",
            "subject": "General Intelligence & Reasoning",
            "total_pages": 51,
            "chapters_count": 2,
            "original_filename": "original_textbook.pdf"
        })
        mock_admin_db.textbook.update_one = AsyncMock()
        mock_admin_db.chapter_status.update_one = AsyncMock()
        mock_admin_db.generated_papers.insert_one = AsyncMock()

        # Run pipeline with client=None to use reliable extractive generation
        with patch("app.routes.admin_competitive_exam_routes.client", None):
            res = asyncio.run(generate_textbook_question_bank_pipeline(
                textbook_id=tb_id,
                file_path=str(src_pdf)
            ))

        assert res["status"] == "completed"
        assert res["questions_generated"] >= 2
        assert os.path.exists(res["pdf_path"])
        # Verify source PDF has been deleted
        assert not os.path.exists(str(src_pdf))

        # Verify db.textbook was updated with generated PDF links and status
        completed_calls = [c[0][1]["$set"] for c in mock_admin_db.textbook.update_one.call_args_list if "$set" in c[0][1] and c[0][1]["$set"].get("question_bank_status") == "Completed"]
        assert len(completed_calls) > 0
        update_call_args = completed_calls[0]
        assert update_call_args["question_bank_status"] == "Completed"
        assert update_call_args["pdf_url"].startswith("/static/textbook/")
        assert update_call_args["download_url"].startswith("/static/textbook/")
        assert update_call_args["file_url"].startswith("/static/textbook/")
        assert update_call_args["chapters_count"] == 2

        # 4. Now test GET /user/competitive-exams/tutorials returns this structure
        user_tb_doc = {
            "_id": ObjectId(tb_id),
            "textbook_id": tb_id,
            "textbook_title": "Smart Question Bank",
            "category_id": cat_id,
            "exam_category": "SSC",
            "exam_name": "SSC CGL (Tier 1 General Studies)",
            "subject": "General Intelligence & Reasoning",
            "total_pages": 51,
            "chapters_count": 2,
            "pdf_url": update_call_args["pdf_url"],
            "download_url": update_call_args["download_url"],
            "file_url": update_call_args["file_url"],
            "original_filename": "original_textbook.pdf",
            "uploaded_at": "2026-11-10T14:47:20.152000+05:30",
            "created_at": "2026-11-10T14:47:20.152000+05:30",
            "chapters": ["Chapter 1", "Chapter 2"]  # legacy chapters array should not be passed to user
        }

        mock_user_db.competitive_exam_categories.find_one = AsyncMock(return_value={
            "_id": ObjectId(cat_id),
            "category_name": "SSC"
        })
        tut_cursor = MagicMock()
        tut_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
        tut_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        mock_user_db.competitive_tutorials.find.return_value = tut_cursor
        mock_user_db.competitive_tutorials.count_documents = AsyncMock(return_value=0)

        tb_cursor = MagicMock()
        tb_cursor.sort.return_value.to_list = AsyncMock(return_value=[user_tb_doc])
        tb_cursor.sort.return_value.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=[user_tb_doc])
        mock_user_db.textbook.find.return_value = tb_cursor
        mock_user_db.textbook.count_documents = AsyncMock(return_value=1)

        tut_resp = asyncio.run(get_competitive_tutorials(category_id=cat_id))

        assert tut_resp["status"] == "success"
        assert "textbooks" in tut_resp
        assert len(tut_resp["textbooks"]) == 1
        ret_tb = tut_resp["textbooks"][0]

        # Exact structure checks
        assert ret_tb["textbook_id"] == tb_id
        assert ret_tb["_id"] == tb_id
        assert ret_tb["textbook_title"] == "Smart Question Bank"
        assert ret_tb["category_id"] == cat_id
        assert ret_tb["exam_category"] == "SSC"
        assert ret_tb["exam_name"] == "SSC CGL (Tier 1 General Studies)"
        assert ret_tb["subject"] == "General Intelligence & Reasoning"
        assert ret_tb["total_pages"] == 51
        assert ret_tb["chapters_count"] == 2
        assert ret_tb["pdf_url"] == update_call_args["pdf_url"]
        assert ret_tb["download_url"] == update_call_args["download_url"]
        assert ret_tb["file_url"] == update_call_args["file_url"]
        assert ret_tb["original_filename"] == "original_textbook.pdf"
        assert ret_tb["uploaded_at"] == "2026-11-10T14:47:20.152000+05:30"
        assert ret_tb["created_at"] == "2026-11-10T14:47:20.152000+05:30"
        assert "chapters" not in ret_tb


def test_retry_question_bank_generation_endpoint():
    """Verify retry endpoint restarts generation for ingested textbooks."""
    import asyncio
    from fastapi import BackgroundTasks
    from app.routes.admin_competitive_exam_routes import retry_question_bank_generation

    tb_id = "6af2bac3162d857fa1495cbc"
    with patch("app.routes.admin_competitive_exam_routes.db") as mock_admin_db:
        mock_admin_db.textbook.find_one = AsyncMock(return_value={
            "_id": ObjectId(tb_id),
            "textbook_id": tb_id,
            "textbook_title": "Smart Question Bank",
            "subject": "Reasoning"
        })
        mock_admin_db.textbook_chapters.count_documents = AsyncMock(return_value=12)
        mock_admin_db.textbook.update_one = AsyncMock()
        mock_admin_db.chapter_status.update_one = AsyncMock()

        bg_tasks = BackgroundTasks()
        res = asyncio.run(retry_question_bank_generation(
            textbook_id=tb_id,
            background_tasks=bg_tasks,
            current_admin={"sub": "admin_test", "role": "Admin"}
        ))

        assert res["status"] in ("processing", "queued")
        assert res["textbook_id"] == tb_id
        assert len(bg_tasks.tasks) == 1


def test_competitive_question_bank_pdf_template(tmp_path):
    """Verify save_competitive_question_bank_pdf generates a valid structured question bank PDF with table of contents and answer matrix."""
    import pymupdf
    from app.report.competitive_question_bank_pdf import save_competitive_question_bank_pdf
    from app.routes.admin_competitive_exam_routes import validate_pdf_file

    pdf_out = tmp_path / "test_qb.pdf"
    sample_qb = {
        "textbook_title": "Smart Question Bank for SSC CGL",
        "exam_name": "SSC CGL (Tier 1)",
        "exam_category": "Staff Selection Commission",
        "subject": "General Intelligence & Reasoning",
        "language": "English",
        "total_questions": 4,
        "sections": [
            {
                "section_title": "Chapter 1: Alphabet & Word Test",
                "topics": ["Alphabet Series", "Dictionary Sequence"],
                "questions": [
                    {
                        "question_number": 1,
                        "question": "Which of the following words appears third in standard dictionary order?",
                        "options": {
                            "A": "Examine",
                            "B": "Edge",
                            "C": "Effort",
                            "D": "Element"
                        },
                        "correct_answer": "A",
                        "difficulty": "Easy",
                        "explanation": "Arranged alphabetically: Edge, Effort, Examine, Element. Third is Examine.",
                        "chapter_reference": "Chapter 1 (P. 1-4)"
                    },
                    {
                        "question_number": 2,
                        "question": "If 'EDGE' is coded as 'GFII', what is the pattern applied to each character?",
                        "options": {
                            "A": "+2, +3, +2, +4",
                            "B": "+2 shift across vowels",
                            "C": "+2 on consonants, +4 on vowels",
                            "D": "Direct alphabetical shift +2, +3, +2, +4"
                        },
                        "correct_answer": "D",
                        "difficulty": "Medium",
                        "explanation": "E(+2)=G, D(+3)=G, G(+2)=I, E(+4)=I.",
                        "chapter_reference": "Chapter 1 (P. 5-8)"
                    }
                ]
            },
            {
                "section_title": "Chapter 2: Seating Arrangement",
                "topics": ["Linear Arrangement", "Circular Table"],
                "questions": [
                    {
                        "question_number": 3,
                        "question": "In a linear row of 6 people facing North, P is sitting to the immediate left of Q. If Q is third from right, where is P?",
                        "options": {
                            "A": "Second from left",
                            "B": "Third from left",
                            "C": "Fourth from right",
                            "D": "Fourth from right (Third from left)"
                        },
                        "correct_answer": "D",
                        "difficulty": "Medium",
                        "explanation": "6 positions (1-6 from left). Q is 3rd from right = pos 4. P is left of Q = pos 3.",
                        "chapter_reference": "Chapter 2 (P. 12-16)"
                    },
                    {
                        "question_number": 4,
                        "question": "Eight friends sit in a circle facing the center. What is the minimum information required to deduce opposite positions?",
                        "options": {
                            "A": "Positions of 3 consecutive individuals",
                            "B": "Diameter symmetry with 2 fixed references",
                            "C": "Both A and B",
                            "D": "Clockwise ordering of at least 4 known elements"
                        },
                        "correct_answer": "B",
                        "difficulty": "Hard",
                        "explanation": "Diameter symmetry with 2 anchored reference vertices uniquely fixes opposite pairings in n=8.",
                        "chapter_reference": "Chapter 2 (P. 17-21)"
                    }
                ]
            }
        ]
    }

    res_path = save_competitive_question_bank_pdf(sample_qb, str(pdf_out))
    assert os.path.exists(res_path)
    assert os.path.getsize(res_path) > 1000

    is_valid, page_cnt, err = validate_pdf_file(res_path)
    assert is_valid is True
    assert page_cnt >= 2
    assert err == ""

    # Verify content inside PDF using PyMuPDF
    doc = pymupdf.open(res_path)
    full_text = " ".join(page.get_text() for page in doc)
    doc.close()

    assert "Smart Question Bank for SSC CGL" in full_text
    assert "General Intelligence & Reasoning" in full_text
    assert "Alphabet & Word Test" in full_text
    assert "Seating Arrangement" in full_text
    assert "OFFICIAL ANSWER KEY" in full_text
    assert "DETAILED PEDAGOGICAL EXPLANATIONS" in full_text






