/**
 * Agent phase 标签映射（自动生成）
 *
 * 来源：app/agent/orchestrator_progress.py PROGRESS_LABELS
 * 请勿手动修改此文件，运行 scripts/generate_agent_phases.py 重新生成
 */
export const AGENT_PHASE_LABELS = Object.freeze({
  initializing: '初始化',
  analyzing: '分析需求',
  evaluation: '评估项目',
  running_tests: '运行测试',
  analyzing_complexity: '分析项目复杂度',
  assigning_models: '分配 AI 模型',
  initializing_roles: '初始化专家角色',
  cost_estimation: '预估生成成本',
  dependency_graph: '构建文件依赖关系',
  generating_file: '正在生成文件',
  file_generated: '文件生成完成',
  react_fallback: '启用增强生成模式',
  pause_for_approval: '等待人工确认',
  file_rejected: '文件已被拒绝',
  validating_file: '验证文件内容',
  reviewing_file: '审查代码质量',
  api_contract_check: '检查 API 一致性',
  final_validation: '最终项目验证',
  dependency_graph_built: '依赖关系构建完成',
  generating_layer: '正在生成分层文件',
  layer_completed: '分层生成完成',
  test_execution: '运行自动化测试',
  test_passed: '测试全部通过',
  test_failed: '测试存在失败',
  auto_repair: '自动修复测试问题',
  repair_completed: '修复完成',
  saving_memory: '保存项目经验',
  generation_complete: '项目生成完成',
  incremental_analysis: '分析变更内容',
  incremental_no_changes: '无变更，跳过生成',
  tests_passed: '测试全部通过',
  tests_failed_recovering: '测试失败，正在自动修复',
  recovery_success: '自动修复成功',
  recovery_failed: '自动修复失败',
  requirement_association: '需求联想增强',
  cross_file_validation: '跨文件一致性检查',
  cross_file_fix: '自动修复一致性问题',
  architecture_review: '架构设计审查',
  cost_tracking: '成本追踪',
  token_usage: 'Token 用量统计',
  react_tool_call: '搜索项目文件',
  react_tool_result: '获取搜索结果',
  react_generating: '基于上下文生成代码',
  designing_analysis: '设计评估维度',
  requirement_analysis: '需求深度分析',
  deep_evaluation: '深度评估中',
  detecting_domain: '识别需求领域',
  searching_history: '搜索历史项目',
  deep_association: '深度关联分析',
  devil_review: '对立面审查',
  building_result: '构建联想结果',
  complete: '完成',
})

/**
 * 获取 phase 的中文标签
 * @param {string} phaseKey - 后端推送的 phase 字段值
 * @returns {string} 中文标签；如果未在映射表中，返回 phaseKey 本身
 */
export function getPhaseLabel(phaseKey) {
  if (!phaseKey) return ''
  return AGENT_PHASE_LABELS[phaseKey] || phaseKey
}
