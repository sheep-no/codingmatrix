import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import Record, User
from app.schemas import RecordCreate, RecordUpdate, RecordResponse, RecordListResponse


def get_db() -> Session:
    """数据库依赖注入"""
    from app.database import SessionLocal
    return SessionLocal()


def get_storage_path() -> str:
    """获取存储文件路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data.json")


def load_records() -> List[Dict[str, Any]]:
    """从 JSON 文件加载记录"""
    path = get_storage_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('records', [])
    except (json.JSONDecodeError, IOError):
        return []


def save_records(records: List[Dict[str, Any]]) -> None:
    """保存记录到 JSON 文件"""
    path = get_storage_path()
    with open(path, 'w', encoding='utf-8') as f:
        # 确保 datetime 对象可以被序列化
        import json
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type not serializable: {type(obj)}")
        json.dump({'records': records}, f, default=serialize, ensure_ascii=False)


def generate_id(records: List[Dict[str, Any]]) -> int:
    """生成唯一 ID"""
    if not records:
        return 1
    return max(int(r['id']) for r in records) + 1


def create_record(db: Session, record_data: RecordCreate) -> RecordResponse:
    """创建新记录"""
    # 检查用户是否存在
    user = db.query(User).filter(User.username == record_data.user).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 构建记录数据
    new_record = {
        "id": generate_id(load_records()),
        "user": record_data.user,
        "date": datetime.now(),
        "income": record_data.income,
        "expense": record_data.expense,
        "category": record_data.category,
        "amount": record_data.amount,
        "note": record_data.note
    }
    
    db_records = load_records()
    db_records.append(new_record)
    save_records(db_records)
    
    return RecordResponse(**new_record)


def get_record_by_id(record_id: int) -> Optional[RecordResponse]:
    """根据 ID 获取记录"""
    records = load_records()
    for record in records:
        if record['id'] == record_id:
            return RecordResponse(**record)
    return None


def list_records() -> RecordListResponse:
    """获取所有记录列表"""
    records = load_records()
    response_records = [RecordResponse(**r) for r in records]
    return RecordListResponse(records=response_records, total=len(records))


def update_record(record_id: int, record_data: RecordUpdate) -> Optional[RecordResponse]:
    """更新记录"""
    records = load_records()
    for i, record in enumerate(records):
        if record['id'] == record_id:
            # 构建更新数据，排除未设置字段
            update_dict = record_data.model_dump(exclude_unset=True)
            for key, value in update_dict.items():
                if value is not None:
                    records[i][key] = value
            
            save_records(records)
            return RecordResponse(**records[i])
    return None


def delete_record(record_id: int) -> bool:
    """删除记录"""
    records = load_records()
    original_count = len(records)
    records = [r for r in records if r['id'] != record_id]
    
    if len(records) == original_count:
        return False
    
    save_records(records)
    return True


def get_record_list_by_user(username: str) -> RecordListResponse:
    """获取指定用户的记录列表"""
    records = load_records()
    user_records = [r for r in records if r['user'] == username]
    response_records = [RecordResponse(**r) for r in user_records]
    return RecordListResponse(records=response_records, total=len(user_records))