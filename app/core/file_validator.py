"""
文件上传安全验证模块
"""
import re
import zipfile
import io
from pathlib import Path
from typing import Tuple


# 允许的 MIME 类型白名单
ALLOWED_MIME_TYPES = {
    # 图片
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    # 文档
    'application/pdf',
    # 文本
    'text/plain', 'text/markdown', 'text/html', 'text/css',
    # 代码
    'application/javascript', 'application/x-javascript', 'text/javascript',
    'application/x-python-code', 'text/x-python',
    'application/java', 'text/x-java',
    'application/json', 'application/xml', 'text/xml',
    'application/x-yaml', 'text/yaml',
    # 压缩包
    'application/zip', 'application/x-zip-compressed',
    'application/x-tar', 'application/x-gzip',
    'application/x-rar-compressed',
    'application/x-7z-compressed'
}

# 文件扩展名与 MIME 类型映射
EXTENSION_MIME_MAP = {
    '.py': ['text/x-python', 'application/x-python-code'],
    '.js': ['application/javascript', 'text/javascript'],
    '.ts': ['application/typescript'],
    '.java': ['text/x-java', 'application/java'],
    '.json': ['application/json'],
    '.yaml': ['application/x-yaml', 'text/yaml'],
    '.yml': ['application/x-yaml', 'text/yaml'],
    '.xml': ['application/xml', 'text/xml'],
    '.html': ['text/html'],
    '.css': ['text/css'],
    '.md': ['text/markdown', 'text/plain'],
    '.txt': ['text/plain'],
    '.pdf': ['application/pdf'],
    '.zip': ['application/zip', 'application/x-zip-compressed'],
    '.tar': ['application/x-tar'],
    '.gz': ['application/x-gzip'],
    '.jpg': ['image/jpeg'],
    '.jpeg': ['image/jpeg'],
    '.png': ['image/png'],
    '.gif': ['image/gif'],
    '.svg': ['image/svg+xml'],
    '.webp': ['image/webp']
}


def validate_file_content(content: bytes, filename: str) -> Tuple[str, str]:
    """
    验证文件内容和类型
    
    Args:
        content: 文件内容
        filename: 文件名
    
    Returns:
        Tuple[str, str]: (检测到的 MIME 类型，安全的文件名)
    
    Raises:
        ValueError: 文件验证失败
    """
    from app.core.config import settings
    
    # 1. 检查空文件
    if len(content) == 0:
        raise ValueError("文件不能为空")
    
    # 2. 检查文件大小
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise ValueError(f"文件大小超过限制 ({settings.max_upload_size_mb}MB)")
    
    # 3. 检查文件扩展名
    file_ext = Path(filename).suffix.lower()
    if not file_ext:
        raise ValueError("文件必须包含扩展名")
    
    # 4. 检测文件真实类型（通过文件头魔数）
    detected_mime = detect_mime_type(content)
    
    # 5. 验证 MIME 类型是否在白名单中
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValueError(f"不允许的文件类型：{detected_mime}")
    
    # 6. 验证扩展名与 MIME 类型是否匹配
    if file_ext in EXTENSION_MIME_MAP:
        allowed_mimes = EXTENSION_MIME_MAP[file_ext]
        if detected_mime not in allowed_mimes:
            raise ValueError(
                f"文件扩展名 ({file_ext}) 与内容类型 ({detected_mime}) 不匹配"
            )
    
    # 7. 特殊文件类型深度检查
    if file_ext == '.svg':
        if not validate_svg_content(content):
            raise ValueError("SVG 文件包含不允许的内容（如脚本、外部实体等）")
    
    if file_ext in ['.zip', '.tar', '.gz', '.rar', '.7z']:
        if not validate_archive_content(content, file_ext):
            raise ValueError("压缩包包含不允许的文件类型")
    
    # 8. 生成安全的文件名
    safe_filename = generate_safe_filename(filename)
    
    return detected_mime, safe_filename


def detect_mime_type(content: bytes) -> str:
    """
    通过文件头魔数检测文件类型
    
    Args:
        content: 文件内容（至少读取前 2048 字节）
    
    Returns:
        str: 检测到的 MIME 类型
    """
    # 常见文件魔数
    magic_signatures = {
        b'\x89PNG\r\n\x1a\n': 'image/png',
        b'\xff\xd8\xff': 'image/jpeg',
        b'GIF87a': 'image/gif',
        b'GIF89a': 'image/gif',
        b'%PDF': 'application/pdf',
        b'PK\x03\x04': 'application/zip',
        b'PK\x05\x06': 'application/zip',  # 空压缩包
        b'ustar': 'application/x-tar',  # tar 文件包含此字符串
        b'\x1f\x8b\x08': 'application/x-gzip',
        b'7z\xbc\xaf\x27\x1c': 'application/x-7z-compressed',
        b'Rar!\x1a\x07': 'application/x-rar-compressed',
        b'{': 'application/json',  # JSON
        b'<?xml': 'application/xml',
        b'<svg': 'image/svg+xml',
        b'<!DOCTYPE html': 'text/html',
        b'<html': 'text/html',
        b'#': 'text/plain',  # 脚本/配置文件
    }
    
    # 检查前 16 字节
    header = content[:16]
    for magic, mime in magic_signatures.items():
        if header.startswith(magic):
            return mime
    
    # 检查是否包含特定字符串（对于文本文件）
    sample = content[:2048].decode('utf-8', errors='ignore')
    
    if sample.strip().startswith('{') and sample.strip().endswith('}'):
        try:
            import json
            json.loads(sample.strip())
            return 'application/json'
        except:
            pass
    
    if '<svg' in sample.lower():
        return 'image/svg+xml'
    
    if '<?xml' in sample:
        return 'application/xml'
    
    # 默认返回二进制流
    return 'application/octet-stream'


def validate_svg_content(content: bytes) -> bool:
    """
    验证 SVG 文件内容安全性
    
    Args:
        content: SVG 文件内容
    
    Returns:
        bool: 是否安全
    """
    try:
        content_str = content.decode('utf-8', errors='ignore').lower()
        
        # 禁止的危险模式
        dangerous_patterns = [
            '<script',
            'javascript:',
            'vbscript:',
            'onerror=',
            'onload=',
            'onclick=',
            'onmouseover=',
            'onmouseout=',
            'onfocus=',
            'onblur=',
            '<!entity',
            '<!doctype',
            'system',
            'public',
            '<iframe',
            '<object',
            '<embed'
        ]
        
        for pattern in dangerous_patterns:
            if pattern in content_str:
                print(f"[WARNING] 检测到 SVG 中的危险模式：{pattern}")
                return False
        
        return True
    except Exception as e:
        print(f"SVG 验证错误：{e}")
        return False


def validate_archive_content(content: bytes, archive_type: str) -> bool:
    """
    验证压缩包内容
    
    Args:
        content: 压缩包内容
        archive_type: 压缩包类型（.zip, .tar, .gz 等）
    
    Returns:
        bool: 是否安全
    """
    try:
        if archive_type == '.zip':
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    # 解析为 Path 后检查每个组件
                    parts = Path(name).parts
                    for part in parts:
                        if part == '..':
                            print(f"[WARNING] 检测到路径穿越：{name}")
                            return False
                        if not is_safe_filename(part):
                            print(f"[WARNING] 检测到不安全的文件名组件：{part}（来自 {name}）")
                            return False
                    
                    # 检查文件扩展名
                    ext = Path(name).suffix.lower()
                    # 这里可以根据需要限制压缩包内的文件类型
                    # 暂时允许所有类型
        return True
    except Exception as e:
        print(f"压缩包验证错误：{e}")
        return False


def is_safe_filename(filename: str) -> bool:
    """
    检查文件名是否安全
    
    Args:
        filename: 文件名
    
    Returns:
        bool: 是否安全
    """
    # 不允许路径分隔符
    if '/' in filename or '\\' in filename:
        return False
    
    # 不允许父目录引用
    if '..' in filename:
        return False
    
    # 不允许特殊字符
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\x00']
    for char in dangerous_chars:
        if char in filename:
            return False
    
    # 长度限制
    if len(filename) > 255:
        return False
    
    return True


def generate_safe_filename(original_filename: str) -> str:
    """
    生成安全的文件名
    
    Args:
        original_filename: 原始文件名
    
    Returns:
        str: 安全的文件名
    """
    import uuid
    
    # 获取扩展名
    ext = Path(original_filename).suffix.lower()
    
    # 验证扩展名
    if ext and not re.match(r'^\.[a-z0-9]{2,10}$', ext):
        raise ValueError(f"无效的扩展名：{ext}")
    
    # 生成 UUID 作为文件名
    safe_name = f"{uuid.uuid4().hex}{ext}"
    
    return safe_name


# 测试代码
if __name__ == "__main__":
    # 测试 MIME 类型检测
    test_cases = [
        (b'\x89PNG\r\n\x1a\n' + b'\x00' * 100, 'test.png', 'image/png'),
        (b'%PDF-1.4' + b'\x00' * 100, 'test.pdf', 'application/pdf'),
        (b'PK\x03\x04' + b'\x00' * 100, 'test.zip', 'application/zip'),
        (b'{"test": true}', 'test.json', 'application/json'),
    ]
    
    for content, filename, expected_mime in test_cases:
        detected = detect_mime_type(content)
        assert detected == expected_mime, f"Expected {expected_mime}, got {detected}"
        print(f"✓ {filename}: {detected}")
    
    print("\n所有 MIME 类型检测测试通过!")
