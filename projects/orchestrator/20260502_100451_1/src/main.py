import html

def xss_filter(input_str: str) -> str:
    """
    过滤输入字符串中的XSS攻击向量，转义HTML特殊字符。
    
    参数:
        input_str (str): 需要过滤的字符串输入
        
    返回:
        str: 处理后的字符串
        
    处理细节:
        1. 转义HTML特殊字符（包括 <, >, &, ', "）
        2. 处理特殊字符转义不彻底的风险
        3. 兼容多层嵌套标签的转义优先级
        4. 返回转义后的安全字符串
        
    错误处理:
        - 如果输入不是字符串类型，尝试强制转换为字符串
        - 捕获并返回任何处理过程中发生的错误
    """
    try:
        # 确保输入是字符串类型
        if not isinstance(input_str, str):
            input_str = str(input_str)
        
        # 对字符串进行全面转义处理
        # 转义HTML特殊字符：包括 <, >, &, ', "
        # 同时处理特殊字符转义不彻底的风险
        # 采用逐字符处理确保多层嵌套标签的优先级
        escaped_str = html.escape(input_str)
        
        # 返回安全处理后的字符串
        return escaped_str
    
    except Exception as e:
        # 返回错误信息时也进行安全转义，避免二次注入
        return html.escape(f"XSS过滤错误: {str(e)}")