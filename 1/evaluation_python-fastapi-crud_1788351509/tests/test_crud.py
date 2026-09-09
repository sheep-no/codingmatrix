import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.crud import get_todos, get_todo, create_todo, update_todo, delete_todo
from app.models import Todo
from app.database import get_db
from app.schemas import TodoCreate, TodoUpdate, TodoRead


@pytest.fixture(scope="module")
def client():
    def override_get_db():
        try:
            yield get_db()
        finally:
            pass

    app = TestClient(TestClient(__import__('app', fromlist=['app']).app))
    return app


@pytest.fixture
def todo_factory(client):
    def _create():
        return TodoCreate(title="测试任务", description="这是一个测试描述")
    return _create


def test_create_todo(client: TestClient):
    response = client.post("/api/v1/todos", json={"title": "新任务", "description": "描述内容"})
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["title"] == "新任务"
    assert data["description"] == "描述内容"
    assert data["completed"] is False
    assert data["created_at"] is not None


def test_get_todos(client: TestClient):
    response = client.get("/api/v1/todos")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_todo_not_found(client: TestClient):
    response = client.get("/api/v1/todos/999")
    assert response.status_code == 404


def test_update_todo(client: TestClient):
    response = client.post("/api/v1/todos", json={"title": "旧任务", "description": "旧描述"})
    todo_data = response.json()
    todo_id = todo_data["id"]
    
    response = client.put(f"/api/v1/todos/{todo_id}", json={"title": "更新后的标题", "description": "更新后的描述", "completed": True})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "更新后的标题"
    assert data["completed"] is True


def test_delete_todo(client: TestClient):
    response = client.post("/api/v1/todos", json={"title": "待删除任务", "description": "待删除描述"})
    todo_data = response.json()
    todo_id = todo_data["id"]
    
    response = client.delete(f"/api/v1/todos/{todo_id}")
    assert response.status_code == 200
    assert not Todo.__table__.where(Todo.id == todo_id).scalar()