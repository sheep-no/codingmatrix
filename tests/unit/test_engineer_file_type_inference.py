"""Engineer 的 _infer_file_type_from_path 不得把无关单词判成业务类型。"""

import pytest

from app.agent.backend_engineer import BackendEngineer
from app.agent.frontend_engineer import FrontendEngineer


@pytest.mark.parametrize(
    "path, expected",
    [
        ("capital/service.py", "service"),
        ("therapeutic/api.py", "api"),
        ("app/models/user.py", "model"),
        ("app/api/users.py", "api"),
        ("app/services/user_service.py", "service"),
        ("tests/test_user.py", "test"),
        ("apple.py", "unknown"),
        ("happened.py", "unknown"),
        ("domain.py", "unknown"),
        ("latest.py", "unknown"),
    ],
)
def test_backend_file_type_avoids_substring_false_positives(path, expected):
    assert BackendEngineer._infer_file_type_from_path(path) == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        ("preview.js", "frontend_component"),
        ("passage.ts", "frontend_component"),
        ("interval/page.tsx", "frontend_page"),
        ("pages/home.tsx", "frontend_page"),
        ("components/Button.vue", "frontend_component"),
        ("styles/main.css", "frontend_style"),
        ("index.html", "template"),
    ],
)
def test_frontend_file_type_avoids_substring_false_positives(path, expected):
    assert FrontendEngineer._infer_file_type_from_path(path) == expected
