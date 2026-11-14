"""schema.codeRequest 模型校验器补测。"""

import sys
import types

import pytest
from pydantic import ValidationError

from app.schema import codeRequest as module
from app.schema.codeRequest import (
    AgentConfig,
    CodeRequest,
    FileAttachment,
    GenerateRequest,
    ToolDefinition,
)


def _valid_model():
    return module.ALLOWED_MODELS_LIST[0]


def test_generate_request_defaults_and_valid_model():
    req = GenerateRequest(requirement="build", session_id="abc-123")
    assert req.model == module.DEFAULT_REASONING_MODEL
    assert req.docker_cpu_limit == 2.0
    assert req.temperature == 0.7


def test_generate_request_rejects_unknown_model():
    with pytest.raises(ValidationError, match="model must be one of"):
        GenerateRequest(requirement="x", session_id="s", model="unknown-model")


@pytest.mark.parametrize("session_id", ["../evil", "a/b", "", "a" * 129, "has space"])
def test_generate_request_rejects_unsafe_session(session_id):
    with pytest.raises(ValidationError):
        GenerateRequest(requirement="x", session_id=session_id)


def test_generate_request_temperature_bounds():
    with pytest.raises(ValidationError):
        GenerateRequest(requirement="x", session_id="s", temperature=2.5)


def test_agent_config_rejects_unknown_model():
    with pytest.raises(ValidationError, match="model must be one of"):
        AgentConfig(model="nope")


def test_agent_config_clamps_temperature():
    assert AgentConfig(temperature=-5).temperature == 0.0
    assert AgentConfig(temperature=9).temperature == 2.0


def test_agent_config_rejects_bad_validation_level():
    with pytest.raises(ValidationError, match="validation_level must be"):
        AgentConfig(validation_level="loose")


@pytest.mark.parametrize("level", ["basic", "standard", "strict"])
def test_agent_config_accepts_validation_level(level):
    assert AgentConfig(validation_level=level).validation_level == level


def test_agent_config_docker_disabled_skips_probe():
    assert AgentConfig(enable_docker_validation=False).enable_docker_validation is False


def test_agent_config_docker_probe_failure_disables(monkeypatch):
    fake_docker = types.ModuleType("docker")

    class Client:
        def ping(self):
            raise RuntimeError("no daemon")

    fake_docker.from_env = lambda: Client()
    monkeypatch.setitem(sys.modules, "docker", fake_docker)

    assert AgentConfig(enable_docker_validation=True).enable_docker_validation is False


def test_agent_config_docker_probe_success_keeps(monkeypatch):
    fake_docker = types.ModuleType("docker")

    class Client:
        def ping(self):
            return True

    fake_docker.from_env = lambda: Client()
    monkeypatch.setitem(sys.modules, "docker", fake_docker)

    assert AgentConfig(enable_docker_validation=True).enable_docker_validation is True


def test_file_attachment_defaults():
    attachment = FileAttachment(server_path="/tmp/a.pdf")
    assert attachment.category == "document"
    assert attachment.name is None


def test_code_request_defaults():
    req = CodeRequest(prompt="hi")
    assert req.stream is False
    assert req.search_mode == "auto"
    assert req.search_count == 5


def test_code_request_rejects_empty_prompt():
    with pytest.raises(ValidationError):
        CodeRequest(prompt="")


def test_code_request_search_count_bounds():
    with pytest.raises(ValidationError):
        CodeRequest(prompt="x", search_count=0)
    with pytest.raises(ValidationError):
        CodeRequest(prompt="x", search_count=21)


def test_tool_definition_allows_arbitrary_func():
    def f():
        return 1

    tool = ToolDefinition(name="t", func=f, description="d", parameters={})
    assert tool.func is f


def test_generate_request_valid_explicit_model_returns_value():
    req = GenerateRequest(requirement="x", session_id="s", model=_valid_model())
    assert req.model == _valid_model()


def test_agent_config_valid_explicit_model_returns_value():
    config = AgentConfig(model=_valid_model())
    assert config.model == _valid_model()
