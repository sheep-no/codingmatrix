"""FastApiCrudRenderer 的确定性渲染回归。

该渲染器按 IR 生成一个六文件 FastAPI + SQLite CRUD 项目。历史缺陷：
`_render_model` / `_render_schema` 用 `dedent` 拼接多行字段块，缩进错乱，
生成文件首行即 `IndentationError`，项目无法导入。
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.constrained_generation import (
    CrudField,
    FastApiCrudIR,
    FastApiCrudLayout,
    FastApiCrudRenderer,
    _example_payload,
    _infer_todo_ir,
    _resolve_layout,
    _snake_case,
    _schema_default,
    _updated_payload,
    select_fastapi_crud_renderer,
)

LAYOUT_PATHS = (
    "main.py",
    "models.py",
    "database.py",
    "schemas.py",
    "crud.py",
    "test_main.py",
)

REQUIREMENT = (
    "用 FastAPI + SQLite 实现 todos 的 CRUD，支持创建、查询、更新、删除，"
    "接口路径 /api/todos"
)


def _renderer() -> FastApiCrudRenderer:
    renderer = select_fastapi_crud_renderer(REQUIREMENT, {p: {} for p in LAYOUT_PATHS})
    assert renderer is not None
    return renderer


@pytest.mark.parametrize("path", LAYOUT_PATHS)
def test_every_rendered_file_is_valid_python(path):
    """所有生成文件必须能通过 AST 解析（回归 IndentationError）。"""
    source = _renderer().render(path)
    ast.parse(source, filename=path)


def test_rendered_model_matches_indentation_conventions():
    source = _renderer().render("models.py")
    lines = source.splitlines()

    assert lines[0].startswith("from sqlalchemy import")
    # 类体成员缩进四空格，顶层 import 不缩进。
    class_index = lines.index("class Todo(Base):")
    assert lines[class_index + 1] == '    __tablename__ = "todos"'
    id_line = next(line for line in lines if line.strip().startswith("id = Column"))
    assert id_line.startswith("    id = Column")


def test_rendered_schema_matches_indentation_conventions():
    source = _renderer().render("schemas.py")
    lines = source.splitlines()

    assert lines[0] == "from pydantic import BaseModel, ConfigDict"
    assert "class TodoCreate(BaseModel):" in lines
    assert "    title: str" in lines
    assert "    model_config = ConfigDict(from_attributes=True)" in lines
    assert "    id: int" in lines


def test_generated_project_runs_its_own_crud_test(tmp_path):
    """端到端：生成六文件项目并执行其自带测试，必须全绿。"""
    renderer = _renderer()
    for path in LAYOUT_PATHS:
        (tmp_path / path).write_text(renderer.render(path), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_main.py", "-q"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout[-3000:]
    assert "1 passed" in result.stdout


def test_render_rejects_path_outside_layout():
    with pytest.raises(ValueError, match="outside the FastAPI CRUD layout"):
        _renderer().render("unexpected.py")


def test_supplied_ir_is_used_when_mapping():
    ir = {
        "kind": "fastapi_sqlite_crud",
        "entity_name": "Note",
        "resource_name": "notes",
        "route_path": "/api/notes",
        "fields": [{"name": "body", "type": "string"}],
    }
    renderer = select_fastapi_crud_renderer(REQUIREMENT, {p: {} for p in LAYOUT_PATHS}, ir)

    assert renderer is not None
    assert renderer.ir.entity_name == "Note"
    assert "class Note(Base):" in renderer.render("models.py")


def test_supplied_ir_with_wrong_kind_is_rejected():
    ir = {"kind": "something_else"}
    assert select_fastapi_crud_renderer(REQUIREMENT, {p: {} for p in LAYOUT_PATHS}, ir) is None


def test_missing_role_layout_is_rejected():
    """六个路径都能识别角色，但集合缺少 test 角色。"""
    paths = ("main.py", "models.py", "database.py", "schemas.py", "crud.py", "notes.py")
    assert _resolve_layout(paths) is None


@pytest.mark.parametrize(
    "paths",
    [
        (),
        ("main.py", "models.py"),
        tuple("abcdef"),
        ("main.py", "models.py", "database.py", "schemas.py", "crud.py", "main2.py"),
        tuple(p.replace(".py", ".txt") for p in LAYOUT_PATHS),
    ],
)
def test_incomplete_layouts_are_rejected(paths):
    assert _resolve_layout(paths) is None


def test_duplicate_role_layout_is_rejected():
    paths = ("main.py", "app_entry.py", "models.py", "database.py", "schemas.py", "crud.py")
    assert _resolve_layout(paths) is None


def test_requirement_without_markers_is_rejected():
    assert select_fastapi_crud_renderer("帮我写一个博客", {p: {} for p in LAYOUT_PATHS}) is None
    assert _infer_todo_ir("用 flask 做一个 todos crud") is None
    assert _infer_todo_ir("fastapi sqlite crud 但没有路由") is None


def test_ir_validates_field_rules():
    with pytest.raises(ValidationError, match="at least one field"):
        FastApiCrudIR(entity_name="Todo", resource_name="todos", route_path="/api/todos")

    with pytest.raises(ValidationError, match="must be unique"):
        FastApiCrudIR(
            entity_name="Todo",
            resource_name="todos",
            route_path="/api/todos",
            fields=(CrudField(name="title", type="string"), CrudField(name="title", type="string")),
        )

    with pytest.raises(ValidationError, match="reserves id"):
        FastApiCrudIR(
            entity_name="Todo",
            resource_name="todos",
            route_path="/api/todos",
            fields=(CrudField(name="id", type="integer"),),
        )


def test_schema_default_and_helpers():
    required = CrudField(name="title", type="string")
    optional = CrudField(name="done", type="boolean", required=False, default=False)
    nullable = CrudField(name="note", type="string", nullable=True)

    assert _schema_default(required) == ""
    assert _schema_default(optional) == " = False"
    assert _schema_default(nullable) == " = None"
    assert _snake_case("TodoItem") == "todo_item"
    assert _example_payload((required, optional, nullable)) == {
        "title": "generated",
        "done": False,
        "note": "generated",
    }
    assert _updated_payload((required, optional)) == {"title": "updated"}


def test_layout_paths_property_order():
    layout = FastApiCrudLayout(
        entry="main.py",
        model="models.py",
        database="database.py",
        schema="schemas.py",
        repository="crud.py",
        test="test_main.py",
    )
    assert layout.paths == LAYOUT_PATHS
