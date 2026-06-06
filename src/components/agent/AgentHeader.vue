<template>
  <div class="page-header">
    <div class="header-left">
      <h1 class="page-title">CodingMatrix</h1>
      <div class="header-actions">
        <button class="btn btn-sm btn-primary" @click="$emit('open-upload')">导入项目</button>
        <button class="btn btn-sm btn-outline" @click="$emit('open-settings')">设置</button>
        <div ref="moreRef" class="header-more">
          <button class="btn btn-sm btn-outline" @click="showMore = !showMore">
            更多
            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12" style="margin-left:2px"><path d="M4 6l4 4 4-4"/></svg>
          </button>
          <div v-if="showMore" class="header-dropdown" @click="showMore = false">
            <button :disabled="!hasFiles" @click="$emit('save-project')">保存项目</button>
            <button :disabled="!hasFiles" @click="$emit('open-performance')">性能监控</button>
            <button @click="$emit('open-learning')">学习反馈</button>
            <button :disabled="!prompt.trim()" @click="$emit('analyze-complexity')">复杂度分析</button>
          </div>
        </div>
      </div>
    </div>
    <div class="header-center">
      <div class="session-selector">
        <select :value="sessionId" class="session-select" @change="onSessionChange">
          <option value="">新建会话...</option>
          <option v-for="session in sessions" :key="session.id" :value="session.id">
            {{ getModeLabel(session.mode) }} - {{ session.filesCount }} 文件 - {{ formatTime(session.timestamp) }}
          </option>
        </select>
        <button class="btn btn-sm btn-outline" title="新建会话" @click="$emit('new-session')">新建</button>
        <button v-if="sessionId" class="btn btn-sm btn-danger" title="删除会话" @click="$emit('delete-session', sessionId)">删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  sessionId: { type: String, default: '' },
  sessions: { type: Array, required: true },
  hasFiles: { type: Boolean, required: true },
  prompt: { type: String, required: true }
})
const emit = defineEmits(['open-settings', 'open-performance', 'save-project', 'open-learning', 'analyze-complexity', 'open-upload', 'switch-session', 'new-session', 'delete-session'])

const showMore = ref(false)
const moreRef = ref(null)

function onSessionChange(event) {
  emit('switch-session', event.target.value)
}

function getModeLabel(mode) {
  return mode === 'create' ? '新建' : mode === 'modify' ? '修改' : '调试'
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const diff = Date.now() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return new Date(timestamp).toLocaleDateString()
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
.header-more {
  position: relative;
}
.header-dropdown {
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
.header-dropdown button {
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
.header-dropdown button:hover {
  background: var(--bg-secondary);
}
.header-dropdown button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
