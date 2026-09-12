from app.agent.critical_decision import CriticalDecisionExtractor


def test_no_auth_or_database_signal_skips_stack_questions():
    extractor = CriticalDecisionExtractor()
    decisions = extractor.extract_from_architecture(
        {"tech_stack": ["Python"], "project_spec": {"default": {}}},
        {
            "has_frontend": False,
            "has_backend": False,
            "has_database": False,
            "has_auth": False,
            "estimated_files": 3,
        },
    )
    assert [item.id for item in decisions] == []


def test_should_skip_user_decision_for_simple_and_script_scope():
    from app.agent.critical_decision import should_skip_user_decision

    questions = [{"id": "api_style", "question": "API?"}]
    assert should_skip_user_decision({"level": "simple", "has_backend": True}, questions) is True
    assert should_skip_user_decision(
        {
            "has_frontend": False,
            "has_backend": False,
            "has_database": False,
            "has_auth": False,
            "estimated_files": 3,
        },
        questions,
    ) is True
    assert should_skip_user_decision(
        {
            "level": "medium",
            "has_frontend": False,
            "has_backend": True,
            "has_database": True,
            "has_auth": True,
            "estimated_files": 8,
        },
        questions,
    ) is False
    assert should_skip_user_decision({"level": "medium"}, []) is True


def test_string_project_spec_and_file_plan_do_not_crash():
    extractor = CriticalDecisionExtractor()
    decisions = extractor.extract_from_architecture(
        {
            "tech_stack": "Python",
            "project_spec": "simple hello world script",
            "file_plan": ["hello.py", {"path": "README.md"}],
        },
        {
            "has_frontend": False,
            "has_backend": False,
            "has_database": False,
            "has_auth": False,
            "estimated_files": 1,
        },
    )
    assert [item.id for item in decisions] == []


def test_auth_and_database_signals_ask_when_undecided():
    extractor = CriticalDecisionExtractor()
    decisions = extractor.extract_from_architecture(
        {"tech_stack": ["Python"], "project_spec": {"default": {}}},
        {
            "has_frontend": False,
            "has_backend": True,
            "has_database": True,
            "has_auth": True,
            "estimated_files": 8,
        },
    )
    assert [item.id for item in decisions] == ["auth_strategy", "database_choice", "api_style"]


def test_explicit_auth_and_storage_skip_questions():
    extractor = CriticalDecisionExtractor()
    decisions = extractor.extract_from_architecture(
        {
            "tech_stack": ["FastAPI", "JWT", "SQLite"],
            "project_spec": {
                "default": {
                    "auth": {"scheme": "jwt_hs256"},
                    "storage": {"type": "sqlite", "backend": "sqlalchemy"},
                }
            },
        },
        {
            "has_frontend": False,
            "has_backend": True,
            "has_database": True,
            "has_auth": True,
            "estimated_files": 8,
        },
    )
    assert "auth_strategy" not in [item.id for item in decisions]
    assert "database_choice" not in [item.id for item in decisions]


def test_architecture_invented_schema_does_not_ask_without_requirement_signal():
    extractor = CriticalDecisionExtractor()
    decisions = extractor.extract_from_architecture(
        {
            "tech_stack": ["Python"],
            "db_schema": {"scores": {"columns": {"id": "INTEGER"}}},
            "project_spec": {"default": {"storage": {"type": "sqlite"}}},
        },
        {
            "has_frontend": False,
            "has_backend": False,
            "has_database": False,
            "has_auth": False,
            "estimated_files": 5,
        },
    )
    assert [item.id for item in decisions] == []
