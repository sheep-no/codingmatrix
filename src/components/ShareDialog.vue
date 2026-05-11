<template>
  <Teleport to="body">
    <Transition name="share-dialog-fade">
      <div v-if="visible" class="share-dialog-overlay" @click.self="handleClose">
        <div class="share-dialog">
          <div class="dialog-header">
            <h3>分享消息</h3>
            <button class="close-btn" @click="handleClose">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <div class="dialog-body">
            <!-- 分享链接 -->
            <div class="share-section">
              <h4>分享链接</h4>
              <div class="share-link-row">
                <input
                  ref="linkInputRef"
                  class="share-link-input"
                  :value="shareLink"
                  readonly
                  @click="selectLink"
                />
                <button class="copy-link-btn" @click="copyShareLink">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="5" y="3" width="13" height="13" rx="2" />
                    <path d="M9 16V8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2h-8a2 2 0 01-2-2z" />
                  </svg>
                  复制链接
                </button>
              </div>
            </div>

            <!-- 导出选项 -->
            <div class="export-section">
              <h4>导出为</h4>
              <div class="export-options">
                <button class="export-btn" @click="exportAsMarkdown">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                  </svg>
                  <span>Markdown</span>
                </button>

                <button class="export-btn" :disabled="exportingImage" @click="exportAsImage">
                  <svg v-if="!exportingImage" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  <div v-else class="export-spinner"></div>
                  <span>{{ exportingImage ? '生成中...' : '图片' }}</span>
                </button>
              </div>
            </div>

            <!-- 预览区域 (用于图片导出) -->
            <div ref="previewRef" class="image-preview" :style="{ display: 'none' }">
              <div class="preview-card">
                <div class="preview-header">
                  <span class="preview-title">AI 对话分享</span>
                  <span class="preview-date">{{ formatDate(new Date()) }}</span>
                </div>
                <div v-if="message.prompt" class="preview-prompt">
                  <div class="preview-role preview-user">你</div>
                  <div class="preview-text">{{ message.prompt }}</div>
                </div>
                <div v-if="message.response" class="preview-response">
                  <div class="preview-role preview-ai">AI 助手</div>
                  <div class="preview-text">{{ stripMarkdown(message.response) }}</div>
                </div>
                <div class="preview-footer">
                  由 AI 助手生成
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
  import { ref, computed, watch, nextTick } from 'vue'
  import html2canvas from 'html2canvas'
  import { useClipboard } from '@/composables/useClipboard'
  import { useToast } from '@/composables/useToast'

  const props = defineProps({
    visible: { type: Boolean, default: false },
    message: { type: Object, default: () => ({}) },
    conversationId: { type: [String, Number], default: null }
  })

  const emit = defineEmits(['close'])

  const { copy } = useClipboard()
  const { success, error: showError } = useToast()

  const linkInputRef = ref(null)
  const previewRef = ref(null)
  const exportingImage = ref(false)

  const shareLink = computed(() => {
    const baseUrl = window.location.origin + window.location.pathname
    const params = new URLSearchParams()
    if (props.conversationId) {
      params.set('conversation', props.conversationId)
    }
    if (props.message?.id) {
      params.set('message', props.message.id)
    }
    return params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl
  })

  function formatDate(date) {
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    })
  }

  function stripMarkdown(text) {
    if (!text) return ''
    return text
      .replace(/#{1,6}\s?/g, '')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/^[-*+]\s?/gm, '')
      .replace(/```[\s\S]*?```/g, '[代码块]')
  }

  function selectLink() {
    linkInputRef.value?.select()
  }

  async function copyShareLink() {
    const ok = await copy(shareLink.value)
    if (ok) {
      success('分享链接已复制')
    }
  }

  function exportAsMarkdown() {
    const msg = props.message
    let md = ''

    if (msg.prompt) {
      md += `## 你\n\n${msg.prompt}\n\n`
    }

    if (msg.reasoning) {
      md += `<details>\n<summary>深度思考过程</summary>\n\n${msg.reasoning}\n\n</details>\n\n`
    }

    if (msg.response) {
      md += `## AI 助手\n\n${msg.response}\n\n`
    }

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `message-${msg.id || Date.now()}.md`
    a.click()
    URL.revokeObjectURL(url)
    success('已导出为 Markdown 文件')
  }

  async function exportAsImage() {
    exportingImage.value = true
    try {
      await nextTick()
      const el = previewRef.value
      if (!el) {
        showError('预览区域未找到')
        return
      }

      el.style.display = 'block'
      el.style.position = 'fixed'
      el.style.left = '-9999px'
      el.style.top = '0'

      await nextTick()

      const canvas = await html2canvas(el, {
        backgroundColor: '#f8fafc',
        scale: 2,
        useCORS: true,
        logging: false
      })

      el.style.display = 'none'

      const link = document.createElement('a')
      link.download = `message-${props.message?.id || Date.now()}.png`
      link.href = canvas.toDataURL('image/png')
      link.click()
      success('已导出为图片')
    } catch (err) {
      console.error('导出图片失败:', err)
      showError('导出图片失败')
    } finally {
      exportingImage.value = false
    }
  }

  function handleClose() {
    emit('close')
  }

  watch(
    () => props.visible,
    async val => {
      if (val) {
        await nextTick()
        selectLink()
      }
    }
  )
</script>

<style scoped>
  .share-dialog-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    backdrop-filter: blur(2px);
  }

  .share-dialog {
    background: var(--bg-primary, white);
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 16px;
    width: 90%;
    max-width: 520px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.15);
    animation: dialog-slide-up 0.3s ease;
  }

  @keyframes dialog-slide-up {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px 16px;
    border-bottom: 1px solid var(--border-color, #e2e8f0);
  }

  .dialog-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    color: var(--text-primary, #1e293b);
  }

  .close-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--text-secondary, #64748b);
    cursor: pointer;
    border-radius: 8px;
    transition: background 0.2s;
  }

  .close-btn:hover {
    background: var(--bg-secondary, #f1f5f9);
    color: var(--text-primary, #1e293b);
  }

  .close-btn svg {
    width: 20px;
    height: 20px;
  }

  .dialog-body {
    padding: 20px 24px 24px;
  }

  .share-section,
  .export-section {
    margin-bottom: 24px;
  }

  .share-section:last-child,
  .export-section:last-child {
    margin-bottom: 0;
  }

  h4 {
    margin: 0 0 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary, #64748b);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .share-link-row {
    display: flex;
    gap: 10px;
  }

  .share-link-input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 10px;
    background: var(--bg-secondary, #f8fafc);
    color: var(--text-primary, #1e293b);
    font-size: 13px;
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    cursor: pointer;
    transition: border-color 0.2s;
  }

  .share-link-input:hover {
    border-color: var(--primary-400, #a78bfa);
  }

  .share-link-input:focus {
    outline: none;
    border-color: var(--primary-500, #8b5cf6);
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15);
  }

  .copy-link-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 16px;
    background: var(--gradient-primary, linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%));
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
    white-space: nowrap;
  }

  .copy-link-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
  }

  .copy-link-btn svg {
    width: 16px;
    height: 16px;
  }

  .export-options {
    display: flex;
    gap: 12px;
  }

  .export-btn {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 20px 16px;
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 12px;
    background: var(--bg-primary, white);
    color: var(--text-primary, #1e293b);
    cursor: pointer;
    transition: all 0.2s;
  }

  .export-btn:hover:not(:disabled) {
    border-color: var(--primary-400, #a78bfa);
    background: var(--bg-secondary, #f8fafc);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  .export-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .export-btn svg {
    width: 24px;
    height: 24px;
    color: var(--primary-500, #8b5cf6);
  }

  .export-btn span {
    font-size: 13px;
    font-weight: 600;
  }

  .export-spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--border-color, #e2e8f0);
    border-top-color: var(--primary-500, #8b5cf6);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* Image Preview (hidden, used for html2canvas) */
  .image-preview {
    width: 400px;
    padding: 20px;
    background: #f8fafc;
  }

  .preview-card {
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 18px;
    background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
    color: white;
  }

  .preview-title {
    font-size: 14px;
    font-weight: 700;
  }

  .preview-date {
    font-size: 12px;
    opacity: 0.85;
  }

  .preview-prompt,
  .preview-response {
    padding: 14px 18px;
    border-bottom: 1px solid #e2e8f0;
  }

  .preview-role {
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 6px;
  }

  .preview-user {
    color: #3b82f6;
  }

  .preview-ai {
    color: #8b5cf6;
  }

  .preview-text {
    font-size: 14px;
    line-height: 1.6;
    color: #334155;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .preview-footer {
    padding: 10px 18px;
    text-align: center;
    font-size: 11px;
    color: #94a3b8;
    background: #f8fafc;
  }

  /* Transitions */
  .share-dialog-fade-enter-active,
  .share-dialog-fade-leave-active {
    transition: opacity 0.25s ease;
  }

  .share-dialog-fade-enter-from,
  .share-dialog-fade-leave-to {
    opacity: 0;
  }
</style>
