# tests/test_generator.py
import pytest
from src.generator import create_generation_task, update_task_status, get_task_status
from src.db_config import db, GenerationTask
from datetime import datetime, timedelta


@pytest.fixture(scope="module")
def test_db():
    """创建测试用的内存数据库"""
    # 初始化数据库配置
    db_fd, db_path = tempfile.mkstemp()
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite://:{db_path}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    yield app
    # 清理数据库
    db.session.remove()
    db.drop_all()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def test_client(test_db):
    """创建测试客户端"""
    with test_db.app_context():
        yield test_db.test_client()


def test_create_generation_task(test_db):
    """
    测试生成任务创建功能
    验证任务是否能正确存储到数据库
    """
    task_id = "TEST-2026-05-04"
    data_type = "test_data"
    batch_size = 100
    
    # 创建任务
    create_generation_task(task_id, data_type, batch_size)
    
    # 验证数据库记录
    with test_db.app_context():
        task = GenerationTask.query.filter_by(task_id=task_id).first()
        assert task is not None
        assert task.task_id == task_id
        assert task.data_type == data_type
        assert task.batch_size == batch_size
        assert task.status == "pending"
        assert task.started_at is None
        assert task.completed_at is None


def test_update_task_status(test_db):
    """
    测试任务状态更新功能
    验证状态能否正确更新
    """
    # 初始化任务
    task_id = "TEST-2026-05-04"
    data_type = "test_data"
    batch_size = 100
    create_generation_task(task_id, data_type, batch_size)
    
    # 更新任务状态
    update_task_status(task_id, "processing")
    
    # 验证状态更新
    with test_db.app_context():
        task = GenerationTask.query.filter_by(task_id=task_id).first()
        assert task.status == "processing"
        assert task.started_at is not None
        assert task.completed_at is None


def test_get_task_status(test_db):
    """
    测试获取任务状态功能
    验证能否正确查询任务状态
    """
    # 创建测试任务
    task_id = "TEST-2026-05-04"
    data_type = "test_data"
    batch_size = 100
    create_generation_task(task_id, data_type, batch_size)
    
    # 查询任务状态
    with test_db.app_context():
        task = get_task_status(task_id)
        assert task is not None
        assert task["task_id"] == task_id
        assert task["data_type"] == data_type
        assert task["batch_size"] == batch_size
        assert task["status"] == "pending"


def test_get_nonexistent_task_status(test_db):
    """
    测试获取不存在任务状态的异常处理
    验证能否正确返回404错误
    """
    # 查询不存在的任务
    nonexistent_task_id = "NONEXISTENT-123"
    with test_db.app_context():
        with pytest.raises(TaskNotFoundError):
            get_task_status(nonexistent_task_id)


def test_invalid_batch_size_creation(test_db):
    """
    测试创建任务时无效batch_size参数的异常处理
    验证是否能正确捕获参数错误
    """
    task_id = "TEST-2026-05-04"
    data_type = "test_data"
    
    # 测试非整数batch_size
    with test_db.app_context():
        with pytest.raises(ValueError):
            create_generation_task(task_id, data_type, "invalid")
    
    # 测试负数batch_size
    with test_db.app_context():
        with pytest.raises(ValueError):
            create_generation_task(task_id, data_type, -50)


def test_task_status_update_with_future_timestamp(test_db):
    """
    测试状态更新时时间戳的验证逻辑
    验证时间戳是否单调递增
    """
    task_id = "TEST-2026-05-04"
    data_type = "test_data"
    batch_size = 100
    create_generation_task(task_id, data_type, batch_size)
    
    # 获取初始时间戳
    with test_db.app_context():
        initial_started_at = GenerationTask.query.filter_by(task_id=task_id).first().started_at
    
    # 模拟未来时间戳
    future_time = datetime.now() + timedelta(minutes=1)
    update_task_status(task_id, "completed", completed_at=future_time)
    
    # 验证时间戳是否符合预期
    with test_db.app_context():
        task = GenerationTask.query.filter_by(task_id=task_id).first()
        assert task.started_at > initial_started_at
        assert task.completed_at == future_time