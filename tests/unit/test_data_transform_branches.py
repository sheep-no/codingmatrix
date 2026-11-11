"""DataTransformNode 全操作分支测试。"""

import pytest

from app.utils.workflow.node_types.data_transform import DataTransformNode


def _node(params=None):
    return DataTransformNode("n1", params or {})


class TestParams:
    def test_required_and_optional_params(self):
        node = _node()
        assert node.get_required_params() == ["operation", "input_variable"]
        assert node.get_optional_params() == {
            "output_variable": "transform_result",
            "config": {},
        }

    def test_validate_reports_missing_operation_and_input(self):
        errors = _node().validate_params()
        assert "Missing required parameter: operation" in errors
        assert "Missing required parameter: input_variable" in errors

    def test_validate_reports_unsupported_operation(self):
        node = _node({"operation": "nope", "input_variable": "x"})
        errors = node.validate_params()
        assert len(errors) == 1
        assert "Unsupported operation: nope" in errors[0]

    def test_validate_accepts_supported_operation(self):
        assert _node({"operation": "map", "input_variable": "x"}).validate_params() == []


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_variable_returns_error(self):
        node = _node({"operation": "map", "input_variable": "missing"})
        result = await node.execute({})

        assert result.success is False
        assert "Variable 'missing' not found in context" in result.error

    @pytest.mark.asyncio
    async def test_success_result_contains_operation_and_output_variable(self):
        node = _node(
            {
                "operation": "pick",
                "input_variable": "data",
                "output_variable": "out",
                "config": {"fields": ["a", "b"]},
            }
        )
        result = await node.execute({"data": {"a": 1, "b": 2}})

        assert result.success is True
        assert result.data["result"] == {"a": 1, "b": 2}
        assert result.data["output_variable"] == "out"
        assert result.data["operation"] == "pick"
        assert result.metadata == {"operation": "pick", "output_variable": "out"}

    @pytest.mark.asyncio
    async def test_non_container_result_skips_len_in_log(self):
        node = _node({"operation": "reduce", "input_variable": "data"})
        result = await node.execute({"data": [1, 2]})

        assert result.success is True
        assert result.data["result"] == 3

    @pytest.mark.asyncio
    async def test_operation_failure_is_wrapped(self):
        node = _node({"operation": "map", "input_variable": "data"})
        result = await node.execute({"data": "not-a-list"})

        assert result.success is False
        assert result.error.startswith("Data transform failed:")

    @pytest.mark.asyncio
    async def test_unknown_operation_is_wrapped(self):
        node = _node({"operation": "bogus", "input_variable": "data"})
        result = await node.execute({"data": 1})

        assert result.success is False
        assert "Unsupported operation: bogus" in result.error


class TestMapAndFilter:
    def test_map_requires_list(self):
        with pytest.raises(ValueError, match="map requires list input"):
            _node()._apply_operation("map", {}, {})

    def test_map_index_variable(self):
        assert _node()._apply_operation("map", [10, 20], {"expression": "index"}) == [0, 1]
        assert _node()._apply_operation("map", [10, 20], {"expression": "i + item"}) == [10, 21]

    def test_map_rejects_forbidden_keywords(self):
        for forbidden in ("import os", "__class__", "eval(x)", "exec(x)", "open(x)", "os.system"):
            with pytest.raises(ValueError, match="Forbidden keyword"):
                _node()._apply_operation("map", [1], {"expression": forbidden})

    def test_map_wraps_expression_errors(self):
        with pytest.raises(ValueError, match="Expression error"):
            _node()._apply_operation("map", [object()], {"expression": "item + 1"})

    def test_filter_requires_list(self):
        with pytest.raises(ValueError, match="filter requires list input"):
            _node()._apply_operation("filter", {}, {})

    def test_filter_default_keeps_all(self):
        assert _node()._apply_operation("filter", [1, 2], {}) == [1, 2]


class TestReduce:
    def test_reduce_requires_list(self):
        with pytest.raises(ValueError, match="reduce requires list input"):
            _node()._apply_operation("reduce", {}, {})

    def test_reduce_with_initial_and_expression(self):
        result = _node()._apply_operation(
            "reduce", [1, 2, 3], {"initial": 5, "expression": "acc * item"}
        )
        assert result == 30

    def test_safe_reduce_rejects_disallowed_ast(self):
        with pytest.raises(ValueError, match="不允许的表达式元素"):
            _node()._safe_eval_reduce("acc + item if item else 0", {"acc": 0, "item": 1})

    def test_safe_reduce_supports_unary_ops(self):
        assert _node()._safe_eval_reduce("-acc + +item", {"acc": 1, "item": 2}) == 1


class TestPickAndRename:
    def test_pick_dict(self):
        assert _node()._apply_operation("pick", {"a": 1, "b": 2}, {"fields": ["a"]}) == {"a": 1}

    def test_pick_list_ignores_non_dict_items(self):
        data = [{"a": 1}, "text", {"a": 2, "b": 3}]
        result = _node()._apply_operation("pick", data, {"fields": ["a"]})
        assert result == [{"a": 1}, {"a": 2}]

    def test_pick_rejects_scalar(self):
        with pytest.raises(ValueError, match="pick requires dict or list input"):
            _node()._apply_operation("pick", "text", {"fields": ["a"]})

    def test_rename_moves_existing_keys(self):
        result = _node()._apply_operation(
            "rename", {"a": 1}, {"mapping": {"a": "b", "missing": "c"}}
        )
        assert result == {"b": 1}

    def test_rename_rejects_non_dict(self):
        with pytest.raises(ValueError, match="rename requires dict input"):
            _node()._apply_operation("rename", [], {})


class TestMergeAndTemplate:
    def test_merge_context_preferred_over_config(self):
        result = _node()._apply_operation(
            "merge",
            {"base": 1},
            {"variables": ["a", "b"], "a": {"from": "config"}},
            {"a": {"from": "context"}},
        )
        # 变量值是参与合并的对象，其键直接并入结果
        assert result == {"base": 1, "from": "context"}

    def test_merge_falls_back_to_config_and_skips_non_dict(self):
        result = _node()._apply_operation(
            "merge",
            "not-a-dict",
            {"variables": ["a", "b"], "a": {"from": "config"}, "b": [1, 2]},
            {},
        )
        assert result == {"from": "config"}

    def test_merge_without_context(self):
        result = _node()._apply_operation("merge", {"x": 1}, {"variables": ["y"], "y": {"z": 2}})
        assert result == {"x": 1, "z": 2}

    def test_template_replaces_placeholders(self):
        result = _node()._apply_operation(
            "template",
            {"name": "Ada", "age": 36},
            {"template": "{name} is {age}"},
        )
        assert result == "Ada is 36"

    def test_template_defaults_to_stringified_data(self):
        result = _node()._apply_operation("template", {"name": "Ada"}, {})
        assert "Ada" in result

    def test_template_with_non_dict_data_skips_substitution(self):
        result = _node()._apply_operation(
            "template", "plain", {"template": "value {name}"}
        )
        assert result == "value {name}"


class TestJsonPath:
    def test_empty_path_returns_data(self):
        assert _node()._apply_operation("jsonpath", {"a": 1}, {}) == {"a": 1}

    def test_nested_dict_and_list_index(self):
        data = {"users": [{"name": "a"}, {"name": "b"}]}
        assert _node()._apply_operation(
            "jsonpath", data, {"path": ".users.1.name"}
        ) == "b"

    def test_list_projection_when_part_is_not_int(self):
        data = [{"name": "a"}, "text", {"name": "b"}]
        assert _node()._apply_operation(
            "jsonpath", data, {"path": "name"}
        ) == ["a", None, "b"]

    def test_out_of_range_index_returns_none(self):
        assert _node()._apply_operation("jsonpath", [1], {"path": "5"}) is None
        assert _node()._apply_operation("jsonpath", [1], {"path": "-1"}) is None

    def test_missing_key_and_none_traversal(self):
        assert _node()._apply_operation("jsonpath", {"a": None}, {"path": "a.b"}) is None
        assert _node()._apply_operation("jsonpath", {"a": 1}, {"path": "b.c"}) is None

    def test_scalar_traversal_returns_none(self):
        assert _node()._apply_operation("jsonpath", 5, {"path": "a"}) is None


class TestSortSliceFlattenUnique:
    def test_sort_requires_list(self):
        with pytest.raises(ValueError, match="sort requires list input"):
            _node()._apply_operation("sort", {}, {})

    def test_sort_by_key_dicts_and_reverse(self):
        data = [{"k": 2}, {"k": 1}]
        assert _node()._apply_operation("sort", data, {"key": "k"}) == [{"k": 1}, {"k": 2}]
        assert _node()._apply_operation("sort", data, {"key": "k", "reverse": True}) == [
            {"k": 2},
            {"k": 1},
        ]

    def test_sort_mixed_scalars_without_key(self):
        assert _node()._apply_operation("sort", [3, 1, 2], {}) == [1, 2, 3]
        assert _node()._apply_operation("sort", [1, 3, 2], {"reverse": True}) == [3, 2, 1]

    def test_sort_key_dict_missing_field_defaults_zero(self):
        data = [{"k": 1}, {}]
        assert _node()._apply_operation("sort", data, {"key": "k"}) == [{}, {"k": 1}]

    def test_slice_requires_list(self):
        with pytest.raises(ValueError, match="slice requires list input"):
            _node()._apply_operation("slice", {}, {})

    def test_slice_start_end(self):
        assert _node()._apply_operation("slice", [1, 2, 3, 4], {"start": 1, "end": 3}) == [2, 3]
        assert _node()._apply_operation("slice", [1, 2, 3], {"start": 1}) == [2, 3]
        assert _node()._apply_operation("slice", [1, 2, 3], {}) == [1, 2, 3]

    def test_flatten_requires_list(self):
        with pytest.raises(ValueError, match="flatten requires list input"):
            _node()._apply_operation("flatten", {}, {})

    def test_flatten_nested_lists(self):
        assert _node()._apply_operation("flatten", [[1, 2], 3, [4]], {}) == [1, 2, 3, 4]

    def test_unique_requires_list(self):
        with pytest.raises(ValueError, match="unique requires list input"):
            _node()._apply_operation("unique", {}, {})

    def test_unique_by_key_handles_non_dict_items(self):
        data = [{"id": 1}, {"id": 1}, {"id": 2}, "x", "x"]
        assert _node()._apply_operation("unique", data, {"key": "id"}) == [
            {"id": 1},
            {"id": 2},
            "x",
        ]

    def test_unique_without_key_uses_fromkeys(self):
        assert _node()._apply_operation("unique", ["a", "a", "b", 1, 1], {}) == ["a", "b", 1]


class TestSafeEvalNodes:
    def test_safe_eval_allows_compare_and_bool_ops(self):
        node = _node()
        assert node._safe_eval("item > 1 and index < 5", {"item": 2, "index": 0}) is True
        assert node._safe_eval("item is not None", {"item": 1}) is True
        assert node._safe_eval("item in 'abc'", {"item": "a"}) is True
        assert node._safe_eval("item not in 'abc'", {"item": "z"}) is True

    def test_safe_eval_allows_arithmetic_and_unary(self):
        node = _node()
        assert node._safe_eval("(-item + +index) * 2", {"item": 1, "index": 3}) == 4

    def test_safe_eval_rejects_call_and_attribute(self):
        node = _node()
        for expression in ("item()", "item.x", "item[0]"):
            with pytest.raises(ValueError, match="不允许的表达式元素"):
                node._safe_eval(expression, {"item": 1})
