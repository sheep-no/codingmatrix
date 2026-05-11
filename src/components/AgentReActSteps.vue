<template>
  <div class="agent-react-steps">
    <div class="steps-header">
      <h4>推理过程</h4>
      <span class="step-count">{{ steps.length }} 步</span>
    </div>

    <div class="steps-timeline">
      <div
        v-for="(step, idx) in steps"
        :key="idx"
        :class="['step-item', `step-${step.type || 'action'}`]"
      >
        <div class="step-connector" v-if="idx > 0"></div>

        <div class="step-node">
          <div :class="['step-icon', getStepIcon(step)]">
            <svg v-if="step.type === 'thought'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <svg v-else-if="step.type === 'action'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
            <svg v-else-if="step.type === 'observation'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
              <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
          </div>
        </div>

        <div class="step-content">
          <div class="step-label">{{ getStepLabel(step) }}</div>
          <div v-if="step.content" class="step-text" v-html="renderMarkdown(step.content)"></div>
          <div v-if="step.tool" class="step-tool">
            <span class="tool-name">{{ step.tool }}</span>
            <span v-if="step.tool_input" class="tool-input">{{ step.tool_input }}</span>
          </div>
          <div v-if="step.duration" class="step-duration">{{ step.duration }}ms</div>
        </div>
      </div>

      <div v-if="steps.length === 0" class="empty-state">
        暂无推理步骤
      </div>
    </div>
  </div>
</template>

<script setup>
  import { useMarkdown } from '@/composables/useMarkdown'

  const { render: renderMarkdown } = useMarkdown()

  defineProps({
    steps: { type: Array, default: () => [] }
  })

  function getStepIcon(step) {
    const type = step.type || 'action'
    if (type === 'thought') return 'icon-thought'
    if (type === 'action') return 'icon-action'
    if (type === 'observation') return 'icon-observation'
    return 'icon-result'
  }

  function getStepLabel(step) {
    const type = step.type || 'action'
    const labels = {
      thought: '思考',
      action: '执行',
      observation: '观察',
      result: '结果',
      tool: '工具'
    }
    return labels[type] || type
  }
</script>

<style scoped>
  .agent-react-steps {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .steps-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .steps-header h4 { margin: 0; font-size: 14px; }
  .step-count { font-size: 12px; color: var(--text-secondary, #9ca3af); }

  .steps-timeline {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .step-item {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    position: relative;
  }

  .step-connector {
    width: 2px;
    height: 20px;
    background: var(--border-color, #2d3748);
    margin-left: 17px;
  }

  .step-node {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
  }

  .step-icon {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .step-icon svg { width: 18px; height: 18px; }
  .icon-thought { background: #8b5cf622; color: #8b5cf6; }
  .icon-action { background: #3b82f622; color: #3b82f6; }
  .icon-observation { background: #10b98122; color: #10b981; }
  .icon-result { background: #f59e0b22; color: #f59e0b; }

  .step-content {
    flex: 1;
    margin-left: 12px;
    margin-bottom: 16px;
  }

  .step-label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }

  .step-text {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-secondary, #9ca3af);
    max-height: 200px;
    overflow-y: auto;
  }

  .step-text :deep(pre) {
    margin: 8px 0;
    padding: 8px 12px;
    border-radius: 6px;
    background: var(--bg-tertiary, #1f2937);
    font-size: 12px;
    overflow-x: auto;
  }

  .step-tool {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 8px;
  }

  .tool-name {
    font-size: 12px;
    font-weight: 500;
    color: var(--accent-color, #4f46e5);
  }

  .tool-input {
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    font-family: monospace;
  }

  .step-duration {
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    margin-top: 4px;
  }

  .empty-state {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary, #9ca3af);
    font-size: 13px;
  }
</style>
