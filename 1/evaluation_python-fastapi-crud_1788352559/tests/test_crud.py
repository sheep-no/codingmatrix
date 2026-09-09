import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import pytest
from fastapi.testclient import TestClient

from app.crud import (
    create_record,
    delete_record,
    get_record_by_id,
    get_record_list_by_user,
    list_records,
    update_record,
    get_storage_path,
    load_records,
    save_records,
    generate_id
)
from app.schemas import (
    RecordCreate,
    RecordUpdate,
    RecordResponse,
    RecordListResponse,
    UserCreate,
    UserResponse
)
from app.models import Record, User


@pytest.fixture
def client():
    """创建 FastAPI 测试客户端，使用内存数据库模式"""
    # 为了测试，我们临时修改 storage_path 指向内存文件
    import sys
    # 临时替换 app.crud.get_storage_path 为返回一个内存字符串，避免实际文件写入
    original_get_storage_path = get_storage_path
    
    def mock_get_storage_path():
        # 创建一个唯一的临时文件路径，确保每次测试都是独立的
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        return path
    
    # 重新导入以获取最新定义的函数
    from app import crud
    
    client = TestClient(crud.app)
    # patch crud 模块的函数
    crud.get_storage_path = mock_get_storage_path
    
    return client


@pytest.fixture
def tmp_path(monkeypatch):
    """创建临时目录并设置存储路径"""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, "data.json")
    
    def mock_get_storage_path():
        return tmp_path
    
    # 使用 pytest monkeypatch 直接修改导入的函数
    monkeypatch.setattr(crud, 'get_storage_path', mock_get_storage_path)
    monkeypatch.setattr(crud, 'load_records', lambda: [])  # 初始化空列表
    
    return tmp_path, tmp_dir


def test_create_record(client):
    """测试创建记录"""
    # 准备数据
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0,
        note="工资收入"
    )
    
    # 创建记录
    response = client.post("/api/v1/records", json=record_data.model_dump())
    
    # 验证状态码
    assert response.status_code == 201
    
    # 验证响应结构
    data = response.json()
    assert data["id"] is not None
    assert data["user"] == "user1"
    assert data["category"] == "工资"
    assert data["amount"] == 5000.0
    assert data["income"] == 5000.0
    assert data["note"] == "工资收入"
    assert "date" in data


def test_list_records(client):
    """测试获取记录列表"""
    # 先创建一条记录
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0
    )
    
    client.post("/api/v1/records", json=record_data.model_dump())
    
    # 获取列表
    response = client.get("/api/v1/records")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["records"][0]["user"] == "user1"


def test_get_record(client):
    """测试获取单条记录"""
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0
    )
    
    # 创建记录并获取 ID
    create_resp = client.post("/api/v1/records", json=record_data.model_dump())
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]
    
    # 获取记录
    response = client.get(f"/api/v1/records/{record_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == record_id
    assert data["user"] == "user1"


def test_update_record(client):
    """测试更新记录"""
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0
    )
    
    # 创建记录
    create_resp = client.post("/api/v1/records", json=record_data.model_dump())
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]
    
    # 准备更新数据
    update_data = RecordUpdate(
        category="工资更新",
        amount=6000.0,
        note="更新后的备注"
    )
    
    # 更新记录
    response = client.put(f"/api/v1/records/{record_id}", json=update_data.model_dump())
    
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "工资更新"
    assert data["amount"] == 6000.0
    assert data["note"] == "更新后的备注"


def test_delete_record(client):
    """测试删除记录"""
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0
    )
    
    # 创建记录
    create_resp = client.post("/api/v1/records", json=record_data.model_dump())
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]
    
    # 删除记录
    response = client.delete(f"/api/v1/records/{record_id}")
    
    assert response.status_code == 204
    
    # 验证记录不存在
    get_resp = client.get(f"/api/v1/records/{record_id}")
    assert get_resp.status_code == 404


def test_get_nonexistent_record(client):
    """测试获取不存在的记录"""
    response = client.get("/api/v1/records/999")
    assert response.status_code == 404


def test_update_nonexistent_record(client):
    """测试更新不存在的记录"""
    update_data = RecordUpdate(category="测试")
    response = client.put("/api/v1/records/999", json=update_data.model_dump())
    assert response.status_code == 404


def test_delete_nonexistent_record(client):
    """测试删除不存在的记录"""
    response = client.delete("/api/v1/records/999")
    assert response.status_code == 404


def test_user_not_found(client):
    """测试用户不存在的情况"""
    record_data = RecordCreate(
        user="nonexistent_user",
        date=datetime.now(),
        category="工资",
        amount=5000.0,
        income=5000.0
    )
    
    response = client.post("/api/v1/records", json=record_data.model_dump())
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "User not found"


def test_invalid_amount(client):
    """测试无效金额"""
    record_data = RecordCreate(
        user="user1",
        date=datetime.now(),
        category="工资",
        amount=-100.0,  # 负数
        income=5000.0
    )
    
    response = client.post("/api/v1/records", json=record_data.model_dump())
    # Pydantic 会抛出异常，FastAPI 会返回 422
    assert response.status_code == 422