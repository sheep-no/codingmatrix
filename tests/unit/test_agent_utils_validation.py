from app.agent.utils import is_valid_code_content


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
