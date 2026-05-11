# app/routes.py
from flask import Blueprint, request, jsonify
from .models import IncrementalData
from app import db
from typing import Tuple, Dict, Any
import logging

# 初始化数据路由蓝图
data_routes = Blueprint('data_routes', __name__)

@data_routes.route('/api/v1/data', methods=['POST'])
def create_data() -> Tuple[Dict[str, Any], int]:
    """
    创建新的增量数据条目
    
    接收查询参数中的data字段，将数据存储到数据库并返回生成的ID。
    查询参数格式：/api/v1/data?data=示例数据
    
    返回:
        200: 成功创建数据，返回包含ID的JSON响应
        400: 缺少必要参数时返回错误信息
        500: 数据库操作失败时返回内部服务器错误
    """
    try:
        # 从查询参数中获取数据
        data_param = request.args.get('data')
        
        if not data_param:
            return {'error': 'Missing required "data" query parameter'}, 400
            
        # 创建新的数据条目
        new_entry = IncrementalData(data=data_param)
        db.session.add(new_entry)
        db.session.commit()
        
        # 返回生成的ID
        return {'id': new_entry.id}, 200
        
    except Exception as e:
        # 记录异常信息
        logging.error(f"Failed to create data entry: {str(e)}")
        db.session.rollback()
        return {'error': 'Failed to create data entry'}, 500

@data_routes.route('/api/v1/data', methods=['GET'])
def get_data() -> Tuple[Dict[str, Any], int]:
    """
    获取所有增量数据列表
    
    返回包含所有数据条目的JSON数组，每个条目包含id、data和created_at字段。
    
    返回:
        200: 成功获取数据列表
        500: 数据库查询失败时返回内部服务器错误
    """
    try:
        # 查询所有数据条目
        entries = IncrementalData.query.all()
        
        # 构建响应数据
        result = [
            {
                'id': entry.id,
                'data': entry.data,
                'created_at': entry.created_at.isoformat()  # 转换为ISO格式时间字符串
            }
            for entry in entries
        ]
        
        return jsonify(result), 200
        
    except Exception as e:
        # 记录异常信息
        logging.error(f"Failed to retrieve data entries: {str(e)}")
        return {'error': 'Failed to retrieve data entries'}, 500