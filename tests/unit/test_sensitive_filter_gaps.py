"""sensitive_filter 掩码函数与检测分类补测。"""

from app.utils.aicloud.sensitive_filter import (
    detect_sensitive_info,
    filter_sensitive_content,
    mask_api_keys,
    mask_passwords,
    mask_tokens,
)

OPENAI = "sk-" + "a" * 48
GITHUB = "ghp_" + "b" * 36
GITLAB = "glpat-" + "c" * 20
JWT = "eyJhbGciOi.eyJzdWIiOi.sigPart"


def test_filter_empty_returns_input():
    assert filter_sensitive_content("") == ""


def test_filter_openai_key():
    assert "sk-" not in filter_sensitive_content(OPENAI)
    assert "[OPENAI_KEY]" in filter_sensitive_content(OPENAI)


def test_filter_github_and_gitlab_tokens():
    text = f"{GITHUB} {GITLAB}"
    filtered = filter_sensitive_content(text)
    assert "[GITHUB_TOKEN]" in filtered
    assert "[GITLAB_TOKEN]" in filtered


def test_filter_password_quoted_with_space():
    filtered = filter_sensitive_content('password="my secret"')
    assert filtered == "password=[REDACTED]"


def test_filter_password_starts_with_s():
    filtered = filter_sensitive_content("password=secret123")
    assert filtered == "password=[REDACTED]"


def test_filter_api_key_variants():
    assert filter_sensitive_content("api-key: abc") == "api_key=[REDACTED]"
    assert filter_sensitive_content("API_KEY=xyz") == "api_key=[REDACTED]"


def test_filter_private_key_block():
    block = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
    assert filter_sensitive_content(block) == "[PRIVATE_KEY]"


def test_filter_mongodb_credentials():
    filtered = filter_sensitive_content("mongodb://user:pass@host/db")
    assert "pass" not in filtered
    assert "mongodb://[REDACTED]@[HOST]" in filtered


def test_filter_jwt():
    assert filter_sensitive_content(JWT) == "[JWT_TOKEN]"


def test_mask_api_keys_all_branches():
    text = f"{OPENAI} {GITHUB} {GITLAB} api_key=zzz"
    masked = mask_api_keys(text)
    assert "[OPENAI_KEY]" in masked
    assert "[GITHUB_TOKEN]" in masked
    assert "[GITLAB_TOKEN]" in masked
    assert "[API_KEY]" in masked


def test_mask_passwords_all_variants():
    text = "password=a passwd=b pwd=c"
    masked = mask_passwords(text)
    assert masked.count("password=[REDACTED]") == 3


def test_mask_tokens_variants():
    text = f"{JWT} Bearer abc.def Token xyz"
    masked = mask_tokens(text)
    assert "[TOKEN]" in masked
    assert masked.count("[TOKEN]") == 3


def test_detect_sensitive_info_identifies_types():
    text = f"{OPENAI} {GITHUB} {GITLAB} password=x api_key=y " \
           "mongodb://u:p@h/db " + JWT
    types = detect_sensitive_info(text)
    assert {
        "OpenAI API Key", "GitHub Token", "GitLab Token",
        "Password", "API Key", "JWT Token", "Database Credentials",
    } <= set(types)


def test_detect_private_key():
    assert "Private Key" in detect_sensitive_info(
        "-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----"
    )


def test_detect_empty_and_clean():
    assert detect_sensitive_info("") == []
    assert detect_sensitive_info("nothing secret here") == []
