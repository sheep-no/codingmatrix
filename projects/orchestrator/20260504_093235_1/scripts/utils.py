# scripts/utils.py
"""
工具函数模块，包含辅助方法

该模块提供通用的辅助函数，用于处理日志记录、字符串操作等任务。
包含类型注解和必要的错误处理逻辑，确保代码健壮性。
"""

def safe_print(text: str) -> None:
    """
    安全打印文本，处理可能的异常

    尝试打印传入的文本内容，若发生异常则捕获并记录错误信息。
    
    Args:
        text: 需要打印的文本内容
        
    Raises:
        TypeError: 如果传入的参数不是字符串类型
    """
    try:
        if not isinstance(text, str):
            raise TypeError("输入参数必须是字符串类型")
        print(text)
    except Exception as e:
        # 记录错误日志（此处简化为控制台输出）
        print(f"打印失败: {str(e)}")

def format_greeting(name: str) -> str:
    """
    格式化问候语
    
    根据传入的名字生成标准问候语格式。
    若输入参数有问题，将返回错误信息。
    
    Args:
        name: 问候对象的名字
        
    Returns:
        格式化后的问候语或错误信息
        
    Raises:
        ValueError: 如果名字为空或包含非法字符
    """
    try:
        # 验证输入参数
        if not name or not name.isalpha():
            raise ValueError("名字必须是有效的字母字符串")
            
        return f"Hello, {name}!"
        
    except ValueError as ve:
        # 返回用户友好的错误信息
        return f"无效的名字输入: {str(ve)}"
    except Exception as e:
        # 捕获其他未预期的异常
        return f"发生未知错误: {str(e)}"

def create_temp_file(content: str, filename: str = "temp.txt") -> str:
    """
    创建临时文件
    
    将内容写入临时文件，返回文件路径。
    若写入失败或路径无效，将返回错误信息。
    
    Args:
        content: 要写入文件的内容
        filename: 临时文件名（默认为"temp.txt"）
        
    Returns:
        成功时返回文件路径，失败时返回错误信息
        
    Raises:
        FileNotFoundError: 如果无法创建指定路径的文件
    """
    try:
        with open(filename, 'w') as file:
            file.write(content)
        return f"临时文件创建成功: {filename}"
            
    except FileNotFoundError as fnfe:
        # 路径无效时的处理
        return f"文件路径无效: {str(fnfe)}"
    except PermissionError as pe:
        # 权限不足时的处理
        return f"没有文件写入权限: {str(pe)}"
    except Exception as e:
        # 捕获其他可能的异常
        return f"创建临时文件时发生错误: {str(e)}"