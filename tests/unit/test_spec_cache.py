"""SpecCache 的持久化、复杂度维度与依赖图缓存（SC1/SC2、SPFG8）。"""

import tempfile
from pathlib import Path

import pytest


class TestSpecCache:
    @pytest.fixture
    def cache_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, cache_dir):
        from app.agent.spec_cache import SpecCache

        return SpecCache(cache_dir)

    @staticmethod
    def _save(cache, requirement="Create a REST API", level="medium", dependency_graph=None):
        specs = {"complexity": {"level": level}}
        architecture = {"tech_stack": ["fastapi"], "language": "python"}
        file_plan = [{"path": "main.py"}]
        return cache.save(
            requirement,
            specs,
            architecture,
            file_plan,
            {"level": level},
            ["fastapi"],
            dependency_graph=dependency_graph,
            complexity_level=level,
        )

    def test_save_and_lookup(self, cache):
        requirement = "Create a REST API"
        self._save(cache, requirement)

        result = cache.lookup(requirement, complexity_level="medium")

        assert result is not None
        assert result.architecture is not None

    def test_cache_miss(self, cache):
        assert cache.lookup("nonexistent requirement") is None

    def test_complexity_levels_are_isolated(self, cache):
        requirement = "Create a REST API"
        self._save(cache, requirement, level="medium")

        # 不同复杂度不得复用同一需求文本的架构产物
        assert cache.lookup(requirement, complexity_level="medium") is not None
        assert cache.lookup(requirement, complexity_level="simple") is None

    def test_two_levels_coexist(self, cache):
        requirement = "Create a REST API"
        self._save(cache, requirement, level="medium")
        self._save(cache, requirement, level="complex")

        medium = cache.lookup(requirement, complexity_level="medium")
        complex_ = cache.lookup(requirement, complexity_level="complex")

        assert medium.complexity["level"] == "medium"
        assert complex_.complexity["level"] == "complex"

    def test_dependency_graph_is_persisted(self, cache):
        requirement = "Create a REST API"
        dependency_graph = {"nodes": {"main.py": {"file_type": "entry"}}, "edges": []}
        self._save(cache, requirement, dependency_graph=dependency_graph)

        result = cache.lookup(requirement, complexity_level="medium")

        assert result.dependency_graph == dependency_graph

    def test_cache_survives_restart(self, cache_dir):
        from app.agent.spec_cache import SpecCache

        requirement = "Create a REST API"
        dependency_graph = {"nodes": {"main.py": {"file_type": "entry"}}, "edges": []}
        self._save(SpecCache(cache_dir), requirement, dependency_graph=dependency_graph)

        # 新实例模拟进程重启，同步 lookup 也应从磁盘索引恢复
        restarted = SpecCache(cache_dir)
        result = restarted.lookup(requirement, complexity_level="medium")

        assert result is not None
        assert result.architecture["language"] == "python"
        assert result.dependency_graph == dependency_graph
