"""Local retrieval path must feed per-file prompts with bounded provenance."""

import json

from app.agent.retrieval.local_context import (
    MAX_CHUNK_CHARS,
    MAX_TOTAL_CHARS,
    retrieve_local_chunks,
)
from app.agent.utils import compact_project_context_for_file


def _context() -> dict:
    return {
        "requirement": "构建一个用户登录页面，包含表单校验和错误提示",
        "architecture": {
            "language": "python",
            "tech_stack": ["fastapi", "vue"],
            "database": "sqlite",
            "file_plan": [
                {"path": "app/auth.py", "description": "用户登录校验与会话签发"},
                {"path": "src/Login.vue", "description": "登录表单与错误提示"},
                {"path": "docs/deploy.md", "description": "部署说明"},
            ],
        },
        "api_contract": "POST /login 返回 token，错误码 401",
        "profile": {"framework": "fastapi", "language": "python"},
    }


def test_retrieves_relevant_plan_entries_with_provenance():
    context = _context()
    chunks = retrieve_local_chunks(
        "src/Login.vue", context, context["architecture"]["file_plan"]
    )

    sources = [chunk["source"] for chunk in chunks]
    assert "file_plan:src/Login.vue" in sources
    assert "file_plan:app/auth.py" in sources
    assert all(chunk["score"] > 0 for chunk in chunks)


def test_chunks_are_bounded_per_item_and_in_total():
    context = _context()
    context["api_contract"] = "x" * 5000
    chunks = retrieve_local_chunks(
        "src/Login.vue", context, context["architecture"]["file_plan"]
    )

    assert chunks
    assert len(chunks) <= 4
    assert all(len(chunk["content"]) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert sum(len(chunk["content"]) for chunk in chunks) <= MAX_TOTAL_CHARS


def test_empty_corpus_returns_no_chunks():
    assert retrieve_local_chunks("main.py", {"requirement": ""}, []) == []


def test_compact_context_embeds_retrieved_sources():
    context = _context()
    compact = json.loads(compact_project_context_for_file("src/Login.vue", context))

    assert compact["retrieved_context"]
    assert any(
        item["source"] == "file_plan:app/auth.py"
        for item in compact["retrieved_context"]
    )


def test_compact_context_prefers_existing_envelope_retrieval():
    context = _context()
    context["context_envelope"] = {
        "items": [
            {
                "source": "retrieval",
                "source_id": "envelope-source",
                "content": "envelope chunk",
            }
        ]
    }

    compact = json.loads(compact_project_context_for_file("src/Login.vue", context))

    assert "retrieved_context" not in compact


def test_single_cjk_char_and_non_serializable_json_are_tolerated():
    context = {
        "requirement": "",
        "api_contract": {1: "mixed keys", "b": "c"},
    }

    chunks = retrieve_local_chunks("看", context)

    assert chunks == []


def test_ignores_malformed_context_and_plan_entries():
    plan = ["not-a-mapping", {"path": "  "}, {"path": "app/main.py", "description": "入口"}]
    chunks = retrieve_local_chunks("app/main.py", {"architecture": "not-a-mapping"}, plan)

    assert [chunk["source"] for chunk in chunks] == ["file_plan:app/main.py"]


def test_non_positive_limit_and_missing_query_yield_no_chunks():
    context = _context()

    assert retrieve_local_chunks("src/Login.vue", context, limit=0) == []
    assert retrieve_local_chunks("", {"requirement": ""}, []) == []


def test_duplicate_sources_are_skipped():
    context = {
        "requirement": "生成页面",
        "api_contract": "生成页面 shared body",
        "profile": "生成页面 shared body",
        "architecture": {"tech_stack": "生成页面 shared body"},
    }

    chunks = retrieve_local_chunks("page.html", context)

    contents = [chunk["content"] for chunk in chunks]
    assert contents.count("生成页面 shared body") == 1
    assert len(contents) == len(set(contents))


def test_total_budget_stops_before_overflowing_chunks():
    plan = [
        {"path": f"src/page{index}.html", "description": "生成页面 " + "x" * 600}
        for index in range(5)
    ]
    context = {"requirement": "生成页面", "architecture": {"file_plan": plan}}

    chunks = retrieve_local_chunks("src/page0.html", context, plan, limit=5)

    assert len(chunks) == 4
    assert sum(len(chunk["content"]) for chunk in chunks) == MAX_TOTAL_CHARS


def test_compact_context_without_matches_omits_retrieved_sources():
    compact = json.loads(compact_project_context_for_file("main.py", {"requirement": ""}))

    assert "retrieved_context" not in compact


def test_compact_context_tolerates_empty_envelope_items():
    context = _context()
    context["context_envelope"] = {"items": None}

    compact = json.loads(compact_project_context_for_file("src/Login.vue", context))

    assert compact["retrieved_context"]
