<template>
  <div class="task-status" :class="`task-status-${status}`" role="status" :aria-label="statusLabel">
    <span class="task-dot" aria-hidden="true"></span>
    <span>{{ statusLabel }}</span>
    <span v-if="stage" class="task-stage">{{ stage }}</span>
    <span v-if="progress !== null" class="task-progress">{{ progress }}%</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'queued' },
  stage: { type: String, default: '' },
  progress: { type: Number, default: null }
})

const labels = { queued: '排队中', running: '运行中', paused: '已暂停', failed: '失败', completed: '已完成' }
const statusLabel = computed(() => labels[props.status] || '处理中')
</script>

<style scoped>
.task-status { display: inline-flex; align-items: center; gap: var(--spacing-2); min-height: var(--control-min-size); color: var(--content-secondary); font-size: var(--text-sm); }
.task-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--status-info); }
.task-status-running .task-dot { animation: state-pulse 1.2s ease-in-out infinite; }
.task-status-completed .task-dot { background: var(--status-success); }
.task-status-failed .task-dot { background: var(--status-danger); }
.task-status-paused .task-dot { background: var(--status-warning); }
.task-stage, .task-progress { color: var(--content-muted); }
@keyframes state-pulse { 50% { opacity: 0.35; } }
</style>
