"""contract_validation OpenAPI 投影与规则聚合补测。"""

from app.agent.stack_adapters.contract_validation import (
    StackContractRule,
    StackContractValidator,
    contracts_from_openapi,
)


class _Context:
    def __init__(self, spec):
        self._spec = spec

    def get_spec(self, name):
        return self._spec if name == "openapi" else None


def test_contracts_from_openapi_projects_routes():
    context = _Context({
        "paths": {
            "/api/items": {
                "get": {"operationId": "list_items"},
                "post": {"operationId": "create_item"},
                "parameters": [],
            },
            "/api/ignored": {"x-custom": {}},
        }
    })

    result = contracts_from_openapi(context)

    assert result == {
        "routes": [
            {"method": "GET", "path": "/api/items", "operation_id": "list_items"},
            {"method": "POST", "path": "/api/items", "operation_id": "create_item"},
        ]
    }


def test_contracts_from_openapi_returns_empty_for_missing_context():
    assert contracts_from_openapi(object()) == {}


def test_contracts_from_openapi_rejects_non_mapping_spec():
    assert contracts_from_openapi(_Context(["not", "mapping"])) == {}


def test_contracts_from_openapi_rejects_non_mapping_paths():
    assert contracts_from_openapi(_Context({"paths": []})) == {}


def test_contracts_from_openapi_skips_bad_entries():
    context = _Context({
        "paths": {
            1: {"get": {}},
            "/ok": "not-a-mapping",
            "/valid": {5: {"operationId": "x"}, "put": None},
        }
    })

    result = contracts_from_openapi(context)

    assert result == {
        "routes": [{"method": "PUT", "path": "/valid", "operation_id": ""}]
    }


def test_stack_rule_matches_extensions_and_roles():
    rule = StackContractRule(
        name="r",
        stack_ids=frozenset({"react"}),
        extensions=frozenset({".tsx"}),
        roles=frozenset({"page"}),
    )

    assert rule.matches("src/App.tsx", "page") is True
    assert rule.matches("src/App.ts", "page") is False
    assert rule.matches("src/App.tsx", "component") is False


def test_stack_rule_without_filters_matches_all():
    rule = StackContractRule(name="r", stack_ids=frozenset({"react"}))
    assert rule.matches("anything.jsx") is True


def test_validator_skips_rule_for_other_stack():
    rule = StackContractRule(
        name="r",
        stack_ids=frozenset({"vue"}),
        callback=lambda path, content: ["vue-only"],
    )
    validator = StackContractValidator([rule], stack_id="react")

    assert validator.validate("a.vue", "x") == ()


def test_validator_skips_rule_without_callback():
    rule = StackContractRule(name="r", stack_ids=frozenset({"react"}))
    validator = StackContractValidator([rule], stack_id="react")

    assert validator.validate("a.tsx", "x") == ()


def test_validator_uses_explicit_stack_override():
    rule = StackContractRule(
        name="r",
        stack_ids=frozenset({"vue"}),
        callback=lambda path, content: ["hit"],
    )
    validator = StackContractValidator([rule], stack_id="react")

    assert validator.validate("a.vue", "x", stack_id="vue") == ("hit",)


def test_validator_runs_plain_callable_rules():
    validator = StackContractValidator(
        [lambda path, content: ["one", 2]], stack_id="react"
    )

    assert validator.validate("a.py", "x") == ("one", "2")


def test_validator_defaults_to_empty():
    assert StackContractValidator().validate("a.py", "x") == ()
