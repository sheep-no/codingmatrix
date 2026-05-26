"""
智能修改优化模块 - 性能验证测试

验证各模块的性能指标是否达到要求：
- ImpactAnalyzer: <3s (100 文件)
- ProjectProfiler: <10s (1000 文件)
- TestSelector: <1s
- FailureClusterer: <2s
"""
import asyncio
import time
import tempfile
import os
from pathlib import Path
from app.agent.impact_analyzer import ImpactAnalyzer
from app.agent.project_profiler import ProjectProfiler
from app.agent.test_selector import TestSelector
from app.agent.failure_clusterer import FailureClusterer
from app.utils.performance_metrics import metrics_collector


def create_test_files(base_dir: Path, count: int, prefix: str):
    """创建测试文件"""
    base_dir.mkdir(parents=True, exist_ok=True)
    
    for i in range(count):
        file_path = base_dir / f"{prefix}_{i:03d}.py"
        content = f'''
"""测试文件 {prefix} #{i}"""

def function_{i}():
    """测试函数"""
    return {i}

class Class_{i}:
    """测试类"""
    def __init__(self):
        self.value = {i}
    
    def method(self):
        return self.value
'''
        file_path.write_text(content)


async def test_impact_analyzer():
    """测试 ImpactAnalyzer 性能"""
    print("\n" + "="*60)
    print("测试 ImpactAnalyzer 性能")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "test_files"
        create_test_files(base_dir, 100, "test")
        
        # 创建修改文件
        modified_files = [f"test_{i:03d}.py" for i in range(10)]
        
        analyzer = ImpactAnalyzer(project_root=str(base_dir))
        
        start = time.time()
        result = analyzer.analyze(modified_files)
        elapsed = time.time() - start
        
        print(f"分析文件数：{len(modified_files)}")
        print(f"耗时：{elapsed*1000:.2f}ms")
        print(f"提取符号：{len(result.symbols) if hasattr(result, 'symbols') else 'N/A'}")
        print(f"✅ PASS" if elapsed < 3.0 else f"❌ FAIL (目标 <3s)")
        
        return elapsed < 3.0


async def test_project_profiler():
    """测试 ProjectProfiler 性能"""
    print("\n" + "="*60)
    print("测试 ProjectProfiler 性能")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "test_project"
        create_test_files(base_dir, 200, "module")
        
        # 创建分层结构
        (base_dir / "api").mkdir()
        (base_dir / "service").mkdir()
        (base_dir / "repository").mkdir()
        create_test_files(base_dir / "api", 50, "api")
        create_test_files(base_dir / "service", 50, "service")
        create_test_files(base_dir / "repository", 50, "repo")
        
        profiler = ProjectProfiler(project_root=str(base_dir))
        
        start = time.time()
        profile = profiler.profile(base_dir)
        elapsed = time.time() - start
        
        print(f"分析文件数：{sum(1 for _ in base_dir.rglob('*.py'))}")
        print(f"耗时：{elapsed*1000:.2f}ms")
        print(f"架构模式：{profile.architecture.pattern}")
        print(f"风险点：{len(profile.risk_areas.high_dependency)}")
        print(f"测试约定：{profile.test_patterns.test_location}")
        print(f"✅ PASS" if elapsed < 10.0 else f"❌ FAIL (目标 <10s)")
        
        return elapsed < 10.0


async def test_test_selector():
    """测试 TestSelector 性能"""
    print("\n" + "="*60)
    print("测试 TestSelector 性能")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "test_project"
        create_test_files(base_dir, 50, "module")
        
        # 创建测试文件
        test_dir = base_dir / "tests"
        test_dir.mkdir()
        create_test_files(test_dir, 30, "test")
        
        analyzer = ImpactAnalyzer(project_root=str(base_dir))
        modified_files = [f"module_{i:03d}.py" for i in range(5)]
        changes = analyzer.analyze(modified_files)
        
        profiler = ProjectProfiler(project_root=str(base_dir))
        profile = profiler.profile(base_dir)
        
        selector = TestSelector(project_root=str(base_dir))
        
        start = time.time()
        selected = selector.select_tests(changes, profile)
        elapsed = time.time() - start
        
        print(f"修改文件：{len(modified_files)}")
        print(f"选择测试：{len(selected)}")
        print(f"耗时：{elapsed*1000:.2f}ms")
        print(f"✅ PASS" if elapsed < 1.0 else f"❌ FAIL (目标 <1s)")
        
        return elapsed < 1.0


async def test_failure_clusterer():
    """测试 FailureClusterer 性能"""
    print("\n" + "="*60)
    print("测试 FailureClusterer 性能")
    print("="*60)
    
    # 模拟测试失败结果
    test_results = [
        {
            "name": f"test_function_{i}",
            "traceback": f"File \"test_module.py\", line {10+i}, in test_function_{i}\n    assert result == {i}\nAssertionError: assert {i+1} == {i}",
            "error_message": f"assert {i+1} == {i}"
        }
        for i in range(20)
    ]
    
    # 添加一些相同错误的测试
    for i in range(10):
        test_results.append({
            "name": f"test_api_{i}",
            "traceback": 'File "api_client.py", line 42, in request\n    raise ConnectionError("Connection timeout")\nConnectionError: Connection timeout',
            "error_message": "Connection timeout"
        })
    
    clusterer = FailureClusterer()
    
    start = time.time()
    clusters = clusterer.cluster(test_results)
    elapsed = time.time() - start
    
    print(f"失败测试数：{len(test_results)}")
    print(f"聚类数：{len(clusters)}")
    print(f"耗时：{elapsed*1000:.2f}ms")
    print(f"✅ PASS" if elapsed < 2.0 else f"❌ FAIL (目标 <2s)")
    
    return elapsed < 2.0


async def main():
    """运行所有性能测试"""
    print("\n" + "="*60)
    print("智能修改优化模块 - 性能验证测试")
    print("="*60)
    
    results = {
        "ImpactAnalyzer": await test_impact_analyzer(),
        "ProjectProfiler": await test_project_profiler(),
        "TestSelector": await test_test_selector(),
        "FailureClusterer": await test_failure_clusterer(),
    }
    
    print("\n" + "="*60)
    print("性能测试结果汇总")
    print("="*60)
    
    for module, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{module}: {status}")
    
    all_passed = all(results.values())
    print("\n" + "="*60)
    print(f"总体结果：{'✅ 所有测试通过' if all_passed else '❌ 部分测试失败'}")
    print("="*60)
    
    # 导出性能指标
    metrics = metrics_collector.export_metrics()
    print("\n性能指标:")
    for module, data in metrics.items():
        if data['total_calls'] > 0:
            print(f"  {module}: avg={data['avg_time_ms']:.2f}ms, calls={data['total_calls']}")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
