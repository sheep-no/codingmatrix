<template>
  <div class="page-header">
    <div class="header-left">
      <h1 class="page-title">CodingMatrix</h1>
      <div class="header-actions">
        <button class="btn btn-sm btn-outline" @click="$emit('open-settings')">设置</button>
        <button class="btn btn-sm btn-outline" :disabled="!hasFiles" @click="$emit('open-performance')">性能</button>
        <button class="btn btn-sm btn-outline" :disabled="!hasFiles" @click="$emit('save-project')">保存项目</button>
        <button class="btn btn-sm btn-outline" @click="$emit('open-learning')">学习反馈</button>
        <button class="btn btn-sm btn-outline" :disabled="!prompt.trim()" @click="$emit('analyze-complexity')">复杂度分析</button>
        <button class="btn btn-sm btn-primary" @click="$emit('open-upload')">导入项目</button>
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
const props = defineProps({
  sessionId: { type: String, default: '' },
  sessions: { type: Array, required: true },
  hasFiles: { type: Boolean, required: true },
  prompt: { type: String, required: true }
})
const emit = defineEmits(['open-settings', 'open-performance', 'save-project', 'open-learning', 'analyze-complexity', 'open-upload', 'switch-session', 'new-session', 'delete-session'])

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
</script>
