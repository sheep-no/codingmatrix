"""人工审批节点回归。

覆盖参数校验、无回调安全拒绝、回调返回各形态、超时默认选项。
历史缺陷：回调返回 dict 且不含 `option` 键时，`option` 被赋成整个 dict，
下游按字符串处理会拿到非预期结构。
"""

import asyncio

import pytest

from app.utils.workflow.node_types.human_approval import HumanApprovalNode


def _node(**params):
    base = {"prompt": "confirm?"}
    base.update(params)
    return HumanApprovalNode("approval-1", base)


def test_validate_params_requires_prompt():
    node = HumanApprovalNode("n", {})
    assert node.validate_params() == ["Missing required parameter: prompt"]


def test_validate_params_prompt_type():
    node = HumanApprovalNode("n", {"prompt": 123})
    assert "Parameter 'prompt' must be a string" in node.validate_params()


@pytest.mark.parametrize("timeout", [0, 3601, "soon"])
def test_validate_params_rejects_bad_timeout(timeout):
    node = _node(timeout=timeout)
    errors = node.validate_params()
    assert any("timeout" in error for error in errors)


def test_validate_params_rejects_short_options():
    node = _node(options=["only-one"])
    assert "Parameter 'options' must be a list with at least 2 items" in node.validate_params()


def test_validate_params_accepts_defaults():
    assert _node().validate_params() == []


def test_optional_and_required_param_declarations():
    node = _node()
    assert node.get_required_params() == ["prompt"]
    assert node.get_optional_params()["output_variable"] == "approval_result"


def test_validate_params_rejects_non_list_options():
    node = _node(options="approve")
    assert "Parameter 'options' must be a list with at least 2 items" in node.validate_params()


@pytest.mark.asyncio
async def test_no_callback_auto_rejects():
    result = await _node().execute({})

    assert result.success
    assert result.data["approved"] is False
    assert result.data["option"] == "auto_reject"
    assert result.metadata["auto"] is True


@pytest.mark.asyncio
async def test_callback_string_approve():
    async def callback(_info):
        return "approve"

    node = _node()
    node.set_approval_callback(callback)
    result = await node.execute({})

    assert result.data["approved"] is True
    assert result.data["option"] == "approve"


@pytest.mark.asyncio
async def test_callback_dict_without_option_falls_back_to_string():
    """回归：缺失 option 时不得把整个 dict 当作选项。"""

    async def callback(_info):
        return {"approved": True}

    node = _node()
    node.set_approval_callback(callback)
    result = await node.execute({})

    assert result.data["approved"] is True
    assert isinstance(result.data["option"], str)
    assert result.data["option"] == "approve"


@pytest.mark.asyncio
async def test_callback_dict_with_option():
    async def callback(_info):
        return {"approved": True, "option": "approve"}

    node = _node()
    node.set_approval_callback(callback)
    result = await node.execute({})

    assert result.data["option"] == "approve"


@pytest.mark.asyncio
async def test_callback_none_uses_default_option():
    async def callback(_info):
        return None

    node = _node(default_option="approve")
    node.set_approval_callback(callback)
    result = await node.execute({})

    assert result.data["option"] == "approve"
    assert result.data["approved"] is True


@pytest.mark.asyncio
async def test_timeout_uses_default_option():
    async def callback(_info):
        await asyncio.sleep(5)
        return "approve"

    node = _node(timeout=0.01)
    node.set_approval_callback(callback)
    result = await node.execute({})

    assert result.data["timeout"] is True
    assert result.data["option"] == "reject"
    assert result.data["approved"] is False


@pytest.mark.asyncio
async def test_input_variable_is_forwarded():
    captured = {}

    async def callback(info):
        captured.update(info)
        return "approve"

    node = _node(input_variable="file_path", output_variable="decision")
    node.set_approval_callback(callback)
    result = await node.execute({"file_path": "/tmp/x.py"})

    assert captured["context_data"] == "/tmp/x.py"
    assert captured["node_id"] == "approval-1"
    assert result.data["output_variable"] == "decision"
