<template>
  <div class="workflow-file-preview">
    <div class="file-header">
      <h3>{{ filename }}</h3>
      <button @click="onClose" class="close-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    </div>
    
    <div class="file-content">
      <pre><code v-html="highlightedContent"></code></pre>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import 'highlight.js/styles/github-dark.css'

hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)

const props = defineProps({
  content: {
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

const getFileExtension = (filename) => {
  return filename.split('.').pop().toLowerCase()
}

const getLanguage = (ext) => {
  const langMap = {
    'py': 'python',
    'js': 'javascript',
    'json': 'json',
    'txt': 'plaintext'
  }
  return langMap[ext] || 'plaintext'
}

const highlightedContent = computed(() => {
  const ext = getFileExtension(props.filename)
  const lang = getLanguage(ext)
  
  if (lang === 'plaintext') {
    return props.content
  }
  
  try {
    return hljs.highlight(props.content, { language: lang }).value
  } catch (e) {
    return props.content
  }
})
</script>

<style scoped>
.workflow-file-preview {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.file-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.file-header h3 {
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

.file-content {
  max-height: 400px;
  overflow-y: auto;
  padding: 16px;
}

.file-content pre {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre;
}
</style>
</component>