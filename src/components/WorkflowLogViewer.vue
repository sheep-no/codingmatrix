<template>
  <div class="workflow-log-viewer">
    <div class="log-header">
      <div class="log-header-left">
        <h4>执行日志</h4>
        <span v-if="activeNode" class="active-node-badge">{{ activeNode.title || activeNode.id }}</span>
      </div>
      <div class="log-header-right">
        <select v-model="logLevel" class="level-select">
          <option value="all">全部</option>
          <option value="info">信息</option>
          <option value="warn">警告</option>
          <option value="error">错误</option>
        </select>
        <button class="btn-icon-sm" title="清空" @click="clearLogs">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
        </button>
        <button class="btn-icon-sm" :class="{ active: autoScroll }" title="自动滚动" @click="autoScroll = !autoScroll">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
            <polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
          </svg>
        </button>
        <button class="btn-icon-sm" :class="{ active: wrapLines }" title="自动换行" @click="wrapLines = !wrapLines">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="15" y2="18"/><polyline points="11 14 15 18 11 22"/>
          </svg>
        </button>
      </div>
    </div>

    <div class="log-content" ref="logContainer">
      <div v-if="filteredLogs.length === 0" class="log-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
        <p>暂无日志输出</p>
      </div>

      <div v-for="entry in filteredLogs" :key="entry.id" :class="['log-entry', `level-${entry.level}`]">
        <span class="log-timestamp">{{ formatTime(entry.timestamp) }}</span>
        <span :class="['log-badge', `badge-${entry.level}`]">{{ entry.level.toUpperCase() }}</span>
        <span v-if="entry.node" class="log-node">{{ entry.node }}</span>
        <span class="log-message" v-html="highlightMessage(entry.message)"></span>
      </div>
    </div>

    <div class="log-footer">
      <span class="log-count">{{ filteredLogs.length }} 条日志</span>
      <span v-if="errorCount > 0" class="error-count">{{ errorCount }} 个错误</span>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, watch, nextTick } from 'vue'

  const props = defineProps({
    logs: { type: Array, default: () => [] },
    activeNode: { type: Object, default: null }
  })

  const logLevel = ref('all')
  const autoScroll = ref(true)
  const wrapLines = ref(false)
  const logContainer = ref(null)

  const filteredLogs = computed(() => {
    if (logLevel.value === 'all') return props.logs
    return props.logs.filter(entry => entry.level === logLevel.value)
  })

  const errorCount = computed(() => props.logs.filter(e => e.level === 'error').length)

  watch(() => props.logs.length, () => {
    if (autoScroll.value && logContainer.value) {
      nextTick(() => {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      })
    }
  })

  function clearLogs() {
    // 通过事件通知父组件清空
  }

  function formatTime(ts) {
    if (!ts) return ''
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  function highlightMessage(msg) {
    if (!msg) return ''
    // 高亮关键字
    let result = escapeHtml(msg)
    result = result.replace(/(ERROR|FATAL|Exception)/g, '<span class="highlight-error">$1</span>')
    result = result.replace(/(WARN|WARNING)/g, '<span class="highlight-warn">$1</span>')
    result = result.replace(/(SUCCESS|OK|Completed)/g, '<span class="highlight-success">$1</span>')
    result = result.replace(/`(.*?)`/g, '<code class="inline-code">$1</code>')
    return result
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }

  // 暴露添加日志的方法供外部调用
  defineExpose({
    addLog(entry) {
      const emit = defineEmits(['add'])
      emit('add', entry)
    }
  })
</script>

<style scoped>
  .workflow-log-viewer {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-primary, #0f172a);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
  }

  .log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
  }

  .log-header-left { display: flex; align-items: center; gap: 12px; }
  .log-header-left h4 { margin: 0; font-size: 14px; font-family: inherit; }

  .active-node-badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    background: var(--accent-muted, #4f46e533);
    color: var(--accent-color, #4f46e5);
  }

  .log-header-right { display: flex; align-items: center; gap: 8px; }

  .level-select {
    padding: 4px 8px;
    border-radius: 4px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-tertiary, #1f2937);
    color: var(--text-primary, #e0e0e0);
    font-size: 12px;
    font-family: inherit;
  }

  .btn-icon-sm {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }
  .btn-icon-sm svg { width: 16px; height: 16px; }

  .log-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    font-size: 12px;
    line-height: 1.6;
  }

  .log-entry {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 4px 0;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .log-entry:last-child { border-bottom: none; }

  .log-timestamp { color: var(--text-secondary, #6b7280); flex-shrink: 0; font-size: 11px; }

  .log-badge {
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .badge-info { background: #3b82f622; color: #3b82f6; }
  .badge-warn { background: #f59e0b22; color: #f59e0b; }
  .badge-error { background: #ef444422; color: #ef4444; }
  .badge-debug { background: #6b728022; color: #6b7280; }

  .log-node {
    color: var(--accent-color, #4f46e5);
    flex-shrink: 0;
    font-size: 11px;
  }

  .log-message { flex: 1; word-break: break-all; }
  .wrapLines .log-message { white-space: pre-wrap; }
  .log-message:not(.wrapLines) { white-space: nowrap; }

  .highlight-error { color: #ef4444; font-weight: 600; }
  .highlight-warn { color: #f59e0b; font-weight: 600; }
  .highlight-success { color: #10b981; font-weight: 600; }
  .inline-code {
    padding: 1px 4px;
    border-radius: 3px;
    background: var(--bg-tertiary, #1f2937);
    color: #e879f9;
  }

  .log-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-secondary, #6b7280);
  }

  .log-empty svg { width: 48px; height: 48px; opacity: 0.3; margin-bottom: 12px; }
  .log-empty p { font-size: 13px; font-family: inherit; }

  .log-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    border-top: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    font-size: 11px;
    color: var(--text-secondary, #9ca3af);
  }

  .error-count { color: #ef4444; }
</style>
