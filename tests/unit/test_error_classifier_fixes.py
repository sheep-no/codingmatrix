"""回归：error_classifier EC1/EC2/EC3/EC4/EC5/EC6。"""

from app.agent import error_classifier as ec_mod
from app.agent.error_classifier import ErrorClassifier, ErrorClassification


class TestEC1OrderByPosition:
    """EC1: 多错误拼接串按出现顺序分类，而非 ERROR_PATTERNS dict 顺序"""

    def test_first_error_wins_typeerror(self):
        msg = "TypeError: 'int' object is not subscriptable; NameError: name 'x' is not defined"
        result = ErrorClassifier()._rule_based_classification(msg)
        # NameError 在 dict 中排在 TypeError 之前，旧实现返回 NameError
        assert result.error_type == "TypeError"

    def test_first_error_wins_nameerror(self):
        msg = "NameError: name 'x' is not defined; TypeError: bad"
        result = ErrorClassifier()._rule_based_classification(msg)
        assert result.error_type == "NameError"

    def test_subtype_taken_from_matched_group(self):
        msg = "ValueError: a; NameError: name 'foo' is not defined"
        result = ErrorClassifier()._rule_based_classification(msg)
        assert result.error_type == "NameError"
        assert result.error_subtype == "foo"

    def test_no_match_returns_none(self):
        assert ErrorClassifier()._rule_based_classification("something totally fine") is None


class TestEC2PatternCoverage:
    """EC2: 常见变体与 LogicError 英文规则可达"""

    def _classify_rule(self, msg):
        return ErrorClassifier()._rule_based_classification(msg)

    def test_keyerror_numeric_key(self):
        assert self._classify_rule("KeyError: 5").error_type == "KeyError"

    def test_keyerror_string_key(self):
        result = self._classify_rule("KeyError: 'missing'")
        assert result.error_type == "KeyError"
        assert result.error_subtype == "missing"

    def test_nameerror_without_quotes(self):
        result = self._classify_rule("name counter is not defined")
        assert result.error_type == "NameError"
        assert result.error_subtype == "counter"

    def test_logicerror_english_reachable(self):
        assert self._classify_rule("Logic Error: expected 1 got 2").error_type == "LogicError"
        assert self._classify_rule("business logic error detected").error_type == "LogicError"


class TestEC3ModelFailureSemantics:
    """EC3: 模型分类失败不再伪装成 LogicError"""

    async def test_empty_content_falls_back_to_unknown(self, monkeypatch):
        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": ""}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("mysterious failure")

        assert result.error_type == "Unknown"
        assert result.confidence == 0.0

    async def test_rule_hit_skips_model(self, monkeypatch):
        async def boom(**kwargs):
            raise AssertionError("模型路径不应被调用")

        monkeypatch.setattr(ec_mod, "call_llm", boom)
        result = await ErrorClassifier().classify_error("NameError: name 'x' is not defined")
        assert result.error_type == "NameError"

    async def test_first_json_block_of_many_used(self, monkeypatch):
        content = (
            '{"error_type": "TypeError", "description": "d", '
            '"suggested_fix_strategy": "s", "confidence": 0.8}\n\n'
            '{"error_type": "NameError", "description": "other", '
            '"suggested_fix_strategy": "s2", "confidence": 0.9}'
        )

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("weird")
        assert result.error_type == "TypeError"

    async def test_json_wrapped_in_prose(self, monkeypatch):
        content = (
            "Here is the result:\n"
            '{"error_type": "KeyError", "description": "d", '
            '"suggested_fix_strategy": "s", "confidence": 0.7}\n'
            "Hope it helps."
        )

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("weird")
        assert result.error_type == "KeyError"

    async def test_missing_required_field_falls_back(self, monkeypatch):
        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": '{"error_type": "TypeError"}'}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("weird")
        assert result.error_type == "Unknown"

    async def test_illegal_error_type_falls_back(self, monkeypatch):
        content = '{"error_type": "Bogus", "description": "d", "suggested_fix_strategy": "s"}'

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("weird")
        assert result.error_type == "Unknown"

    async def test_confidence_clamped(self, monkeypatch):
        content = (
            '{"error_type": "TypeError", "description": "d", '
            '"suggested_fix_strategy": "s", "confidence": 5.0}'
        )

        async def fake_call_llm(**kwargs):
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        result = await ErrorClassifier().classify_error("weird")
        assert result.confidence == 1.0

    async def test_call_llm_exception_falls_back(self, monkeypatch):
        async def boom(**kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(ec_mod, "call_llm", boom)
        result = await ErrorClassifier().classify_error("mysterious")
        assert result.error_type == "Unknown"


class TestCEC3ClientPassthrough:
    """CEC3: 模型分类兜底透传 api_key_token/cancel_event，走统一客户端。"""

    async def test_token_and_cancel_event_forwarded(self, monkeypatch):
        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return {"choices": [{"message": {"content": ""}}]}

        monkeypatch.setattr(ec_mod, "call_llm", fake_call_llm)
        cancel = object()
        await ErrorClassifier().classify_error(
            "mysterious failure",
            api_key_token="tok-123",
            cancel_event=cancel,
        )

        assert captured.get("api_key_token") == "tok-123"
        assert captured.get("cancel_event") is cancel

    async def test_rule_hit_does_not_call_model(self, monkeypatch):
        """规则命中时不进入模型路径，token 无需求。"""

        async def boom(**kwargs):
            raise AssertionError("规则命中不应调用模型")

        monkeypatch.setattr(ec_mod, "call_llm", boom)
        result = await ErrorClassifier().classify_error(
            "NameError: name 'x' is not defined",
            api_key_token="tok-123",
        )
        assert result.error_type == "NameError"


class TestEC4HistoryBound:
    """EC4: classification_history 有上限，长会话不无界增长"""

    def test_history_bounded(self):
        classifier = ErrorClassifier()
        assert classifier.classification_history.maxlen == ErrorClassifier.HISTORY_MAXLEN

        item = ErrorClassification("TypeError", "", "d", "s", 0.9)
        for _ in range(ErrorClassifier.HISTORY_MAXLEN + 50):
            classifier.add_to_history(item)
        assert len(classifier.classification_history) == ErrorClassifier.HISTORY_MAXLEN


class TestEC6CommentAlignment:
    """EC6: 策略文案不再声明与实际模型不符的 deepseek-r1"""

    def test_logic_error_strategy_has_no_stale_model(self):
        strategy = ErrorClassifier.ERROR_PATTERNS["LogicError"]["fix_strategy"]
        assert "deepseek" not in strategy.lower()
