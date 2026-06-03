<template>
  <div class="file-preview-panel">
    <div class="panel-header">
      <h3>文件预览</h3>
      <button class="close-panel" @click="$emit('close')">×</button>
    </div>
    <div class="file-preview-body">
      <div class="file-list">
        <div
          v-for="file in files"
          :key="file.path"
          class="file-list-item"
          :class="{ active: selectedFile === file.path }"
          @click="selectFile(file.path)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="file-icon-small">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
          <span class="file-path">{{ file.path }}</span>
        </div>
      </div>
      <div v-if="selectedFile" class="file-content-view">
        <div class="file-content-header">
          <span class="file-name">{{ selectedFile }}</span>
          <div class="file-actions">
            <button class="btn-small" @click="$emit('copy', selectedFile)">复制</button>
            <button class="btn-small btn-danger-small" @click="$emit('delete', selectedFile)">删除</button>
          </div>
        </div>
        <pre class="file-code"><code>{{ fileContent }}</code></pre>
      </div>
      <div v-else class="file-content-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <p>选择文件查看内容</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

defineProps({
  files: { type: Array, required: true },
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'select', 'copy', 'delete', 'load'])

const selectedFile = ref(null)
const fileContent = ref('')

watch(selectedFile, async (newPath) => {
  if (newPath) {
    emit('select', newPath)
  } else {
    fileContent.value = ''
  }
})

function selectFile(filePath) {
  selectedFile.value = filePath
}

function setContent(content) {
  fileContent.value = content
}

function reset() {
  selectedFile.value = null
  fileContent.value = ''
}

defineExpose({ selectFile, setContent, reset })
</script>

<style scoped>
.file-preview-panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.close-panel {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  font-size: 18px;
}

.close-panel:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.file-preview-body {
  display: flex;
  min-height: 300px;
  max-height: 70vh;
  height: 400px;
}

.file-list {
  width: 250px;
  overflow-y: auto;
  border-right: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.file-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.file-list-item:hover {
  background: var(--bg-tertiary);
}

.file-list-item.active {
  background: var(--primary);
  color: white;
}

.file-icon-small {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.file-path {
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-content-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
}

.file-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.file-actions {
  display: flex;
  gap: 8px;
}

.btn-small {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-small:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.btn-danger-small {
  border-color: var(--danger);
  color: var(--danger);
}

.btn-danger-small:hover {
  background: var(--danger);
  color: white;
}

.file-code {
  flex: 1;
  margin: 0;
  padding: 16px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.6;
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.file-content-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.file-content-empty svg {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.file-content-empty p {
  margin: 0;
  font-size: 14px;
}
</style>
