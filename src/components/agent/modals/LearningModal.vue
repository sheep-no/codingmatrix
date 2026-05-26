<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
      <div class="modal-content"><div class="modal-header"><h3>学习反馈</h3><button class="modal-close" @click="$emit('update:modelValue', false)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg></button></div>
        <div class="modal-body">
          <div v-if="learningStats.total_feedbacks" class="learning-stats-grid">
            <div class="learning-stat-card"><div class="learning-stat-label">总反馈数</div><div class="learning-stat-value">{{ learningStats.total_feedbacks }}</div></div>
            <div class="learning-stat-card"><div class="learning-stat-label">已修复问题</div><div class="learning-stat-value">{{ learningStats.fixed_count || 0 }}</div></div>
            <div class="learning-stat-card"><div class="learning-stat-label">平均修复时间</div><div class="learning-stat-value">{{ learningStats.avg_fix_time || 'N/A' }}</div></div>
            <div class="learning-stat-card"><div class="learning-stat-label perf-success">{{ learningStats.accuracy_improvement || '0' }}%</div></div>
          </div>
          <div v-if="!learningStats.total_feedbacks" class="empty-learning"><p>暂无学习数据</p></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({ modelValue: Boolean, learningStats: { type: Object, required: true } })
defineEmits(['update:modelValue'])
</script>

<style scoped>
.learning-stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.learning-stat-card { background: var(--bg-tertiary); padding: 16px; border-radius: 8px; text-align: center; }
.learning-stat-label { font-size: 12px; color: var(--text-secondary); }
.learning-stat-value { font-size: 24px; font-weight: 800; margin-top: 4px; }
.perf-success { color: var(--success); }
.empty-learning { text-align: center; color: var(--text-secondary); padding: 16px; }
</style>
