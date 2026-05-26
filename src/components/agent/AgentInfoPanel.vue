<template>
  <div class="right-panel">
    <div class="thinking-section">
      <div class="section-header">
        <h2>Agent 思考过程</h2>
        <button class="btn-sm" @click="$emit('clear-thinking')">清空</button>
      </div>
      <div v-if="messages.length > 0" class="thinking-timeline">
        <div v-for="(msg, index) in messages" :key="index" class="thinking-item">
          <div class="thinking-dot"></div>
          <div class="thinking-content">
            <div class="thinking-meta">
              <span class="agent-name">{{ msg.agent }}</span>
              <span v-if="msg.model" class="model-badge">{{ msg.model }}</span>
              <span v-if="msg.phase" class="phase-tag">{{ msg.phase }}</span>
              <span class="thinking-time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="thinking-message">{{ msg.message }}</div>
          </div>
        </div>
      </div>
      <div v-else class="empty-thinking"><p>暂无思考记录</p></div>
    </div>

    <div class="steps-section">
      <div class="section-header">
        <h2>执行步骤</h2>
        <button class="btn-sm" @click="$emit('clear-steps')">清空</button>
      </div>
      <div v-if="steps.length > 0" class="steps-list">
        <div v-for="(detail, index) in steps" :key="index" class="step-item">
          <div class="step-number">{{ index + 1 }}</div>
          <div class="step-content">
            <div class="step-category">{{ detail.category }}</div>
            <div class="step-description">{{ detail.description }}</div>
          </div>
          <div class="step-time">{{ formatTime(detail.timestamp) }}</div>
        </div>
      </div>
      <div v-else class="empty-steps"><p>暂无执行记录</p></div>
    </div>

    <div class="logs-section">
      <div class="section-header">
        <h2>消息日志</h2>
        <button class="btn-sm" @click="$emit('clear-logs')">清空</button>
      </div>
      <div v-if="logs.length > 0" ref="logsContainer" class="logs-container">
        <div v-for="(log, index) in logs" :key="index" class="log-item" :class="`log-${log.level}`">
          <span class="log-level-badge">{{ log.level.toUpperCase() }}</span>
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
      <div v-else class="empty-logs"><p>暂无日志记录</p></div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'

const props = defineProps({
  messages: { type: Array, required: true },
  steps: { type: Array, required: true },
  logs: { type: Array, required: true }
})
defineEmits(['clear-thinking', 'clear-steps', 'clear-logs'])

const logsContainer = ref(null)

watch(() => props.logs.length, () => {
  nextTick(() => {
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
  })
}, { immediate: true })

function formatTime(timestamp) {
  if (!timestamp) return ''
  return new Date(timestamp).toLocaleTimeString()
}
</script>
