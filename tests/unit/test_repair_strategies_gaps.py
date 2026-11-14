"""repair_strategies 各技术栈匹配谓词与文件来源补测。"""

from app.agent.stack_adapters.repair_strategies import (
    RepairContext,
    fastapi_crud_repair_applies,
    flask_crud_repair_applies,
    express_crud_repair_applies,
    nestjs_crud_repair_applies,
    go_crud_repair_applies,
    pygame_snake_repair_applies,
    spring_crud_repair_applies,
)


def test_fastapi_rejects_app_py_without_package_entry():
    ctx = RepairContext(
        requirement="repair the existing python fastapi crud",
        file_entries=("app.py",),
    )
    assert fastapi_crud_repair_applies(ctx) is False


def test_fastapi_accepts_packaged_layout():
    ctx = RepairContext(
        requirement="repair the existing python fastapi crud",
        file_entries=("app.py", "app/main.py"),
    )
    assert fastapi_crud_repair_applies(ctx) is True


def test_spring_matches_by_requirement_endpoint():
    ctx = RepairContext(
        requirement="repair java spring todo /api/v1/todos",
        file_entries=(),
    )
    assert spring_crud_repair_applies(ctx) is True


def test_spring_matches_by_planned_types():
    ctx = RepairContext(
        requirement="repair java spring todo",
        file_entries=(
            "src/main/java/Todo.java",
            "src/main/java/TodoController.java",
            "src/main/java/TodoRepository.java",
        ),
    )
    assert spring_crud_repair_applies(ctx) is True


def test_spring_rejects_non_java_requirement():
    ctx = RepairContext(requirement="repair python fastapi", file_entries=())
    assert spring_crud_repair_applies(ctx) is False


def test_flask_rejects_packaged_entry():
    ctx = RepairContext(
        requirement="repair the existing python flask crud",
        file_entries=("app/main.py",),
    )
    assert flask_crud_repair_applies(ctx) is False


def test_flask_accepts_flat_layout():
    ctx = RepairContext(
        requirement="repair the existing python flask crud",
        file_entries=("app.py",),
    )
    assert flask_crud_repair_applies(ctx) is True


def test_express_requires_entry_and_markers():
    matching = RepairContext(
        requirement="repair typescript express crud",
        file_entries=("src/app.ts",),
    )
    assert express_crud_repair_applies(matching) is True
    assert express_crud_repair_applies(
        RepairContext(requirement="repair typescript express crud", file_entries=())
    ) is False


def test_nestjs_requires_main_entry():
    matching = RepairContext(
        requirement="repair typescript nestjs crud",
        file_entries=("src/main.ts",),
    )
    assert nestjs_crud_repair_applies(matching) is True
    assert nestjs_crud_repair_applies(
        RepairContext(requirement="repair typescript nestjs crud", file_entries=())
    ) is False


def test_go_requires_server_entry():
    matching = RepairContext(
        requirement="repair go crud",
        file_entries=("cmd/server/main.go",),
    )
    assert go_crud_repair_applies(matching) is True
    assert go_crud_repair_applies(
        RepairContext(requirement="go crud", file_entries=())
    ) is False


def test_pygame_requires_all_files():
    entries = (
        "main.py", "game/rules.py", "game/renderer.py",
        "game/input_loop.py", "tests/test_game.py",
    )
    assert pygame_snake_repair_applies(
        RepairContext(requirement="pygame snake", file_entries=entries)
    ) is True
    assert pygame_snake_repair_applies(
        RepairContext(requirement="pygame snake", file_entries=entries[:-1])
    ) is False


def test_context_files_fall_back_to_project_allowed_files():
    ctx = RepairContext(
        requirement="pygame snake",
        file_entries=(),
        project_context={
            "allowed_files": (
                "main.py", "game/rules.py", "game/renderer.py",
                "game/input_loop.py", "tests/test_game.py",
            )
        },
    )
    assert pygame_snake_repair_applies(ctx) is True


def test_context_files_normalizes_backslashes():
    ctx = RepairContext(
        requirement="repair typescript express crud",
        project_context={"allowed_files": (r"src\app.ts",)},
    )
    assert express_crud_repair_applies(ctx) is True


def test_context_files_empty_without_project_context():
    ctx = RepairContext(requirement="repair typescript express crud")
    assert express_crud_repair_applies(ctx) is False
