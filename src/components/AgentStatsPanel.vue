<template>
  <div class="agent-stats-panel">
    <div class="panel-header">
      <h4>模型统计</h4>
      <button class="btn-icon-sm" title="刷新" @click="$emit('refresh')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
    </div>

    <div class="stats-content">
      <!-- 概览 -->
      <div class="stats-overview">
        <div class="overview-item">
          <span class="overview-value">{{ totalRequests }}</span>
          <span class="overview-label">总请求</span>
        </div>
        <div class="overview-item">
          <span class="overview-value">{{ totalTokens }}</span>
          <span class="overview-label">总 Token</span>
        </div>
        <div class="overview-item">
          <span class="overview-value">{{ successRate }}%</span>
          <span class="overview-label">成功率</span>
        </div>
      </div>

      <!-- 模型列表 -->
      <div class="model-list">
        <div v-for="stat in stats" :key="stat.model_key" class="model-item">
          <div class="model-header">
            <span class="model-name">{{ formatModel(stat.model_key) }}</span>
            <span :class="['model-rate', { good: getRate(stat) >= 90, warn: getRate(stat) < 90 }]">
              {{ getRate(stat) }}%
            </span>
          </div>
          <div class="model-details">
            <span>{{ stat.request_count || 0 }} 请求</span>
            <span>{{ formatNumber(stat.total_tokens) }} Token</span>
            <span class="cache-hint" v-if="stat.cache_hits">缓存 {{ stat.cache_hits }}</span>
          </div>
          <div class="model-bar">
            <div
              class="bar-fill"
              :style="{ width: getRate(stat) + '%' }"
              :class="{ good: getRate(stat) >= 90, warn: getRate(stat) < 90 }"
            ></div>
          </div>
        </div>

        <div v-if="stats.length === 0" class="empty-state">
          暂无统计数据
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { computed } from 'vue'

  const props = defineProps({
    stats: { type: Array, default: () => [] }
  })

  defineEmits(['refresh'])

  const totalRequests = computed(() =>
    props.stats.reduce((sum, s) => sum + (s.request_count || 0), 0)
  )

  const totalTokens = computed(() =>
    formatNumber(props.stats.reduce((sum, s) => sum + (s.total_tokens || 0), 0))
  )

  const successRate = computed(() => {
    const total = props.stats.reduce((sum, s) => sum + (s.success_count || 0) + (s.failure_count || 0), 0)
    if (total === 0) return 0
    const success = props.stats.reduce((sum, s) => sum + (s.success_count || 0), 0)
    return Math.round((success / total) * 100)
  })

  function getRate(stat) {
    const total = (stat.success_count || 0) + (stat.failure_count || 0)
    if (total === 0) return 0
    return Math.round(((stat.success_count || 0) / total) * 100)
  }

  function formatModel(key) {
    return key?.split('/').pop()?.split('-').slice(0, 2).join('-') || '未知'
  }

  function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
    return String(n)
  }
</script>

<style scoped>
  .agent-stats-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-secondary, #16213e);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .panel-header h4 { margin: 0; font-size: 14px; }

  .btn-icon-sm {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm svg { width: 14px; height: 14px; }

  .stats-content { flex: 1; overflow-y: auto; padding: 16px; }

  .stats-overview {
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
  }

  .overview-item {
    flex: 1;
    text-align: center;
    padding: 16px 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
  }

  .overview-value {
    display: block;
    font-size: 24px;
    font-weight: 700;
    color: var(--accent-color, #4f46e5);
    margin-bottom: 4px;
  }

  .overview-label {
    font-size: 12px;
    color: var(--text-secondary, #9ca3af);
  }

  .model-list { display: flex; flex-direction: column; gap: 12px; }

  .model-item {
    padding: 12px;
    border-radius: 8px;
    background: var(--bg-tertiary, #1f2937);
  }

  .model-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }

  .model-name { font-size: 13px; font-weight: 500; }
  .model-rate { font-size: 13px; font-weight: 600; }
  .model-rate.good { color: #10b981; }
  .model-rate.warn { color: #f59e0b; }

  .model-details {
    display: flex;
    gap: 12px;
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
    margin-bottom: 8px;
  }

  .cache-hint { color: var(--accent-color, #4f46e5); }

  .model-bar {
    height: 4px;
    border-radius: 2px;
    background: var(--bg-secondary, #16213e);
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
  }

  .bar-fill.good { background: #10b981; }
  .bar-fill.warn { background: #f59e0b; }

  .empty-state {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary, #9ca3af);
    font-size: 13px;
  }
</style>
