"""
multi_angle_review 模块单元测试
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.multi_angle_review import (
    ReviewSeverity,
    REVIEW_ROLES,
    parse_multi_review_response,
    parse_devil_response,
)


class TestReviewSeverity:
    """审查严格度测试"""

    def test_enum_values(self):
        """测试枚举值"""
        assert ReviewSeverity.LIGHT == "light"
        assert ReviewSeverity.STANDARD == "standard"
        assert ReviewSeverity.STRICT == "strict"


class TestReviewRoles:
    """审查角色测试"""

    def test_role_names(self):
        """测试角色名称"""
        assert "performance" in REVIEW_ROLES
        assert "security" in REVIEW_ROLES
        assert "maintainability" in REVIEW_ROLES

    def test_role_system_prompts(self):
        """测试角色 System Prompt"""
        assert len(REVIEW_ROLES["performance"]["system_prompt"]) > 100
        assert len(REVIEW_ROLES["security"]["system_prompt"]) > 100
        assert len(REVIEW_ROLES["maintainability"]["system_prompt"]) > 100

    def test_performance_role_content(self):
        """测试性能师角色内容"""
        prompt = REVIEW_ROLES["performance"]["system_prompt"]
        assert "性能工程师" in prompt
        assert "N+1" in prompt
        assert "缓存" in prompt

    def test_security_role_content(self):
        """测试安全师角色内容"""
        prompt = REVIEW_ROLES["security"]["system_prompt"]
        assert "安全工程师" in prompt
        assert "SQL 注入" in prompt
        assert "XSS" in prompt

    def test_maintainability_role_content(self):
        """测试可维护性师角色内容"""
        prompt = REVIEW_ROLES["maintainability"]["system_prompt"]
        assert "软件架构师" in prompt
        assert "模块耦合" in prompt
        assert "DRY" in prompt


class TestParseMultiReviewResponse:
    """解析多角度审查响应测试"""

    def test_valid_response(self):
        """测试有效响应"""
        response = json.dumps({
            "reviews": [
                {
                    "target": "user.py Line 42",
                    "issue": "N+1 查询问题",
                    "severity": "high",
                    "suggestion": "使用 select_related",
                    "category": "database"
                }
            ]
        })
        
        results = parse_multi_review_response(response, "performance")
        
        assert len(results) == 1
        assert results[0]["role"] == "性能师"
        assert results[0]["target"] == "user.py Line 42"
        assert results[0]["issue"] == "N+1 查询问题"
        assert results[0]["severity"] == "high"

    def test_response_with_markdown(self):
        """测试带 Markdown 包装的响应"""
        response = """```json
        {
            "reviews": [
                {
                    "target": "auth.py",
                    "issue": "SQL 注入风险",
                    "severity": "critical",
                    "suggestion": "使用参数化查询",
                    "category": "security"
                }
            ]
        }
        ```"""
        
        results = parse_multi_review_response(response, "security")
        
        assert len(results) == 1
        assert results[0]["role"] == "安全师"

    def test_invalid_response(self):
        """测试无效响应"""
        response = "这不是 JSON"
        results = parse_multi_review_response(response, "performance")
        assert results == []

    def test_response_max_limit(self):
        """测试响应数量限制"""
        reviews = []
        for i in range(15):
            reviews.append({
                "target": f"file{i}.py",
                "issue": f"Issue {i}",
                "severity": "medium",
                "suggestion": f"Fix {i}",
                "category": "general"
            })
        
        response = json.dumps({"reviews": reviews})
        results = parse_multi_review_response(response, "performance")
        
        # 每个角色最多 10 条
        assert len(results) <= 10


class TestParseDevilResponse:
    """解析魔鬼代言人响应测试"""

    def test_valid_response(self):
        """测试有效响应"""
        response = json.dumps({
            "reviews": [
                {
                    "target": "需求 A",
                    "issue": "缺少前置条件",
                    "severity": "high",
                    "suggestion": "添加依赖说明",
                    "role": "devil_advocate"
                }
            ]
        })
        
        results = parse_devil_response(response)
        
        assert len(results) == 1
        assert results[0]["role"] == "devil_advocate"

    def test_invalid_response(self):
        """测试无效响应"""
        response = "invalid json"
        results = parse_devil_response(response)
        assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
