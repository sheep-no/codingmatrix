"""Schema 层 Pydantic v2 迁移与死符号清理的回归（SD2/SD3/SD6）。"""
import inspect

import pytest
from pydantic import ValidationError

from app.schema import file_schema, girl_request, nginxConf, task_schema


def test_nginx_schema_no_deprecated_v1_api():
    src = inspect.getsource(nginxConf)
    assert "@validator(" not in src
    assert "from pydantic import BaseModel, Field, field_validator" in src


def test_file_and_task_schema_no_deprecated_config_class():
    for module in (file_schema, task_schema):
        src = inspect.getsource(module)
        assert "class Config:" not in src
        assert "model_config = ConfigDict(from_attributes=True)" in src


def test_nginx_validators_still_enforced():
    request = nginxConf.NginxGenerateRequest(
        platform="linux", config_type="proxy", server_name="example.com", port=80
    )
    assert request.server_name == "example.com"

    with pytest.raises(ValidationError):
        nginxConf.NginxGenerateRequest(
            platform="solaris", config_type="proxy", server_name="example.com", port=80
        )
    with pytest.raises(ValidationError):
        nginxConf.NginxGenerateRequest(
            platform="linux", config_type="magic", server_name="example.com", port=80
        )
    with pytest.raises(ValidationError):
        nginxConf.NginxGenerateRequest(
            platform="linux", config_type="proxy", server_name="   ", port=80
        )


class _OrmLike:
    """模拟 ORM 对象属性访问，验证 from_attributes 生效。"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_from_attributes_still_works_after_migration():
    uploaded = file_schema.FileUploadResponse.model_validate(
        _OrmLike(
            id=1,
            filename="a.txt",
            file_size=3,
            content_type="text/plain",
            created_at="2026-09-20",
            download_url="/files/1",
        )
    )
    assert uploaded.filename == "a.txt"

    task = task_schema.TaskResponse.model_validate(
        _OrmLike(
            task_id="t1",
            task_type="code_generate",
            status="pending",
            created_at="2026-09-20",
        )
    )
    assert task.task_id == "t1"
    assert task.priority == 5


def test_dead_schema_symbols_removed():
    for name in (
        "FileDownloadResponse",
        "FileCreate",
        "FileResponse",
        "validate_page",
        "validate_page_size",
    ):
        assert not hasattr(file_schema, name)
    assert not hasattr(girl_request, "HistoryQuery")
