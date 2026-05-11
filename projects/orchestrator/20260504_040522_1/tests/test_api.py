# tests/test_api.py
"""API接口测试模块"""

from typing import Any, Dict, Generator, List, Optional
import pytest
from flask import Flask, Response
from src.api import create_app
from src.db_config import db
from src.generator import generate_data
from tests.test_generator import TestGenerator  # 假设已实现生成器测试逻辑

@pytest.fixture(scope="module")
def test_app() -> Generator:
    """创建测试用的Flask应用实例"""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SQLALCHEMY_TRACK_MODIFICATIONS': False
    })
    
    # 初始化数据库
    with app.app_context():
        db.create_all()
    
    # 创建测试客户端
    client = app.test_client()
    
    # 清理数据库
    yield client
    
    # 关闭后删除数据库
    with app.app_context():
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope="module")
def test_app_context(test_app: Flask) -> Any:
    """获取测试应用的上下文"""
    return test_app.app_context()

def test_generate_endpoint(test_app_context: Any) -> None:
    """测试生成数据接口"""
    with test_app_context:
        # 创建测试应用
        app = create_app()
        client = app.test_client()
        
        # 测试有效请求
        response = client.post('/api/v1/generate', 
                             query_string={'batch_size': 10, 'data_type': 'test_data'})
        assert response.status_code == 202
        assert b"Task accepted" in response.data
        
        # 验证数据库记录
        task = GenerationTask.query.filter_by(data_type='test_data', batch_size=10).first()
        assert task is not None
        assert task.status == 'pending'
        assert task.task_id is not None  # 确保生成了task_id
        
        # 测试无效参数
        invalid_response = client.post('/api/v1/generate', 
                                  query_string={'batch_size': 'invalid', 'data_type': 'test_data'})
        assert invalid_response.status_code == 400
        
        # 测试缺少参数
        missing_response = client.post('/api/v1/generate', 
                                  query_string={'batch_size': 5})
        assert missing_response.status_code == 400

def test_status_endpoint(test_app_context: Any) -> None:
    """测试任务状态查询接口"""
    with test_app_context:
        # 创建测试应用
        app = create_app()
        client = app.test_client()
        
        # 创建测试任务
        task_id = "test_task_123"
        data_type = "test_data"
        batch_size = 15
        
        # 插入测试数据
        task = GenerationTask(task_id=task_id, data_type=data_type, batch_size=batch_size)
        db.session.add(task)
        db.session.commit()
        
        # 测试有效任务ID
        response = client.get('/api/v1/status', query_string={'task_id': task_id})
        assert response.status_code == 200
        data = response.get_json()
        assert data['task_id'] == task_id
        assert data['data_type'] == data_type
        assert data['batch_size'] == batch_size
        assert data['status'] == 'pending'
        
        # 测试无效任务ID
        invalid_response = client.get('/api/v1/status', query_string={'task_id': 'invalid_id'})
        assert invalid_response.status_code == 404
        assert b"Task not found" in invalid_response.data
        
        # 测试更新任务状态
        # 模拟生成器完成任务
        generate_data(task_id)
        
        # 验证状态更新
        updated_task = GenerationTask.query.get(task_id)
        assert updated_task.status == 'completed'
        assert updated_task.completed_at is not None
        
        # 再次查询状态
        status_response = client.get('/api/v1/status', query_string={'task_id': task_id})
        assert status_response.status_code == 200
        status_data = status_response.get_json()
        assert status_data['status'] == 'completed'

# 数据库模型定义（需要与src/api.py中的模型保持一致）
class GenerationTask(db.Model):
    """生成任务模型"""
    __tablename__ = 'generation_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(255), unique=True, nullable=False)
    data_type = db.Column(db.String(255), nullable=False)
    batch_size = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='pending')
    started_at = db.Column(db.TIMESTAMP)
    completed_at = db.Column(db.TIMESTAMP)