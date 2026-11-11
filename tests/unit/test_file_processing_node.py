"""FileProcessingNode 参数校验与文件操作测试。"""

import pytest

from app.utils.file_operator import FileOperator, PathSecurityError
from app.utils.workflow.node_types.file_processing import FileProcessingNode


@pytest.fixture
def node_factory(tmp_path):
    def factory(params):
        node = FileProcessingNode("n1", params)
        node._operator = FileOperator(
            base_path=str(tmp_path), allow_protected_paths=True
        )
        return node

    return factory


class TestParamsContract:
    @pytest.mark.parametrize("operation", ["read", "write", "delete", "create_dir", "list_dir"])
    def test_path_only_operations(self, operation):
        node = FileProcessingNode("n1", {"operation": operation})
        assert node.get_required_params() == ["path"]

    @pytest.mark.parametrize("operation", ["copy", "move"])
    def test_copy_and_move_require_source_and_destination(self, operation):
        node = FileProcessingNode("n1", {"operation": operation})
        assert node.get_required_params() == ["source", "destination"]

    def test_unknown_operation_requires_operation_field(self):
        node = FileProcessingNode("n1", {})
        assert node.get_required_params() == ["operation"]

    def test_optional_params_defaults(self):
        node = FileProcessingNode("n1", {})
        assert node.get_optional_params() == {
            "encoding": "utf-8",
            "recursive": False,
            "parents": True,
        }


class TestValidateParams:
    def test_missing_operation(self):
        node = FileProcessingNode("n1", {})
        assert node.validate_params() == ["Missing required parameter: operation"]

    def test_unknown_operation(self):
        node = FileProcessingNode("n1", {"operation": "chmod"})
        errors = node.validate_params()

        assert len(errors) == 1
        assert errors[0].startswith("Invalid operation: chmod")

    def test_valid_read_path(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        node = node_factory({"operation": "read", "path": "a.txt"})

        assert node.validate_params() == []

    def test_missing_path_for_read(self, node_factory):
        node = node_factory({"operation": "read"})
        assert node.validate_params() == ["Missing required parameter: path"]

    def test_path_security_error_is_collected(self, node_factory):
        node = node_factory({"operation": "read", "path": "../escape.txt"})
        errors = node.validate_params()

        assert len(errors) == 1
        assert "路径超出允许范围" in errors[0]

    def test_copy_requires_both_keys(self, node_factory):
        node = node_factory({"operation": "copy"})
        errors = node.validate_params()

        assert errors == [
            "Missing required parameter: source",
            "Missing required parameter: destination",
        ]

    def test_copy_validates_existing_keys(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        node = node_factory(
            {"operation": "copy", "source": "a.txt", "destination": "b.txt"}
        )

        assert node.validate_params() == []

    def test_copy_security_error_on_source(self, node_factory):
        node = node_factory(
            {"operation": "copy", "source": "../x", "destination": "b.txt"}
        )
        errors = node.validate_params()

        assert len(errors) == 1
        assert "路径超出允许范围" in errors[0]

    def test_move_validates_destination_security(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        node = node_factory(
            {"operation": "move", "source": "a.txt", "destination": "../out.txt"}
        )
        errors = node.validate_params()

        assert len(errors) == 1
        assert "路径超出允许范围" in errors[0]


class TestExecuteOperations:
    @pytest.mark.asyncio
    async def test_read(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
        node = node_factory({"operation": "read", "path": "a.txt"})

        result = await node.execute({})

        assert result.success is True
        assert result.data["content"] == "line1\nline2\n"
        assert result.metadata["operation"] == "read"

    @pytest.mark.asyncio
    async def test_read_with_paging(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("a\nb\nc\n", encoding="utf-8")
        node = node_factory(
            {"operation": "read", "path": "a.txt", "offset": 1, "limit": 1}
        )

        result = await node.execute({})

        assert result.data["content"] == "b\n"

    @pytest.mark.asyncio
    async def test_write(self, node_factory, tmp_path):
        node = node_factory(
            {"operation": "write", "path": "out.txt", "content": "hello"}
        )

        result = await node.execute({})

        assert result.success is True
        assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "hello"

    @pytest.mark.asyncio
    async def test_write_defaults_to_empty_content(self, node_factory, tmp_path):
        node = node_factory({"operation": "write", "path": "empty.txt"})

        result = await node.execute({})

        assert result.success is True
        assert (tmp_path / "empty.txt").read_text(encoding="utf-8") == ""

    @pytest.mark.asyncio
    async def test_write_with_backup(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("old", encoding="utf-8")
        node = node_factory(
            {
                "operation": "write",
                "path": "a.txt",
                "content": "new",
                "create_backup": True,
            }
        )

        result = await node.execute({})

        assert result.success is True
        assert (tmp_path / "a.txt.bak").read_text(encoding="utf-8") == "old"

    @pytest.mark.asyncio
    async def test_copy(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("data", encoding="utf-8")
        node = node_factory(
            {"operation": "copy", "source": "a.txt", "destination": "b.txt"}
        )

        result = await node.execute({})

        assert result.success is True
        assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "data"
        assert result.metadata["operation"] == "copy"

    @pytest.mark.asyncio
    async def test_move(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("data", encoding="utf-8")
        node = node_factory(
            {"operation": "move", "source": "a.txt", "destination": "c.txt"}
        )

        result = await node.execute({})

        assert result.success is True
        assert not (tmp_path / "a.txt").exists()
        assert (tmp_path / "c.txt").read_text(encoding="utf-8") == "data"

    @pytest.mark.asyncio
    async def test_delete_file(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        node = node_factory({"operation": "delete", "path": "a.txt"})

        result = await node.execute({})

        assert result.success is True
        assert not (tmp_path / "a.txt").exists()

    @pytest.mark.asyncio
    async def test_delete_recursive_directory(self, node_factory, tmp_path):
        sub = tmp_path / "dir" / "nested"
        sub.mkdir(parents=True)
        (sub / "a.txt").write_text("x", encoding="utf-8")
        node = node_factory(
            {"operation": "delete", "path": "dir", "recursive": True}
        )

        result = await node.execute({})

        assert result.success is True
        assert not (tmp_path / "dir").exists()

    @pytest.mark.asyncio
    async def test_create_dir(self, node_factory, tmp_path):
        node = node_factory({"operation": "create_dir", "path": "new/nested"})

        result = await node.execute({})

        assert result.success is True
        assert (tmp_path / "new" / "nested").is_dir()

    @pytest.mark.asyncio
    async def test_list_dir(self, node_factory, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        node = node_factory({"operation": "list_dir", "path": "."})

        result = await node.execute({})

        assert result.success is True
        names = {entry["name"] for entry in result.data["entries"]}
        assert names == {"a.txt", "sub"}

    @pytest.mark.asyncio
    async def test_list_dir_recursive(self, node_factory, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("x", encoding="utf-8")
        node = node_factory(
            {"operation": "list_dir", "path": ".", "recursive": True}
        )

        result = await node.execute({})

        paths = {entry["path"] for entry in result.data["entries"]}
        assert "sub/b.txt" in paths

    @pytest.mark.asyncio
    async def test_unsupported_operation(self):
        node = FileProcessingNode("n1", {"operation": "chmod"})

        result = await node.execute({})

        assert result.success is False
        assert result.error == "Unsupported operation: chmod"
        assert result.metadata["node_type"] == node.task_type.value

    @pytest.mark.asyncio
    async def test_missing_operation_is_unsupported(self):
        node = FileProcessingNode("n1", {})

        result = await node.execute({})

        assert result.success is False
        assert result.error == "Unsupported operation: "


class TestExecuteErrors:
    @pytest.mark.asyncio
    async def test_file_not_found(self, node_factory):
        node = node_factory({"operation": "read", "path": "missing.txt"})

        result = await node.execute({})

        assert result.success is False
        assert result.error.startswith("File not found:")
        assert result.metadata["operation"] == "read"

    @pytest.mark.asyncio
    async def test_permission_denied(self, node_factory, monkeypatch):
        node = node_factory({"operation": "read", "path": "a.txt"})

        async def denied(**_kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(node._operator, "read_async", denied)

        result = await node.execute({})

        assert result.success is False
        assert result.error.startswith("Permission denied:")

    @pytest.mark.asyncio
    async def test_path_security_error(self, node_factory):
        node = node_factory({"operation": "read", "path": "../outside.txt"})

        result = await node.execute({})

        assert result.success is False
        assert result.error.startswith("Path security error:")

    @pytest.mark.asyncio
    async def test_generic_exception(self, node_factory, monkeypatch):
        node = node_factory({"operation": "copy", "source": "a", "destination": "b"})

        def boom(**_kwargs):
            raise RuntimeError("copy failed")

        monkeypatch.setattr(node._operator, "copy", boom)

        result = await node.execute({})

        assert result.success is False
        assert result.error == "File operation failed: copy failed"
