import pytest

from app.agent.scaffolding import official_scaffold_request


def test_official_scaffold_is_parameterized_and_shell_free():
    request = official_scaffold_request("typescript", "express", "sample")

    assert request.as_command_spec().shell is False
    assert request.command == ("npx", "express-generator", "sample")


def test_unknown_framework_has_explicit_pending_state():
    with pytest.raises(LookupError):
        official_scaffold_request("go", "gin", "sample")
