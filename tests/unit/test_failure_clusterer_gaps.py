"""failure_clusterer 聚类合并、提示生成与边界补测。"""

from app.agent import failure_clusterer as module
from app.agent.failure_clusterer import FailureCluster, FailureClusterer


def _tb(err, loc="tests/test_a.py:10", msg=None):
    return (
        f"File \"{loc.split(':')[0]}\", line {loc.split(':')[1]}, in test\n"
        f"{err}: {msg or err}\n"
    )


def test_empty_results_returns_empty():
    assert FailureClusterer().cluster([]) == []


def test_single_failure_returns_one_cluster(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    clusters = FailureClusterer().cluster([
        {"name": "test_a", "traceback": _tb("ValueError"), "error_message": "bad"},
    ])

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.error_type == "ValueError"
    assert cluster.count == 1
    assert cluster.tests == [{"name": "test_a", "error": "bad"}]
    assert "在 tests/test_a.py:10 处发生 ValueError" in cluster.root_cause_hint


def test_multiple_same_type_same_location_grouped(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    clusters = FailureClusterer().cluster([
        {"name": "a", "traceback": _tb("ValueError"), "error_message": "a"},
        {"name": "b", "traceback": _tb("ValueError"), "error_message": "b"},
    ])

    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert clusters[0].root_cause_hint.startswith("此根因影响 2 个测试。")


def test_different_locations_and_types_split(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    clusters = FailureClusterer().cluster([
        {"name": "a", "traceback": _tb("ValueError", "tests/x.py:1"), "error_message": "a"},
        {"name": "b", "traceback": _tb("ValueError", "tests/x.py:2"), "error_message": "b"},
        {"name": "c", "traceback": _tb("TypeError", "tests/y.py:1"), "error_message": "c"},
        {"name": "d", "traceback": _tb("KeyError", "tests/z.py:1"), "error_message": "d"},
        {"name": "e", "traceback": _tb("IndexError", "tests/w.py:1"), "error_message": "e"},
    ])

    assert len(clusters) == 2
    totals = sum(c.count for c in clusters)
    assert totals == 5


def test_small_clusters_merge_into_matching_type(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    # 3 个集群，max_clusters = 5 // 2 = 2，末尾的小集群应与同类型主集群合并
    results = [
        {"name": "a1", "traceback": _tb("ValueError", "tests/a.py:1"), "error_message": "a1"},
        {"name": "a2", "traceback": _tb("ValueError", "tests/a.py:2"), "error_message": "a2"},
        {"name": "a3", "traceback": _tb("ValueError", "tests/a.py:3"), "error_message": "a3"},
        {"name": "b1", "traceback": _tb("TypeError", "tests/b.py:1"), "error_message": "b1"},
        {"name": "b2", "traceback": _tb("TypeError", "tests/b.py:2"), "error_message": "b2"},
        {"name": "v1", "traceback": _tb("ValueError", "tests/c.py:1"), "error_message": "v1"},
        {"name": "b3", "traceback": _tb("TypeError", "tests/b.py:3"), "error_message": "b3"},
        {"name": "b4", "traceback": _tb("TypeError", "tests/b.py:4"), "error_message": "b4"},
    ]
    clusters = FailureClusterer().cluster(results)

    by_type = {c.error_type: c for c in clusters}
    assert by_type["TypeError"].count >= 4
    assert sum(c.count for c in clusters) == len(results)


def test_small_cluster_without_matching_type_folds_into_first(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    results = [
        {"name": "a1", "traceback": _tb("ValueError", "tests/a.py:1"), "error_message": "a1"},
        {"name": "a2", "traceback": _tb("ValueError", "tests/a.py:2"), "error_message": "a2"},
        {"name": "a3", "traceback": _tb("ValueError", "tests/a.py:3"), "error_message": "a3"},
        {"name": "a4", "traceback": _tb("ValueError", "tests/a.py:4"), "error_message": "a4"},
        {"name": "u1", "traceback": "mystery failure\n", "error_message": "u1"},
        {"name": "u2", "traceback": "another mystery\n", "error_message": "u2"},
        {"name": "a5", "traceback": _tb("ValueError", "tests/a.py:5"), "error_message": "a5"},
        {"name": "a6", "traceback": _tb("ValueError", "tests/a.py:6"), "error_message": "a6"},
    ]
    clusters = FailureClusterer().cluster(results)

    assert sum(c.count for c in clusters) == len(results)
    assert clusters[0].count > 4


def test_keywords_dedup_and_limited():
    tb = "\n".join(f"E   ValueError: same {i}" for i in range(8)) + "\nValueError: same 0\n"
    _, _, keywords = FailureClusterer()._parse_traceback(tb)
    assert len(keywords) <= 5
    assert len(set(keywords)) == len(keywords)


def test_keywords_falls_back_to_last_meaningful_line():
    _, _, keywords = FailureClusterer()._parse_traceback("plain text only\n")
    assert keywords == ["plain text only"]


def test_no_keywords_when_only_whitespace():
    _, _, keywords = FailureClusterer()._parse_traceback("\n\n")
    assert keywords == []


def test_generate_hint_without_location():
    hint = FailureClusterer()._generate_hint("ValueError", "")
    assert hint.startswith("发生 ValueError：")


def test_generate_hint_unknown_type():
    hint = FailureClusterer()._generate_hint("WeirdError", "")
    assert "未知错误" in hint


def test_normalize_location_edge_cases():
    assert FailureClusterer._normalize_location("single.py") == "single.py"
    assert FailureClusterer._normalize_location("not_a_number:abc") == "not_a_number:abc"


def test_small_cluster_matches_main_same_type(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    results = [
        {"name": "v1", "traceback": _tb("ValueError", "tests/a.py:1"), "error_message": "v1"},
        {"name": "v2", "traceback": _tb("ValueError", "tests/a.py:2"), "error_message": "v2"},
        {"name": "v3", "traceback": _tb("ValueError", "tests/a.py:3"), "error_message": "v3"},
        {"name": "t1", "traceback": _tb("TypeError", "tests/b.py:1"), "error_message": "t1"},
        {"name": "t2", "traceback": _tb("TypeError", "tests/b.py:2"), "error_message": "t2"},
        {"name": "k1", "traceback": _tb("KeyError", "tests/c.py:1"), "error_message": "k1"},
        {"name": "i1", "traceback": _tb("ImportError", "tests/d.py:1"), "error_message": "i1"},
        {"name": "r1", "traceback": _tb("RuntimeError", "tests/e.py:1"), "error_message": "r1"},
        {"name": "v4", "traceback": _tb("ValueError", "tests/f.py:1"), "error_message": "v4"},
        {"name": "v5", "traceback": _tb("ValueError", "tests/f.py:2"), "error_message": "v5"},
    ]
    clusters = FailureClusterer().cluster(results)

    assert len(clusters) == 5
    value_cluster = next(c for c in clusters if c.error_type == "ValueError")
    assert value_cluster.count > 3
    assert sum(c.count for c in clusters) == len(results)


def test_small_same_type_cluster_merges_into_main(monkeypatch):
    class Timer:
        def start_timer(self, name):
            return 1.0

        def end_timer(self, *args):
            pass

    monkeypatch.setattr(module, "metrics_collector", Timer())

    results = [
        {"name": f"v{i}", "traceback": _tb("ValueError", "tests/a.py:1"), "error_message": "v"}
        for i in range(5)
    ]
    results += [
        {"name": "t1", "traceback": _tb("TypeError", "tests/b.py:1"), "error_message": "t1"},
        {"name": "k1", "traceback": _tb("KeyError", "tests/c.py:1"), "error_message": "k1"},
        {"name": "i1", "traceback": _tb("ImportError", "tests/d.py:1"), "error_message": "i1"},
        {"name": "r1", "traceback": _tb("RuntimeError", "tests/e.py:1"), "error_message": "r1"},
        {"name": "vsmall", "traceback": _tb("ValueError", "tests/z.py:1"), "error_message": "vs"},
    ]
    clusters = FailureClusterer().cluster(results)

    assert len(clusters) == 5
    value_cluster = max(clusters, key=lambda c: c.count)
    assert value_cluster.error_type == "ValueError"
    assert value_cluster.count == 6
    assert sum(c.count for c in clusters) == len(results)
