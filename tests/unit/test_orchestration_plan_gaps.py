"""补齐 plan.py 的校验与归一化边界分支。"""

import pytest
from pydantic import ValidationError

from app.agent.orchestration.plan import (
    FilePlanValidationError,
    GenerationPlan,
    PlanFileOrigin,
    PlanPolicy,
    PlannedFile,
    _normalize_priority,
    build_file_plan,
    normalize_plan_path,
)


class _BadInt:
    def __int__(self):
        raise TypeError("not an int")


class TestGenerationPlanValidators:
    @staticmethod
    def _file(path):
        return PlannedFile(path=path)

    def test_duplicate_planned_paths_rejected(self):
        with pytest.raises(ValidationError, match="must be unique"):
            GenerationPlan(
                version=1,
                policy=PlanPolicy.EXTENSIBLE,
                requested_paths=(),
                files=(self._file("a.py"), self._file("a.py")),
                digest="0" * 64,
            )

    def test_duplicate_requested_paths_rejected(self):
        with pytest.raises(ValidationError, match="requested_paths must be unique"):
            GenerationPlan(
                version=1,
                policy=PlanPolicy.EXTENSIBLE,
                requested_paths=("a.py", "a.py"),
                files=(),
                digest="0" * 64,
            )

    def test_strict_scope_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="strict plan files must equal"):
            GenerationPlan(
                version=1,
                policy=PlanPolicy.STRICT,
                requested_paths=("a.py",),
                files=(self._file("b.py"),),
                digest="0" * 64,
            )

    def test_missing_dependency_rejected(self):
        file = PlannedFile(path="a.py", dependencies=("b.py",))
        with pytest.raises(ValidationError, match="missing dependencies"):
            GenerationPlan(
                version=1,
                policy=PlanPolicy.EXTENSIBLE,
                requested_paths=(),
                files=(file,),
                digest="0" * 64,
            )


class TestPriorityAndPathNormalization:
    def test_non_numeric_priority_falls_back(self):
        assert _normalize_priority(_BadInt()) == 3

    def test_numeric_string_priority_is_clamped(self):
        assert _normalize_priority("9") == 5
        assert _normalize_priority("0") == 1

    def test_non_string_path_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            normalize_plan_path(123)

    def test_null_byte_rejected(self):
        with pytest.raises(ValueError, match="null byte"):
            normalize_plan_path("src/a\x00.py")

    @pytest.mark.parametrize("path", ["src/a,b.py", "src/a;b.py"])
    def test_unsupported_separator_rejected(self, path):
        with pytest.raises(ValueError, match="unsupported separator"):
            normalize_plan_path(path)

    @pytest.mark.parametrize("path", ["./", ".//.", "   "])
    def test_path_without_parts_rejected(self, path):
        with pytest.raises(ValueError):
            normalize_plan_path(path)


class TestBuildFilePlanIssues:
    def _codes(self, entries, **kwargs):
        with pytest.raises(FilePlanValidationError) as raised:
            build_file_plan(entries, **kwargs)
        return {issue.code for issue in raised.value.issues}

    def test_non_mapping_entry(self):
        assert "plan.invalid_file" in self._codes(["not-a-mapping"])

    def test_invalid_path_entry(self):
        assert "plan.invalid_path" in self._codes([{"path": "../escape.py"}])

    def test_none_dependencies(self):
        codes = self._codes([{"path": "a.py", "dependencies": None}])
        assert "plan.invalid_dependencies" in codes

    def test_string_dependencies_and_contract_refs(self):
        plan = build_file_plan(
            [
                {"path": "a.py", "dependencies": "b.py", "contract_refs": "api:v1"},
                {"path": "b.py"},
            ]
        )

        assert plan.files[0].dependencies == ("b.py",)
        assert plan.files[0].contract_refs == ("api:v1",)

    def test_none_contract_becomes_empty_mapping(self):
        plan = build_file_plan([{"path": "a.py", "contract": None}])

        assert dict(plan.files[0].contract) == {}

    def test_non_mapping_contract_rejected(self):
        assert "plan.invalid_file" in self._codes([{"path": "a.py", "contract": [1, 2]}])

    def test_invalid_extension_provenance_rejected(self):
        assert "plan.invalid_file" in self._codes(
            [{"path": "a.py", "origin": PlanFileOrigin.EXTENSION.value}]
        )

    def test_empty_plan_rejected(self):
        assert "plan.empty" in self._codes([])

    def test_empty_plan_allowed(self):
        plan = build_file_plan([], allow_empty=True)

        assert plan.files == ()

    def test_invalid_requested_path(self):
        assert "plan.invalid_requested_path" in self._codes([], requested_paths=["/abs.py"])

    def test_duplicate_requested_path(self):
        assert "plan.duplicate_requested_path" in self._codes(
            [{"path": "a.py"}], requested_paths=["a.py", "./a.py"]
        )

    def test_empty_requested_scope(self):
        assert "plan.empty_requested_scope" in self._codes([], requested_paths=[])

    def test_empty_requested_scope_allowed(self):
        plan = build_file_plan([], requested_paths=[], allow_empty=True)

        assert plan.requested_paths == ()


class TestDependencyNormalization:
    def _codes(self, entries):
        with pytest.raises(FilePlanValidationError) as raised:
            build_file_plan(entries)
        return {issue.code for issue in raised.value.issues}

    def test_invalid_dependency_path(self):
        assert "plan.invalid_dependency_path" in self._codes(
            [{"path": "a.py", "dependencies": ["/abs.py"]}]
        )

    def test_self_dependency(self):
        assert "plan.self_dependency" in self._codes(
            [{"path": "a.py", "dependencies": ["./a.py"]}]
        )

    def test_duplicate_dependencies_collapsed(self):
        plan = build_file_plan(
            [
                {"path": "a.py", "depends_on": ["./b.py", "b.py"]},
                {"path": "b.py"},
            ]
        )

        assert plan.files[0].dependencies == ("b.py",)
