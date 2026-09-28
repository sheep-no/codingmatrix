"""CodeReviewAgent 的 Skill 分支结果契约（B1）。

覆盖 accessibility Skill 命中缺少 alt 的图片时，返回 ReviewCategory.ACCESSIBILITY
而非抛 AttributeError。
"""

from app.utils.review.code_review_agent import (
    CodeReviewAgent,
    ReviewCategory,
)


class TestAccessibilitySkill:
    def test_missing_alt_reports_accessibility_issue(self):
        agent = CodeReviewAgent(skills=["accessibility"])

        issues = agent.review_javascript_code(
            "<img src='logo.png'>", "web/index.js"
        )

        assert len(issues) == 1
        issue = issues[0]
        assert issue.category is ReviewCategory.ACCESSIBILITY
        assert issue.skill_tag == "accessibility"
        assert "alt" in issue.message

    def test_image_with_alt_reports_nothing(self):
        agent = CodeReviewAgent(skills=["accessibility"])

        issues = agent.review_javascript_code(
            "<img src='logo.png' alt='logo'>", "web/index.js"
        )

        assert issues == []
