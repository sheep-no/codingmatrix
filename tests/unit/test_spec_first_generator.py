import pytest
import tempfile
from pathlib import Path

class TestSpecFirstGenerator:
    @pytest.fixture
    def generator(self):
        from app.agent.spec_first_generator import SpecFirstGenerator
        from app.agent.shared_context import SharedContext
        
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            ctx.model_assignment = {"architect_model": "test-model"}
            yield SpecFirstGenerator(ctx)
    
    def test_get_spec_context_for_file(self, generator):
        from app.agent.shared_context import SpecArtifact
        
        generator.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi",
            content={"paths": {"/users": {}}},
            generated_by="test-model"
        )
        
        context = generator.get_spec_context_for_file("api.py", "backend")
        assert context is not None

    @pytest.mark.asyncio
    async def test_generate_all_specs_skips_http_when_not_needed(self, generator, monkeypatch):
        async def fail_if_called(*_args, **_kwargs):
            raise AssertionError("HTTP spec generation should be skipped")

        monkeypatch.setattr(generator, "_generate_openapi_spec", fail_if_called)
        monkeypatch.setattr(generator, "_generate_types", fail_if_called)
        monkeypatch.setattr(generator, "_generate_db_schema", fail_if_called)
        monkeypatch.setattr(generator, "_generate_config", fail_if_called)

        ok = await generator.generate_all_specs(
            "做一个可运行的贪吃蛇小游戏，方向键控制蛇移动，吃食物加分。",
            {
                "level": "simple",
                "has_frontend": False,
                "has_backend": False,
                "has_database": False,
                "has_auth": False,
            },
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_generate_all_specs_fails_when_types_fail(self, generator, monkeypatch):
        async def openapi_ok(*_args, **_kwargs):
            return True

        async def types_fail(*_args, **_kwargs):
            return False

        async def unused(*_args, **_kwargs):
            raise AssertionError("later spec steps should not run")

        monkeypatch.setattr(generator, "_generate_openapi_spec", openapi_ok)
        monkeypatch.setattr(generator, "_generate_types", types_fail)
        monkeypatch.setattr(generator, "_generate_db_schema", unused)
        monkeypatch.setattr(generator, "_generate_config", unused)

        ok = await generator.generate_all_specs(
            "做一个 FastAPI 用户接口，PostgreSQL 存储。",
            {
                "level": "medium",
                "has_frontend": False,
                "has_backend": True,
                "has_database": True,
                "has_auth": False,
            },
        )
        assert ok is False

    def test_needs_db_spec_ignores_negated_database(self, generator):
        requirement = "写一个 Python 文件 hello.py，运行后打印 Hello World。只要这一个文件，不要数据库、不要前端、不要测试。"
        complexity = {
            "level": "simple",
            "has_frontend": False,
            "has_backend": False,
            "has_database": False,
        }
        assert generator._needs_db_spec(requirement, complexity) is False
        assert generator._needs_http_spec(requirement, complexity) is False

    def test_needs_db_spec_detects_positive_database(self, generator):
        assert generator._needs_db_spec("需要 PostgreSQL 数据库存储用户", {"has_database": False}) is True

    @pytest.mark.asyncio
    async def test_generate_all_specs_skips_negated_database(self, generator, monkeypatch):
        async def fail_if_called(*_args, **_kwargs):
            raise AssertionError("database spec generation should be skipped")

        monkeypatch.setattr(generator, "_generate_openapi_spec", fail_if_called)
        monkeypatch.setattr(generator, "_generate_types", fail_if_called)
        monkeypatch.setattr(generator, "_generate_db_schema", fail_if_called)
        monkeypatch.setattr(generator, "_generate_config", fail_if_called)

        ok = await generator.generate_all_specs(
            "写一个 Python 文件 hello.py，运行后打印 Hello World。只要这一个文件，不要数据库、不要前端、不要测试。",
            {
                "level": "simple",
                "has_frontend": False,
                "has_backend": False,
                "has_database": False,
                "has_auth": False,
            },
        )
        assert ok is True


def test_spec_first_generator_requires_model_assignment(tmp_path):
    from app.agent.spec_first_generator import SpecFirstGenerator
    from app.agent.shared_context import SharedContext

    ctx = SharedContext("test", tmp_path)
    with pytest.raises(RuntimeError, match="model assignment is required for spec generation"):
        SpecFirstGenerator(ctx)


class TestSpecModelConfigAndTypeDefense:
    """SFG3/SFG4：OpenAPI 走 model_config，_generate_types 对非 dict 规范防御。"""

    @pytest.fixture
    def generator(self):
        from app.agent.spec_first_generator import SpecFirstGenerator
        from app.agent.shared_context import SharedContext

        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = SharedContext("test", Path(tmpdir))
            ctx.model_assignment = {"architect_model": "test-model"}
            yield SpecFirstGenerator(ctx)

    @pytest.mark.asyncio
    async def test_openapi_spec_uses_model_config_limits(self, generator, monkeypatch):
        generator.model_config = {"max_tokens": 4242, "thinking_budget": 111}
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"openapi":"3.0.0","info":{},"paths":{"/x":{}},"components":{"schemas":{}}}'
                        }
                    }
                ]
            }

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake_call_llm)

        ok = await generator._generate_openapi_spec(
            "做一个 FastAPI 用户接口", {"has_backend": True}
        )

        assert ok is True
        assert captured["max_tokens"] == 4242
        assert captured["thinking_budget"] == 111

    @pytest.mark.asyncio
    async def test_generate_types_parses_string_spec(self, generator, monkeypatch):
        from app.agent.shared_context import SpecArtifact

        generator.context.specs["openapi"] = SpecArtifact(
            spec_type="openapi",
            content='{"openapi":"3.0.0","paths":{"/x":{}}}',
            generated_by="test-model",
        )
        prompts = []

        async def fake_call_llm(**kwargs):
            prompts.append(kwargs["prompt"])
            return {"choices": [{"message": {"content": "class X: pass"}}]}

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fake_call_llm)

        ok = await generator._generate_types()

        assert ok is True
        # 字符串规范被重新解析为 dict 后按 JSON 结构注入，而非整体字符串字面量
        assert '"openapi": "3.0.0"' in prompts[0]
        assert '"/x"' in prompts[0]
        assert '\\"' not in prompts[0]

    @pytest.mark.asyncio
    async def test_generate_types_returns_false_without_spec(self, generator, monkeypatch):
        async def fail_if_called(**_kwargs):
            raise AssertionError("types generation should be skipped without a spec")

        monkeypatch.setattr("app.agent.spec_first_generator.call_llm", fail_if_called)

        assert await generator._generate_types() is False
