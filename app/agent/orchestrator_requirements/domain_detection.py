from typing import List, Dict

DOMAIN_KEYWORDS = {
    "banking": ["银行", "金融", "转账", "存款", "贷款", "账户", "支付", "理财", "信贷", "风控"],
    "ecommerce": ["电商", "商城", "购物", "商品", "订单", "库存", "物流", "促销", "购物车", "支付"],
    "cms": ["cms", "内容管理", "文章", "发布", "编辑", "博客", "新闻", "媒体", "栏目", "评论"],
    "saas": ["saas", "后台", "管理平台", "租户", "订阅", "计费", "套餐", "workspace", "组织"],
    "social": ["社交", "聊天", "朋友圈", "消息", "关注", "粉丝", "动态", "通知", "群组", "好友"],
    "dashboard": ["大屏", "数据大屏", "报表", "可视化", "监控", "统计", "图表", "dashboard", "bi"],
    "education": ["教育", "课程", "学生", "教师", "考试", "作业", "班级", "成绩", "在线学习"],
    "healthcare": ["医疗", "健康", "挂号", "病历", "处方", "诊断", "体检", "医院", "医生", "患者"],
    "iot": ["iot", "物联网", "传感器", "设备", "智能家居", "采集", "告警", "远程控制"],
    "erp": ["erp", "进销存", "采购", "销售", "仓库", "财务", "报表", "审批", "流程"],
}


def _detect_domains(requirement: str) -> List[str]:
    req_lower = requirement.lower()

    scored = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in req_lower)
        if score >= 1:
            scored.append((domain, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    domains = []
    for domain, score in scored:
        if score >= 2:
            domains.append(domain)
        elif score >= 1 and len(domains) < 2:
            domains.append(domain)

    return domains[:3]


def _detect_domain(requirement: str) -> str:
    domains = _detect_domains(requirement)
    return domains[0] if domains else ""