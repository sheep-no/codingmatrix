<template>
  <div class="agent-code-viewer">
    <div v-if="!content" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
        <polyline points="13 2 13 9 20 9"/>
      </svg>
      <p>选择文件查看内容</p>
    </div>

    <template v-else>
      <div class="viewer-header">
        <div class="file-info">
          <span class="filename">{{ filename }}</span>
          <span class="file-meta">{{ lines }} 行 · {{ formatSize(size) }}</span>
        </div>
        <div class="viewer-actions">
          <button class="btn-icon-sm" title="复制" @click="copyContent">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
          </button>
          <button v-if="editable" class="btn-icon-sm" title="编辑" @click="$emit('edit')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="code-container">
        <div class="line-numbers">
          <div v-for="n in lines" :key="n">{{ n }}</div>
        </div>
        <div class="code-content">
          <pre><code v-if="!isImage" :class="langClass" v-html="highlightedCode"></code></pre>
          <img v-else :src="content" class="image-preview" alt="image" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
  import { computed, watch, ref } from 'vue'
  import hljs from 'highlight.js'

  const props = defineProps({
    filename: { type: String, default: '' },
    content: { type: String, default: '' },
    size: { type: Number, default: 0 },
    editable: { type: Boolean, default: false }
  })

  defineEmits(['edit'])

  const highlightedCode = ref('')

  const langClass = computed(() => {
    const ext = props.filename.split('.').pop()?.toLowerCase() || ''
    const map = {
      js: 'javascript', ts: 'typescript', py: 'python', vue: 'html',
      html: 'html', css: 'css', json: 'json', md: 'markdown',
      yaml: 'yaml', yml: 'yaml', xml: 'xml', sh: 'bash', sql: 'sql',
      java: 'java', go: 'go', rs: 'rust', rb: 'ruby', php: 'php'
    }
    return `language-${map[ext] || 'plaintext'}`
  })

  const isImage = computed(() => {
    return props.filename.match(/\.(png|jpg|jpeg|gif|svg|webp)$/i)
  })

  const lines = computed(() => {
    if (isImage.value) return 0
    return props.content.split('\n').length
  })

  watch(() => props.content, () => {
    if (isImage.value || !props.content) return
    const lang = langClass.value.replace('language-', '')
    if (hljs.getLanguage(lang)) {
      highlightedCode.value = hljs.highlight(props.content, { language: lang, ignoreIllegals: true }).value
    } else {
      highlightedCode.value = escapeHtml(props.content)
    }
  }, { immediate: true })

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  async function copyContent() {
    try {
      await navigator.clipboard.writeText(props.content)
    } catch (e) {
      console.error('Copy failed:', e)
    }
  }
</script>

<style scoped>
  .agent-code-viewer {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--bg-primary, #1a1a2e);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-secondary, #9ca3af);
  }

  .empty-state svg { width: 48px; height: 48px; opacity: 0.3; margin-bottom: 12px; }
  .empty-state p { font-size: 14px; }

  .viewer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
  }

  .file-info { display: flex; align-items: center; gap: 12px; }
  .filename { font-size: 13px; font-weight: 500; font-family: monospace; }
  .file-meta { font-size: 11px; color: var(--text-secondary, #9ca3af); }

  .viewer-actions { display: flex; gap: 4px; }

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
  .btn-icon-sm svg { width: 16px; height: 16px; }

  .code-container {
    flex: 1;
    display: flex;
    overflow: auto;
  }

  .line-numbers {
    padding: 16px 0;
    text-align: right;
    user-select: none;
    color: var(--text-secondary, #9ca3af);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    line-height: 1.6;
    min-width: 48px;
    padding-right: 12px;
    padding-left: 12px;
    background: var(--bg-secondary, #16213e);
    border-right: 1px solid var(--border-color, #2d3748);
  }

  .code-content {
    flex: 1;
    overflow: auto;
    padding: 16px;
  }

  .code-content pre {
    margin: 0;
    padding: 0;
    background: transparent;
  }

  .code-content code {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    line-height: 1.6;
    background: transparent;
  }

  .image-preview {
    max-width: 100%;
    border-radius: 8px;
  }
</style>
