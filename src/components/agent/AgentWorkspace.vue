<template>
  <div class="main-panel">
    <!-- Progress bar - only when generating -->
    <div v-if="stages && stages.length > 0" class="progress-bar-section">
      <div class="progress-meta">
        <span class="progress-label">生成进度</span>
        <span class="progress-value">{{ Math.round(overallProgress) }}%</span>
        <span v-if="eta" class="progress-eta">{{ eta }}</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: `${overallProgress}%` }"></div>
      </div>
    </div>

    <!-- Timeline -->
    <div v-if="stages && stages.length > 0" class="timeline">
      <div
        v-for="(stage, index) in stages"
        :key="stage.id"
        class="timeline-item"
        :class="[`status-${stage.status}`, { expanded: expandedStages[stage.id] }]"
      >
        <div class="timeline-connector">
          <div class="timeline-dot">
            <svg v-if="stage.status === 'completed'" viewBox="0 0 16 16" fill="currentColor" class="dot-icon"><path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/></svg>
            <svg v-else-if="stage.status === 'failed'" viewBox="0 0 16 16" fill="currentColor" class="dot-icon"><path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z"/></svg>
            <div v-else-if="stage.status === 'running'" class="dot-pulse"></div>
            <div v-else class="dot-empty"></div>
          </div>
          <div v-if="index < stages.length - 1" class="timeline-line"></div>
        </div>

        <div class="timeline-body" @click="toggleStage(stage.id)">
          <div class="stage-header">
            <span class="stage-name">{{ stage.name }}</span>
            <div class="stage-right">
              <span v-if="stage.status === 'running' && stage.progress > 0" class="stage-progress">{{ stage.progress }}%</span>
              <span class="stage-status-tag" :class="`tag-${stage.status}`">{{ statusText(stage.status) }}</span>
              <svg
                v-if="stage.thinking && stage.thinking.length > 0"
                class="expand-icon"
                :class="{ rotated: expandedStages[stage.id] }"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
              </svg>
            </div>
          </div>
          <div v-if="stage.status === 'running'" class="stage-progress-bar">
            <div class="stage-progress-fill" :style="{ width: `${stage.progress}%` }"></div>
          </div>
        </div>

        <div v-if="expandedStages[stage.id] && stage.thinking && stage.thinking.length > 0" class="thinking-panel">
          <div v-for="(t, ti) in stage.thinking" :key="ti" class="thinking-entry">
            <div class="thinking-header">
              <span class="thinking-agent">{{ t.agent }}</span>
              <span v-if="t.model" class="thinking-model">{{ t.model }}</span>
              <span class="thinking-time">{{ formatTime(t.timestamp) }}</span>
            </div>
            <div class="thinking-body">{{ t.message }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Decisions -->
    <div v-if="decisions && decisions.length > 0" class="decisions-panel">
      <div class="decisions-title">
        <span>需要确认的决策</span>
        <span class="decisions-count">{{ decisions.length }}</span>
      </div>
      <div v-for="decision in decisions" :key="decision.id" class="decision-card">
        <div class="decision-question">{{ decision.question }}</div>
        <div class="decision-context">{{ decision.context }}</div>
        <div class="decision-options">
          <button
            v-for="option in (decision.options || [])"
            :key="option.label"
            class="decision-btn"
            :class="{ active: decisionAnswers[decision.id] === option.label, default: option.label === decision.default }"
            @click="$emit('select-decision', decision.id, option.label)"
          >
            <span class="option-label">{{ option.label }}</span>
            <span class="option-desc">{{ option.description }}</span>
          </button>
        </div>
        <div class="decision-actions">
          <button class="btn-decision btn-decision-secondary" @click="$emit('use-default', decision.id)">默认值</button>
          <button class="btn-decision btn-decision-primary" @click="$emit('submit-decision')">确认</button>
        </div>
      </div>
    </div>

    <!-- Merged sections from right panel -->
    <div v-if="(thinkingMessages && thinkingMessages.length > 0) || (executionSteps && executionSteps.length > 0) || (logs && logs.length > 0)" class="merged-sections">
      <!-- Thinking -->
      <div v-if="thinkingMessages && thinkingMessages.length > 0" class="merged-section">
        <div class="merged-section-header" @click="toggleMerged('thinking')">
          <div class="merged-header-left">
            <span class="merged-dot thinking-dot-bg"></span>
            <span class="merged-title">Agent 思考过程</span>
            <span class="merged-count">{{ thinkingMessages.length }}</span>
          </div>
          <div class="merged-header-right">
            <button class="merged-clear-btn" @click.stop="$emit('clear-thinking')">清空</button>
            <svg class="merged-expand-icon" :class="{ rotated: mergedExpanded.thinking }" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </div>
        </div>
        <div v-if="mergedExpanded.thinking" class="merged-section-body">
          <div class="thinking-timeline-merged">
            <div v-for="(msg, index) in thinkingMessages" :key="index" class="thinking-item-merged">
              <div class="thinking-item-dot"></div>
              <div class="thinking-item-content">
                <div class="thinking-item-meta">
                  <span class="thinking-agent-name">{{ msg.agent }}</span>
                  <span v-if="msg.model" class="thinking-model-badge">{{ msg.model }}</span>
                  <span v-if="msg.phase" class="thinking-phase-tag">{{ msg.phase }}</span>
                  <span class="thinking-item-time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <div class="thinking-item-message">{{ msg.message }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Execution Steps -->
      <div v-if="executionSteps && executionSteps.length > 0" class="merged-section">
        <div class="merged-section-header" @click="toggleMerged('steps')">
          <div class="merged-header-left">
            <span class="merged-dot steps-dot-bg"></span>
            <span class="merged-title">执行步骤</span>
            <span class="merged-count">{{ executionSteps.length }}</span>
          </div>
          <div class="merged-header-right">
            <button class="merged-clear-btn" @click.stop="$emit('clear-steps')">清空</button>
            <svg class="merged-expand-icon" :class="{ rotated: mergedExpanded.steps }" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </div>
        </div>
        <div v-if="mergedExpanded.steps" class="merged-section-body">
          <div class="steps-list-merged">
            <div v-for="(detail, index) in executionSteps" :key="index" class="step-item-merged">
              <div class="step-num">{{ index + 1 }}</div>
              <div class="step-item-content">
                <div class="step-cat">{{ detail.category }}</div>
                <div class="step-desc">{{ detail.description }}</div>
              </div>
              <div class="step-item-time">{{ formatTime(detail.timestamp) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Logs -->
      <div v-if="logs && logs.length > 0" class="merged-section">
        <div class="merged-section-header" @click="toggleMerged('logs')">
          <div class="merged-header-left">
            <span class="merged-dot logs-dot-bg"></span>
            <span class="merged-title">消息日志</span>
            <span class="merged-count">{{ logs.length }}</span>
          </div>
          <div class="merged-header-right">
            <button class="merged-clear-btn" @click.stop="$emit('clear-logs')">清空</button>
            <svg class="merged-expand-icon" :class="{ rotated: mergedExpanded.logs }" viewBox="0 0 20 20" fill="currentColor">
              <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
            </svg>
          </div>
        </div>
        <div v-if="mergedExpanded.logs" class="merged-section-body">
          <div ref="logsContainerRef" class="logs-container-merged">
            <div v-for="(log, index) in logs" :key="index" class="log-item-merged" :class="`log-${log.level}`">
              <span class="log-level-badge">{{ log.level.toUpperCase() }}</span>
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <span class="log-msg">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- File editor -->
    <div v-if="selectedFile" class="editor-section">
      <div class="editor-header">
        <div class="editor-info">
          <span class="editor-filename">{{ selectedFile.name }}</span>
          <span class="editor-path">{{ selectedFile.path }}</span>
          <span class="editor-lang">{{ language }}</span>
        </div>
        <div class="editor-actions">
          <button v-if="hasDiff" class="editor-btn" @click="$emit('show-diff')">变更</button>
          <button class="editor-btn" @click="$emit('save-version')">保存</button>
          <button class="editor-btn" @click="$emit('version-history')">历史</button>
          <button class="editor-btn" @click="$emit('copy')">复制</button>
          <button class="editor-btn" @click="$emit('download')">下载</button>
          <button class="editor-btn btn-delete" @click="$emit('delete-file')">删除</button>
        </div>
      </div>
      <div class="code-block" v-html="highlightedCode"></div>
      <div class="editor-footer">
        <span>{{ lineCount }} 行</span>
        <span>{{ fileSize }}</span>
        <span>{{ language }}</span>
        <span v-if="fileComplexity" class="complexity-badge" :class="`complexity-${fileComplexity.level}`">
          复杂度: {{ fileComplexity.level }}
        </span>
      </div>
    </div>

    <!-- Test Results Section -->
    <div v-if="testResults" class="info-section test-results-section">
      <div class="section-header">
        <span class="section-icon">🧪</span>
        <span class="section-title">测试结果</span>
      </div>
      <div class="section-body">
        <div class="stats-grid">
          <div class="stat-item stat-passed">
            <span class="stat-value">{{ testResults.passed }}</span>
            <span class="stat-label">通过</span>
          </div>
          <div class="stat-item stat-failed">
            <span class="stat-value">{{ testResults.failed }}</span>
            <span class="stat-label">失败</span>
          </div>
          <div class="stat-item stat-skipped">
            <span class="stat-value">{{ testResults.skipped }}</span>
            <span class="stat-label">跳过</span>
          </div>
          <div v-if="testResults.coverage" class="stat-item stat-coverage">
            <span class="stat-value">{{ testResults.coverage }}%</span>
            <span class="stat-label">覆盖率</span>
          </div>
        </div>
        <div v-if="testResults.duration" class="duration-info">
          耗时: {{ formatDuration(testResults.duration) }}
        </div>
      </div>
    </div>

    <!-- Validation Results Section -->
    <div v-if="validationResults" class="info-section validation-results-section">
      <div class="section-header">
        <span class="section-icon">✅</span>
        <span class="section-title">验证结果</span>
      </div>
      <div class="section-body">
        <div class="validation-status" :class="validationResults.passed ? 'passed' : 'failed'">
          {{ validationResults.passed ? '全部通过' : '存在问题' }}
        </div>
        <div v-if="validationResults.checks && validationResults.checks.length > 0" class="checks-list">
          <div v-for="(check, idx) in validationResults.checks" :key="idx" class="check-item" :class="check.passed ? 'check-passed' : 'check-failed'">
            <span class="check-icon">{{ check.passed ? '✓' : '✗' }}</span>
            <span class="check-name">{{ check.name }}</span>
            <span v-if="check.message" class="check-message">{{ check.message }}</span>
          </div>
        </div>
        <div v-if="validationResults.issues && validationResults.issues.length > 0" class="issues-summary">
          {{ validationResults.issues.length }} 个问题需要修复
        </div>
      </div>
    </div>

    <!-- Cost & Performance Section -->
    <div v-if="costData && costData.totalTokens > 0" class="info-section cost-section">
      <div class="section-header">
        <span class="section-icon">💰</span>
        <span class="section-title">成本与性能</span>
      </div>
      <div class="section-body">
        <div class="cost-grid">
          <div class="cost-item">
            <span class="cost-label">总 Token</span>
            <span class="cost-value">{{ formatNumber(costData.totalTokens) }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label">费用</span>
            <span class="cost-value">${{ costData.totalCostUsd?.toFixed(4) || '0.0000' }}</span>
          </div>
          <div class="cost-item">
            <span class="cost-label">速度</span>
            <span class="cost-value">{{ costData.tokensPerSecond?.toFixed(0) || 0 }} tok/s</span>
          </div>
        </div>
        <div v-if="performanceMetrics && performanceMetrics.llmCalls > 0" class="performance-grid">
          <div class="perf-item">
            <span class="perf-label">LLM 调用</span>
            <span class="perf-value">{{ performanceMetrics.llmCalls }} 次</span>
          </div>
          <div class="perf-item">
            <span class="perf-label">生成速度</span>
            <span class="perf-value">{{ performanceMetrics.filesPerMinute?.toFixed(1) || 0 }} 文件/分</span>
          </div>
          <div v-if="performanceMetrics.retryCount > 0" class="perf-item">
            <span class="perf-label">重试次数</span>
            <span class="perf-value">{{ performanceMetrics.retryCount }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="(!stages || stages.length === 0) && !selectedFile" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
          <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
      </div>
      <p class="empty-text">输入需求后点击生成，Agent 将自动完成项目搭建</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, nextTick, watch } from 'vue'

const props = defineProps({
  stages: { type: Array, required: true },
  overallProgress: { type: Number, required: true },
  eta: { type: String, default: '' },
  decisions: { type: Array, required: true },
  decisionAnswers: { type: Object, required: true },
  selectedFile: { type: Object, default: null },
  fileType: { type: String, default: '' },
  highlightedCode: { type: String, default: '' },
  lineCount: { type: Number, default: 0 },
  fileSize: { type: String, default: '0 B' },
  language: { type: String, default: 'Unknown' },
  hasDiff: { type: Boolean, default: false },
  thinkingMessages: { type: Array, default: () => [] },
  executionSteps: { type: Array, default: () => [] },
  logs: { type: Array, default: () => [] },
  // 新增 props
  testResults: { type: Object, default: null },
  validationResults: { type: Object, default: null },
  costData: { type: Object, default: null },
  performanceMetrics: { type: Object, default: null },
  fileComplexity: { type: Object, default: null }
})

defineEmits(['select-decision', 'use-default', 'submit-decision', 'show-diff', 'save-version', 'version-history', 'copy', 'download', 'delete-file', 'download-project', 'clear-thinking', 'clear-steps', 'clear-logs'])

const expandedStages = reactive({})
const mergedExpanded = reactive({ thinking: false, steps: false, logs: false })
const logsContainerRef = ref(null)

function toggleStage(id) {
  expandedStages[id] = !expandedStages[id]
}

function toggleMerged(key) {
  mergedExpanded[key] = !mergedExpanded[key]
}

function statusText(status) {
  return { completed: '完成', running: '执行中', pending: '等待', failed: '失败' }[status] || status
}

function formatTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleTimeString()
}

function formatDuration(seconds) {
  if (!seconds) return '0 秒'
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return mins > 0 ? `${mins} 分 ${secs} 秒` : `${secs} 秒`
}

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

watch(() => props.logs?.length, () => {
  nextTick(() => {
    if (logsContainerRef.value) {
      logsContainerRef.value.scrollTop = logsContainerRef.value.scrollHeight
    }
  })
})
</script>
