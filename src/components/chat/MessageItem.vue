<template>
  <div
    class="message-item"
    :class="['message-' + type, { streaming, highlight: isNew }]"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <!-- 操作菜单 -->
    <Transition name="actions-fade">
      <div v-if="showActions && !streaming" class="message-actions">
        <button class="action-btn" title="复制" @click="handleCopy">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="5" y="3" width="13" height="13" rx="2" />
            <path d="M9 16V8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2h-8a2 2 0 01-2-2z" />
          </svg>
        </button>

        <button
          v-if="type === 'ai'"
          class="action-btn"
          title="重新生成"
          @click="$emit('regenerate', id)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10" />
            <path
              d="M20.49 15a9 9 0 11-2.12-9.36L23 10"
            />
          </svg>
        </button>

        <button
          v-if="type === 'user'"
          class="action-btn action-btn-danger"
          title="删除"
          @click="$emit('delete', id)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
          </svg>
        </button>

        <button class="action-btn" title="分享" @click="$emit('share', messageData)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
        </button>
      </div>
    </Transition>

    <!-- 头像 -->
    <div class="message-avatar" :class="`avatar-${type}`">
      <template v-if="type === 'user'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </template>

      <template v-else-if="streaming">
        <div class="typing-indicator">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </template>

      <template v-else>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M9 9l6 6M15 9l-6 6" />
        </svg>
      </template>
    </div>

    <!-- 消息内容 -->
    <div class="message-content">
      <!-- 头部信息 -->
      <div class="message-header">
        <span class="sender-name">{{ type === 'user' ? '你' : 'AI 助手' }}</span>
        <span class="message-time" :datetime="createdAt">
          {{ formatTime(createdAt) }}
        </span>
      </div>

      <!-- 思考过程 -->
      <details
        v-if="reasoning && reasoning.trim()"
        class="thinking-section"
        :open="thinkingOpen !== false"
      >
        <summary class="thinking-summary">
          <div class="thinking-indicator">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
            <span>深度思考过程</span>
          </div>
          <svg
            class="chevron"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </summary>
        <div class="thinking-content markdown-body" v-html="renderMarkdown(reasoning)" />
      </details>

      <!-- AI 回复内容 -->
      <div v-if="response || streaming" class="response-content">
        <div class="response-card">
          <div v-if="type === 'ai'" class="card-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path
                d="M12 2a3 3 0 013 3v7h3a3 3 0 013 3v5a3 3 0 01-3 3H6a3 3 0 01-3-3v-5a3 3 0 013-3h3V5a3 3 0 013-3z"
              />
            </svg>
            <span>AI 回复</span>
          </div>
          <div class="card-content markdown-body" v-html="renderMarkdown(response)" />

          <!-- 下载按钮 (项目生成) -->
          <div v-if="outputDir && !streaming && isProjectGenerator" class="download-actions">
            <Button variant="primary" size="sm" @click="$emit('download', outputDir)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>下载项目</span>
            </Button>
          </div>
        </div>
      </div>

      <!-- 流式输出占位符 -->
      <div v-if="streaming && !response && !reasoning" class="streaming-placeholder">
        <div class="streaming-animation">
          <div class="streaming-circle" />
          <div class="streaming-circle" />
          <div class="streaming-circle" />
        </div>
        <span class="streaming-label">AI 正在思考中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed } from 'vue'
  import DOMPurify from 'dompurify'
  import Button from '../ui/Button.vue'
  import { useClipboard } from '@/composables/useClipboard'

  const props = defineProps({
    id: { type: [String, Number], required: true },
    type: {
      type: String,
      default: 'ai',
      validator: v => ['user', 'ai'].includes(v)
    },
    prompt: { type: String, default: '' },
    response: { type: String, default: '' },
    reasoning: { type: String, default: '' },
    createdAt: { type: [String, Number], default: '' },
    streaming: { type: Boolean, default: false },
    isNew: { type: Boolean, default: false },
    thinkingOpen: { type: Boolean, default: true },
    isProjectGenerator: { type: Boolean, default: false },
    outputDir: { type: String, default: '' }
  })

  const emit = defineEmits(['download', 'share', 'regenerate', 'delete'])

  const showActions = ref(false)
  const { copy } = useClipboard()

  const messageData = computed(() => ({
    id: props.id,
    type: props.type,
    prompt: props.prompt,
    response: props.response,
    reasoning: props.reasoning,
    createdAt: props.createdAt
  }))

  async function handleCopy() {
    let text = ''
    if (props.type === 'user') {
      text = props.prompt
    } else {
      const parts = []
      if (props.reasoning) parts.push(`思考过程：\n${props.reasoning}`)
      if (props.response) parts.push(props.response)
      text = parts.join('\n\n')
    }
    await copy(text)
  }

  // 格式化时间
  const formatTime = timestamp => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now - date

    // 今天
    if (diff < 24 * 60 * 60 * 1000) {
      return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
      })
    }

    // 昨天
    if (diff < 48 * 60 * 60 * 1000) {
      return '昨天'
    }

    // 7 天内
    if (diff < 7 * 24 * 60 * 60 * 1000) {
      const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
      return days[date.getDay()]
    }

    // 超过 7 天显示日期
    return date.toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric'
    })
  }

  // Markdown 渲染（简化版）
  const renderMarkdown = text => {
    if (!text) return ''

    const html = text
      // 代码块
      .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>')
      // 行内代码
      .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
      // 粗体
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      // 斜体
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      // 标题
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      // 列表
      .replace(/^\s*-\s+(.*)$/gim, '<li>$1</li>')
      // 链接
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      // 换行
      .replace(/\n/g, '<br/>')

    return DOMPurify.sanitize(html)
  }
</script>

<style scoped>
  .message-item {
    display: flex;
    gap: var(--spacing-4);
    margin-bottom: var(--spacing-6);
    padding: var(--spacing-4);
    border-radius: var(--radius-lg);
    transition: all var(--transition-fast);
  }

  .message-item:hover {
    background: var(--bg-secondary);
  }

  .message-item.highlight {
    animation: highlight-fade 2s ease;
  }

  @keyframes highlight-fade {
    0%,
    100% {
      background: transparent;
    }
    50% {
      background: var(--color-blue-50);
    }
  }

  /* User Message */
  .message-user {
    flex-direction: row-reverse;
  }

  .message-user .message-content {
    align-items: flex-end;
  }

  .message-user .response-card {
    background: linear-gradient(135deg, var(--color-blue-600) 0%, var(--color-blue-700) 100%);
    color: white;
  }

  .message-user .response-card :deep(*) {
    color: white;
  }

  /* AI Message */
  .message-ai .response-card {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
  }

  /* Avatar */
  .message-avatar {
    width: 40px;
    height: 40px;
    border-radius: var(--radius-lg);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .avatar-user {
    background: linear-gradient(135deg, var(--color-blue-600) 0%, var(--color-blue-700) 100%);
    color: white;
  }

  .avatar-ai {
    background: linear-gradient(135deg, var(--color-teal-600) 0%, #14b8a6 100%);
    color: white;
  }

  .message-avatar svg {
    width: 24px;
    height: 24px;
  }

  /* Typing Indicator */
  .typing-indicator {
    display: flex;
    gap: 4px;
    padding: 4px;
  }

  .typing-dot {
    width: 8px;
    height: 8px;
    background: currentColor;
    border-radius: 50%;
    animation: bounce 1.4s ease-in-out infinite;
  }

  .typing-dot:nth-child(2) {
    animation-delay: 0.2s;
  }
  .typing-dot:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes bounce {
    0%,
    60%,
    100% {
      transform: translateY(0);
    }
    30% {
      transform: translateY(-4px);
    }
  }

  /* Content */
  .message-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-2);
    min-width: 0;
  }

  .message-header {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
    font-size: var(--text-sm);
  }

  .sender-name {
    font-weight: 600;
    color: var(--text-primary);
  }

  .message-time {
    color: var(--text-tertiary);
    font-size: var(--text-xs);
  }

  /* Thinking Section */
  .thinking-section {
    border-left: 3px solid var(--color-teal-500);
    padding-left: var(--spacing-4);
    margin: var(--spacing-2) 0;
  }

  .thinking-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--spacing-2) 0;
    cursor: pointer;
    font-size: var(--text-sm);
    color: var(--text-secondary);
    font-weight: 600;
    list-style: none;
  }

  .thinking-summary::-webkit-details-marker {
    display: none;
  }

  .thinking-indicator {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
  }

  .thinking-indicator svg {
    width: 18px;
    height: 18px;
    color: var(--color-teal-500);
  }

  .chevron {
    width: 16px;
    height: 16px;
    transition: transform var(--transition-base);
  }

  .thinking-section[open] .chevron {
    transform: rotate(180deg);
  }

  .thinking-content {
    margin-top: var(--spacing-3);
    padding: var(--spacing-3);
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    line-height: 1.6;
    color: var(--text-secondary);
  }

  /* Response Card */
  .response-card {
    padding: var(--spacing-4);
    border-radius: var(--radius-lg);
    line-height: 1.6;
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
    margin-bottom: var(--spacing-3);
    padding-bottom: var(--spacing-3);
    border-bottom: 1px solid var(--border-color);
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-secondary);
  }

  .card-header svg {
    width: 18px;
    height: 18px;
  }

  .card-content {
    font-size: var(--text-base);
    color: var(--text-primary);
  }

  /* Markdown Styles */
  .markdown-body {
    :deep(p) {
      margin-bottom: var(--spacing-2);
    }
    :deep(p:last-child) {
      margin-bottom: 0;
    }

    :deep(h1),
    :deep(h2),
    :deep(h3) {
      margin-top: var(--spacing-4);
      margin-bottom: var(--spacing-2);
      font-weight: 600;
      line-height: 1.4;
    }

    :deep(code.inline-code) {
      background: var(--bg-tertiary);
      padding: 2px 6px;
      border-radius: var(--radius-sm);
      font-size: 0.9em;
      font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    }

    :deep(pre.code-block) {
      background: var(--color-slate-800);
      color: var(--color-slate-100);
      padding: var(--spacing-4);
      border-radius: var(--radius-md);
      overflow-x: auto;
      margin: var(--spacing-3) 0;
    }

    :deep(pre code) {
      background: none;
      padding: 0;
    }

    :deep(ul),
    :deep(ol) {
      padding-left: var(--spacing-6);
      margin: var(--spacing-2) 0;
    }

    :deep(li) {
      margin-bottom: var(--spacing-1);
    }

    :deep(a) {
      color: var(--color-blue-600);
      text-decoration: underline;
    }

    :deep(a:hover) {
      color: var(--color-blue-700);
    }

    :deep(blockquote) {
      border-left: 3px solid var(--border-color);
      padding-left: var(--spacing-3);
      margin: var(--spacing-3) 0;
      color: var(--text-secondary);
    }

    :deep(table) {
      width: 100%;
      border-collapse: collapse;
      margin: var(--spacing-3) 0;
    }

    :deep(th),
    :deep(td) {
      border: 1px solid var(--border-color);
      padding: var(--spacing-2);
      text-align: left;
    }

    :deep(th) {
      background: var(--bg-tertiary);
      font-weight: 600;
    }
  }

  /* Streaming Placeholder */
  .streaming-placeholder {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
    padding: var(--spacing-4);
    color: var(--text-secondary);
  }

  .streaming-animation {
    display: flex;
    gap: 4px;
  }

  .streaming-circle {
    width: 8px;
    height: 8px;
    background: var(--color-blue-500);
    border-radius: 50%;
    animation: pulse 1s ease-in-out infinite;
  }

  .streaming-circle:nth-child(2) {
    animation-delay: 0.2s;
  }
  .streaming-circle:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.5;
      transform: scale(0.8);
    }
  }

  .streaming-label {
    font-size: var(--text-sm);
    font-style: italic;
  }

  /* Download Actions */
  .download-actions {
    margin-top: var(--spacing-4);
    padding-top: var(--spacing-4);
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: flex-end;
  }

  /* Streaming State */
  .message-item.streaming {
    opacity: 0.8;
  }

  /* Message Actions */
  .message-actions {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    gap: 4px;
    background: var(--bg-primary, white);
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 8px;
    padding: 4px;
    box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.1));
    z-index: 10;
  }

  .message-user .message-actions {
    right: auto;
    left: 8px;
  }

  .action-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--text-secondary, #64748b);
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
  }

  .action-btn:hover {
    background: var(--bg-secondary, #f1f5f9);
    color: var(--text-primary, #1e293b);
  }

  .action-btn.action-btn-danger:hover {
    background: #fef2f2;
    color: #ef4444;
  }

  .action-btn svg {
    width: 16px;
    height: 16px;
  }

  .message-item {
    position: relative;
  }

  /* Actions Transition */
  .actions-fade-enter-active,
  .actions-fade-leave-active {
    transition: opacity 0.2s ease;
  }

  .actions-fade-enter-from,
  .actions-fade-leave-to {
    opacity: 0;
  }
</style>
