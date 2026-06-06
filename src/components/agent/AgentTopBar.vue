<template>
  <div class="agent-topbar">
    <div class="topbar-left">
      <h1 class="topbar-title">CodingMatrix</h1>
      <div class="topbar-status" :class="`status-${status}`">
        <span class="status-dot"></span>
        <span class="status-text">{{ statusLabel }}</span>
      </div>
    </div>
    <div class="topbar-right">
      <div v-if="costData && costData.totalTokens > 0" class="topbar-cost">
        <span class="cost-tokens">{{ formatNumber(costData.totalTokens) }} tokens</span>
        <span class="cost-divider">|</span>
        <span class="cost-usd">${{ costData.totalCostUsd?.toFixed(4) || '0.0000' }}</span>
        <span v-if="costData.tokensPerSecond" class="cost-divider">|</span>
        <span v-if="costData.tokensPerSecond" class="cost-speed">{{ costData.tokensPerSecond?.toFixed(0) }} tok/s</span>
      </div>
      <button class="topbar-btn" title="导入项目" @click="$emit('open-upload')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      </button>
      <button class="topbar-btn" title="设置" @click="$emit('open-settings')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
      </button>
      <div ref="moreRef" class="topbar-more">
        <button class="topbar-btn" title="更多" @click="showMore = !showMore">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>
        </button>
        <div v-if="showMore" class="topbar-dropdown" @click="showMore = false">
          <button :disabled="!hasFiles" @click="$emit('save-project')">保存项目</button>
          <button :disabled="!hasFiles" @click="$emit('open-performance')">性能监控</button>
          <button @click="$emit('open-learning')">学习反馈</button>
          <button :disabled="!prompt.trim()" @click="$emit('analyze-complexity')">复杂度分析</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  status: { type: String, default: 'idle' },
  costData: { type: Object, default: null },
  hasFiles: { type: Boolean, default: false },
  prompt: { type: String, default: '' }
})

defineEmits(['open-upload', 'open-settings', 'save-project', 'open-performance', 'open-learning', 'analyze-complexity'])

const showMore = ref(false)
const moreRef = ref(null)

const statusLabel = computed(() => ({
  idle: '空闲',
  running: '运行中',
  failed: '失败',
  completed: '已完成'
}[props.status] || props.status))

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

function handleClickOutside(e) {
  if (moreRef.value && !moreRef.value.contains(e.target)) {
    showMore.value = false
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.agent-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
  z-index: 100;
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.topbar-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--text-primary) 0%, var(--primary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.topbar-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-idle { background: var(--bg-secondary); color: var(--text-secondary); }
.status-idle .status-dot { background: var(--text-tertiary); }
.status-running { background: color-mix(in srgb, var(--primary), transparent 90%); color: var(--primary); }
.status-running .status-dot { background: var(--primary); animation: pulse 1.5s infinite; }
.status-completed { background: color-mix(in srgb, var(--success), transparent 90%); color: var(--success); }
.status-completed .status-dot { background: var(--success); }
.status-failed { background: color-mix(in srgb, var(--danger), transparent 90%); color: var(--danger); }
.status-failed .status-dot { background: var(--danger); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.topbar-right { display: flex; align-items: center; gap: 12px; }
.topbar-cost {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
}
.cost-divider { color: var(--text-tertiary); }
.topbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.topbar-btn:hover { background: var(--bg-secondary); color: var(--text-primary); }
.topbar-more { position: relative; }
.topbar-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  box-shadow: 0 8px 24px var(--shadow-color);
  z-index: 200;
  min-width: 140px;
  overflow: hidden;
}
.topbar-dropdown button {
  display: block;
  width: 100%;
  padding: 8px 14px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s;
}
.topbar-dropdown button:hover { background: var(--bg-secondary); }
.topbar-dropdown button:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
