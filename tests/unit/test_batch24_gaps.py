"""Batch 24 coverage gaps: request schemas, parsers, workflow IR and layout."""

from pathlib import Path

import pytest
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from app.agent.declarative_contracts import (
    ArtifactFacts,
    FactSet,
    SymbolContract,
    _dependency_diagnostics,
)
from app.agent.error_classifier import ErrorClassifier
from app.agent.framework_detector import FrameworkDetector
from app.agent.orchestrator_generation import error_recovery as er_module
from app.agent.orchestrator_generation.error_recovery import ErrorRecoveryMixin
from app.agent.output_parser import (
    CppTestParser,
    GenericTextParser,
    JUnitXMLParser,
    JestJSONParser,
    PytestXMLParser,
    RustTestParser,
)
from app.agent.workflow_ir import WorkflowIR, WorkflowNode, WorkflowNodeKind
from app.agent.orchestration.budget import ExecutionBudget
from app.api.v1.ai_agent.schemas import (
    OrchestratorRequest,
    OrchestratorResponse,
    validate_path_safety,
    validate_session_id,
)
from app.utils.visual.layout_decider import LayoutDecider, LayoutElement, LayoutType, SlideLayoutPlan
from app.utils.visual.visual_analyzer import (
    ImageDecision,
    ImagePosition,
    ImageType,
    SlideVisualDecision,
)


def _budget():
    return ExecutionBudget(
        task_seconds=60, stage_seconds=30, file_seconds=20, model_call_seconds=10
    )


def _node(node_id, *, depends_on=()):
    return WorkflowNode(
        node_id=node_id,
        kind=WorkflowNodeKind.GENERATE,
        handler_ref="orchestration.generate",
        depends_on=depends_on,
    )


def test_session_id_rejects_too_long_value():
    with pytest.raises(ValueError, match="128"):
        validate_session_id("a" * 129)


def test_path_safety_rejects_dot_components():
    with pytest.raises(ValueError, match="路径组件"):
        validate_path_safety("config..backup/file.py")


def test_path_safety_allows_none():
    assert validate_path_safety(None) is None


def test_orchestrator_request_rejects_invalid_project_name():
    with pytest.raises(ValueError):
        OrchestratorRequest(requirement="build", project_name="bad name")


def test_project_name_validator_rejects_oversized_value():
    # 字段级 max_length 会先于校验器拦截超长值，直接调用校验器验证防御分支。
    with pytest.raises(ValueError, match="50"):
        OrchestratorRequest.validate_project_name("a" * 51)


def test_orchestrator_request_rejects_blank_and_dense_requirement():
    with pytest.raises(ValueError):
        OrchestratorRequest(requirement="   ")
    with pytest.raises(ValueError):
        OrchestratorRequest(requirement="a\n\n\n\nb")


def test_orchestrator_response_serializes_dict_context_summary():
    response = OrchestratorResponse(
        success=True,
        output_dir="/tmp/x",
        total_files_created=0,
        files=[],
        validation={},
        errors=[],
        warnings=[],
        elapsed_time=1.0,
        context_summary={"b": 2, "a": 1},
    )
    assert response.context_summary == '{"a": 1, "b": 2}'


def test_orchestrator_response_keeps_string_context_summary():
    response = OrchestratorResponse(
        success=True,
        output_dir="/tmp/x",
        total_files_created=0,
        files=[],
        validation={},
        errors=[],
        warnings=[],
        elapsed_time=1.0,
        context_summary="already",
    )
    assert response.context_summary == "already"


def test_framework_detector_scans_all_workflow_files(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yaml").write_text("run: echo hi\n", encoding="utf-8")
    (workflows / "b.yml").write_text("run: mvn verify\n", encoding="utf-8")

    config = FrameworkDetector().detect(tmp_path)

    assert config is not None
    assert config.framework == "maven"


def test_framework_detector_exhausts_unmatched_workflows(tmp_path: Path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text("name: nothing\n", encoding="utf-8")

    config = FrameworkDetector().detect(tmp_path)
    assert config.framework == "pytest"


def test_framework_detector_survives_broken_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")

    config = FrameworkDetector().detect(tmp_path)
    assert config.framework == "pytest"


def test_framework_detector_detects_gradle_and_cmake(tmp_path: Path):
    (tmp_path / "build.gradle").write_text("plugins {}", encoding="utf-8")
    assert FrameworkDetector().detect(tmp_path).framework == "gradle"

    gradle_dir = tmp_path / "cmake_project"
    gradle_dir.mkdir()
    (gradle_dir / "CMakeLists.txt").write_text("project(x)", encoding="utf-8")
    assert FrameworkDetector().detect(gradle_dir).framework == "cmake"


@pytest.mark.asyncio
async def test_react_fix_that_stays_failing_raises(monkeypatch):
    from app.agent import react_agent as react_agent_module
    from app.agent import test_runner as test_runner_module

    from types import SimpleNamespace

    class _FakeAgent:
        def __init__(self, **kwargs):
            pass

        @staticmethod
        async def process(task, context):
            return SimpleNamespace(success=False)

    class _Runner:
        def __init__(self, output_dir):
            self.output_dir = output_dir

    monkeypatch.setattr(react_agent_module, "ReActAgent", _FakeAgent)
    monkeypatch.setattr(react_agent_module, "ReActResult", SimpleNamespace)
    monkeypatch.setattr(test_runner_module, "IsolatedTestRunner", _Runner)

    obj = ErrorRecoveryMixin()
    obj.error_recovery = object()
    obj.reviewer = object()
    obj.model_assignment = SimpleNamespace(backend_model="m")
    obj.output_dir = "/tmp/proj"
    obj.enable_error_recovery = True

    async def _run_dynamic_tests(runner):
        return {"success": False}

    obj._run_dynamic_tests = _run_dynamic_tests

    with pytest.raises(RuntimeError, match="did not repair"):
        await obj._try_react_auto_fix({"failed_tests": ["t"]})


def test_generic_parser_reports_empty_output():
    result = GenericTextParser().parse("   ")
    assert result.errors == ["测试输出为空"]


def test_generic_parser_reads_skipped_count():
    result = GenericTextParser().parse("3 passed, 1 failed, 2 skipped")
    assert result.skipped == 2


@pytest.mark.parametrize(
    ("raw_output", "expected"),
    [
        ("2 failed", {"passed": 0, "failed": 2}),
        ("5 passed", {"passed": 5, "failed": 0}),
    ],
)
def test_generic_parser_independent_counts(raw_output, expected):
    result = GenericTextParser().parse(raw_output)
    assert result.passed == expected["passed"]
    assert result.failed == expected["failed"]


def test_junit_parser_counts_failure_message_and_skipped_case():
    xml = (
        '<testsuite tests="2">'
        '<testcase name="a"><failure message="boom"/></testcase>'
        '<testcase name="b"><skipped/></testcase>'
        "</testsuite>"
    )
    result = JUnitXMLParser().parse(xml)
    assert result.failed == 1
    assert result.skipped == 1
    assert result.errors == ["boom"]


def test_junit_parser_failure_without_message_has_empty_error():
    xml = '<testsuite><testcase name="a"><failure/></testcase></testsuite>'
    result = JUnitXMLParser().parse(xml)
    assert result.failed == 1
    assert result.test_cases[0].error_message == ""


def test_pytest_parser_counts_errors_as_failures():
    result = PytestXMLParser().parse("2 passed, 1 failed, 3 errors in 1.2s")
    assert result.failed == 4


def test_jest_parser_collects_failed_suite_message():
    payload = (
        '{"numPassedTests": 0, "numFailedTests": 0,'
        ' "testResults": [{"status": "failed", "message": "suite exploded",'
        ' "assertionResults": []}]}'
    )
    result = JestJSONParser().parse(payload)
    assert result.errors == ["suite exploded"]


def test_jest_parser_ignores_unknown_assertion_status_and_empty_suite_message():
    payload = (
        '{"numPassedTests": 1, "numFailedTests": 0, "numPendingTests": 0,'
        ' "testResults": [{"status": "failed", "message": "",'
        ' "assertionResults": [{"status": "unknown", "fullName": "x"}]}]}'
    )
    result = JestJSONParser().parse(payload)
    assert result.errors == []


def test_jest_parser_handles_pending_assertions_from_top_level_counts():
    payload = (
        '{"testResults": [{"assertionResults": ['
        '{"status": "pending", "fullName": "a"},'
        '{"status": "passed", "fullName": "b"}]}]}'
    )
    result = JestJSONParser().parse(payload)
    assert result.skipped == 1
    assert result.passed == 1


def test_jest_parser_ignores_unknown_assertion_status_when_counting():
    payload = (
        '{"testResults": [{"assertionResults": ['
        '{"status": "unknown", "fullName": "a"},'
        '{"status": "failed", "fullName": "b"}]}]}'
    )
    result = JestJSONParser().parse(payload)
    assert result.failed == 1
    assert result.skipped == 0


def test_rust_parser_reads_ignored_only():
    result = RustTestParser().parse("1 ignored")
    assert result.skipped == 1
    assert result.passed == 0


def test_cpp_parser_handles_catch2_without_failures_and_gtest_failures():
    clean = CppTestParser().parse("test cases: 3 | 3 passed | 0 failed")
    assert clean.failed == 0
    assert clean.errors == []

    failures = CppTestParser().parse("[  FAILED  ] 2 tests.")
    assert failures.failed == 2
    assert failures.errors == ["[  FAILED  ] 2 tests."]


def test_cpp_parser_gtest_passed_without_any_failed_lines():
    result = CppTestParser().parse("[  PASSED  ] 1 test.\nRan 1 test.\n")
    assert result.passed == 1
    assert result.failed == 0
    assert result.errors == []


def test_error_classifier_accepts_non_numeric_confidence():
    classifier = ErrorClassifier()
    parsed = classifier._coerce_model_result(
        {
            "error_type": "Unknown",
            "error_subtype": "misc",
            "description": "d",
            "suggested_fix_strategy": "s",
            "confidence": "high",
        }
    )
    assert parsed is not None
    assert parsed.confidence == 0.5


def test_workflow_rejects_duplicate_nodes():
    with pytest.raises(ValueError, match="unique"):
        WorkflowIR.build(
            workflow_id="t",
            name="n",
            mode="generate",
            entry_node="plan",
            nodes=(_node("plan"), _node("plan")),
            budgets=_budget(),
        )


def test_workflow_rejects_missing_entry_and_self_dependency():
    with pytest.raises(ValueError, match="entry_node"):
        WorkflowIR.build(
            workflow_id="t",
            name="n",
            mode="generate",
            entry_node="missing",
            nodes=(_node("plan"),),
            budgets=_budget(),
        )
    with pytest.raises(ValueError, match="depend on itself"):
        WorkflowIR.build(
            workflow_id="t",
            name="n",
            mode="generate",
            entry_node="plan",
            nodes=(_node("plan", depends_on=("plan",)),),
            budgets=_budget(),
        )


def test_workflow_rejects_tampered_digest():
    workflow = WorkflowIR.build(
        workflow_id="t",
        name="n",
        mode="generate",
        entry_node="plan",
        nodes=(_node("plan"),),
        budgets=_budget(),
    )
    payload = workflow.model_dump()
    payload["digest"] = "0" * 64

    with pytest.raises(ValueError, match="digest"):
        WorkflowIR(**payload)


def test_artifact_facts_reject_duplicate_names():
    with pytest.raises(ValueError, match="unique"):
        ArtifactFacts(facts=(FactSet(name="exports"), FactSet(name="exports")))


def test_symbol_contract_rejects_duplicate_symbols():
    with pytest.raises(ValueError, match="unique"):
        SymbolContract(artifact="a.py", provides=("x", "x"))


class _Import:
    def __init__(self, module, *, relative=False, symbols=(), target=None):
        self.module = module
        self.is_relative = relative
        self.symbols = symbols
        self._target = target


class _Adapter:
    def __init__(self, import_info, *, target=None, self_target=None):
        self._import = import_info
        self._target = target
        self._self_target = self_target

    def parse_imports(self, content, file_path):
        return [self._import]

    def resolve_import_to_file(self, import_info, current_file):
        if self._self_target is not None and current_file == self._self_target:
            return [current_file]
        return [self._target] if self._target else []

    def is_project_module(self, module_name):
        return False

    def extract_contract_facts(self, content, file_path):
        return {"exports": ("x",)}


def test_dependency_diagnostics_flags_self_import():
    import_info = _Import("pkg.self", symbols=("x",))
    adapter = _Adapter(import_info, self_target="pkg/self.py")
    diagnostics = _dependency_diagnostics(
        adapter, "pkg/self.py", "import pkg.self", {"pkg/self.py": "x"}
    )
    assert any("imports itself" in message for message in diagnostics)


def test_dependency_diagnostics_skips_wildcard_and_no_content_target():
    wildcard = _Import("pkg.other", symbols=("*",))
    adapter = _Adapter(wildcard, target="pkg/other.py")
    assert _dependency_diagnostics(
        adapter, "pkg/self.py", "from pkg.other import *", {"pkg/other.py": "x"}
    ) == ()

    empty_target = _Import("pkg.other", symbols=("x",))
    adapter = _Adapter(empty_target, target="pkg/other.py")
    assert _dependency_diagnostics(
        adapter, "pkg/self.py", "from pkg.other import x", {"pkg/other.py": ""}
    ) == ()


def test_layout_element_and_plan_default_collections():
    element = LayoutElement("shape", Inches(1), Inches(1), Inches(1), Inches(1))
    plan = SlideLayoutPlan(slide_index=1, layout_type=LayoutType.CONTENT_ONLY)
    assert element.properties == {}
    assert plan.elements == []


def _decision(position, **kwargs):
    image = ImageDecision(
        image_type=ImageType.PHOTO, position=position, width_ratio=0.4, **kwargs
    )
    return SlideVisualDecision(
        slide_index=1, title="t", content_summary="正文", images=[image]
    )


def test_corner_position_uses_default_geometry():
    plan = LayoutDecider().plan_slide_layout(_decision(ImagePosition.CORNER), 1, 3)
    image = next(e for e in plan.elements if e.element_type == "image")
    content = next(e for e in plan.elements if e.element_type == "content")
    assert image.height == Inches(4.5)
    assert content.width == Inches(image.left.inches - LayoutDecider().MARGIN_LEFT.inches - 0.3)


def test_semantic_title_slide_without_content_only_moves_title():
    decider = LayoutDecider()
    title = LayoutElement("title", Inches(0), Inches(0), Inches(1), Inches(1), {"font_size": 10})

    result = decider._apply_semantic_geometry([title], LayoutType.TITLE_SLIDE)

    assert result == [title]
    assert title.properties["font_size"] == 32


def test_plan_without_separator_line_skips_line_element():
    decision = SlideVisualDecision(
        slide_index=1, title="t", content_summary="正文", images=[], has_separator_line=False
    )
    plan = LayoutDecider().plan_slide_layout(decision, 1, 3)
    assert [e.element_type for e in plan.elements].count("line") == 0


def test_plan_with_image_without_separator_line_skips_line_element():
    decision = _decision(ImagePosition.RIGHT)
    decision.has_separator_line = False
    plan = LayoutDecider().plan_slide_layout(decision, 1, 3)
    assert [e.element_type for e in plan.elements].count("line") == 0


def test_plan_skips_decorations_whose_geometry_is_dropped(monkeypatch):
    decider = LayoutDecider()
    decoration = ImageDecision(
        image_type=ImageType.ICON,
        position=ImagePosition.CORNER,
        is_decoration=True,
    )
    decision = SlideVisualDecision(
        slide_index=1, title="t", content_summary="正文", images=[decoration]
    )
    monkeypatch.setattr(decider, "_plan_decoration_image", lambda _img: None)

    plan = decider.plan_slide_layout(decision, 1, 3)

    assert [e.element_type for e in plan.elements].count("image") == 0


def _rendered_slide(plan):
    prs = Presentation()
    LayoutDecider().render_slide(prs, plan, image_asset=None)
    return prs.slides[0]


def test_render_string_items_and_integral_font_size():
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "content",
                Inches(1),
                Inches(1),
                Inches(5),
                Inches(3),
                {"items": "单条", "font_size": 24, "highlight_points": ["单"]},
            )
        ],
    )
    slide = _rendered_slide(plan)
    frame = next(
        shape for shape in slide.shapes
        if shape.has_text_frame and "『单』" in shape.text_frame.text
    )
    assert "『单』" in frame.text_frame.text
    assert frame.text_frame.paragraphs[0].font.size == Pt(24)


def test_render_content_accepts_pt_font_size():
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "content",
                Inches(1),
                Inches(1),
                Inches(5),
                Inches(3),
                {"items": "正文", "font_size": Pt(18)},
            )
        ],
    )
    slide = _rendered_slide(plan)
    frame = next(
        shape for shape in slide.shapes
        if shape.has_text_frame and "正文" in shape.text_frame.text
    )
    assert frame.text_frame.paragraphs[0].font.size == Pt(18)


def test_render_image_without_asset_returns_early():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    element = LayoutElement("image", Inches(1), Inches(1), Inches(2), Inches(2), {})
    LayoutDecider()._render_image(slide, element, None, None)
    assert len(slide.shapes) == 0


def test_render_image_element_without_asset_is_skipped():
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[LayoutElement("image", Inches(1), Inches(1), Inches(2), Inches(2), {})],
    )
    slide = _rendered_slide(plan)
    assert not [shape for shape in slide.shapes if shape.shape_type == 13]


def test_render_line_with_non_sequence_color_falls_back():
    plan = SlideLayoutPlan(
        slide_index=1,
        layout_type=LayoutType.CONTENT_ONLY,
        add_decorations=False,
        elements=[
            LayoutElement(
                "line",
                Inches(0.5),
                Inches(1.3),
                Inches(12),
                Inches(0.03),
                {"color": 123},
            )
        ],
    )
    slide = _rendered_slide(plan)
    line = next(
        shape for shape in slide.shapes
        if shape.shape_type == 1 and shape.fill.fore_color.rgb == RGBColor(0x33, 0x33, 0x33)
    )
    assert line.fill.fore_color.rgb == RGBColor(0x33, 0x33, 0x33)
