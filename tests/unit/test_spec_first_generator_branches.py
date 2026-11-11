"""SpecFirstGenerator 分支覆盖测试。"""

import asyncio
import json

import pytest

from app.agent.shared_context import SharedContext, SpecArtifact
from app.agent.spec_first_generator import SpecFirstGenerator


def _generator(tmp_path, language="python", model_config=None):
    ctx = SharedContext("req", tmp_path)
    ctx.model_assignment = {"architect_model": "arch"}
    gen = SpecFirstGenerator(ctx, language=language)
    gen.model_config = model_config or {"max_tokens": 10, "thinking_budget": 5}
    return gen


def _llm_response(content):
    async def fake_call_llm(**kwargs):
        fake_call_llm.kwargs = kwargs
        return {"choices": [{"message": {"content": content}}]}

    return fake_call_llm


class TestInitAndBudget:
    def test_init_requires_architect_model(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        with pytest.raises(RuntimeError, match="model assignment is required"):
            SpecFirstGenerator(ctx)

    def test_init_rejects_empty_model_name(self, tmp_path):
        ctx = SharedContext("req", tmp_path)
        ctx.model_assignment = {"architect_model": ""}
        with pytest.raises(RuntimeError, match="model assignment is required"):
            SpecFirstGenerator(ctx)

    def test_init_accepts_object_assignment(self, tmp_path, monkeypatch):
        ctx = SharedContext("req", tmp_path)
        ctx.model_assignment = type("A", (), {"architect_model": "obj-model"})()
        monkeypatch.setattr(
            "app.agent.dynamic_model_router.LayeredModelRouter.get_model_config",
            staticmethod(lambda name: {"max_tokens": 1, "thinking_budget": 1}),
        )

        gen = SpecFirstGenerator(ctx)

        assert gen.architect_model == "obj-model"

    def test_spec_budget_tiers(self):
        assert SpecFirstGenerator.get_spec_budget(1000) == 2000
        assert SpecFirstGenerator.get_spec_budget(32768) == 2000
        assert SpecFirstGenerator.get_spec_budget(40000) == 3500
        assert SpecFirstGenerator.get_spec_budget(65536) == 3500
        assert SpecFirstGenerator.get_spec_budget(100000) == 5000

    @pytest.mark.parametrize(
        "complexity,expected",
        [
            (None, False),
            ({}, False),
            ({"has_backend": True}, True),
            (type("C", (), {"has_backend": True})(), True),
            (type("C", (), {})(), False),
        ],
    )
    def test_complexity_flag(self, complexity, expected):
        assert SpecFirstGenerator._complexity_flag(complexity, "has_backend") is expected

    def test_needs_http_from_keyword(self, tmp_path):
        gen = _generator(tmp_path)
        assert gen._needs_http_spec("做一个 FastAPI 用户接口", {}) is True
        assert gen._needs_http_spec("", {}) is False

    def test_needs_db_from_keyword(self, tmp_path):
        gen = _generator(tmp_path)
        assert gen._needs_db_spec("需要 PostgreSQL 数据库", {}) is True
        assert gen._needs_db_spec("", {}) is False


class TestGenerateAllSpecs:
    @pytest.mark.asyncio
    async def test_openapi_failure_stops(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        calls = []

        async def fail(*_a, **_k):
            calls.append("openapi")
            return False

        monkeypatch.setattr(gen, "_generate_openapi_spec", fail)
        ok = await gen.generate_all_specs("FastAPI api", {"has_backend": True})

        assert ok is False
        assert calls == ["openapi"]
        assert gen.context.errors

    @pytest.mark.asyncio
    async def test_db_failure_stops(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def ok_openapi(*_a, **_k):
            return True

        async def ok_types(*_a, **_k):
            return True

        async def fail_db(*_a, **_k):
            return False

        monkeypatch.setattr(gen, "_generate_openapi_spec", ok_openapi)
        monkeypatch.setattr(gen, "_generate_types", ok_types)
        monkeypatch.setattr(gen, "_generate_db_schema", fail_db)

        ok = await gen.generate_all_specs(
            "FastAPI + PostgreSQL", {"has_backend": True, "has_database": True}
        )

        assert ok is False

    @pytest.mark.asyncio
    async def test_config_failure_stops(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def ok(*_a, **_k):
            return True

        monkeypatch.setattr(gen, "_generate_openapi_spec", ok)
        monkeypatch.setattr(gen, "_generate_types", ok)

        async def fail(*_a, **_k):
            return False

        monkeypatch.setattr(gen, "_generate_config", fail)

        ok_result = await gen.generate_all_specs(
            "FastAPI 项目", {"has_backend": True}
        )

        assert ok_result is False
        assert "config" in gen.context.errors[-1].lower() or gen.context.errors

    @pytest.mark.asyncio
    async def test_db_only_skips_http(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        steps = []

        async def db_ok(*_a, **_k):
            steps.append("db")
            return True

        async def config_ok(*_a, **_k):
            steps.append("config")
            return True

        monkeypatch.setattr(gen, "_generate_db_schema", db_ok)
        monkeypatch.setattr(gen, "_generate_config", config_ok)
        monkeypatch.setattr(
            gen, "_needs_http_spec", lambda *a, **k: False
        )
        monkeypatch.setattr(gen, "_needs_db_spec", lambda *a, **k: True)

        ok = await gen.generate_all_specs("something", {})

        assert ok is True
        assert steps == ["db", "config"]

    @pytest.mark.asyncio
    async def test_full_success_reports_progress(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def ok(*_a, **_k):
            return True

        monkeypatch.setattr(gen, "_generate_openapi_spec", ok)
        monkeypatch.setattr(gen, "_generate_types", ok)
        monkeypatch.setattr(gen, "_generate_db_schema", ok)
        monkeypatch.setattr(gen, "_generate_config", ok)

        events = []
        ok = await gen.generate_all_specs(
            "FastAPI + PostgreSQL", {"has_backend": True, "has_database": True},
            callback=events.append,
        )

        assert ok is True
        steps = [json.loads(event)["step"] for event in events]
        assert steps == [
            "openapi_generated",
            "types_generated",
            "db_schema_generated",
            "config_generated",
        ]


class TestOpenApiBranches:
    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("")
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_unparseable_content(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("not json")
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_list_payload_with_dict_first(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = '[{"openapi":"3.0.0","paths":{}}]'
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )

        assert await gen._generate_openapi_spec("req", {}) is True
        assert "openapi" in gen.context.specs

    @pytest.mark.asyncio
    async def test_nested_list_payload(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = '[[{"openapi":"3.0.0","paths":{}}]]'
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_list_of_json_string(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps([json.dumps({"openapi": "3.0.0", "paths": {}})])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_list_string_with_embedded_json(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        embedded = json.dumps({"openapi": "3.0.0", "paths": {}})
        payload = json.dumps(["prefix " + embedded])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_list_other_element_dict(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps(["noise", {"openapi": "3.0.0", "paths": {}}])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_first_dict_without_openapi_scans_rest(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps(
            [{"note": "noise"}, {"openapi": "3.0.0", "paths": {}}]
        )
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_list_with_only_noise_dicts_returns_false(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps([{"note": "noise"}, {"other": 1}])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_list_other_element_string_embedded(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        embedded = json.dumps({"openapi": "3.0.0", "paths": {}})
        payload = json.dumps(["noise", "prefix " + embedded])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is True

    @pytest.mark.asyncio
    async def test_list_without_openapi_returns_false(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps(["noise", {"a": 1}])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_list_with_unexpected_first_type(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = "[1, 2]"
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_empty_list(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("[]")
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_scalar_payload(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response('"scalar"')
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_nested_empty_list_payload(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("[[]]")
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_string_parsing_to_non_dict_falls_through(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        payload = json.dumps(["[1, 2]"])
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response(payload)
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_missing_openapi_key(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response('{"paths":{}}')
        )
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_exception_is_swallowed(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def boom(**_kwargs):
            raise RuntimeError("network")

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", boom)
        assert await gen._generate_openapi_spec("req", {}) is False

    @pytest.mark.asyncio
    async def test_non_container_parse_result_rejected(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("ignored")
        )
        monkeypatch.setattr(gen, "_extract_json", lambda _text: 42)

        assert await gen._generate_openapi_spec("req", {}) is False


class TestGenerateTypesLanguages:
    @pytest.mark.parametrize(
        "language,expected",
        [
            ("python", "Pydantic"),
            ("javascript", "TypeScript interface"),
            ("go", "Go struct"),
            ("java", "Java POJO"),
            ("rust", "Rust struct"),
            ("ruby", "ruby 的类型定义"),
        ],
    )
    @pytest.mark.asyncio
    async def test_language_hints(self, tmp_path, monkeypatch, language, expected):
        gen = _generator(tmp_path, language=language)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi",
            content={"openapi": "3.0.0"},
            generated_by="arch",
        )
        fake = _llm_response("class X: pass")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_types() is True
        assert expected in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_empty_response_returns_false(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content={"openapi": "3"}, generated_by="a"
        )
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("")
        )
        assert await gen._generate_types() is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content={"openapi": "3"}, generated_by="a"
        )

        async def boom(**_kwargs):
            raise RuntimeError("x")

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", boom)
        assert await gen._generate_types() is False

    @pytest.mark.asyncio
    async def test_string_spec_that_fails_to_parse_falls_back_to_empty(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content="not-json", generated_by="a"
        )

        async def fail(**_kwargs):
            raise AssertionError("should not call LLM")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fail)
        assert await gen._generate_types() is False


class TestGenerateDbSchema:
    @pytest.mark.parametrize(
        "language,expected",
        [
            ("python", "SQLAlchemy"),
            ("javascript", "Prisma"),
            ("go", "GORM"),
            ("java", "JPA"),
            ("rust", "Diesel"),
            ("elixir", "elixir 的数据库模型定义"),
        ],
    )
    @pytest.mark.asyncio
    async def test_language_hints(self, tmp_path, monkeypatch, language, expected):
        gen = _generator(tmp_path, language=language)
        fake = _llm_response("class M: pass")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_db_schema("need db", {}) is True
        assert expected in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_string_openapi_spec_is_parsed(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi",
            content='{"openapi":"3.0.0","components":{"schemas":{"User":{}}}}',
            generated_by="a",
        )
        fake = _llm_response("class M: pass")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_db_schema("req", {}) is True
        assert '"User"' in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_unparseable_string_openapi_defaults_empty(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content="broken", generated_by="a"
        )
        fake = _llm_response("class M: pass")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_db_schema("req", {}) is True
        assert "OpenAPI 规范中的数据结构" not in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_non_dict_openapi_defaults_empty(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content=[1, 2], generated_by="a"
        )
        fake = _llm_response("class M: pass")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_db_schema("req", {}) is True
        assert "OpenAPI 规范中的数据结构" not in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("")
        )
        assert await gen._generate_db_schema("req", {}) is False

    @pytest.mark.asyncio
    async def test_exception(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def boom(**_kwargs):
            raise RuntimeError("db")

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", boom)
        assert await gen._generate_db_schema("req", {}) is False


class TestGenerateConfig:
    @pytest.mark.parametrize(
        "language,expected",
        [
            ("python", "pydantic-settings"),
            ("javascript", "dotenv"),
            ("go", "Viper"),
            ("java", "application.yml"),
            ("rust", "config crate"),
            ("cobol", "cobol 的配置管理代码"),
        ],
    )
    @pytest.mark.asyncio
    async def test_language_hints(self, tmp_path, monkeypatch, language, expected):
        gen = _generator(tmp_path, language=language)
        fake = _llm_response("CONFIG=1")
        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake)

        assert await gen._generate_config("req", {"key_technologies": ["X"]}) is True
        assert expected in fake.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_empty_response(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.spec_first_generator.call_llm", _llm_response("")
        )
        assert await gen._generate_config("req", {}) is False

    @pytest.mark.asyncio
    async def test_exception(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)

        async def boom(**_kwargs):
            raise RuntimeError("cfg")

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", boom)
        assert await gen._generate_config("req", {}) is False


class TestHelpers:
    def test_extract_json_returns_none_on_value_error(self, tmp_path, monkeypatch):
        gen = _generator(tmp_path)
        monkeypatch.setattr(
            "app.agent.json_parser.safe_parse_json",
            lambda text: (_ for _ in ()).throw(ValueError("bad")),
        )
        assert gen._extract_json("{") is None

    def test_report_progress_without_callback(self, tmp_path):
        gen = _generator(tmp_path)
        gen._report_progress("step", None)

    def test_report_progress_sync_callback(self, tmp_path):
        gen = _generator(tmp_path)
        events = []
        gen._report_progress("step", events.append)

        assert json.loads(events[0])["step"] == "step"

    @pytest.mark.asyncio
    async def test_report_progress_async_callback(self, tmp_path):
        gen = _generator(tmp_path)
        events = []

        async def callback(payload):
            events.append(payload)

        gen._report_progress("step", callback)
        if gen._pending_tasks:
            await asyncio.gather(*gen._pending_tasks)

        assert json.loads(events[0])["step"] == "step"
        assert gen._pending_tasks == set()

    def test_report_progress_callback_exception_is_swallowed(self, tmp_path):
        gen = _generator(tmp_path)

        def callback(_payload):
            raise RuntimeError("boom")

        gen._report_progress("step", callback)

    def test_get_spec_context_default_budget(self, tmp_path):
        gen = _generator(tmp_path)
        gen.context.specs["config"] = SpecArtifact(
            spec_type="config", content={"code": "A=1"}, generated_by="a"
        )
        context = gen.get_spec_context_for_file("a.py", "config", 0)
        assert context.startswith("## 配置规范")

    def test_get_spec_context_returns_empty_when_no_specs(self, tmp_path):
        gen = _generator(tmp_path)
        assert gen.get_spec_context_for_file("a.py", "api") == ""

    def test_get_spec_context_covers_all_file_types(self, tmp_path):
        gen = _generator(tmp_path)
        gen.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi", content={"paths": {}}, generated_by="a"
        )
        gen.context.specs["types"] = SpecArtifact(
            spec_type="types", content={"code": "class T: pass"}, generated_by="a"
        )
        gen.context.specs["db_schema"] = SpecArtifact(
            spec_type="db_schema", content={"code": "class D: pass"}, generated_by="a"
        )
        gen.context.specs["config"] = SpecArtifact(
            spec_type="config", content={"code": "A=1"}, generated_by="a"
        )

        assert "OpenAPI 接口规范" in gen.get_spec_context_for_file("a.py", "controller")
        assert "类型定义" in gen.get_spec_context_for_file("a.py", "dto")
        assert "数据库 Schema" in gen.get_spec_context_for_file("a.py", "dao")
        assert "配置规范" in gen.get_spec_context_for_file("a.py", "settings")

    def test_get_spec_context_explicit_budget(self, tmp_path):
        gen = _generator(tmp_path)
        gen.context.specs["config"] = SpecArtifact(
            spec_type="config", content={"code": "A=1"}, generated_by="a"
        )
        context = gen.get_spec_context_for_file("a.py", "config", 5)
        assert "## 配置规范" in context

    def test_get_spec_context_missing_specs_are_skipped(self, tmp_path):
        gen = _generator(tmp_path)
        assert gen.get_spec_context_for_file("a.py", "model") == ""
        assert gen.get_spec_context_for_file("a.py", "repository") == ""
        assert gen.get_spec_context_for_file("a.py", "settings") == ""
