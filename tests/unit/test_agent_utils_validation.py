import json

from app.agent.utils import (
    _is_edit_marker,
    is_valid_code_content,
    try_extract_from_metadata,
    validate_content_quality,
)


def test_pom_validation_accepts_well_formed_project() -> None:
    valid, reason = is_valid_code_content(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion>
<properties><java.version>17</java.version></properties>
<dependencies />
<build />
</project>""",
    )

    assert valid
    assert reason == ""


def test_pom_validation_rejects_duplicate_project_elements() -> None:
    valid, reason = is_valid_code_content(
        "pom.xml",
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion>
<properties><java.version>17</java.version></properties>
<properties><application.mainClass>com.example.Application</application.mainClass></properties>
</project>""",
    )

    assert not valid
    assert reason == "POM 包含重复的 <properties> 元素"


def test_pom_validation_rejects_invalid_xml() -> None:
    valid, reason = is_valid_code_content("pom.xml", "<project><modelVersion>4.0.0</project>")

    assert not valid
    assert reason.startswith("POM XML 格式错误:")


def test_python_docstring_bullets_are_not_treated_as_markdown() -> None:
    content = (
        '"""服务层。\n'
        "\n"
        "职责:\n"
        "- 用户注册\n"
        "- 用户登录\n"
        "1. 校验参数\n"
        "> 注意: 需要 JWT\n"
        '"""\n'
        "def register():\n"
        "    return None\n"
    )
    valid, reason = is_valid_code_content("app/services/auth.py", content)

    assert valid, reason


def test_python_metadata_payload_is_still_rejected() -> None:
    valid, reason = is_valid_code_content(
        "app/main.py", '{"status": "ok", "file_path": "app/main.py"}'
    )

    assert not valid
    assert reason == "内容是 JSON 元数据而非代码"


def test_json_config_with_metadata_like_keys_is_accepted() -> None:
    valid, reason = is_valid_code_content(
        "data/config.json", '{"status": "active", "output": "x", "port": 8000}'
    )

    assert valid, reason


def test_markdown_is_still_rejected_for_non_syntax_checked_files() -> None:
    valid, reason = is_valid_code_content(
        "notes.ts", "## Title\n- a\n- b\n```\ncode\n```\n"
    )

    assert not valid
    assert reason == "内容是 Markdown 文档而非代码"


def test_markdown_documentation_file_is_accepted() -> None:
    readme = "# Project\n\n## Install\n\n- step one\n- step two\n\n## Usage\n\n1. run\n2. done\n"

    assert is_valid_code_content("README.md", readme)[0]
    assert is_valid_code_content("docs/guide.rst", readme)[0]


def test_code_file_embedding_markdown_template_is_accepted() -> None:
    content = (
        "const tpl = `# Title\\n\\n## Section\\n\\n- item\\n\\n1. first`\n"
        "export default tpl\n"
    )

    assert is_valid_code_content("web/app.js", content)[0]


def test_markdown_metadata_payload_is_still_rejected_for_docs() -> None:
    valid, reason = is_valid_code_content(
        "README.md", json.dumps({"status": "completed", "content": "code here"})
    )

    assert not valid
    assert reason == "内容是 JSON 元数据而非代码"


def test_json_data_file_with_content_key_is_not_rewritten() -> None:
    payload = {"content": "正文" * 40, "title": "文章"}

    assert try_extract_from_metadata("data/content.json", json.dumps(payload, ensure_ascii=False)) is None


def test_wrapped_json_output_is_still_extracted() -> None:
    inner = json.dumps({"name": "app", "version": "1.0.0", "description": "a sample project"})
    wrapped = json.dumps({"status": "completed", "file_path": "config.json", "content": inner})

    assert try_extract_from_metadata("config.json", wrapped) == inner


def test_json_config_is_not_treated_as_edit_marker() -> None:
    payload = json.dumps({"status": "active", "output": "dist/", "port": 8000})

    assert not _is_edit_marker(payload, "data/config.json")


def test_json_explicit_action_is_still_an_edit_marker() -> None:
    assert _is_edit_marker(json.dumps({"action": "edited"}), "data/config.json")


def test_code_file_metadata_payload_is_still_an_edit_marker() -> None:
    payload = json.dumps({"status": "completed", "file_path": "app/main.py"})

    assert _is_edit_marker(payload, "app/main.py")


def test_content_quality_allows_yaml_front_matter() -> None:
    content = "---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n"

    assert validate_content_quality("k8s/deploy.yaml", content) == ""
    assert validate_content_quality("docs/guide.md", "---\ntitle: Guide\n---\n\n# Guide\n") == ""


def test_content_quality_allows_docs_prose_first_line() -> None:
    assert validate_content_quality("README.md", "This module provides a small API.\n") == ""
    assert validate_content_quality("docs/intro.md", "The following is an overview.\n") == ""


def test_content_quality_still_flags_code_reasoning_leak() -> None:
    content = "Let me think about this.\n\n\ndef f():\n    return 1\n"

    assert validate_content_quality("app/x.py", content) != ""


def test_content_quality_allows_css_chinese_comments() -> None:
    content = (
        "/*\n"
        " * 这段注释用于说明整体样式设计思路的实现\n"
        " * 包括颜色、间距和排版等细节内容的设计\n"
        " * 以及响应式断点的处理方式说明与实现\n"
        " * 还有更多补充说明文字用于描述样式\n"
        " * 最后再补充一行说明用于触发检测阈值\n"
        " */\n\n"
        "body {\n  margin: 0;\n  padding: 0;\n}\n"
    )

    assert validate_content_quality("styles.css", content) == ""


def test_content_quality_still_flags_css_chinese_prose() -> None:
    content = (
        "这是一段中文说明文字，并非真正的样式代码内容。\n"
        "这里继续描述样式应该如何设计以及颜色和间距的细节。\n"
        "还有更多说明文字，用于模拟模型直接返回了描述而非代码。\n"
        "继续补充更多中文描述内容以触发检测条件。\n"
        "再补充一行中文说明文字。\n"
    )

    assert validate_content_quality("styles.css", content) != ""
