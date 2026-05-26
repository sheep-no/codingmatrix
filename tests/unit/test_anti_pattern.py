"""
测试反模式追踪功能
"""
import pytest
from datetime import datetime, timedelta
from app.agent.feedback_learner import FixPattern
from app.agent.fix_pattern_cache import FixPattern as CacheFixPattern


class TestFixPatternAntiPattern:
  """测试 FixPattern 的反模式判定"""

  def test_is_anti_pattern_threshold(self):
      """测试反模式阈值判定"""
  # 失败 3 次 + 成功率 0.2 -> 是反模式
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py'],
  failed_count=3,
  success_rate=0.2
  )
  assert pattern.is_anti_pattern() is True

  def test_not_anti_pattern_low_failures(self):
      """测试失败次数不足的情况"""
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py'],
  failed_count=2, # < 3
  success_rate=0.2
  )
  assert pattern.is_anti_pattern() is False

  def test_not_anti_pattern_high_success(self):
      """测试成功率较高的情况"""
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py'],
  failed_count=5,
  success_rate=0.5 # >= 0.3
  )
  assert pattern.is_anti_pattern() is False

  def test_default_values(self):
      """测试默认值"""
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py']
  )
  assert pattern.failed_count == 0
  assert pattern.success_rate == 1.0
  assert pattern.is_anti_pattern() is False


class TestCacheFixPatternAntiPattern:
  """测试 CacheFixPattern 的反模式判定"""

  def test_is_anti_pattern_threshold(self):
      """测试反模式阈值判定"""
  pattern = CacheFixPattern(
  error_signature='abc',
  error_type='syntax',
  error_subtype='indent',
  project_type='web',
  file_type='.py',
  fix_strategy='fix indent',
  model_used='qwen',
  fixed_code_snippet='pass',
  success_rate=0.2,
  usage_count=5,
  failed_count=4
  )
  assert pattern.is_anti_pattern() is True

  def test_not_anti_pattern_low_failures(self):
      """测试失败次数不足的情况"""
  pattern = CacheFixPattern(
  error_signature='abc',
  error_type='syntax',
  error_subtype='indent',
  project_type='web',
  file_type='.py',
  fix_strategy='fix indent',
  model_used='qwen',
  fixed_code_snippet='pass',
  success_rate=0.2,
  usage_count=5,
  failed_count=2 # < 3
  )
  assert pattern.is_anti_pattern() is False

  def test_not_anti_pattern_high_success(self):
      """测试成功率较高的情况"""
  pattern = CacheFixPattern(
  error_signature='abc',
  error_type='syntax',
  error_subtype='indent',
  project_type='web',
  file_type='.py',
  fix_strategy='fix indent',
  model_used='qwen',
  fixed_code_snippet='pass',
  success_rate=0.5, # >= 0.3
  usage_count=5,
  failed_count=3
  )
  assert pattern.is_anti_pattern() is False

  def test_default_values(self):
      """测试默认值"""
  pattern = CacheFixPattern(
  error_signature='abc',
  error_type='syntax',
  error_subtype='indent',
  project_type='web',
  file_type='.py',
  fix_strategy='fix indent',
  model_used='qwen',
  fixed_code_snippet='pass',
  success_rate=1.0,
  usage_count=0
  )
  assert pattern.failed_count == 0
  assert pattern.success_rate == 1.0
  assert pattern.usage_count == 0
  assert pattern.is_anti_pattern() is False


class TestFailureReasonTracking:
  """测试失败原因追踪"""

  def test_failure_reason_field(self):
      """测试失败原因字段"""
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py'],
  failed_count=3,
  failure_reason='修复后仍然触发相同错误'
  )
  assert pattern.failure_reason == '修复后仍然触发相同错误'

  def test_last_failed_at_field(self):
      """测试最后失败时间字段"""
  now = datetime.now()
  pattern = FixPattern(
  error_type='syntax',
  error_message='test',
  error_pattern='test',
  fix_description='test',
  fix_example='',
  file_types=['.py'],
  failed_count=3,
  last_failed_at=now
  )
  assert pattern.last_failed_at == now
