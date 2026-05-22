"""
智能测试过滤模块

基于目录关联、高依赖模块和冒烟测试三层策略，选择最小但充分的测试集。
"""
import os
import logging
from pathlib import Path
from typing import List, Optional, Set

from app.utils.performance_metrics import metrics_collector
from .impact_analyzer import ChangeSummary
from .project_profiler import ProjectProfile

logger = logging.getLogger(__name__)


class TestSelector:
    """智能测试选择器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        
    def select_tests(self, changes: ChangeSummary, profile: ProjectProfile) -> List[str]:
        """
        选择相关测试用例
        
        Args:
            changes: 变更摘要
            profile: 项目指纹
            
        Returns:
            测试文件路径列表
        """
        start_time = metrics_collector.start_timer('TestSelector')
        selected_tests = []
        
        # 第 1 层：同目录测试
        same_dir_tests = self._select_same_directory_tests(changes.modified_files, profile)
        selected_tests.extend(same_dir_tests)
        
        # 第 2 层：高依赖模块测试
        high_dep_tests = self._select_high_dependency_tests(changes, profile)
        selected_tests.extend(high_dep_tests)
        
        # 第 3 层：冒烟测试
        smoke_tests = self._select_smoke_tests(profile)
        selected_tests.extend(smoke_tests)
        
        # 去重
        unique_tests = list(dict.fromkeys(selected_tests))
        
        # 记录测试覆盖率
        total_tests = len(self._select_all_tests(profile))
        coverage = (len(unique_tests) / total_tests * 100) if total_tests > 0 else 0
        metrics_collector.record_test_coverage('TestSelector', coverage)
        metrics_collector.end_timer('TestSelector', start_time, 'select_tests', {'selected': len(unique_tests), 'coverage': coverage})
        
        # 回退逻辑：如果没有选择到任何测试，运行全部测试
        if not unique_tests:
            logger.warning("智能测试过滤未选择到任何测试，回退到运行全部测试")
            unique_tests = self._select_all_tests(profile)
        
        logger.info(
            f"智能测试过滤完成 | "
            f"同目录测试：{len(same_dir_tests)} | "
            f"高依赖测试：{len(high_dep_tests)} | "
            f"冒烟测试：{len(smoke_tests)} | "
            f"最终选择：{len(unique_tests)}"
        )
        
        return unique_tests
    
    def _select_same_directory_tests(self, modified_files: List[str], profile: ProjectProfile) -> List[str]:
        """
        选择与修改文件同目录的测试
        
        Args:
            modified_files: 修改的文件列表
            profile: 项目指纹
            
        Returns:
            测试文件列表
        """
        tests = []
        test_dir = profile.test_patterns.test_location
        naming = profile.test_patterns.naming_convention
        
        for file_path in modified_files:
            # 获取文件所在目录
            file_dir = os.path.dirname(file_path)
            
            # 映射到测试目录
            test_path = os.path.join(test_dir, file_dir)
            full_test_path = self.project_root / test_path
            
            if full_test_path.exists() and full_test_path.is_dir():
                # 查找测试文件
                if naming == "test_*.py":
                    test_files = list(full_test_path.glob('test_*.py'))
                else:
                    test_files = list(full_test_path.glob('*_test.py'))
                
                for tf in test_files:
                    tests.append(str(tf.relative_to(self.project_root)))
        
        return tests
    
    def _select_high_dependency_tests(self, changes: ChangeSummary, profile: ProjectProfile) -> List[str]:
        """
        选择与高风险模块相关的测试
        
        Args:
            changes: 变更摘要
            profile: 项目指纹
            
        Returns:
            测试文件列表
        """
        tests = []
        risk_files = profile.risk_areas.high_dependency + profile.risk_areas.security_critical
        
        # 检查是否修改了高风险模块
        modified_risk_files = [
            f for f in changes.modified_files
            if any(risk in f for risk in risk_files)
        ]
        
        if modified_risk_files:
            # 选择所有相关测试
            test_dir = profile.test_patterns.test_location
            full_test_dir = self.project_root / test_dir
            
            if full_test_dir.exists():
                naming = profile.test_patterns.naming_convention
                if naming == "test_*.py":
                    test_files = list(full_test_dir.rglob('test_*.py'))
                else:
                    test_files = list(full_test_dir.rglob('*_test.py'))
                
                for tf in test_files:
                    tests.append(str(tf.relative_to(self.project_root)))
        
        return tests
    
    def _select_smoke_tests(self, profile: ProjectProfile) -> List[str]:
        """
        选择冒烟测试
        
        Args:
            profile: 项目指纹
            
        Returns:
            测试文件列表（最多 10 个）
        """
        smoke_keywords = ['smoke', 'core', 'basic', 'critical', 'essential']
        tests = []
        
        test_dir = profile.test_patterns.test_location
        full_test_dir = self.project_root / test_dir
        
        if not full_test_dir.exists():
            return tests
        
        naming = profile.test_patterns.naming_convention
        if naming == "test_*.py":
            all_tests = list(full_test_dir.rglob('test_*.py'))
        else:
            all_tests = list(full_test_dir.rglob('*_test.py'))
        
        # 优先选择名称包含冒烟关键字的测试
        for tf in all_tests:
            if any(kw in tf.name.lower() for kw in smoke_keywords):
                tests.append(str(tf.relative_to(self.project_root)))
                if len(tests) >= 10:
                    break
        
        # 如果冒烟测试不足 5 个，补充前几个测试
        if len(tests) < 5:
            for tf in all_tests:
                test_rel = str(tf.relative_to(self.project_root))
                if test_rel not in tests:
                    tests.append(test_rel)
                    if len(tests) >= 5:
                        break
        
        return tests[:10]  # 最多 10 个
    
    def _select_all_tests(self, profile: ProjectProfile) -> List[str]:
        """
        选择所有测试（回退逻辑）
        
        Args:
            profile: 项目指纹
            
        Returns:
            所有测试文件列表
        """
        tests = []
        test_dir = profile.test_patterns.test_location
        full_test_dir = self.project_root / test_dir
        
        if not full_test_dir.exists():
            return tests
        
        naming = profile.test_patterns.naming_convention
        if naming == "test_*.py":
            test_files = list(full_test_dir.rglob('test_*.py'))
        else:
            test_files = list(full_test_dir.rglob('*_test.py'))
        
        for tf in test_files:
            tests.append(str(tf.relative_to(self.project_root)))
        
        return tests
