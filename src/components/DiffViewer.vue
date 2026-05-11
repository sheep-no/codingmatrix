<template>
  <div class="diff-viewer">
    <div class="diff-header">
      <h3>文件差异对比</h3>
      <div class="diff-controls">
        <select v-model="diffType" class="diff-type-selector">
          <option value="line">行级对比</option>
          <option value="word">词级对比</option>
          <option value="char">字符级对比</option>
        </select>
        <button @click="toggleUnified" class="diff-mode-btn">
          {{ unified ? '并排模式' : '统一模式' }}
        </button>
      </div>
    </div>
    
    <div v-if="unified" class="diff-unified">
      <div 
        v-for="(line, index) in unifiedDiff" 
        :key="index" 
        class="diff-line"
        :class="getLineClass(line.type)"
      >
        <span class="diff-line-number">{{ getLineNumber(line, index) }}</span>
        <span class="diff-content">{{ line.content }}</span>
      </div>
    </div>
    
    <div v-else class="diff-split">
      <div class="diff-original">
        <div class="diff-panel-header">原始版本</div>
        <div class="diff-lines">
          <div 
            v-for="(line, index) in originalLines" 
            :key="index" 
            class="diff-line"
            :class="getOriginalLineClass(index)"
          >
            <span class="diff-line-number">{{ index + 1 }}</span>
            <span class="diff-content">{{ line }}</span>
          </div>
        </div>
      </div>
      
      <div class="diff-modified">
        <div class="diff-panel-header">修改版本</div>
        <div class="diff-lines">
          <div 
            v-for="(line, index) in modifiedLines" 
            :key="index" 
            class="diff-line"
            :class="getModifiedLineClass(index)"
          >
            <span class="diff-line-number">{{ index + 1 }}</span>
            <span class="diff-content">{{ line }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

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

const diffType = ref('line')
const unified = ref(true)

// 简单的行级diff算法
const computeDiff = () => {
  const originalLines = props.original.split('\n')
  const modifiedLines = props.modified.split('\n')
  
  // 找出差异
  const maxLength = Math.max(originalLines.length, modifiedLines.length)
  const unifiedDiff = []
  const changes = []
  
  for (let i = 0; i < maxLength; i++) {
    const origLine = originalLines[i] || ''
    const modLine = modifiedLines[i] || ''
    
    if (origLine === modLine) {
      unifiedDiff.push({ type: 'unchanged', content: origLine, lineNumber: i + 1 })
    } else {
      if (origLine) {
        unifiedDiff.push({ type: 'deleted', content: origLine, lineNumber: i + 1 })
      }
      if (modLine) {
        unifiedDiff.push({ type: 'added', content: modLine, lineNumber: i + 1 })
      }
      changes.push(i)
    }
  }
  
  return {
    unifiedDiff,
    originalLines,
    modifiedLines,
    changes
  }
}

const diffResult = computed(() => computeDiff())

const unifiedDiff = computed(() => diffResult.value.unifiedDiff)
const originalLines = computed(() => diffResult.value.originalLines)
const modifiedLines = computed(() => diffResult.value.modifiedLines)
const changes = computed(() => diffResult.value.changes)

const getLineClass = (type) => {
  return {
    'diff-unchanged': type === 'unchanged',
    'diff-deleted': type === 'deleted',
    'diff-added': type === 'added'
  }
}

const getOriginalLineClass = (index) => {
  return {
    'diff-deleted': changes.value.includes(index),
    'diff-context': !changes.value.includes(index)
  }
}

const getModifiedLineClass = (index) => {
  return {
    'diff-added': changes.value.includes(index),
    'diff-context': !changes.value.includes(index)
  }
}

const getLineNumber = (line, index) => {
  if (line.type === 'unchanged') {
    return line.lineNumber
  } else if (line.type === 'deleted') {
    return `-${line.lineNumber}`
  } else if (line.type === 'added') {
    return `+${line.lineNumber}`
  }
  return index + 1
}

const toggleUnified = () => {
  unified.value = !unified.value
}
</script>

<style scoped>
.diff-viewer {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
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

.diff-controls {
  display: flex;
  gap: 8px;
}

.diff-type-selector {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
}

.diff-mode-btn {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.diff-mode-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.diff-unified {
  max-height: 400px;
  overflow-y: auto;
}

.diff-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  max-height: 400px;
}

.diff-original,
.diff-modified {
  border-right: 1px solid var(--border-color);
}

.diff-modified {
  border-right: none;
}

.diff-panel-header {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.diff-lines {
  max-height: 350px;
  overflow-y: auto;
}

.diff-line {
  display: flex;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
}

.diff-line-number {
  padding: 0 8px;
  min-width: 40px;
  text-align: right;
  color: var(--text-tertiary);
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

.diff-context {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}
</style>
</component>