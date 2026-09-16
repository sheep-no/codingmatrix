from app.agent.adapters import ImportInfo, JavaScriptLanguageAdapter
from app.agent.integrity_validator import IntegrityValidator


REACT_PROJECT = {
    "src/App.tsx": "export default function App() { return null }\n",
    "src/components/Button.tsx": "export function Button() { return null }\n",
    "src/hooks/useAuth.ts": "export function useAuth() { return null }\n",
    "src/api/client.ts": "export const client = {}\n",
}

VUE_PROJECT = {
    "src/App.vue": "<script setup>\nimport Card from '@/components/Card'\n</script>\n",
    "src/components/Card/index.vue": "<template><div/></template>\n",
    "src/components/HelloWorld.vue": "<template><h1/></template>\n",
    "src/utils/format.js": "export const format = (v) => v\n",
}


def test_javascript_adapter_resolves_alias_to_vue_single_file_component() -> None:
    """Vue 单文件组件同样落在别名/相对导入的候选路径里。"""
    adapter = JavaScriptLanguageAdapter()

    flat = adapter.resolve_import_to_file(
        ImportInfo(module="@/components/HelloWorld", symbols=[], is_relative=False),
        "src/App.vue",
    )
    nested = adapter.resolve_import_to_file(
        ImportInfo(module="@/components/Card", symbols=[], is_relative=False),
        "src/App.vue",
    )
    relative = adapter.resolve_import_to_file(
        ImportInfo(module="./components/HelloWorld", symbols=[], is_relative=True),
        "src/App.vue",
    )

    assert "src/components/HelloWorld.vue" in flat
    assert "src/components/Card/index.vue" in nested
    assert "src/components/HelloWorld.vue" in relative


def test_javascript_adapter_resolves_explicit_extension_as_is() -> None:
    """带显式扩展名的导入不能被补全成 `x.vue.js` 之类。"""
    adapter = JavaScriptLanguageAdapter()

    candidates = adapter.resolve_import_to_file(
        ImportInfo(module="@/components/HelloWorld.vue", symbols=[], is_relative=False),
        "src/App.vue",
    )
    relative = adapter.resolve_import_to_file(
        ImportInfo(module="./components/HelloWorld.vue", symbols=[], is_relative=True),
        "src/App.vue",
    )

    assert candidates[0] == "src/components/HelloWorld.vue"
    assert relative[0] == "src/components/HelloWorld.vue"


def test_javascript_adapter_normalizes_relative_import_candidates() -> None:
    """相对候选要能被文件集合命中，不能保留 `./` 或 `../` 片段。"""
    adapter = JavaScriptLanguageAdapter()

    sibling = adapter.resolve_import_to_file(
        ImportInfo(module="./components/Button", symbols=[], is_relative=True),
        "src/App.jsx",
    )
    parent = adapter.resolve_import_to_file(
        ImportInfo(module="../shared/env.js", symbols=[], is_relative=True),
        "src/App.jsx",
    )

    assert "src/components/Button.jsx" in sibling
    assert parent[0] == "shared/env.js"


def test_javascript_adapter_does_not_require_directory_index_files() -> None:
    adapter = JavaScriptLanguageAdapter()

    assert adapter.validate_package_structure("src", REACT_PROJECT) == []
    assert adapter.validate_package_structure("src/components", REACT_PROJECT) == []
    assert adapter.get_required_package_files("src/components") == []


def test_integrity_validation_accepts_standard_react_layout() -> None:
    result = IntegrityValidator(language_adapter=JavaScriptLanguageAdapter()).validate(
        REACT_PROJECT
    )

    assert result.passed
    assert result.issues == []
    assert result.missing_files == []


def test_integrity_validation_generates_no_index_barrel_fixes() -> None:
    validator = IntegrityValidator(language_adapter=JavaScriptLanguageAdapter())
    result = validator.validate(REACT_PROJECT)

    assert validator.generate_fixes(result, REACT_PROJECT) == {}


def test_integrity_validation_still_requires_python_package_init() -> None:
    from app.agent.adapters import PythonLanguageAdapter

    files = {
        "app/main.py": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        "app/routers/users.py": "from fastapi import APIRouter\n\nrouter = APIRouter()\n",
    }
    result = IntegrityValidator(language_adapter=PythonLanguageAdapter()).validate(files)

    assert not result.passed
    assert set(result.missing_files) == {"app/__init__.py", "app/routers/__init__.py"}
