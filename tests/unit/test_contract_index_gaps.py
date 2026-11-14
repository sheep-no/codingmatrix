"""contract_index 显式契约、摘要校验与异常输入补测。"""

import pytest

from app.agent.contract_index import ContractEntry, ContractIndex


def test_digest_tampering_rejected():
    index = ContractIndex.build([{"name": "a", "kind": "api", "owner": "x"}])

    with pytest.raises(ValueError, match="digest"):
        ContractIndex(version=1, entries=index.entries, digest="0" * 64)


def test_missing_contracts():
    index = ContractIndex.build([{"name": "a", "kind": "api", "owner": "x"}])
    assert index.missing(["a", "b", "b"]) == ("b",)


def test_explicit_entries_accept_contract_entry_objects():
    index = ContractIndex.from_generation_plan(
        None,
        contracts={"entries": [{"name": "x", "kind": "k", "owner": "o"}]},
    )
    assert index.get("x") is not None


def test_explicit_contract_index_is_reused():
    base = ContractIndex.build([{"name": "x", "kind": "k", "owner": "o"}])
    index = ContractIndex.from_generation_plan(None, contracts=base)
    assert index.get("x").owner == "o"


def test_explicit_contracts_reject_non_mapping():
    with pytest.raises(ValueError, match="mapping"):
        ContractIndex.from_generation_plan(None, contracts=["bad"])


def test_explicit_entries_must_be_sequence():
    with pytest.raises(ValueError, match="sequence"):
        ContractIndex.from_generation_plan(None, contracts={"entries": "nope"})


def test_explicit_entries_are_validated():
    index = ContractIndex.from_generation_plan(
        None,
        contracts={"entries": [{"name": "a", "kind": "api", "owner": "o"}]},
    )
    assert tuple(entry.name for entry in index.entries) == ("a",)


def test_routes_mapping_values_are_projected():
    index = ContractIndex.from_generation_plan(
        None,
        contracts={"routes": {"first": {"method": "get", "path": "/x", "operation_id": "read"}}},
    )
    entry = index.entries[0]
    assert entry.name == "read"
    assert entry.schema["method"] == "get"


def test_non_sequence_route_collection_skipped():
    index = ContractIndex.from_generation_plan(None, contracts={"routes": "not-a-list"})
    assert index.entries == ()


def test_non_mapping_route_skipped():
    index = ContractIndex.from_generation_plan(None, contracts={"routes": ["bad", {"method": "GET", "path": "/ok"}]})
    assert len(index.entries) == 1


def test_route_name_falls_back_to_method_and_path():
    index = ContractIndex.from_generation_plan(
        None, contracts={"routes": [{"method": "GET", "route": "/health"}]}
    )
    assert index.entries[0].name == "GET /health"


def test_route_name_falls_back_to_collection_position():
    index = ContractIndex.from_generation_plan(
        None, contracts={"endpoints": [{}]}
    )
    assert index.entries[0].name == "endpoints:0"


def test_route_owner_from_contracts_mapping():
    index = ContractIndex.from_generation_plan(
        None,
        contracts={"owner": "team", "routes": [{"method": "GET", "path": "/a"}]},
    )
    assert index.entries[0].owner == "team"


def test_contract_entry_build_from_mapping_and_object():
    entry = ContractEntry(name="a", kind="api", owner="o")
    index = ContractIndex.build([entry, {"name": "b", "kind": "data", "owner": "o"}])
    assert tuple(item.name for item in index.entries) == ("a", "b")


def test_from_generation_plan_skips_file_without_contract():
    class _Plan:
        version = 2
        interfaces = None
        files = [type("F", (), {"path": "a.py", "contract": {}, "file_type": "code"})()]

    index = ContractIndex.from_generation_plan(_Plan())
    assert index.entries == ()
    assert index.version == 2


def test_file_contract_falls_back_to_file_type_and_path():
    class _Plan:
        version = 1
        interfaces = None
        files = [type(
            "F", (),
            {"path": "a.py", "file_type": "entry", "contract": {"exports": ["x"]}},
        )()]

    entry = ContractIndex.from_generation_plan(_Plan()).entries[0]
    assert entry.name == "file:a.py"
    assert entry.kind == "entry"
    assert entry.owner == "a.py"


def test_file_contract_version_is_honoured():
    class _Plan:
        version = 1
        interfaces = None
        files = [type(
            "F", (),
            {"path": "a.py", "file_type": "code", "contract": {"name": "n", "version": 3}},
        )()]

    entry = ContractIndex.from_generation_plan(_Plan()).entries[0]
    assert entry.version == 3


def test_duplicate_file_and_route_names_keep_first():
    class _Plan:
        version = 1
        interfaces = None
        files = [type(
            "F", (),
            {"path": "a.py", "file_type": "code", "contract": {"name": "dup"}},
        )()]

    index = ContractIndex.from_generation_plan(
        _Plan(), contracts={"routes": [{"name": "dup", "method": "GET", "path": "/x"}]}
    )
    assert tuple(entry.name for entry in index.entries) == ("dup",)
    assert index.entries[0].owner == "a.py"


def test_interface_entries_with_public_symbols():
    from app.agent.interface_registry import InterfaceVisibility

    class _Visibility:
        value = "public"
        __class__ = InterfaceVisibility

    class _Symbol:
        name = "public_symbol"
        parameters = ("a",)
        return_type = "int"
        is_async = False
        visibility = InterfaceVisibility.PUBLIC

    class _Interface:
        owner = "src/a.py"
        module = "src.a"
        symbols = (_Symbol(),)

    class _Interfaces:
        entries = (_Interface(),)

    class _Plan:
        version = 1
        interfaces = _Interfaces()
        files = ()

    entry = ContractIndex.from_generation_plan(_Plan()).entries[0]
    assert entry.kind == "interface"
    assert entry.schema["parameters"] == ["a"]
