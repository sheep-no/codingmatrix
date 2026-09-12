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
