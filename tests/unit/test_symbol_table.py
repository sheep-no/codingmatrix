import types
from app.agent.architect import Architect
from app.agent.backend_engineer import BackendEngineer
from app.agent.symbol_table import (
    freeze_symbol_table,
    remember_generated_file,
    rewrite_manifests,
    scan_python_packages,
    validate_file_against_symbol_table,
)
from app.agent.utils import compact_project_context_for_file


def _complexity():
    return types.SimpleNamespace(
        has_frontend=False,
        has_backend=True,
        has_database=True,
        key_technologies=[],
        risk_factors=[],
    )


def test_compact_eight_file_architecture_freezes_ticket_signatures():
    architect = object.__new__(Architect)
    result = architect._get_compact_eight_file_architecture(
        "实现工单系统，包含注册登录鉴权",
        _complexity(),
        language="python",
    )

    table = result["symbol_table"]
    assert table["storage"]["backend"] == "sqlalchemy"
    assert table["auth"]["scheme"] == "jwt_hs256"
    assert table["route_prefix"] == ""
    provides = table["files"]["app/services.py"]["provides"]
    assert "hash_password" in provides
    assert "create_access_token" in provides
    services = next(item for item in result["file_plan"] if item["path"] == "app/services.py")
    assert "hash_password" in services["contract"]["exports"]


def test_compact_context_injects_symbol_table_and_generated_signatures():
    architecture = {
        "language": "python",
        "requirement": "工单服务",
        "file_plan": [
            {"path": "main.py", "file_type": "entry", "description": "入口", "imports": []},
            {"path": "app/models.py", "file_type": "model", "description": "模型"},
        ],
    }
    freeze_symbol_table(architecture)
    architecture["symbol_table"] = {
        "storage": {"backend": "sqlalchemy"},
        "auth": {"scheme": "jwt_hs256"},
        "route_prefix": "",
        "files": {
            "main.py": {"provides": ["app"], "requires": ["router"], "signatures": {}, "routes": []},
            "app/models.py": {"provides": ["Ticket"], "requires": ["Base"], "signatures": {}, "routes": []},
        },
    }
    context = {
        "requirement": "工单服务",
        "architecture": architecture,
        "generated_signatures": {"app/models.py": "class Ticket(Base)"},
    }
    compact = compact_project_context_for_file("main.py", context)
    assert "app/models.py" in compact
    assert "hash_password" not in compact or "symbol_table" in compact
    assert "already_generated" in compact
    assert "class Ticket(Base)" in compact
    assert "jwt_hs256" in compact


def test_symbol_gate_reports_missing_auth_helpers_and_dual_storage():
    architecture = {
        "language": "python",
        "file_plan": [{"path": "app/services.py", "file_type": "service"}],
        "symbol_table": {
            "storage": {"backend": "sqlalchemy"},
            "auth": {"scheme": "jwt_hs256"},
            "route_prefix": "",
            "files": {
                "app/services.py": {
                    "provides": ["hash_password", "create_access_token"],
                    "requires": [],
                    "signatures": {},
                    "routes": [],
                }
            },
        },
    }
    content = (
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "def _generate_jwt(data):\n"
        "    return 'token'\n"
        "\n"
        "def save():\n"
        "    json.dump({}, open('data.json', 'w'))\n"
    )
    issues = validate_file_against_symbol_table("app/services.py", content, architecture)
    assert any("hash_password" in item for item in issues)
    assert any("create_access_token" in item for item in issues)
    assert any("JSON file storage" in item for item in issues)


def test_symbol_gate_rejects_api_v1_prefix():
    architecture = {
        "language": "python",
        "file_plan": [{"path": "app/routers.py", "file_type": "api"}],
        "symbol_table": {
            "storage": {"backend": "sqlalchemy"},
            "route_prefix": "",
            "files": {
                "app/routers.py": {
                    "provides": ["router"],
                    "requires": [],
                    "signatures": {},
                    "routes": ["POST /register", "POST /login"],
                }
            },
        },
    }
    content = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        '@router.post("/api/v1/register")\n'
        "def register():\n"
        "    return {}\n"
        '@router.post("/api/v1/login")\n'
        "def login():\n"
        "    return {}\n"
    )
    issues = validate_file_against_symbol_table("app/routers.py", content, architecture)
    assert any("/api/v1" in item for item in issues)


def test_scan_python_packages_maps_jose_and_sqlalchemy():
    files = {
        "app/services.py": (
            "from jose import jwt\n"
            "from passlib.context import CryptContext\n"
            "from sqlalchemy.orm import Session\n"
            "from fastapi import Depends\n"
        ),
        "tests/test_app.py": "from fastapi.testclient import TestClient\n",
    }
    packages = scan_python_packages(files)
    assert "python-jose[cryptography]" in packages
    assert "sqlalchemy" in packages
    assert "fastapi" in packages
    assert "pytest" in packages


def test_scan_python_packages_keeps_unmapped_third_party():
    packages = scan_python_packages({
        "game.py": "import pygame\nfrom models.snake_model import Snake\n",
        "models/snake_model.py": "class Snake:\n    pass\n",
    })
    assert "pygame" in packages
    assert "models" not in packages
    assert "snake_model" not in packages


def test_rewrite_manifests_writes_requirements_and_readme(tmp_path):
    architecture = {
        "language": "python",
        "requirement": "工单系统",
        "file_plan": [
            {"path": "requirements.txt", "file_type": "config"},
            {"path": "README.md", "file_type": "docs"},
            {"path": "tests/test_app.py", "file_type": "test"},
        ],
        "symbol_table": {
            "storage": {"backend": "sqlalchemy"},
            "auth": {"scheme": "jwt_hs256"},
        },
    }
    files = {
        "app/database.py": "from sqlalchemy.orm import sessionmaker\n",
        "app/services.py": "from jose import jwt\nfrom passlib.context import CryptContext\n",
        "tests/test_app.py": "def test_ok():\n    assert True\n",
    }
    rewritten = rewrite_manifests(tmp_path, architecture, files)
    requirements = (tmp_path / "requirements.txt").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "sqlalchemy" in requirements
    assert "python-jose[cryptography]" in requirements
    assert "pytest" in requirements
    assert "## Test" in readme
    assert "pytest" in readme
    assert rewritten["requirements.txt"] == requirements


def test_remember_generated_file_stores_signatures():
    context = {"generated_signatures": {}}
    issues = remember_generated_file(
        context,
        "app/services.py",
        "def hash_password(password: str) -> str:\n    return password\n",
        {"language": "python", "symbol_table": {}},
    )
    assert issues == []
    assert "hash_password" in context["generated_signatures"]["app/services.py"]


def test_backend_constraints_include_frozen_signatures():
    architecture = {
        "language": "python",
        "file_plan": [{"path": "app/services.py", "file_type": "service", "contract": {}}],
        "symbol_table": {
            "storage": {"backend": "sqlalchemy"},
            "auth": {"scheme": "jwt_hs256"},
            "files": {
                "app/services.py": {
                    "provides": ["hash_password"],
                    "signatures": {"hash_password": "def hash_password(password: str) -> str"},
                    "routes": [],
                }
            },
        },
    }
    text = BackendEngineer._build_contract_constraints("app/services.py", architecture)
    assert "def hash_password(password: str) -> str" in text
    assert "jwt_hs256" in text
    assert "sqlalchemy" in text


def test_rewrite_manifests_writes_frozen_ticket_tests(tmp_path):
    architecture = {
        "language": "python",
        "used_compact_eight_file_plan": True,
        "file_plan": [
            {"path": "tests/test_app.py", "file_type": "test"},
            {"path": "README.md", "file_type": "docs"},
        ],
        "symbol_table": {
            "storage": {"backend": "sqlalchemy"},
            "auth": {"scheme": "jwt_hs256"},
            "route_prefix": "",
            "files": {
                "tests/test_app.py": {
                    "routes": [
                        "POST /register",
                        "POST /login",
                        "POST /tickets",
                        "GET /tickets",
                        "POST /tickets/{ticket_id}/close",
                    ]
                }
            },
        },
    }
    rewritten = rewrite_manifests(tmp_path, architecture, {"tests/test_app.py": "def test_ok():\n    assert True\n"})
    tests = (tmp_path / "tests" / "test_app.py").read_text(encoding="utf-8")
    assert 'client.post("/register"' in tests
    assert "/api/v1" not in tests
    assert rewritten["tests/test_app.py"] == tests


def test_adapter_owned_frozen_tests_skip_review():
    from app.agent.orchestrator_generation.spec_first_generate import (
        _is_adapter_owned_file,
        _skipped_refinement,
    )

    architecture = {
        "language": "python",
        "used_compact_eight_file_plan": True,
        "symbol_table": {
            "files": {
                "tests/test_app.py": {
                    "routes": ["POST /register", "POST /login", "POST /tickets"],
                }
            }
        },
    }
    assert _is_adapter_owned_file("tests/test_app.py", "test", architecture)
    result = _skipped_refinement("print(1)")
    assert result.success is True
    assert result.final_content == "print(1)"
