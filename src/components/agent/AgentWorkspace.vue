<template>
  <div class="agent-workspace">
    <!-- Progress bar -->
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

    <!-- Merged sections -->
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
                  <span v-if="msg.streaming" class="thinking-streaming-indicator">
                    <span class="thinking-streaming-dot"></span>
                    生成中
                  </span>
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

    <!-- Test Results -->
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

    <!-- Validation Results -->
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

    <!-- Empty state -->
    <div v-if="(!stages || stages.length === 0)" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" width="48" height="48">
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
  thinkingMessages: { type: Array, default: () => [] },
  executionSteps: { type: Array, default: () => [] },
  logs: { type: Array, default: () => [] },
  testResults: { type: Object, default: null },
  validationResults: { type: Object, default: null }
})

defineEmits(['select-decision', 'use-default', 'submit-decision', 'clear-thinking', 'clear-steps', 'clear-logs'])

const expandedStages = reactive({})
const mergedExpanded = reactive({ thinking: true, steps: false, logs: false })
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

watch(() => props.logs?.length, () => {
  nextTick(() => {
    if (logsContainerRef.value) {
      logsContainerRef.value.scrollTop = logsContainerRef.value.scrollHeight
    }
  })
})
</script>

<style scoped>
.agent-workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding: 16px;
}
.progress-bar-section {
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-radius: 10px;
  border: 1px solid var(--border-color);
}
.progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}
.progress-label { color: var(--text-secondary); font-weight: 500; }
.progress-value { color: var(--primary); font-weight: 600; }
.progress-eta { color: var(--text-tertiary); }
.progress-track {
  height: 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 3px;
  transition: width 0.3s ease;
}

/* Timeline */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.timeline-item {
  display: flex;
  gap: 12px;
}
.timeline-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}
.timeline-dot {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dot-icon { width: 14px; height: 14px; }
.dot-pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.6; }
}
.dot-empty {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 2px solid var(--border-color);
}
.timeline-line {
  flex: 1;
  width: 2px;
  background: var(--border-color);
  min-height: 16px;
}
.timeline-body {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.15s;
}
.timeline-body:hover { border-color: var(--primary); }
.stage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.stage-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.stage-right { display: flex; align-items: center; gap: 8px; }
.stage-progress { font-size: 11px; color: var(--primary); font-weight: 600; }
.stage-status-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.tag-completed { background: color-mix(in srgb, var(--success), transparent 90%); color: var(--success); }
.tag-running { background: color-mix(in srgb, var(--primary), transparent 90%); color: var(--primary); }
.tag-pending { background: var(--bg-tertiary); color: var(--text-tertiary); }
.tag-failed { background: color-mix(in srgb, var(--danger), transparent 90%); color: var(--danger); }
.expand-icon {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
}
.expand-icon.rotated { transform: rotate(180deg); }
.stage-progress-bar {
  margin-top: 6px;
  height: 3px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}
.stage-progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* Thinking panel */
.thinking-panel {
  margin-top: 4px;
  padding: 8px 12px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}
.thinking-entry { padding: 6px 0; }
.thinking-entry + .thinking-entry { border-top: 1px solid var(--border-color); }
.thinking-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}
.thinking-agent { font-size: 11px; font-weight: 600; color: var(--primary); }
.thinking-model { font-size: 10px; color: var(--text-tertiary); background: var(--bg-secondary); padding: 1px 4px; border-radius: 3px; }
.thinking-time { font-size: 10px; color: var(--text-tertiary); margin-left: auto; }
.thinking-body { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }

/* Decisions */
.decisions-panel {
  padding: 16px;
  background: color-mix(in srgb, var(--warning), transparent 95%);
  border: 1px solid color-mix(in srgb, var(--warning), transparent 80%);
  border-radius: 10px;
}
.decisions-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.decisions-count {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--warning);
  color: white;
  border-radius: 10px;
}
.decision-card {
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}
.decision-card + .decision-card { margin-top: 8px; }
.decision-question { font-size: 13px; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; }
.decision-context { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
.decision-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.decision-btn {
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.decision-btn:hover { border-color: var(--primary); }
.decision-btn.active { border-color: var(--primary); background: color-mix(in srgb, var(--primary), transparent 90%); }
.option-label { display: block; font-size: 12px; font-weight: 500; color: var(--text-primary); }
.option-desc { font-size: 11px; color: var(--text-tertiary); }
.decision-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.btn-decision {
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-decision-secondary { background: transparent; color: var(--text-secondary); }
.btn-decision-secondary:hover { background: var(--bg-secondary); }
.btn-decision-primary { background: var(--primary); color: white; border-color: var(--primary); }
.btn-decision-primary:hover { background: var(--primary-hover); }

/* Merged sections */
.merged-sections {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.merged-section {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}
.merged-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-secondary);
  cursor: pointer;
}
.merged-header-left { display: flex; align-items: center; gap: 8px; }
.merged-dot { width: 8px; height: 8px; border-radius: 50%; }
.thinking-dot-bg { background: var(--primary); }
.steps-dot-bg { background: var(--success); }
.logs-dot-bg { background: var(--warning); }
.merged-title { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.merged-count {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  border-radius: 4px;
}
.merged-header-right { display: flex; align-items: center; gap: 6px; }
.merged-clear-btn {
  padding: 2px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 11px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}
.merged-clear-btn:hover { background: var(--bg-secondary); color: var(--text-primary); }
.merged-expand-icon {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
}
.merged-expand-icon.rotated { transform: rotate(180deg); }
.merged-section-body {
  padding: 12px 14px;
  max-height: 300px;
  overflow-y: auto;
}

/* Thinking timeline */
.thinking-timeline-merged {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.thinking-item-merged {
  display: flex;
  gap: 10px;
}
.thinking-item-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  margin-top: 5px;
  flex-shrink: 0;
}
.thinking-item-content { flex: 1; min-width: 0; }
.thinking-item-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 2px;
  flex-wrap: wrap;
}
.thinking-agent-name { font-size: 11px; font-weight: 600; color: var(--primary); }
.thinking-model-badge { font-size: 10px; padding: 1px 4px; background: var(--bg-tertiary); border-radius: 3px; color: var(--text-tertiary); }
.thinking-phase-tag { font-size: 10px; padding: 1px 4px; background: color-mix(in srgb, var(--success), transparent 90%); border-radius: 3px; color: var(--success); }
.thinking-streaming-indicator { font-size: 10px; padding: 1px 6px; background: color-mix(in srgb, var(--primary), transparent 90%); border-radius: 3px; color: var(--primary); display: inline-flex; align-items: center; gap: 4px; }
.thinking-streaming-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--primary); animation: thinking-blink 1s ease-in-out infinite; }
@keyframes thinking-blink { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.thinking-item-time { font-size: 10px; color: var(--text-tertiary); margin-left: auto; }
.thinking-item-message { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }

/* Steps list */
.steps-list-merged {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.step-item-merged {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.step-num {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  background: color-mix(in srgb, var(--success), transparent 90%);
  color: var(--success);
  border-radius: 50%;
  flex-shrink: 0;
}
.step-item-content { flex: 1; min-width: 0; }
.step-cat { font-size: 10px; color: var(--text-tertiary); margin-bottom: 1px; }
.step-desc { font-size: 12px; color: var(--text-secondary); }
.step-item-time { font-size: 10px; color: var(--text-tertiary); white-space: nowrap; }

/* Logs */
.logs-container-merged {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.log-item-merged {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
}
.log-info { background: color-mix(in srgb, var(--primary), transparent 95%); }
.log-success { background: color-mix(in srgb, var(--success), transparent 95%); }
.log-warning { background: color-mix(in srgb, var(--warning), transparent 95%); }
.log-error { background: color-mix(in srgb, var(--danger), transparent 95%); }
.log-level-badge {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 3px;
  min-width: 32px;
  text-align: center;
}
.log-info .log-level-badge { background: color-mix(in srgb, var(--primary), transparent 80%); color: var(--primary); }
.log-success .log-level-badge { background: color-mix(in srgb, var(--success), transparent 80%); color: var(--success); }
.log-warning .log-level-badge { background: color-mix(in srgb, var(--warning), transparent 80%); color: var(--warning); }
.log-error .log-level-badge { background: color-mix(in srgb, var(--danger), transparent 80%); color: var(--danger); }
.log-time { font-size: 10px; color: var(--text-tertiary); white-space: nowrap; }
.log-msg { color: var(--text-secondary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Info sections */
.info-section {
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}
.section-icon { font-size: 14px; }
.section-title { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.section-body { padding: 12px 14px; }

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 8px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
.stat-value { font-size: 18px; font-weight: 700; }
.stat-label { font-size: 10px; color: var(--text-tertiary); margin-top: 2px; }
.stat-passed .stat-value { color: var(--success); }
.stat-failed .stat-value { color: var(--danger); }
.stat-skipped .stat-value { color: var(--warning); }
.stat-coverage .stat-value { color: var(--primary); }
.duration-info { margin-top: 8px; font-size: 12px; color: var(--text-secondary); text-align: center; }

/* Validation */
.validation-status {
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  padding: 8px;
  border-radius: 8px;
  margin-bottom: 8px;
}
.validation-status.passed { background: color-mix(in srgb, var(--success), transparent 90%); color: var(--success); }
.validation-status.failed { background: color-mix(in srgb, var(--danger), transparent 90%); color: var(--danger); }
.checks-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
}
.check-passed { background: color-mix(in srgb, var(--success), transparent 95%); }
.check-failed { background: color-mix(in srgb, var(--danger), transparent 95%); }
.check-icon { font-size: 12px; font-weight: 600; }
.check-passed .check-icon { color: var(--success); }
.check-failed .check-icon { color: var(--danger); }
.check-name { color: var(--text-primary); }
.check-message { color: var(--text-tertiary); font-size: 11px; }
.issues-summary { margin-top: 8px; font-size: 12px; color: var(--danger); text-align: center; }

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  color: var(--text-tertiary);
}
.empty-icon { margin-bottom: 12px; opacity: 0.5; }
.empty-text { font-size: 14px; }
</style>
