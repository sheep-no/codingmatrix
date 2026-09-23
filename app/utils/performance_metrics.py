"""
性能指标收集器

收集各模块的执行时间、内存占用、缓存命中率，支持指标导出和告警。
"""
import time
import logging
import psutil
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 每个模块保留的原始指标点上限，避免长运行服务内存无限增长
_MAX_METRIC_POINTS_PER_MODULE = 1000


@dataclass
class MetricPoint:
    """指标数据点"""
    timestamp: str
    module: str
    metric_name: str
    value: float
    unit: str = "ms"
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class ModuleMetrics:
    """模块性能指标"""
    module_name: str
    total_calls: int = 0
    total_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    alerts: List[str] = field(default_factory=list)


class MetricsCollector:
    """性能指标收集器"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.metrics: Dict[str, List[MetricPoint]] = {}
        self.module_metrics: Dict[str, ModuleMetrics] = {}
        self.storage_path = Path(storage_path) if storage_path else Path('./metrics')
        self.storage_path.mkdir(parents=True, exist_ok=True)
        # 已处于低命中率告警状态的模块，避免每次 miss 重复告警（PMC3）
        self._cache_alert_active: set = set()
        
        # 阈值配置
        self.thresholds = {
            'ImpactAnalyzer.analyze': 3000,  # 3 秒
            'ProjectProfiler.profile': 10000,  # 10 秒
            'TestSelector.select_tests': 1000,  # 1 秒
            'FailureClusterer.cluster': 2000,  # 2 秒
            'cache_hit_rate_min': 50.0,  # 50%
            'test_coverage_min': 80.0,  # 80%
        }
    
    def start_timer(self, module: str) -> float:
        """开始计时"""
        return time.time()
    
    def end_timer(self, module: str, start_time: float, metric_name: str = "execution_time", tags: Optional[Dict] = None):
        """结束计时并记录指标"""
        elapsed_ms = (time.time() - start_time) * 1000
        
        point = MetricPoint(
            timestamp=datetime.now().isoformat(),
            module=module,
            metric_name=metric_name,
            value=elapsed_ms,
            unit="ms",
            tags=tags or {}
        )
        
        self._record_metric(point)
        self._update_module_metrics(module, elapsed_ms)
        
        # 检查阈值告警
        threshold_key = f"{module}.{metric_name}"
        if threshold_key in self.thresholds:
            threshold = self.thresholds[threshold_key]
            if elapsed_ms > threshold:
                alert = f"性能告警：{module}.{metric_name} 耗时 {elapsed_ms:.0f}ms 超过阈值 {threshold:.0f}ms"
                logger.warning(alert)
                if module in self.module_metrics:
                    self.module_metrics[module].alerts.append(alert)
        
        return elapsed_ms
    
    def record_cache_hit(self, module: str):
        """记录缓存命中"""
        if module not in self.module_metrics:
            self.module_metrics[module] = ModuleMetrics(module_name=module)
        
        self.module_metrics[module].cache_hits += 1
        self._update_cache_hit_rate(module)
        self._check_cache_hit_rate_alert(module)
    
    def record_cache_miss(self, module: str):
        """记录缓存未命中"""
        if module not in self.module_metrics:
            self.module_metrics[module] = ModuleMetrics(module_name=module)
        
        self.module_metrics[module].cache_misses += 1
        self._update_cache_hit_rate(module)
        self._check_cache_hit_rate_alert(module)

    def _check_cache_hit_rate_alert(self, module: str):
        """命中率跌破阈值只告警一次，恢复到阈值以上后重新武装（PMC3）。

        原实现每次未命中都 append 告警，低命中率状态下 alerts 无限增长、
        warning 日志重复刷屏；而命中率随每次采样变化，按文本去重无效，
        故以「是否已处于告警态」判重。
        """
        hit_rate = self.module_metrics[module].cache_hit_rate
        threshold = self.thresholds['cache_hit_rate_min']
        if hit_rate < threshold:
            if module in self._cache_alert_active:
                return
            self._cache_alert_active.add(module)
            alert = f"缓存命中率告警：{module} 缓存命中率 {hit_rate:.1f}% 低于阈值 {threshold}%"
            logger.warning(alert)
            self.module_metrics[module].alerts.append(alert)
        else:
            self._cache_alert_active.discard(module)
    
    def record_test_coverage(self, module: str, coverage: float):
        """记录测试覆盖率"""
        if coverage < self.thresholds['test_coverage_min']:
            alert = f"测试覆盖率告警：{module} 测试覆盖率 {coverage:.1f}% 低于阈值 {self.thresholds['test_coverage_min']}%"
            logger.warning(alert)
            if module not in self.module_metrics:
                self.module_metrics[module] = ModuleMetrics(module_name=module)
            self.module_metrics[module].alerts.append(alert)
    
    def get_module_metrics(self, module: str) -> Optional[ModuleMetrics]:
        """获取模块指标"""
        return self.module_metrics.get(module)
    
    def get_all_metrics(self) -> Dict[str, ModuleMetrics]:
        """获取所有模块指标"""
        return self.module_metrics

    def get_last_duration(self, module: str, metric_name: str = "execution_time") -> float:
        """获取指定模块/指标最近一次记录的耗时（毫秒）；无记录返回 0。

        调用方可能在 `end_timer` 之前读取（如测试结果事件），此时返回的是上一次的耗时。
        """
        points = self.metrics.get(module)
        if not points:
            return 0.0
        for point in reversed(points):
            if point.metric_name == metric_name:
                return point.value
        return 0.0
    
    def export_metrics(self) -> Dict:
        """导出指标为 JSON 格式"""
        result = {}
        
        for module_name, metrics in self.module_metrics.items():
            result[module_name] = {
                'total_calls': metrics.total_calls,
                'total_time_ms': metrics.total_time_ms,
                'avg_time_ms': metrics.avg_time_ms,
                'min_time_ms': metrics.min_time_ms if metrics.min_time_ms != float('inf') else 0,
                'max_time_ms': metrics.max_time_ms,
                'cache_hits': metrics.cache_hits,
                'cache_misses': metrics.cache_misses,
                'cache_hit_rate': metrics.cache_hit_rate,
                'alerts': metrics.alerts,
            }
        
        return result
    
    def save_metrics(self):
        """保存指标到文件"""
        import json
        metrics_file = self.storage_path / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(self.export_metrics(), f, ensure_ascii=False, indent=2)
            logger.info(f"性能指标已保存：{metrics_file}")
        except Exception as e:
            logger.error(f"保存性能指标失败：{e}")
    
    def _record_metric(self, point: MetricPoint):
        """记录指标点；每个模块仅保留最近的 _MAX_METRIC_POINTS_PER_MODULE 条。"""
        points = self.metrics.setdefault(point.module, [])
        points.append(point)
        if len(points) > _MAX_METRIC_POINTS_PER_MODULE:
            del points[:-_MAX_METRIC_POINTS_PER_MODULE]
    
    def _update_module_metrics(self, module: str, elapsed_ms: float):
        """更新模块指标"""
        if module not in self.module_metrics:
            self.module_metrics[module] = ModuleMetrics(module_name=module)
        
        metrics = self.module_metrics[module]
        metrics.total_calls += 1
        metrics.total_time_ms += elapsed_ms
        metrics.avg_time_ms = metrics.total_time_ms / metrics.total_calls
        metrics.min_time_ms = min(metrics.min_time_ms, elapsed_ms)
        metrics.max_time_ms = max(metrics.max_time_ms, elapsed_ms)
    
    def _update_cache_hit_rate(self, module: str):
        """更新缓存命中率"""
        if module in self.module_metrics:
            metrics = self.module_metrics[module]
            total = metrics.cache_hits + metrics.cache_misses
            if total > 0:
                metrics.cache_hit_rate = (metrics.cache_hits / total) * 100


# 全局指标收集器实例
metrics_collector = MetricsCollector()
