<template>
  <div class="workflow-diff-viewer">
    <div class="diff-header">
      <h3>{{ filename }} - 差异对比</h3>
      <button @click="onClose" class="close-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
    
    <div class="diff-content">
      <div class="diff-lines">
        <div 
          v-for="(line, index) in diffLines" 
          :key="index" 
          class="diff-line"
          :class="getLineClass(line.type)"
        >
          <span class="diff-marker">{{ line.marker }}</span>
          <span class="diff-content">{{ line.content }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  original: {
    type: String,
    required: true
  },
  modified: {
    type: String,
    required: true
  },
  filename: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['close'])

const onClose = () => {
  emit('close')
}

// 简单的行级diff算法
const computeDiff = () => {
  const originalLines = props.original.split('\n')
  const modifiedLines = props.modified.split('\n')
  
  const diffLines = []
  let origIndex = 0
  let modIndex = 0
  
  while (origIndex < originalLines.length || modIndex < modifiedLines.length) {
    if (origIndex >= originalLines.length) {
      // 只有修改版本有内容
      diffLines.push({
        type: 'added',
        marker: '+',
        content: modifiedLines[modIndex]
      })
      modIndex++
    } else if (modIndex >= modifiedLines.length) {
      // 只有原始版本有内容
      diffLines.push({
        type: 'deleted',
        marker: '-',
        content: originalLines[origIndex]
      })
      origIndex++
    } else if (originalLines[origIndex] === modifiedLines[modIndex]) {
      // 相同的行
      diffLines.push({
        type: 'unchanged',
        marker: ' ',
        content: originalLines[origIndex]
      })
      origIndex++
      modIndex++
    } else {
      // 不同的行
      diffLines.push({
        type: 'deleted',
        marker: '-',
        content: originalLines[origIndex]
      })
      diffLines.push({
        type: 'added',
        marker: '+',
        content: modifiedLines[modIndex]
      })
      origIndex++
      modIndex++
    }
  }
  
  return diffLines
}

const diffLines = computed(() => computeDiff())

const getLineClass = (type) => {
  return {
    'diff-unchanged': type === 'unchanged',
    'diff-deleted': type === 'deleted',
    'diff-added': type === 'added'
  }
}
</script>

<style scoped>
.workflow-diff-viewer {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
  max-height: 80vh;
}

.diff-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.diff-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.diff-content {
  max-height: 70vh;
  overflow-y: auto;
}

.diff-lines {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.diff-line {
  display: flex;
}

.diff-marker {
  padding: 0 8px;
  min-width: 20px;
  text-align: center;
  background: var(--bg-tertiary);
  border-right: 1px solid var(--border-color);
}

.diff-content {
  padding: 0 12px;
  white-space: pre;
  word-break: break-all;
}

.diff-unchanged {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.diff-deleted {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
}

.diff-added {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
}
</style>
</component>