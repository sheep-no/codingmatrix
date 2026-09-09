<template>
  <section v-if="visible" class="task-feedback-panel" aria-live="polite">
    <div class="task-feedback-header">
      <TaskStatus :status="feedback.status" :stage="feedback.stage" :progress="feedback.progress" />
      <span v-if="connectionLabel" class="connection-status" :class="`connection-${connectionStatus}`">
        {{ connectionLabel }}
      </span>
    </div>
    <div class="task-feedback-meta">
      <span>耗时 {{ elapsedLabel }}</span>
    </div>
    <p v-if="feedback.error" class="task-feedback-error" role="alert">{{ feedback.error }}</p>
    <NextAction :label="feedback.nextAction" :action-label="primaryAction?.label" @action="handlePrimaryAction" />
    <div v-if="actions.length > 1" class="task-feedback-actions">
      <button
        v-for="action in actions.slice(1)"
        :key="action.key"
        type="button"
        class="task-feedback-action"
        :class="`action-${action.variant || 'secondary'}`"
        @click="emit('action', action.key)"
      >
        {{ action.label }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import NextAction from './NextAction.vue'
import TaskStatus from './TaskStatus.vue'

const props = defineProps({
  feedback: {
    type: Object,
    required: true
  },
  connectionStatus: {
    type: String,
    default: 'connected'
  },
  visible: {
    type: Boolean,
    default: true
  },
  actions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['action'])

const actions = computed(() => props.actions.filter(action => action?.key && action?.label))
const primaryAction = computed(() => actions.value[0] || null)

function handlePrimaryAction() {
  if (primaryAction.value) emit('action', primaryAction.value.key)
}

const elapsedLabel = computed(() => {
  const totalSeconds = Math.max(0, Math.floor(Number(props.feedback.elapsedMs || 0) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

const connectionLabel = computed(() => ({
  reconnecting: '正在恢复连接',
  disconnected: '连接已中断'
})[props.connectionStatus] || '')
</script>

<style scoped>
.task-feedback-panel {
  display: grid;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  border: 1px solid var(--control-border);
  border-radius: var(--radius-lg);
  background: var(--surface-raised);
  color: var(--content-secondary);
}

.task-feedback-header,
.task-feedback-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.task-feedback-meta,
.connection-status {
  color: var(--content-muted);
  font-size: var(--text-xs);
}

.connection-reconnecting { color: var(--status-warning); }
.connection-disconnected,
.task-feedback-error { color: var(--status-danger); }
.task-feedback-error { margin: 0; font-size: var(--text-sm); }
.task-feedback-actions { display: flex; flex-wrap: wrap; gap: var(--spacing-2); }
.task-feedback-action { min-height: var(--control-min-size); padding: 0 var(--spacing-3); border: 1px solid var(--control-border); border-radius: var(--radius-sm); background: transparent; color: var(--content-primary); cursor: pointer; }
.task-feedback-action.action-primary { border-color: var(--accent-primary); background: var(--accent-primary); color: var(--content-inverse); }

@media (max-width: 480px) {
  .task-feedback-header { align-items: flex-start; flex-direction: column; }
}
</style>
