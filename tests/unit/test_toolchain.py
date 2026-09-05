import pytest

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner, detect_toolchain


def test_toolchain_detects_parameterized_python_commands(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    plan = detect_toolchain(tmp_path)

    assert plan.status == "detected"
    assert plan.for_action(ToolchainAction.TEST).command == ("python3", "-m", "pytest")
    assert plan.for_action(ToolchainAction.TEST).shell is False


@pytest.mark.parametrize("command", [("bash", "run.sh"), ("npm", "test", "&&", "npm", "build")])
def test_toolchain_rejects_shell_execution(command):
    with pytest.raises(ValueError):
        CommandSpec(action=ToolchainAction.TEST, command=command)


def test_toolchain_rejects_shell_flag():
    with pytest.raises(ValueError, match="shell=false"):
        CommandSpec(action=ToolchainAction.TEST, command=("npm", "test"), shell=True)


@pytest.mark.asyncio
async def test_toolchain_workspace_wrapper_must_exist(tmp_path):
    spec = CommandSpec(action=ToolchainAction.BUILD, command=("./gradlew", "build"))

    with pytest.raises(FileNotFoundError, match="wrapper not found"):
        await ToolchainRunner().run(spec, tmp_path)


def test_toolchain_marks_unknown_workspace_unsupported(tmp_path):
    assert detect_toolchain(tmp_path).status == "unsupported"


@pytest.mark.asyncio
async def test_toolchain_runner_executes_parameter_array_without_shell(tmp_path):
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "print('signature')"),
        timeout_seconds=5,
    )

    result = await ToolchainRunner().run(spec, tmp_path)

    assert result == (0, "signature\n", "")


@pytest.mark.asyncio
async def test_toolchain_runner_rejects_unallowlisted_executable(tmp_path):
    spec = CommandSpec(action=ToolchainAction.INSPECT, command=("rm", "-f", "data"))

    with pytest.raises(ValueError, match="allowlisted"):
        await ToolchainRunner().run(spec, tmp_path)


@pytest.mark.asyncio
async def test_toolchain_runner_limits_output_while_process_is_running(tmp_path):
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "print('x' * 10000)"),
        timeout_seconds=5,
    )

    returncode, stdout, stderr = await ToolchainRunner(output_limit=32).run(spec, tmp_path)

    assert returncode == 0
    assert len(stdout.encode()) == 32
    assert stderr == ""


def test_toolchain_uses_project_install_for_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    plan = detect_toolchain(tmp_path)

    assert plan.for_action(ToolchainAction.INSTALL).command == ("python3", "-m", "pip", "install", ".")


def test_toolchain_detects_node_scripts_and_lockfile(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"lint":"eslint .","typecheck":"tsc","build":"vite build","test":"vitest run","dev":"vite"}}',
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    plan = detect_toolchain(tmp_path)

    assert plan.for_action(ToolchainAction.INSTALL).command == ("npm", "ci")
    assert plan.for_action(ToolchainAction.LINT).command == ("npm", "run", "lint")
    assert plan.for_action(ToolchainAction.TYPECHECK).command == ("npm", "run", "typecheck")
    assert plan.for_action(ToolchainAction.BUILD).command == ("npm", "run", "build")
    assert plan.for_action(ToolchainAction.START).command == ("npm", "run", "dev")


@pytest.mark.parametrize(
    ("manifest", "action", "command"),
    [
        ("go.mod", ToolchainAction.LINT, ("go", "vet", "./...")),
        ("Cargo.toml", ToolchainAction.TYPECHECK, ("cargo", "check")),
        ("pom.xml", ToolchainAction.BUILD, ("mvn", "-q", "-DskipTests", "package")),
        ("build.gradle", ToolchainAction.TEST, ("gradle", "test")),
    ],
)
def test_toolchain_detects_compiled_language_manifests(tmp_path, manifest, action, command):
    (tmp_path / manifest).write_text("", encoding="utf-8")

    assert detect_toolchain(tmp_path).for_action(action).command == command


def test_toolchain_rejects_invalid_package_manifest(tmp_path):
    (tmp_path / "package.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain an object"):
        detect_toolchain(tmp_path)
