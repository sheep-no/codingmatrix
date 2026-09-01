from app.agent.repair_router import RepairBudget, RepairRouter


def test_router_sends_basic_errors_to_automatic_repair():
    assert RepairRouter.route("SyntaxError", "invalid syntax") == RepairRouter.route("syntax", "语法")
    assert RepairRouter.route("ImportError", "No module named x").repairer == "dependency_repair"
    assert RepairRouter.route("TypeError", "wrong type").auto_apply is True


def test_router_sends_business_and_test_errors_to_confirmation():
    business = RepairRouter.route("LogicError", "业务逻辑错误")
    test = RepairRouter.route("test_failure", "assertion failed")

    assert business.auto_apply is False
    assert business.repairer == "user_confirmation"
    assert test.auto_apply is False
    assert test.category == "test"


def test_repair_budget_enforces_category_and_total_limits():
    budget = RepairBudget(per_category_limit=3, total_limit=5)

    assert [budget.consume("syntax") for _ in range(4)] == [True, True, True, False]
    assert budget.consume("import") is True
    assert budget.consume("type") is True
    assert budget.consume("unknown") is False
    assert budget.total_used == 5
