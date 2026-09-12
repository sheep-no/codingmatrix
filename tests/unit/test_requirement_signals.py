from app.agent.complexity import ComplexityAnalyzer, ProjectComplexity
from app.agent.architect import Architect
from app.agent.language_detector import LanguageDetector
from app.agent.requirement_signals import has_positive_keyword, first_positive_span


HELLO_REQ = (
    "写一个 Python 文件 hello.py，运行后打印 Hello World。"
    "只要这一个文件，不要数据库、不要前端、不要测试。"
)


def test_negation_skips_frontend_and_database():
    assert has_positive_keyword("不要前端", ["前端"]) is False
    assert has_positive_keyword("不要数据库", ["数据库"]) is False
    assert has_positive_keyword("without database", ["database"]) is False
    assert has_positive_keyword("don't use python", ["python"]) is False


def test_word_boundary_avoids_substring_false_positives():
    assert has_positive_keyword("rebuild", ["ui"]) is False
    assert has_positive_keyword("rapid", ["api"]) is False
    assert has_positive_keyword("rapid api", ["api"]) is True


def test_positive_keywords_still_match():
    assert has_positive_keyword("Vue 3 + FastAPI 全栈", ["vue", "fastapi"]) is True
    assert first_positive_span("不要用 Python，用 Go 写", "python") is None
    assert first_positive_span("不要用 Python，用 Go 写", "go") is not None


def test_hello_world_is_simple_script():
    result = ComplexityAnalyzer.analyze(HELLO_REQ)
    assert result.level == ProjectComplexity.SIMPLE
    assert result.estimated_files == 1
    assert result.has_frontend is False
    assert result.has_backend is False
    assert result.has_database is False
    assert "FastAPI" not in result.key_technologies


def test_fullstack_still_detected():
    result = ComplexityAnalyzer.analyze("Vue 3 + FastAPI 全栈项目带用户登录")
    assert result.has_frontend is True
    assert result.has_backend is True
    assert result.has_auth is True
    assert "Vue" in result.key_technologies
    assert "FastAPI" in result.key_technologies


def test_blog_with_database_still_positive():
    result = ComplexityAnalyzer.analyze("创建一个带数据库的博客系统")
    assert result.has_database is True


def test_language_respects_negated_python():
    result = LanguageDetector.detect("不要用 Python，用 Go 写一个命令行程序")
    assert result.language == "go"


def test_hello_world_language_is_python():
    result = LanguageDetector.detect(HELLO_REQ)
    assert result.language == "python"


def test_explicit_dont_use_python_use_go():
    result = LanguageDetector.detect("don't use python, use go for this cli")
    assert result.language == "go"


def test_scope_rules_forbid_default_fastapi_for_simple_script():
    complexity = ComplexityAnalyzer.analyze(HELLO_REQ)
    text = Architect._build_scope_rules_text(complexity)
    assert "禁止默认 FastAPI" in text
    assert "db_schema 必须为 {}" in text
    assert "不得包含页面" in text
