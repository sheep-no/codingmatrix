# src/utils.py
import html
import re

def escape_html(text: str) -> str:
    """
    对输入文本进行HTML特殊字符转义，防止XSS攻击。
    转义规则：
    - < 转义为 &lt;
    - > 转义为 &gt;
    - " 转义为 &quot;
    - ' 转义为 &apos;
    - & 转义为 &amp;
    
    参数:
        text (str): 需要转义的原始字符串
        
    返回:
        str: 转义后的安全字符串
        
    异常:
        ValueError: 当输入不是字符串类型时抛出
    """
    if not isinstance(text, str):
        raise ValueError("输入必须是字符串类型")
    # 使用标准库html.escape处理所有特殊字符
    return html.escape(text)

def contains_xss_pattern(text: str) -> bool:
    """
    检测输入文本是否包含潜在XSS攻击模式。
    检测范围包括：
    1. script标签（区分大小写）
    2. 事件处理属性（如onerror, onclick等）
    3. 可能的脚本注入模式（如eval(), alert()等）
    
    参数:
        text (str): 要检查的原始字符串
        
    返回:
        bool: 检测到XSS模式返回True，否则返回False
        
    异常:
        ValueError: 当输入不是字符串类型时抛出
    """
    if not isinstance(text, str):
        raise ValueError("输入必须是字符串类型")
    
    # 匹配script标签的正则表达式
    script_pattern = re.compile(r'<\s*script\s.*?>', re.IGNORECASE)
    # 匹配常见事件处理属性的正则表达式
    event_pattern = re.compile(r'onerror|onclick|onload|onfocus|onchange|onsubmit|onmouseover|onmousedown|onkeydown|onkeyup|onkeypress|oninput|onpropertychange|onpaste|oncut|oncopy|onopen|onbeforeload|onunreportederror|onbeforeunload|onbeforeprint|onafterprint|onbeforecopy|onaftercopy|onbeforecut|onaftercut|onbeforepaste|onafterpaste|onabort|onbegin|onbounce|oncanplay|oncanplaythrough|onchecking|onclose|oncomplete|oncuechange|oncontextmenu|oncontrolsin|onend|onerror|onflick|onfullscreenchange|onfullscreenerror|onhashchange|oninvalid|onkeydown|onkeypress|onkeyup|onloadstart|onloadend|onloadeddata|onloadedmetadata|onmousedown|onmousewheel|onmove|onpause|onplay|onplaying|onprogress|onratechange|onreadystatechange|onreset|onresize|onseeked|onseeking|onselect|onshow|onstalled|onscroll|onstart|onsubmit|ontimeupdate|onvolumechange|onwaiting', re.IGNORECASE)
    # 匹配常见脚本注入关键字的正则表达式
    script_keyword_pattern = re.compile(r'eval$$.*?$$|alert$$.*?$$|document$$write|location$$href|innerHTML', re.IGNORECASE)
    
    # 检查是否存在script标签、事件属性或脚本关键字
    if script_pattern.search(text) or event_pattern.search(text) or script_keyword_pattern.search(text):
        return True
    return False