"""
性能基准测试脚本

测试动态模型路由器的性能特征：
1. 单次路由延迟
2. 并发路由吞吐量
3. 指标记录开销
4. 健康报告生成性能
5. 内存占用

使用方法：
 python3 tests/e2e/test_performance_benchmark.py
"""

import asyncio
import time
import sys
import os
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agent.dynamic_model_router import DynamicModelRouter, get_dynamic_router


class BenchmarkResult:
 """基准测试结果"""

 def __init__(self, name: str):
 self.name = name
 self.latencies: List[float] = []
 self.start_time = time.time()

 def record(self, latency_ms: float):
 self.latencies.append(latency_ms)

 @property
 def avg_ms(self) -> float:
 return sum(self.latencies) / len(self.latencies) if self.latencies else 0

 @property
 def p50_ms(self) -> float:
 if not self.latencies:
 return 0
 sorted_latencies = sorted(self.latencies)
 return sorted_latencies[len(sorted_latencies) // 2]

 @property
 def p95_ms(self) -> float:
 if not self.latencies:
 return 0
 sorted_latencies = sorted(self.latencies)
 idx = int(len(sorted_latencies) * 0.95)
 return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

 @property
 def p99_ms(self) -> float:
 if not self.latencies:
 return 0
 sorted_latencies = sorted(self.latencies)
 idx = int(len(sorted_latencies) * 0.99)
 return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

 @property
 def throughput(self) -> float:
 elapsed = time.time() - self.start_time
 return len(self.latencies) / elapsed if elapsed > 0 else 0

 def __str__(self) -> str:
 return (
 f"{self.name}:\n"
 f" 平均延迟：{self.avg_ms:.2f}ms\n"
 f" P50 延迟：{self.p50_ms:.2f}ms\n"
 f" P95 延迟：{self.p95_ms:.2f}ms\n"
 f" P99 延迟：{self.p99_ms:.2f}ms\n"
 f" 吞吐量：{self.throughput:.0f} ops/sec\n"
 f" 总请求数：{len(self.latencies)}"
 )


async def benchmark_single_routing(router: DynamicModelRouter, iterations: int = 1000) -> BenchmarkResult:
 """单次路由延迟测试"""
 result = BenchmarkResult("单次路由延迟")

 # 预热
 for _ in range(10):
 await router.get_best_model(["model-a", "model-b"])

 for i in range(iterations):
 start = time.perf_counter()
 await router.get_best_model(["model-a", "model-b", "model-c"])
 latency_ms = (time.perf_counter() - start) * 1000
 result.record(latency_ms)

 return result


async def benchmark_concurrent_routing(router: DynamicModelRouter, concurrency: int = 100, iterations: int = 1000) -> BenchmarkResult:
 """并发路由吞吐量测试"""
 result = BenchmarkResult(f"并发路由 ({concurrency} 并发)")

 async def single_request():
 start = time.perf_counter()
 await router.get_best_model(["model-a", "model-b"])
 latency_ms = (time.perf_counter() - start) * 1000
 result.record(latency_ms)

 # 预热
 await asyncio.gather(*[single_request() for _ in range(10)])

 # 并发测试
 for batch in range(iterations // concurrency):
 tasks = [single_request() for _ in range(concurrency)]
 await asyncio.gather(*tasks)

 return result


async def benchmark_metrics_recording(router: DynamicModelRouter, iterations: int = 1000) -> BenchmarkResult:
 """指标记录开销测试"""
 result = BenchmarkResult("指标记录开销")

 for i in range(iterations):
 start = time.perf_counter()
 await router.record_call("model-a", success=(i % 10 != 0), latency_ms=100.0 + i % 50)
 latency_ms = (time.perf_counter() - start) * 1000
 result.record(latency_ms)

 return result


async def benchmark_health_report(router: DynamicModelRouter, iterations: int = 100) -> BenchmarkResult:
 """健康报告生成性能测试"""
 result = BenchmarkResult("健康报告生成")

 # 预热数据
 for model in [f"model-{i}" for i in range(20)]:
 for _ in range(10):
 await router.record_call(model, success=True, latency_ms=100.0)

 for _ in range(iterations):
 start = time.perf_counter()
 await router.get_model_health_report()
 latency_ms = (time.perf_counter() - start) * 1000
 result.record(latency_ms)

 return result


async def benchmark_memory_overhead(router: DynamicModelRouter, model_count: int = 1000) -> Dict:
 """内存占用测试"""
 import gc
 import tracemalloc

 tracemalloc.start()

 # 基准内存使用
 gc.collect()
 baseline = tracemalloc.get_traced_memory()

 # 创建大量模型指标
 for i in range(model_count):
 metrics = router.get_or_create_metrics(f"model-{i}")
 for _ in range(100):
 metrics.record_success(100.0)

 gc.collect()
 after = tracemalloc.get_traced_memory()

 tracemalloc.stop()

 return {
 "baseline_current_mb": baseline[0] / 1024 / 1024,
 "baseline_peak_mb": baseline[1] / 1024 / 1024,
 "after_current_mb": after[0] / 1024 / 1024,
 "after_peak_mb": after[1] / 1024 / 1024,
 "overhead_current_mb": (after[0] - baseline[0]) / 1024 / 1024,
 "overhead_peak_mb": (after[1] - baseline[1]) / 1024 / 1024,
 "per_model_bytes": (after[0] - baseline[0]) / model_count if model_count > 0 else 0
 }


async def run_all_benchmarks():
 """运行所有基准测试"""
 print("=" * 60)
 print("动态模型路由器性能基准测试")
 print("=" * 60)

 router = DynamicModelRouter()

 # 1. 单次路由延迟
 print("\n[1/5] 单次路由延迟测试 (1000 次)...")
 result1 = await benchmark_single_routing(router, iterations=1000)
 print(result1)

 # 2. 并发路由吞吐量
 print("\n[2/5] 并发路由吞吐量测试 (100 并发 x 1000 次)...")
 result2 = await benchmark_concurrent_routing(router, concurrency=100, iterations=1000)
 print(result2)

 # 3. 指标记录开销
 print("\n[3/5] 指标记录开销测试 (1000 次)...")
 result3 = await benchmark_metrics_recording(router, iterations=1000)
 print(result3)

 # 4. 健康报告生成性能
 print("\n[4/5] 健康报告生成测试 (100 次)...")
 result4 = await benchmark_health_report(router, iterations=100)
 print(result4)

 # 5. 内存占用
 print("\n[5/5] 内存占用测试 (1000 模型)...")
 router2 = DynamicModelRouter()
 memory_result = await benchmark_memory_overhead(router2, model_count=1000)
 print(f"内存占用:")
 print(f" 基准当前：{memory_result['baseline_current_mb']:.2f} MB")
 print(f" 基准峰值：{memory_result['baseline_peak_mb']:.2f} MB")
 print(f" 测试后当前：{memory_result['after_current_mb']:.2f} MB")
 print(f" 测试后峰值：{memory_result['after_peak_mb']:.2f} MB")
 print(f" 额外开销：{memory_result['overhead_current_mb']:.2f} MB")
 print(f" 每模型开销：{memory_result['per_model_bytes']:.0f} bytes")

 # 总结
 print("\n" + "=" * 60)
 print("性能基准测试总结")
 print("=" * 60)
 print(f"单次路由延迟：{result1.avg_ms:.2f}ms (P95: {result1.p95_ms:.2f}ms)")
 print(f"并发吞吐量：{result2.throughput:.0f} ops/sec")
 print(f"指标记录延迟：{result3.avg_ms:.2f}ms")
 print(f"健康报告延迟：{result4.avg_ms:.2f}ms")
 print(f"内存开销/模型：{memory_result['per_model_bytes']:.0f} bytes")

 # 性能评估
 print("\n" + "-" * 60)
 print("性能评估:")
 if result1.avg_ms < 1.0:
 print(" [PASS] 单次路由延迟 < 1ms (优秀)")
 elif result1.avg_ms < 5.0:
 print(" [PASS] 单次路由延迟 < 5ms (良好)")
 else:
 print(f" [WARN] 单次路由延迟 {result1.avg_ms:.2f}ms (需要优化)")

 if result2.throughput > 10000:
 print(" [PASS] 并发吞吐量 > 10k ops/sec (优秀)")
 elif result2.throughput > 5000:
 print(" [PASS] 并发吞吐量 > 5k ops/sec (良好)")
 else:
 print(f" [WARN] 并发吞吐量 {result2.throughput:.0f} ops/sec (需要优化)")

 if memory_result['per_model_bytes'] < 1000:
 print(" [PASS] 每模型内存 < 1KB (优秀)")
 elif memory_result['per_model_bytes'] < 5000:
 print(" [PASS] 每模型内存 < 5KB (良好)")
 else:
 print(f" [WARN] 每模型内存 {memory_result['per_model_bytes']:.0f} bytes (需要优化)")


if __name__ == "__main__":
 asyncio.run(run_all_benchmarks())
