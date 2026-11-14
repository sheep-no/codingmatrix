"""synthesis_protocol 协议选择、可比输入与作用域校验补测。"""

import pytest
from pydantic import ValidationError

from app.agent.code_synthesis_contracts import ModelCapabilityProfile
from app.agent.synthesis_protocol import (
    ComparableSynthesisInput,
    ModelOperation,
    ModelOperationKind,
    ModelResponseProtocol,
    _safe_relative_path,
    select_response_protocol,
)


def _profile(**kwargs):
    base = dict(name="m", supports_json_schema=False, supports_tool_calls=False)
    base.update(kwargs)
    if base.get("supports_json_schema"):
        base.setdefault("supports_structured_output", True)
    return ModelCapabilityProfile(**base)


@pytest.mark.parametrize("flags,expected", [
    ({"supports_json_schema": True, "supports_tool_calls": True}, ModelResponseProtocol.JSON_SCHEMA),
    ({"supports_json_schema": False, "supports_tool_calls": True}, ModelResponseProtocol.TOOL_CALL),
    ({"supports_json_schema": False, "supports_tool_calls": False}, ModelResponseProtocol.RESTRICTED_JSON),
])
def test_select_response_protocol(flags, expected):
    assert select_response_protocol(_profile(**flags)) is expected


def test_comparable_input_requires_digest_lengths():
    with pytest.raises(ValidationError):
        ComparableSynthesisInput(
            request="r", plan_digest="short",
            contract_digest="a" * 64, context_hash="b" * 64,
        )


def test_comparable_assert_compatible_equal():
    first = ComparableSynthesisInput(
        request="r", plan_digest="a" * 64,
        contract_digest="b" * 64, context_hash="c" * 64,
    )
    second = first.model_copy()
    assert first.assert_compatible(second) is None


def test_comparable_assert_compatible_mismatch():
    base = dict(
        request="r", plan_digest="a" * 64,
        contract_digest="b" * 64, context_hash="c" * 64,
    )
    first = ComparableSynthesisInput(**base)
    second = ComparableSynthesisInput(**{**base, "context_hash": "d" * 64})
    with pytest.raises(ValueError, match="not comparable"):
        first.assert_compatible(second)


@pytest.mark.parametrize("path,expected", [
    ("app/main.py", True),
    ("", False),
    ("/etc/passwd", False),
    ("\\windows\\system32", False),
    ("../escape.py", False),
    ("a/../b.py", False),
    ("folder/file.py", True),
])
def test_safe_relative_path(path, expected):
    assert _safe_relative_path(path) is expected


def test_plan_operation_valid():
    op = ModelOperation(operation=ModelOperationKind.PLAN)
    assert op.operation is ModelOperationKind.PLAN


def test_plan_operation_rejects_target_content():
    with pytest.raises(ValidationError, match="plan operation"):
        ModelOperation(operation=ModelOperationKind.PLAN, target_path="a.py")
    with pytest.raises(ValidationError, match="plan operation"):
        ModelOperation(operation=ModelOperationKind.PLAN, content="x")


def test_file_slot_requires_target_and_content():
    with pytest.raises(ValidationError):
        ModelOperation(operation=ModelOperationKind.FILE_SLOT, content="x")
    with pytest.raises(ValidationError):
        ModelOperation(operation=ModelOperationKind.FILE_SLOT, target_path="a.py")
    with pytest.raises(ValidationError):
        ModelOperation(
            operation=ModelOperationKind.FILE_SLOT, target_path="a.py",
            content="x", patch="p",
        )
    valid = ModelOperation(
        operation=ModelOperationKind.FILE_SLOT, target_path="a.py", content="x",
    )
    assert valid.content == "x"


def test_patch_requires_target_and_patch():
    with pytest.raises(ValidationError):
        ModelOperation(operation=ModelOperationKind.PATCH, patch="p")
    with pytest.raises(ValidationError):
        ModelOperation(operation=ModelOperationKind.PATCH, target_path="a.py")
    with pytest.raises(ValidationError):
        ModelOperation(
            operation=ModelOperationKind.PATCH, target_path="a.py",
            patch="p", content="c",
        )
    valid = ModelOperation(
        operation=ModelOperationKind.PATCH, target_path="a.py", patch="p",
    )
    assert valid.patch == "p"


def test_repair_explanation_requires_explanation_only():
    with pytest.raises(ValidationError):
        ModelOperation(operation=ModelOperationKind.REPAIR_EXPLANATION)
    with pytest.raises(ValidationError):
        ModelOperation(
            operation=ModelOperationKind.REPAIR_EXPLANATION, explanation="e", content="c",
        )
    with pytest.raises(ValidationError):
        ModelOperation(
            operation=ModelOperationKind.REPAIR_EXPLANATION, explanation="e", patch="p",
        )
    valid = ModelOperation(
        operation=ModelOperationKind.REPAIR_EXPLANATION, explanation="e",
    )
    assert valid.explanation == "e"


def test_allowed_paths_must_be_safe():
    with pytest.raises(ValidationError, match="allowed_paths"):
        ModelOperation(operation=ModelOperationKind.PLAN, allowed_paths=("/abs.py",))
    with pytest.raises(ValidationError, match="allowed_paths"):
        ModelOperation(operation=ModelOperationKind.PLAN, allowed_paths=("../x.py",))


def test_target_path_must_be_safe():
    with pytest.raises(ValidationError, match="target_path"):
        ModelOperation(
            operation=ModelOperationKind.FILE_SLOT,
            target_path="../evil.py", content="x",
        )


def test_target_path_outside_allowed_scope():
    with pytest.raises(ValidationError, match="outside the allowed path scope"):
        ModelOperation(
            operation=ModelOperationKind.FILE_SLOT, target_path="b.py",
            allowed_paths=("a.py",), content="x",
        )


def test_depends_on_outside_allowed_scope():
    with pytest.raises(ValidationError, match="depends_on"):
        ModelOperation(
            operation=ModelOperationKind.PLAN,
            allowed_paths=("a.py",), depends_on=("b.py",),
        )


def test_depends_on_allowed_scope_passes():
    op = ModelOperation(
        operation=ModelOperationKind.PLAN,
        allowed_paths=("a.py", "b.py"), depends_on=("b.py",),
    )
    assert op.depends_on == ("b.py",)


def test_content_min_length():
    with pytest.raises(ValidationError):
        ModelOperation(
            operation=ModelOperationKind.FILE_SLOT, target_path="a.py", content="",
        )
