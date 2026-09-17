from app.agent.adapters.python import PythonLanguageAdapter
from app.agent.change_plan import ChangePlan, collapse_change_items, expand_change_plan_for_missing_exports
from app.agent.project_snapshot import ProjectSnapshot


def test_collapse_change_items_merges_duplicate_modify_paths():
    collapsed = collapse_change_items(
        [
            {"action": "modify", "path": "calc.py", "reason": "implement subtract"},
            {"action": "modify", "path": "main.py", "reason": "fix parenthesis"},
            {"action": "modify", "path": "calc.py", "reason": "add multiply"},
        ],
        known_paths={"calc.py", "main.py"},
    )

    assert [item["path"] for item in collapsed] == ["calc.py", "main.py"]
    assert collapsed[0]["action"] == "modify"
    assert "subtract" in collapsed[0]["reason"]
    assert "multiply" in collapsed[0]["reason"]


def test_change_plan_build_accepts_duplicate_paths(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(add(1, 2)\n", encoding="utf-8")
    snapshot = ProjectSnapshot.scan(tmp_path, revision="r1")

    plan = ChangePlan.build(snapshot, [
        {"path": "calc.py", "action": "modify", "reason": "subtract"},
        {"path": "calc.py", "action": "modify", "reason": "multiply"},
        {"path": "main.py", "action": "modify", "reason": "syntax"},
    ])

    assert [item.path for item in plan.changes] == ["calc.py", "main.py"]
    assert "subtract" in plan.changes[0].reason
    assert "multiply" in plan.changes[0].reason


def test_collapse_add_and_modify_keeps_modify_for_existing_file():
    collapsed = collapse_change_items(
        [
            {"action": "add", "path": "calc.py", "reason": "create helper"},
            {"action": "modify", "path": "calc.py", "reason": "fill subtract"},
        ],
        known_paths={"calc.py"},
    )

    assert len(collapsed) == 1
    assert collapsed[0]["action"] == "modify"


def test_expand_change_plan_adds_provider_for_missing_export(tmp_path):
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from calc import add, subtract, multiply\nprint(add(1, 2)\n",
        encoding="utf-8",
    )

    expanded = expand_change_plan_for_missing_exports(
        [{"action": "modify", "path": "main.py", "reason": "fix parenthesis"}],
        output_dir=tmp_path,
        language_adapter=PythonLanguageAdapter(),
        known_files=["calc.py", "main.py"],
    )

    assert [item["path"] for item in expanded] == ["main.py", "calc.py"]
    calc = expanded[1]
    assert calc["action"] == "modify"
    assert "multiply" in calc["reason"]
    assert "main.py" in calc["reason"]


def test_expand_change_plan_merges_reason_into_existing_provider(tmp_path):
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from calc import add, subtract, multiply\nprint(add(1, 2)\n",
        encoding="utf-8",
    )

    expanded = expand_change_plan_for_missing_exports(
        [
            {"action": "modify", "path": "calc.py", "reason": "implement subtract"},
            {"action": "modify", "path": "main.py", "reason": "fix parenthesis"},
        ],
        output_dir=tmp_path,
        language_adapter=PythonLanguageAdapter(),
        known_files=["calc.py", "main.py"],
    )

    assert [item["path"] for item in expanded] == ["calc.py", "main.py"]
    assert "subtract" in expanded[0]["reason"]
    assert "multiply" in expanded[0]["reason"]


def test_expand_change_plan_skips_when_exports_exist(tmp_path):
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from calc import add\nprint(add(1, 2))\n",
        encoding="utf-8",
    )

    expanded = expand_change_plan_for_missing_exports(
        [{"action": "modify", "path": "main.py", "reason": "fix print"}],
        output_dir=tmp_path,
        language_adapter=PythonLanguageAdapter(),
        known_files=["calc.py", "main.py"],
    )

    assert [item["path"] for item in expanded] == ["main.py"]
