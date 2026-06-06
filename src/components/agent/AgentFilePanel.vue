<template>
  <div class="agent-file-panel">
    <!-- 文件编辑器 -->
    <div v-if="selectedFile" class="editor-section">
      <div class="editor-header">
        <div class="editor-info">
          <span class="editor-filename">{{ selectedFile.name }}</span>
          <span class="editor-path">{{ selectedFile.path }}</span>
          <span class="editor-lang">{{ language }}</span>
        </div>
        <div class="editor-actions">
          <button v-if="hasDiff" class="editor-btn" @click="$emit('show-diff')">变更</button>
          <button class="editor-btn" @click="$emit('save-version')">保存</button>
          <button class="editor-btn" @click="$emit('version-history')">历史</button>
          <button class="editor-btn" @click="$emit('copy')">复制</button>
          <button class="editor-btn" @click="$emit('download')">下载</button>
          <button class="editor-btn btn-delete" @click="$emit('delete-file')">删除</button>
        </div>
      </div>
      <div class="code-block" v-html="highlightedCode"></div>
      <div class="editor-footer">
        <span>{{ lineCount }} 行</span>
        <span>{{ fileSize }}</span>
        <span>{{ language }}</span>
        <span v-if="fileComplexity" class="complexity-badge" :class="`complexity-${fileComplexity.level}`">
          复杂度: {{ fileComplexity.level }}
        </span>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" width="48" height="48">
          <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
          <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
      </div>
      <p class="empty-text">选择文件查看预览</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  selectedFile: { type: Object, default: null },
  highlightedCode: { type: String, default: '' },
  lineCount: { type: Number, default: 0 },
  fileSize: { type: String, default: '0 B' },
  language: { type: String, default: 'Unknown' },
  hasDiff: { type: Boolean, default: false },
  fileComplexity: { type: Object, default: null }
})

defineEmits(['show-diff', 'save-version', 'version-history', 'copy', 'download', 'delete-file'])
</script>

<style scoped>
.agent-file-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.editor-section {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-secondary);
  flex-wrap: wrap;
  gap: 8px;
}
.editor-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.editor-filename {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.editor-path {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.editor-lang {
  font-size: 10px;
  padding: 2px 6px;
  background: color-mix(in srgb, var(--primary), transparent 90%);
  color: var(--primary);
  border-radius: 4px;
  font-weight: 500;
}
.editor-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.editor-btn {
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 11px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.editor-btn:hover { background: var(--bg-secondary); border-color: var(--primary); color: var(--primary); }
.btn-delete:hover { border-color: var(--danger); color: var(--danger); }
.code-block {
  flex: 1;
  overflow: auto;
  padding: 16px;
  font-family: 'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  background: var(--bg-primary);
}
.editor-footer {
  display: flex;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--border-color);
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
}
.complexity-badge {
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 500;
}
.complexity-low { background: color-mix(in srgb, var(--success), transparent 90%); color: var(--success); }
.complexity-medium { background: color-mix(in srgb, var(--warning), transparent 90%); color: var(--warning); }
.complexity-high { background: color-mix(in srgb, var(--danger), transparent 90%); color: var(--danger); }

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
}
.empty-icon { margin-bottom: 12px; opacity: 0.5; }
.empty-text { font-size: 14px; }
</style>
