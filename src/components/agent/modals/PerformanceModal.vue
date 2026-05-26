<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content perf-modal"><div class="modal-header"><h3>性能监控</h3><button class="modal-close" @click="$emit('update:modelValue', false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg></button></div>
        <div class="modal-body">
          <div class="perf-stats-grid">
            <div class="perf-stat-card"><div class="perf-stat-label">开始时间</div><div class="perf-stat-value">{{ performanceStats.startTime }}</div></div>
            <div class="perf-stat-card"><div class="perf-stat-label">总文件数</div><div class="perf-stat-value">{{ performanceStats.totalFiles }}</div></div>
            <div class="perf-stat-card"><div class="perf-stat-label">总 Token 数</div><div class="perf-stat-value">{{ (performanceStats.totalTokens || 0).toLocaleString() }}</div></div>
            <div class="perf-stat-card"><div class="perf-stat-label">错误次数</div><div class="perf-stat-value perf-error">{{ performanceStats.errorCount }}</div></div>
            <div class="perf-stat-card"><div class="perf-stat-label perf-success">{{ performanceStats.successRate }}%</div></div>
          </div>
          <div class="perf-stage-section"><h4>阶段进度</h4>
            <div class="perf-stages-list">
              <div v-for="(stage, i) in performanceStats.stageTimings || []" :key="i" class="perf-stage-item">
                <span class="perf-stage-name">{{ stage.name }}</span>
                <span class="perf-stage-status" :class="`status-${stage.status}`">{{ stage.status === 'completed' ? '完成' : stage.status === 'running' ? '进行中' : '等待中' }}</span>
                <div class="perf-stage-bar"><div class="perf-stage-fill" :style="{ width: `${stage.progress}%` }"></div></div>
                <span class="perf-stage-progress">{{ Math.round(stage.progress) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({ modelValue: Boolean, performanceStats: { type: Object, required: true } })
defineEmits(['update:modelValue'])
</script>

<style scoped>
.perf-modal { max-width: 900px; }
.perf-stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.perf-stat-card { background: var(--bg-tertiary); padding: 12px; border-radius: 8px; }
.perf-stat-label { font-size: 11px; color: var(--text-secondary); }
.perf-stat-value { font-size: 18px; font-weight: 700; margin-top: 4px; }
.perf-error { color: var(--danger); }
.perf-success { color: var(--success); }
.perf-stage-section { margin-top: 16px; }
.perf-stage-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.perf-stages-list { display: flex; flex-direction: column; gap: 6px; }
.perf-stage-item { display: flex; align-items: center; gap: 12px; padding: 8px; background: var(--bg-tertiary); border-radius: 6px; font-size: 13px; }
.perf-stage-bar { flex: 1; height: 4px; background: var(--bg-primary); border-radius: 2px; }
.perf-stage-fill { height: 100%; background: var(--primary); border-radius: 2px; }
</style>
