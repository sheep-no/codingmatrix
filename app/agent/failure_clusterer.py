"""
测试失败根因聚类模块

对批量测试失败进行分组，识别共同的错误类型和位置，减少修复次数。
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict
from collections import defaultdict

from app.utils.performance_metrics import metrics_collector

logger = logging.getLogger(__name__)


@dataclass
class FailureCluster:
    """失败集群"""
    error_type: str
    error_location: str
    error_keywords: List[str] = field(default_factory=list)
    tests: List[Dict] = field(default_factory=list)
    root_cause_hint: str = ""
    count: int = 0


class FailureClusterer:
    """测试失败聚类器"""

    # 错误类型提示映射
    ERROR_HINTS = {
        'TypeError': '类型不匹配，检查参数类型和返回值类型',
        'ValueError': '值无效，检查输入值的范围和格式',
        'AssertionError': '断言失败，检查预期值和实际值',
        'AttributeError': '属性不存在，检查对象是否有该属性',
        'KeyError': '键不存在，检查字典键是否正确',
        'IndexError': '索引越界，检查列表索引范围',
        'ImportError': '导入失败，检查模块路径和依赖',
        'ModuleNotFoundError': '模块未找到，检查是否安装了依赖',
        'RuntimeError': '运行时错误，检查逻辑流程',
        'Exception': '未知错误，需要详细分析 traceback',
    }

    def __init__(self):
        pass

    def cluster(self, test_results: List[Dict]) -> List[FailureCluster]:
        """
        聚类测试失败，识别共同根因

        Args:
            test_results: 测试结果列表，每个结果包含：
                - name: 测试名称
                - traceback: 错误堆栈
                - error_message: 错误信息

        Returns:
            失败集群列表
        """
        start_time = metrics_collector.start_timer('FailureClusterer')

        if not test_results:
            return []

        # 单个失败测试直接返回
        if len(test_results) == 1:
            result = test_results[0]
            error_type, error_location, keywords = self._parse_traceback(result.get('traceback', ''))
            hint = self._generate_hint(error_type, error_location)

            return [FailureCluster(
                error_type=error_type,
                error_location=error_location,
                error_keywords=keywords,
                tests=[{'name': result['name'], 'error': result.get('error_message', '')}],
                root_cause_hint=hint,
                count=1
            )]

        # 解析所有失败用例
        parsed_results = []
        for result in test_results:
            error_type, error_location, keywords = self._parse_traceback(result.get('traceback', ''))
            parsed_results.append({
                'name': result['name'],
                'error_type': error_type,
                'error_location': error_location,
                'error_keywords': keywords,
                'error_message': result.get('error_message', '')
            })

        # 聚类
        clusters_map = defaultdict(list)

        for parsed in parsed_results:
            # 集群键：错误类型 + 错误位置
            cluster_key = (parsed['error_type'], parsed['error_location'])
            clusters_map[cluster_key].append(parsed)

        # 生成集群结果
        clusters = []
        for (error_type, error_location), tests in clusters_map.items():
            # 合并关键词
            all_keywords = []
            for t in tests:
                all_keywords.extend(t['error_keywords'])
            unique_keywords = list(dict.fromkeys(all_keywords))[:5]  # 最多 5 个关键词

            # 生成根因提示
            hint = self._generate_hint(error_type, error_location)
            if len(tests) > 1:
                hint = f"此根因影响 {len(tests)} 个测试。{hint}"

            cluster = FailureCluster(
                error_type=error_type,
                error_location=error_location,
                error_keywords=unique_keywords,
                tests=[{'name': t['name'], 'error': t['error_message']} for t in tests],
                root_cause_hint=hint,
                count=len(tests)
            )
            clusters.append(cluster)

        # 控制集群数量（不超过失败测试数量的 50%）
        max_clusters = max(1, len(test_results) // 2)
        if len(clusters) > max_clusters:
            # 按测试数量排序，合并小集群
            clusters.sort(key=lambda c: c.count, reverse=True)

            # 保留主要集群，合并剩余的
            main_clusters = clusters[:max_clusters]
            small_clusters = clusters[max_clusters:]

            # 将小集群合并到最相似的主要集群
            for small in small_clusters:
                # 找到最相似的主要集群（相同错误类型）
                best_match = None
                for main in main_clusters:
                    if main.error_type == small.error_type:
                        best_match = main
                        break

                if best_match:
                    best_match.tests.extend(small.tests)
                    best_match.count += small.count
                else:
                    # 如果没有匹配的，添加到第一个集群
                    main_clusters[0].tests.extend(small.tests)
                    main_clusters[0].count += small.count

            clusters = main_clusters

        metrics_collector.end_timer('FailureClusterer', start_time, 'cluster', {'failures': len(test_results), 'clusters': len(clusters)})

        logger.info(
            f"测试失败聚类完成 | "
            f"失败测试：{len(test_results)} | "
            f"聚类数量：{len(clusters)} | "
            f"平均每个集群：{len(test_results) / len(clusters):.1f} 个测试"
        )

        return clusters

    def _parse_traceback(self, traceback: str) -> tuple:
        """
        解析 traceback，提取错误类型、位置和关键词

        Args:
            traceback: 错误堆栈字符串

        Returns:
            (error_type, error_location, keywords)
        """
        if not traceback:
            return ('Unknown', '', [])

        # 提取错误类型（最后一行）
        error_type = 'Unknown'
        error_match = re.search(r'^(\w+Error|\w+Exception):', traceback, re.MULTILINE)
        if error_match:
            error_type = error_match.group(1)

        # 提取错误位置（最后一个文件：行号）
        error_location = ''
        location_matches = re.findall(r'File "([^"]+)", line (\d+)', traceback)
        if location_matches:
            last_location = location_matches[-1]
            error_location = f"{last_location[0]}:{last_location[1]}"

        # 提取错误信息关键词
        keywords = []
        lines = traceback.split('\n')
        if lines:
            last_line = lines[-1].strip()
            # 提取前 50 字符作为关键词
            keywords = [last_line[:50]] if last_line else []

        return (error_type, error_location, keywords)

    def _generate_hint(self, error_type: str, error_location: str) -> str:
        """
        生成根因提示

        Args:
            error_type: 错误类型
            error_location: 错误位置

        Returns:
            根因提示字符串
        """
        hint = self.ERROR_HINTS.get(error_type, '未知错误，需要详细分析')

        if error_location:
            hint = f"在 {error_location} 处发生 {error_type}：{hint}"
        else:
            hint = f"发生 {error_type}：{hint}"

        return hint
