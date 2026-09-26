"""FileOperator 路径安全规则回归。

覆盖已建档缺陷：
- FO1 PROTECTED_FILES 子串匹配误伤：".env" 命中任意含该子串的路径，
  导致 SAFE_EXTENSIONS 明确允许的 ".env.example" 模板被拒。
- FO7 grep/search 以 errors='ignore' 读取：含非法字节的文件内容被静默
  丢弃，搜索结果不完整且无任何提示。
"""

from pathlib import Path

import pytest

from app.utils.file_operator import FileOperator, PathSecurityError


def test_env_file_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/.env", must_exist=False)


def test_env_example_template_is_allowed():
    """SAFE_EXTENSIONS 白名单内的 .env.example 模板不应被敏感文件规则拦截。"""
    target = FileOperator()._validate_path("/srv/app/.env.example", must_exist=False)

    assert target.name == ".env.example"


def test_env_substring_path_is_not_misflagged():
    """路径含 ".env" 子串但文件名不同名时不应被误判为敏感文件。"""
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/.envrc"), "/srv/app/.envrc", ".env"
        )
        is False
    )
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/notes.env.bak"), "/srv/app/notes.env.bak", ".env"
        )
        is False
    )


def test_env_named_file_is_protected():
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/.env"), "/srv/app/.env", ".env"
        )
        is True
    )


def test_git_config_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/.git/config", must_exist=False)


def test_private_key_file_is_rejected():
    with pytest.raises(PathSecurityError):
        FileOperator()._validate_path("/srv/app/id_rsa", must_exist=False)


def test_git_config_substring_path_is_not_misflagged():
    """.git/config 按路径尾段匹配，普通 config 文件不受影响。"""
    assert (
        FileOperator._is_protected_file(
            Path("/srv/app/config"), "/srv/app/config", ".git/config"
        )
        is False
    )


def _make_undecodable(root: Path) -> Path:
    """写入含非法 UTF-8 字节的文本文件（内容中含可搜索的 ASCII 关键字）。"""
    bad = root / "broken.txt"
    bad.write_bytes("needle here\n".encode("utf-8") + b"\xff\xfe\x80 invalid\n")
    return bad


def test_grep_reports_undecodable_file(tmp_path):
    """FO7：grep 不应静默跳过无法解码的文件。"""
    _make_undecodable(tmp_path)
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.grep("needle", path=".")

    assert result["undecodable_files"] == ["broken.txt"]
    assert result["matched_files"] == 0


def test_search_reports_undecodable_file(tmp_path):
    """FO7：search 不应静默跳过无法解码的文件。"""
    _make_undecodable(tmp_path)
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.search("needle", path=".")

    assert result["undecodable_files"] == ["broken.txt"]
    assert result["matches_found"] == 0


def test_grep_reports_no_undecodable_for_valid_files(tmp_path):
    """FO7：正常 UTF-8 文件不进入 undecodable 列表。"""
    (tmp_path / "ok.txt").write_text("needle here\n", encoding="utf-8")
    operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    result = operator.grep("needle", path=".")

    assert result["undecodable_files"] == []
    assert result["matched_files"] == 1


class TestReadStreaming:
    """FO5: read 流式分页，不依赖 readlines 全量载入。"""

    def _operator(self, root: Path) -> FileOperator:
        return FileOperator(base_path=str(root), allow_protected_paths=True)

    def test_paging_matches_expected_semantics(self, tmp_path):
        (tmp_path / "data.txt").write_text(
            "\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8"
        )
        operator = self._operator(tmp_path)

        first = operator.read("data.txt", offset=0, limit=3)
        assert first["total_lines"] == 10
        assert first["offset"] == 0
        assert first["has_more"] is True
        assert first["content"] == "line1\nline2\nline3\n"

        tail = operator.read("data.txt", offset=8, limit=5)
        assert tail["offset"] == 8
        assert tail["has_more"] is False
        assert tail["content"] == "line9\nline10\n"

    def test_offset_beyond_eof_clamps_to_total(self, tmp_path):
        (tmp_path / "data.txt").write_text("a\nb\n", encoding="utf-8")
        operator = self._operator(tmp_path)

        result = operator.read("data.txt", offset=99, limit=10)

        assert result["offset"] == 2
        assert result["has_more"] is False
        assert result["content"] == ""

    def test_does_not_call_readlines(self, tmp_path, monkeypatch):
        """FO5: 大文件读取不应触发 readlines（一次性全量载入）。"""
        (tmp_path / "data.txt").write_text("x\ny\nz\n", encoding="utf-8")
        operator = self._operator(tmp_path)

        real_open = open

        class NoReadlines:
            def __init__(self, handle):
                self._handle = handle

            def __iter__(self):
                return iter(self._handle)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return self._handle.__exit__(*exc)

            def readlines(self):
                raise AssertionError("read 不应调用 readlines")

        def fake_open(*args, **kwargs):
            return NoReadlines(real_open(*args, **kwargs))

        monkeypatch.setattr("builtins.open", fake_open)

        result = operator.read("data.txt", offset=1, limit=1)

        assert result["total_lines"] == 3
        assert result["content"] == "y\n"

    def test_stats_counts_lines_without_readlines(self, tmp_path, monkeypatch):
        """FO5: stats 逐文件计数改为流式，仍能正确统计行数。"""
        (tmp_path / "a.txt").write_text("1\n2\n3\n", encoding="utf-8")
        (tmp_path / "b.txt").write_text("x\n", encoding="utf-8")
        operator = self._operator(tmp_path)

        real_open = open

        class NoReadlines:
            def __init__(self, handle):
                self._handle = handle

            def __iter__(self):
                return iter(self._handle)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return self._handle.__exit__(*exc)

            def readlines(self):
                raise AssertionError("stats 不应调用 readlines")

        monkeypatch.setattr(
            "builtins.open", lambda *a, **k: NoReadlines(real_open(*a, **k))
        )

        result = operator.stats(".")

        assert result["total_files"] == 2
        assert result["total_lines"] == 4


class TestWriteExtensionWhitelist:
    """FO3: 扩展名白名单此前仅 create 生效，write 可写任意扩展名。"""

    def _operator(self, root: Path) -> FileOperator:
        return FileOperator(base_path=str(root), allow_protected_paths=True)

    def test_write_rejects_unknown_extension(self, tmp_path):
        operator = self._operator(tmp_path)

        with pytest.raises(PathSecurityError, match="不支持的文件扩展名"):
            operator.write("payload.unknownext", "x")

    def test_write_allows_whitelisted_extension(self, tmp_path):
        operator = self._operator(tmp_path)

        result = operator.write("src/main.py", "x = 1\n")

        assert result["success"] is True
        assert (tmp_path / "src" / "main.py").read_text(encoding="utf-8") == "x = 1\n"

    def test_write_allows_extensionless_files(self, tmp_path):
        operator = self._operator(tmp_path)

        assert operator.write("Dockerfile", "FROM python\n")["success"] is True
        assert operator.write("LICENSE", "MIT\n")["success"] is True

    @pytest.mark.parametrize("name", ["go.mod", "go.sum", "build.gradle", "app.csproj", "schema.proto", "app.log"])
    def test_write_and_create_allow_common_project_files(self, tmp_path, name):
        """FO3: 白名单补充常见工程文件后，create/write 均放行（否则 create 会误拒）。"""
        operator = self._operator(tmp_path)

        assert operator.write(f"w/{name}", "content\n")["success"] is True
        assert operator.create(f"c/{name}", content="content\n")["success"] is True

    def test_create_also_enforces_whitelist(self, tmp_path):
        operator = self._operator(tmp_path)

        with pytest.raises(PathSecurityError, match="不支持的文件扩展名"):
            operator.create("payload.unknownext", content="x")


class TestHiddenVisibility:
    """FO6: 隐藏工程文件此前在 search/grep/stats/list_dir/tree 中全部不可见。"""

    def _operator(self, root: Path) -> FileOperator:
        return FileOperator(base_path=str(root), allow_protected_paths=True)

    def _seed(self, root: Path) -> None:
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "ci.yml").write_text(
            "name: needle-ci\n", encoding="utf-8"
        )
        (root / ".gitignore").write_text("needle.pyc\n", encoding="utf-8")
        (root / ".env.example").write_text("API_KEY=needle\n", encoding="utf-8")
        (root / ".env").write_text("API_KEY=needle-secret\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text("needle\n", encoding="utf-8")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "dep.js").write_text("needle\n", encoding="utf-8")
        (root / "main.py").write_text("needle\n", encoding="utf-8")

    def test_collect_files_includes_hidden_project_files(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        collected = {str(p) for p in operator._collect_files(tmp_path)}

        assert ".github/workflows/ci.yml" in collected
        assert ".gitignore" in collected
        assert ".env.example" in collected
        assert "main.py" in collected

    def test_collect_files_skips_skip_dirs_and_protected_files(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        collected = {str(p) for p in operator._collect_files(tmp_path)}

        assert ".env" not in collected
        assert ".git/config" not in collected
        assert "node_modules/dep.js" not in collected

    def test_grep_sees_hidden_but_not_protected(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        result = operator.grep("needle", path=".")

        matched = {m["file"] for m in result["results"]}
        assert ".github/workflows/ci.yml" in matched
        assert ".env.example" in matched
        assert ".gitignore" in matched
        assert ".env" not in matched
        assert ".git/config" not in matched
        assert "node_modules/dep.js" not in matched

    def test_stats_counts_hidden_files(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        result = operator.stats(".")

        # main.py + .gitignore + .env.example + .github/workflows/ci.yml
        assert result["total_files"] == 4

    def test_list_dir_shows_hidden_entries(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        names = {e["name"] for e in operator.list_dir(".", recursive=False)["entries"]}

        assert ".github" in names
        assert ".gitignore" in names
        assert ".env.example" in names
        assert ".env" not in names
        assert ".git" not in names
        assert "node_modules" not in names

    def test_list_dir_recursive_descends_hidden_dirs(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        paths = {e["path"] for e in operator.list_dir(".", recursive=True)["entries"]}

        assert ".github/workflows/ci.yml" in paths

    def test_tree_includes_hidden_entries(self, tmp_path):
        self._seed(tmp_path)
        operator = self._operator(tmp_path)

        result = operator.tree(".", max_depth=4)

        child_names = {c["name"] for c in result["tree"]["children"]}
        assert ".github" in child_names
        assert ".gitignore" in child_names
        assert ".env" not in child_names
        assert "node_modules" not in child_names
        assert result["file_count"] == 4
