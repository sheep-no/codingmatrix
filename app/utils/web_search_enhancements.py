"""
Web 搜索增强功能模块

包含：
1. 查询词增强
2. 结果去重
3. 质量评分
"""

import re
from typing import List


class SearchResult:
    """搜索结果项（用于类型提示的简化版本）"""
    def __init__(self, title: str, url: str, snippet: str, source: str = None, summary: str = None):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source = source
        self.summary = summary


# ============================================================================
# 查询词增强功能 - 通用框架
# ============================================================================

def is_chinese_query(query: str) -> bool:
    """判断是否为中文查询"""
    chinese_chars = sum(1 for c in query if '\u4e00' <= c <= '\u9fff')
    return chinese_chars > len(query) * 0.3


def is_technical_query(query: str) -> bool:
    """判断是否为技术问题"""
    tech_keywords = [
        'code', '编程', '代码', '开发', 'developer', 'github',
        'api', 'framework', 'library', '函数', '类', 'object',
        'python', 'java', 'javascript', 'typescript', 'react', 'vue', 'node'
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in tech_keywords)


def is_error_query(query: str) -> bool:
    """判断是否为错误相关问题"""
    error_keywords = [
        'error', 'exception', 'bug', '报错', '异常', 'failed',
        'fix', '解决', '问题', 'issue', 'traceback', 'attributeerror',
        'typeerror', 'valueerror', 'keyerror', 'importerror', 'syntaxerror'
    ]
    query_lower = query.lower().replace(' ', '').replace('_', '')
    return any(kw in query_lower for kw in error_keywords)


def enhance_query(query: str, prompt: str = "", enable_enhance: bool = True) -> str:
    """
    通用查询词增强 - 基于查询意图自动优化
    
    核心原则：
    1. 不确定时不增强 - 避免误判
    2. 优先级匹配 - 先匹配具体特征
    3. 可配置 - 允许用户控制
    
    Args:
        query: 原始查询词
        prompt: 完整提示词
        enable_enhance: 是否启用增强（默认 True）
    
    Returns:
        增强后的查询词
    """
    # 如果未启用增强，直接返回原查询
    if not enable_enhance:
        return query
    
    query = query.strip()
    full_text = f"{query} {prompt}".lower()
    
    # ========== 第 1 优先级：错误/异常问题（任何查询都可能遇到） ==========
    # 检查是否为错误相关问题，优先 StackOverflow
    if is_error_query(query):
        if "site:stackoverflow.com" not in query:
            return f"{query} site:stackoverflow.com solutions error fix"
        return query
    
    # ========== 第 2 优先级：明确的查询意图 ==========
    # 这些意图明确，可以安全增强
    
    # 技术问题 → GitHub/StackOverflow
    if is_technical_query(full_text):
        # 代码相关
        if any(kw in full_text for kw in ['代码', '源码', 'code', 'github', 'repository', '项目']):
            if "site:github.com" not in query:
                return f"{query} site:github.com"
            return query
        # API/框架
        if any(kw in full_text for kw in ['api', 'framework', '库', 'library', 'sdk']):
            if "official" not in query and "site:github.com" not in query:
                return f"{query} official documentation OR site:github.com"
            return query
        # 错误/异常
        if is_error_query(query):
            if "site:stackoverflow.com" not in query:
                return f"{query} site:stackoverflow.com solutions error fix"
            return query
        # 一般技术问题
        if "site:github.com" not in query and "site:stackoverflow.com" not in query:
            return f"{query} tutorial site:github.com OR site:stackoverflow.com"
        return query
    
    # 政府/政策类 → gov.cn
    gov_keywords = ['政府', '政策', '规定', '办法', '条例', '通知', '公告', '国务院', '发改委']
    if any(kw in query for kw in gov_keywords):
        if "site:gov.cn" not in query:
            return f"{query} site:gov.cn"
        return query
    
    # 企业/商业类 → 官网
    company_keywords = ['公司', '企业', '集团', '股份', '有限', '注册资本', '法人']
    if any(kw in query for kw in company_keywords):
        if "官网" not in query:
            return f"{query} 官网"
        return query
    
    # 教程/学习类 → guide
    if any(kw in query for kw in ['教程', 'tutorial', '入门', 'guide', '学习', '怎么学']):
        if "guide" not in query.lower():
            current_year = 2025
            return f"{query} complete guide {current_year} {current_year-1}"
        return query
    
    # 新闻/时效类 → 新闻站点
    news_keywords = ['新闻', 'news', '最新', 'recent', 'break']
    if any(kw in query for kw in news_keywords):
        if "site:reuters.com" not in query and "site:bloomberg.com" not in query:
            return f"{query} site:reuters.com OR site:bloomberg.com OR site:theguardian.com"
        return query
    
    # ========== 第 2 优先级：需要特殊处理的查询 ==========
    # 学校查询 → 提取学校名（避免长查询词）
    school_keywords = ['学院', '大学', '学校', '职业技术学院']
    if any(kw in query for kw in school_keywords):
        # 只有明确包含学校关键词时才处理
        school_name = _extract_school_name(query)
        if school_name and school_name != query:  # 避免无变化
            return f"{school_name} 官网"
        # 如果无法提取，返回原查询（不强行添加"官网"）
        return query
    
    # ========== 第 3 优先级：其他查询 ==========
    # 默认返回原查询（不增强）
    return query


def _extract_school_name(query: str) -> str:
    """
    从查询词中提取学校名（通用方法）
    
    原则：
    1. 只提取第一个匹配的学校名
    2. 去掉后续可能的专业/描述词
    3. 太短（<4 字）或太长（>20 字）则认为无效
    """
    # 常见学校名结尾
    school_endings = ['职业技术学院', '学院', '大学', '学校']
    
    for ending in school_endings:
        if ending in query:
            # 找到学校名结尾的位置
            idx = query.find(ending)
            school_name = query[:idx + len(ending)]
            
            # 长度检查
            if 4 <= len(school_name) <= 20:
                return school_name
    
    return ""
    
    # 检查是否匹配学校关键词
    is_school_query = any(kw in query for kw in school_keywords)
    
    if is_school_query:
        # 策略：只提取学校名，不加专业名（避免 Bing 跑偏到旅游）
        # 例如："广州铁路职业技术学院计算机应用技术专业" → "广州铁路职业技术学院"
        school_name = _extract_school_name(query)
        if school_name:
            return f"{school_name} 官网"
        if "官网" not in query:
            return f"{query} 官网"
        return query
    
    # ========== 2. 政府/政策类查询 ==========
    gov_keywords = ['政府', '政策', '规定', '办法', '条例', '通知', '公告', '国务院', '发改委']
    if any(kw in query for kw in gov_keywords):
        if "site:gov.cn" not in query:
            return f"{query} site:gov.cn"
        return query
    
    # ========== 3. 企业/商业类查询 ==========
    company_keywords = ['公司', '企业', '集团', '股份', '有限', '注册资本', '法人']
    if any(kw in query for kw in company_keywords):
        if "官网" not in query:
            return f"{query} 官网"
        return query
    
    # ========== 4. 医疗/健康类查询 ==========
    medical_keywords = ['病', '症状', '治疗', '药物', '医院', '医生', '健康', '医学']
    if any(kw in query for kw in medical_keywords):
        if "治疗" not in query:
            return f"{query} 治疗方法"
        return query
    
    # ========== 5. 错误/异常问题 ==========
    if is_error_query(query):
        if "site:stackoverflow.com" not in query:
            return f"{query} site:stackoverflow.com solutions error fix"
        return query
    
    # ========== 5b. 技术问题 ==========
    if is_technical_query(full_text):
        # 代码相关 → GitHub
        if any(kw in full_text for kw in ['代码', '源码', 'code', 'github', 'repository', '项目']):
            if "site:github.com" not in query:
                return f"{query} site:github.com"
            return query
        # API/框架 → 官方文档
        if any(kw in full_text for kw in ['api', 'framework', '库', 'library', 'sdk']):
            if "official" not in query and "site:github.com" not in query:
                return f"{query} official documentation OR site:github.com"
            return query
        # 一般技术问题 → GitHub + SO
        if "site:github.com" not in query and "site:stackoverflow.com" not in query:
            return f"{query} tutorial site:github.com OR site:stackoverflow.com"
        return query
    
    # ========== 6. 教程/学习类 ==========
    if any(kw in query for kw in ['教程', 'tutorial', '入门', 'guide', '学习', '怎么学']):
        if "guide" not in query.lower():
            current_year = 2025
            return f"{query} complete guide {current_year} {current_year-1}"
        return query
    
    # ========== 7. 新闻/时效类 ==========
    news_keywords = ['新闻', 'news', '最新', 'recent', 'break']
    if any(kw in query for kw in news_keywords):
        if "site:reuters.com" not in query and "site:bloomberg.com" not in query:
            return f"{query} site:reuters.com OR site:bloomberg.com OR site:theguardian.com"
        return query
    
    # ========== 8. 一般查询 ==========
    return query


def _extract_school_name(query: str) -> str:
    """从查询词中提取学校名（去掉专业名等后缀）"""
    # 常见学校名结尾
    school_endings = ['学院', '大学', '学校', '职业技术学院']
    
    for ending in school_endings:
        if ending in query:
            # 找到学校名结尾的位置
            idx = query.find(ending)
            school_name = query[:idx + len(ending)]
            
            # 如果学校名太短（少于 4 字），说明提取失败
            if len(school_name) >= 4:
                return school_name
    
    return ""


# ============================================================================
# 搜索结果去重和质量评分
# ============================================================================

def calculate_similarity(s1: str, s2: str) -> float:
    """
    计算两个字符串的相似度（Jaccard 相似度）
    """
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def deduplicate_results(results: List[SearchResult], threshold: float = 0.85) -> List[SearchResult]:
    """
    基于标题和 URL 的去重
    
    Args:
        results: 搜索结果列表
        threshold: 相似度阈值（0-1，越接近 1 越严格）
    
    Returns:
        去重后的结果
    """
    unique_results = []
    seen_urls = set()
    seen_titles = []
    
    for result in results:
        # URL 去重（最简单有效）
        base_url = result.url.split('?')[0]
        if base_url in seen_urls:
            continue
        
        # 标题相似度去重
        is_duplicate = False
        for seen_title in seen_titles:
            similarity = calculate_similarity(result.title, seen_title)
            if similarity > threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_results.append(result)
            seen_urls.add(base_url)
            seen_titles.append(result.title)
    
    return unique_results


def score_search_result(result: SearchResult) -> float:
    """
    给搜索结果打分，优先展示高质量结果
    """
    score = 0.0
    
    # 域名权威性（最高 0.4 分）
    high_quality_domains = [
        'github.com', 'stackoverflow.com', 'medium.com',
        'zhihu.com', 'juejin.cn', 'docs.python.org',
        'reuters.com', 'bloomberg.com', 'theguardian.com'
    ]
    for domain in high_quality_domains:
        if domain in result.url.lower():
            score += 0.4
            break
    
    # 标题质量（最高 0.3 分）
    if len(result.title) > 20 and len(result.title) < 100:
        score += 0.1
    title_lower = result.title.lower()
    if any(kw in title_lower for kw in ['tutorial', 'guide', 'official', '文档', '教程', 'documentation']):
        score += 0.2
    
    # 摘要质量（最高 0.2 分）
    if result.snippet:
        if len(result.snippet) > 50:
            score += 0.1
        if len(result.snippet) > 100:
            score += 0.1
    
    # 时效性（最高 0.1 分）
    date_pattern = r'\d{4}[-/]\d{2}[-/]\d{2}'
    if re.search(date_pattern, result.url) or re.search(date_pattern, result.snippet or ''):
        score += 0.1
    
    return score


def sort_by_quality(results: List[SearchResult]) -> List[SearchResult]:
    """按质量评分排序（从高到低）"""
    return sorted(results, key=score_search_result, reverse=True)
