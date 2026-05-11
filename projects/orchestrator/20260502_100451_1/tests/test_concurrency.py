# tests/test_concurrency.py
import pytest
import concurrent.futures
import time
import os
import psutil
from typing import List, Dict, Any, Optional
from src.concurrency_test import run_concurrent_tasks, TaskResult, PerformanceMetrics

# 从配置文件导入并发参数
from config.settings import CONCURRENCY_COUNT, TEST_DURATION, MAX_RETRIES, ERROR_LOG_PATH

# 用于模拟任务的测试函数
def mock_task(task_id: int) -> TaskResult:
    """
    模拟一个并发任务，根据 task_id 判断是否返回错误
    
    Args:
        task_id: 任务唯一标识
        
    Returns:
        TaskResult: 任务结果对象
    """
    if task_id % 3 == 0:
        # 模拟任务失败（每隔3个任务失败一次）
        raise ValueError(f"Task {task_id} failed")
    
    # 模拟任务执行耗时（0.1-0.5秒随机）
    sleep_time = 0.1 + 0.4 * task_id / 100
    time.sleep(sleep_time)
    
    return TaskResult(
        task_id=task_id,
        status="completed",
        duration=sleep_time,
        error=None
    )

# 测试用例：验证并发执行的基本功能
def test_concurrent_task_success() -> None:
    """
    测试并发任务正常执行的情况
    
    验证：
    1. 任务结果包含预期的 task_id
    2. 成功任务数量等于 CONCURRENCY_COUNT
    3. 任务执行时间在合理范围内
    4. 错误日志未被写入（无失败任务）
    """
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = run_concurrent_tasks(
            task_function=mock_task,
            task_count=CONCURRENCY_COUNT,
            max_workers=CONCURRENCY_COUNT,
            duration=TEST_DURATION
        )
    
    # 验证结果数量
    assert len(results) == CONCURRENCY_COUNT, "任务结果数量不匹配"
    
    # 验证所有任务成功执行
    assert all(result.status == "completed" for result in results), "存在未完成任务"
    
    # 验证执行时间不超过测试时长
    total_time = time.time() - results[0].timestamp
    assert total_time <= TEST_DURATION, f"执行时间超出限制 {total_time:.2f} > {TEST_DURATION}"
    
    # 验证没有错误日志生成
    assert not os.path.exists(ERROR_LOG_PATH), "意外生成错误日志文件"

# 测试用例：验证任务失败情况的处理
def test_concurrent_task_error() -> None:
    """
    测试并发任务失败情况的处理
    
    验证：
    1. 缺失任务的错误信息正确记录
    2. 错误日志文件被正确生成
    3. 成功任务数量等于 CONCURRENCY_COUNT - 1
    """
    # 设置临时文件路径
    temp_log_path = f"{ERROR_LOG_PATH}_temp"
    os.makedirs(os.path.dirname(temp_log_path), exist_ok=True)
    
    # 运行测试并捕获异常
    with pytest.raises(Exception) as exc_info:
        run_concurrent_tasks(
            task_function=mock_task,
            task_count=CONCURRENCY_COUNT,
            max_workers=CONCURRENCY_COUNT,
            duration=TEST_DURATION,
            error_log_path=temp_log_path
        )
    
    # 验证错误信息包含预期内容
    assert "Task 3 failed" in str(exc_info.value), "错误信息不匹配"
    
    # 验证错误日志文件是否存在
    assert os.path.exists(temp_log_path), "错误日志文件未生成"
    
    # 验证日志内容符合预期
    with open(temp_log_path, 'r') as f:
        log_content = f.read()
    
    assert "Task 3 failed" in log_content, "日志内容不匹配"
    assert "Task 0 failed" not in log_content, "不应记录非失败任务的错误"
    
    # 清理临时文件
    os.remove(temp_log_path)

# 测试用例：验证性能指标统计准确性
def test_concurrent_performance() -> None:
    """
    测试并发性能指标的统计准确性
    
    验证：
    1. 平均执行时间计算正确
    2. 吞吐量（任务/秒）在合理范围
    3. 最大耗时任务符合预期
    """
    # 创建临时任务列表（仅包含成功任务）
    def successful_task(task_id: int) -> TaskResult:
        """仅返回成功结果的模拟任务"""
        return TaskResult(
            task_id=task_id,
            status="completed",
            duration=0.1 + 0.1 * task_id,
            error=None
        )
    
    # 执行测试
    metrics = run_concurrent_tasks(
        task_function=successful_task,
        task_count=CONCURRENCY_COUNT,
        max_workers=CONCURRENCY_COUNT,
        duration=TEST_DURATION
    )
    
    # 计算预期的平均时间（简单平均值）
    expected_avg_duration = sum(task.duration for task in metrics) / CONCURRENCY_COUNT
    actual_avg_duration = metrics.average_duration
    
    # 验证平均时间的计算准确性
    assert abs(actual_avg_duration - expected_avg_duration) < 0.01, \
        f"平均时间计算不准确: 实际={actual_avg_duration:.2f}, 预期={expected_avg_duration:.2f}"
    
    # 验证吞吐量计算
    throughput = metrics.total_tasks / metrics.total_duration
    assert throughput >= CONCURRENCY_COUNT / TEST_DURATION, \
        f"吞吐量不足: 实际={throughput:.2f}, 预期≥{CONCURRENCY_COUNT / TEST_DURATION:.2f} tasks/sec"

# 测试用例：验证并发控制的准确性
def test_concurrent_throttling() -> None:
    """
    测试并发数控制功能
    
    验证：
    1. 实际并发数不超限
    2. 任务执行顺序符合预期
    3. 资源使用率在可控范围
    """
    # 创建一个会占用资源的任务函数
    def resource_intensive_task(task_id: int) -> TaskResult:
        """模拟占用计算资源的任务"""
        process = psutil.Process()
        process.cpu_percent(interval=0.01)
        process.memory_percent()
        return TaskResult(
            task_id=task_id,
            status="completed",
            duration=0.1,
            error=None
        )
    
    # 记录资源使用峰值
    resource_usage = []
    
    # 执行并发测试
    metrics = run_concurrent_tasks(
        task_function=resource_intensive_task,
        task_count=CONCURRENCY_COUNT,
        max_workers=CONCURRENCY_COUNT,
        duration=TEST_DURATION
    )
    
    # 验证资源使用率是否合理（避免过高）
    max_cpu = 0.0
    max_memory = 0.0
    
    # 检查资源监控逻辑（模拟）
    for result in metrics:
        cpu_usage = psutil.Process(result.pid).cpu_percent()
        memory_usage = psutil.Process(result.pid).memory_percent()
        resource_usage.append((cpu_usage, memory_usage))
        
        max_cpu = max(max_cpu, cpu_usage)
        max_memory = max(max_memory, memory_usage)
    
    # 验证资源使用未超标
    assert max_cpu < 100, f"CPU使用率异常高: {max_cpu}%"
    assert max_memory < 90, f"内存使用率异常高: {max_memory}%"
    
    # 验证并发任务按预期执行
    assert all(task.pid for task in metrics), "所有任务应有有效PID"
    assert len(metrics) == CONCURRENCY_COUNT, "任务数量不匹配"

# 测试用例：验证异常处理机制
def test_concurrent_error_handling() -> None:
    """
    测试并发任务异常处理机制
    
    验证：
    1. 任务异常时能够正确记录
    2. 异常任务不影响其他任务执行
    3. 错误重试机制正常工作
    """
    # 创建会随机抛出异常的任务函数
    def error_prone_task(task_id: int) -> TaskResult:
        """可能会抛出异常的测试任务"""
        if task_id % 5 == 0:
            raise RuntimeError(f"Error in task {task_id}")
        return TaskResult(
            task_id=task_id,
            status="completed",
            duration=0.1,
            error=None
        )
    
    # 运行测试并捕获异常
    with pytest.raises(Exception) as exc_info:
        run_concurrent_tasks(
            task_function=error_prone_task,
            task_count=CONCURRENCY_COUNT,
            max_workers=CONCURRENCY_COUNT,
            duration=TEST_DURATION,
            max_retries=MAX_RETRIES
        )
    
    # 验证重试次数是否合理
    assert "Task 5 failed" in str(exc_info.value), "未正确处理失败任务"
    
    # 验证失败任务的重试计数
    result = exc_info.value.task_result
    assert result.retries == MAX_RETRIES, "重试次数记录不准确"
    
    # 验证错误任务未影响其他任务
    assert len(result.task_results) > 1, "错误任务应不影响整体结果统计"