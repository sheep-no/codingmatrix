"""dependency_manifest 归一化与校验分支补测。"""

import pytest
from pydantic import ValidationError

from app.agent.dependency_manifest import (
    Dependency,
    DependencyKind,
    DependencyManifest,
    _coerce_dependency,
    _normalize_dependencies,
)


def test_build_from_mapping_with_versions():
    manifest = DependencyManifest.build({"requests": "2.0", "flask": "3.0"})

    assert manifest.names() == ("flask", "requests")
    assert {item.kind for item in manifest.dependencies} == {DependencyKind.RUNTIME}


def test_build_from_category_lists():
    manifest = DependencyManifest.build({
        "runtime": ["flask"],
        "test": ["pytest"],
    })

    assert manifest.names(DependencyKind.TEST) == ("pytest",)


def test_build_from_nested_dependencies_key():
    manifest = DependencyManifest.build({"dependencies": ["flask", "requests"]})
    assert len(manifest.dependencies) == 2


def test_build_from_single_string_value():
    manifest = DependencyManifest.build({"dependencies": "flask"})
    assert manifest.names() == ("flask",)


def test_build_from_none_and_string():
    assert DependencyManifest.build(None).dependencies == ()
    assert DependencyManifest.build("flask").dependencies == ()


def test_build_from_single_mapping():
    manifest = DependencyManifest.build({"name": "flask", "kind": "runtime"})
    assert manifest.names() == ("flask",)


def test_build_rejects_duplicates():
    with pytest.raises(ValueError, match="more than once"):
        DependencyManifest.build(["flask", "flask"])


def test_build_rejects_forbidden():
    with pytest.raises(ValueError, match="forbidden"):
        DependencyManifest.build([{"name": "evil", "kind": "forbidden"}])


def test_names_without_filter_returns_all():
    manifest = DependencyManifest.build([
        {"name": "flask", "kind": "runtime"},
        {"name": "pytest", "kind": "test"},
    ])
    assert set(manifest.names()) == {"flask", "pytest"}


def test_allows_respects_forbidden_kind():
    manifest = DependencyManifest.build(["flask"])
    assert manifest.allows("flask") is True
    assert manifest.allows("django") is False


def test_digest_mismatch_rejected():
    manifest = DependencyManifest.build(["flask"])

    with pytest.raises(ValidationError):
        DependencyManifest(version=1, dependencies=manifest.dependencies, digest="0" * 64)


def test_coerce_string_and_mapping():
    assert _coerce_dependency("flask").kind is DependencyKind.RUNTIME
    partial = _coerce_dependency({"package": "x", "category": "test", "version": 2})
    assert partial.name == "x"
    assert partial.kind is DependencyKind.TEST
    assert partial.version == "2"


def test_normalize_category_with_scalar_non_string():
    normalized = _normalize_dependencies({"runtime": Dependency(name="a", kind=DependencyKind.RUNTIME)})
    assert normalized[0].name == "a"


def test_normalize_non_category_names_uses_runtime():
    entries = _normalize_dependencies({"custom": ["x"]})
    assert entries == ({"name": "x", "kind": "runtime"},)


def test_normalize_category_with_mapping_item_passthrough():
    entries = _normalize_dependencies({"test": [{"name": "pytest", "kind": "test"}]})
    assert entries == ({"name": "pytest", "kind": "test"},)


def test_coerce_existing_dependency_object():
    dep = Dependency(name="a", kind=DependencyKind.TEST)
    assert _coerce_dependency(dep) is dep
