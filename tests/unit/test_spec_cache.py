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


class TestTechStackAndKeywords:
    """SC3/SC4/SC5/SC6：阈值可达、关键词表单一来源、技术栈口径统一、按全文比较。"""

    @pytest.fixture
    def cache_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, cache_dir):
        from app.agent.spec_cache import SpecCache

        return SpecCache(cache_dir)

    def test_extract_keywords_and_tech_keywords_share_one_table(self, cache):
        from app.agent import spec_cache
        from app.agent.spec_cache import TECH_KEYWORDS

        assert isinstance(TECH_KEYWORDS, tuple)
        text = "用 Flask 开发一个博客系统，存放 MySQL"
        # 索引预过滤词必须是关键词表的子集（同一份来源，不会口径分裂）
        for kw in cache._extract_tech_keywords(text):
            assert kw in TECH_KEYWORDS
        assert set(cache._extract_tech_keywords(text)) <= set(cache.extract_keywords(text))
        assert spec_cache.JACCARD_SIMILARITY_THRESHOLD < 0.85

    def test_tech_stack_sources_are_merged_and_normalized(self, cache):
        cache.save(
            "Create a REST API",
            {"complexity": {"level": "medium"}},
            {"tech_stack": ["Flask", "MySQL"]},
            [{"path": "main.py"}],
            {"level": "medium", "key_technologies": ["flask", "redis"]},
            ["Docker"],
            complexity_level="medium",
        )

        entry = next(iter(cache._cache.values()))
        # 三个来源合并、小写归一、保序去重
        assert entry.tech_stack == ["flask", "mysql", "docker", "redis"]
        # 归一后索引键为小写，_extract_tech_keywords 的小写查询才能命中
        assert cache._tech_index["flask"] == [entry.requirement_hash]

    def test_similarity_uses_full_requirement_not_preview(self, cache):
        # 技术栈关键词只出现在第 200 字符之后，预览里看不到
        requirement = "开发一个用户管理系统。" + "细节描述" * 60 + "，使用 Flask 和 MySQL"
        cache.save(
            requirement,
            {"complexity": {"level": "medium"}},
            {"tech_stack": ["flask", "mysql"]},
            [{"path": "main.py"}],
            {"level": "medium"},
            ["flask", "mysql"],
            complexity_level="medium",
        )

        entry = next(iter(cache._cache.values()))
        assert entry.requirement == requirement
        assert "flask" not in entry.requirement_preview

        # 若仍按截断预览比较，flask/mysql 不在候选词集，Jaccard 只有 0.6 而漏命中
        hit = cache.lookup("开发一个用户管理系统，使用 Flask 和 MySQL")

        assert hit is not None

    def test_near_identical_keyword_sets_get_fuzzy_hit(self, cache):
        requirement = "开发一个博客系统，使用 Flask 和 MySQL"
        cache.save(
            requirement,
            {"complexity": {"level": "medium"}},
            {"tech_stack": ["flask", "mysql"]},
            [{"path": "main.py"}],
            {"level": "medium"},
            ["flask", "mysql"],
            complexity_level="medium",
        )

        # 文本不同（大小写/虚词）但技术+领域+动作关键词集合一致，Jaccard=1.0 >= 0.75
        hit = cache.lookup("开发一个博客系统，使用 flask 与 MySQL")

        assert hit is not None
        assert hit.requirement == requirement
