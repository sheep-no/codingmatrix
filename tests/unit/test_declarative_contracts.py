import ast
import inspect

import pytest

import app.agent.declarative_contracts as declarative_contracts
from app.agent.adapters.python import PythonLanguageAdapter
from app.agent.declarative_contracts import (
    ArtifactFacts,
    ContractDeclaration,
    GateStatus,
    SymbolContract,
    compare_contract,
    missing_symbols,
    validate_candidate,
)


@pytest.mark.parametrize(
    ("fact_name", "actual", "operator", "expected", "status"),
    [
        ("exports", ["create", "read"], "contains_all", ["read"], GateStatus.PASSED),
        ("types", ["Record"], "equals", ["Record"], GateStatus.PASSED),
        ("imports", ["storage"], "excludes_all", ["network"], GateStatus.PASSED),
        ("exports", ["create"], "contains_all", ["delete"], GateStatus.FAILED),
    ],
)
def test_generic_gate_compares_arbitrary_declared_fact_sets(
    fact_name, actual, operator, expected, status
):
    declaration = ContractDeclaration.model_validate({
        "schema_version": 1,
        "assertions": [{
            "fact": fact_name,
            "operator": operator,
            "expected": expected,
            "reference": "fixture-contract",
        }],
    })

    result = compare_contract(declaration, ArtifactFacts.build({fact_name: actual}))

    assert result.status is status


def test_generic_gate_reports_missing_parser_capability_as_unsupported():
    declaration = ContractDeclaration.model_validate({
        "assertions": [{
            "fact": "protocol_messages",
            "operator": "contains_all",
            "expected": ["ready"],
        }],
    })

    result = compare_contract(declaration, ArtifactFacts.build({"symbols": []}))

    assert result.status is GateStatus.UNSUPPORTED
    assert result.diagnostics[0].code == "contract.fact_unsupported"


def test_symbol_contract_is_language_neutral_and_reports_missing_exports():
    contract = SymbolContract.build(
        "src/service",
        provides=["Service"],
        requires=["Repository", "Repository"],
        required_fixtures=["client"],
    )

    assert contract.requires == ("Repository",)
    assert missing_symbols(contract, ArtifactFacts.build({"symbols": ["Service"]})) == ("Repository",)


def test_python_forward_annotation_repair_reenters_the_same_generic_gate():
    adapter = PythonLanguageAdapter()
    declaration = ContractDeclaration.model_validate({
        "assertions": [{
            "fact": "symbols",
            "operator": "contains_all",
            "expected": ["Envelope", "Payload"],
        }],
    })
    content = (
        "from pydantic import BaseModel\n"
        "class Envelope(BaseModel):\n"
        "    payload: Payload\n"
        "class Payload(BaseModel):\n"
        "    value: str\n"
    )
    planned = {"pkg/contracts.py": content}

    first = validate_candidate(adapter, "pkg/contracts.py", content, declaration, planned)
    repaired_content = adapter.repair_source(content, "pkg/contracts.py", first.diagnostics)
    assert repaired_content is not None
    repaired = validate_candidate(
        adapter,
        "pkg/contracts.py",
        repaired_content,
        declaration,
        {"pkg/contracts.py": repaired_content},
    )

    assert first.passed is False
    assert repaired.passed is True
    assert repaired_content.startswith("from __future__ import annotations\n")


def test_python_missing_external_export_is_rejected_and_unused_import_is_repaired():
    adapter = PythonLanguageAdapter()
    declaration = ContractDeclaration()
    content = "from pathlib import Path, MissingPath\n\nROOT = Path('.')\n"

    first = validate_candidate(adapter, "pkg/config.py", content, declaration, {})
    repaired_content = adapter.repair_source(
        content, "pkg/config.py", first.diagnostics
    )

    assert first.passed is False
    assert first.diagnostics == ("Python module pathlib does not export: MissingPath",)
    assert repaired_content == "from pathlib import Path\n\nROOT = Path('.')\n"
    repaired = validate_candidate(
        adapter, "pkg/config.py", repaired_content, declaration, {}
    )
    assert repaired.passed is True


def test_python_missing_external_export_remains_when_referenced():
    adapter = PythonLanguageAdapter()
    content = "from pathlib import MissingPath\n\nROOT = MissingPath('.')\n"

    first = validate_candidate(
        adapter, "pkg/config.py", content, ContractDeclaration(), {}
    )

    assert first.passed is False
    assert adapter.repair_source(content, "pkg/config.py", first.diagnostics) is None


def test_python_parameterized_call_to_local_class_without_constructor_is_rejected():
    adapter = PythonLanguageAdapter()
    content = (
        "class Record:\n"
        "    value = None\n"
        "\n"
        "record = Record(value='saved')\n"
    )

    result = validate_candidate(
        adapter, "pkg/service.py", content, ContractDeclaration(), {}
    )

    assert result.passed is False
    assert result.diagnostics == (
        "Python local classes do not accept the supplied constructor arguments: Record",
    )


def test_python_local_class_constructor_diagnostic_allows_dynamic_constructors():
    adapter = PythonLanguageAdapter()
    samples = (
        "class Record(Base):\n    pass\n\nrecord = Record(value='saved')\n",
        "@decorate\nclass Record:\n    pass\n\nrecord = Record(value='saved')\n",
        (
            "class Record:\n"
            "    def __init__(self, value):\n"
            "        self.value = value\n"
            "\n"
            "record = Record(value='saved')\n"
        ),
    )

    for content in samples:
        assert adapter._incompatible_local_constructor_calls(ast.parse(content)) == ()


def test_python_undefined_name_is_imported_from_unique_existing_provider():
    adapter = PythonLanguageAdapter()
    content = "from pathlib import Path\n\nROOT = Path(PurePath('.'))\n"

    first = validate_candidate(
        adapter, "pkg/config.py", content, ContractDeclaration(), {}
    )
    repaired_content = adapter.repair_source(
        content, "pkg/config.py", first.diagnostics
    )

    assert first.diagnostics == ("Python module uses undefined global names: PurePath",)
    assert repaired_content == (
        "from pathlib import Path, PurePath\n\nROOT = Path(PurePath('.'))\n"
    )
    assert validate_candidate(
        adapter, "pkg/config.py", repaired_content, ContractDeclaration(), {}
    ).passed is True


def test_python_undefined_name_with_ambiguous_existing_providers_is_not_repaired(
    monkeypatch,
):
    adapter = PythonLanguageAdapter()
    content = (
        "from package_a import First\n"
        "from package_b import Second\n\n"
        "value = Shared()\n"
    )
    monkeypatch.setattr(
        adapter,
        "_static_module_exports",
        lambda module: frozenset({"First", "Shared"})
        if module == "package_a"
        else frozenset({"Second", "Shared"}),
    )

    assert adapter._add_uniquely_available_imports(content, "pkg/service.py") == content


def test_generic_gate_source_contains_no_fixture_or_stack_constants():
    source = inspect.getsource(declarative_contracts).lower()

    for forbidden in (
        "fastapi",
        "spring",
        "express",
        "todo",
        "main.py",
        "/health",
    ):
        assert forbidden not in source
