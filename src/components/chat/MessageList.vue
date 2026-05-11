<template>
  <div class="chat-interface" role="main" aria-label="对话内容">
    <!-- 空状态 -->
    <div v-if="!hasMessages" class="empty-state">
      <div class="empty-content">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            <circle cx="8" cy="10" r="1" fill="currentColor" />
            <circle cx="12" cy="10" r="1" fill="currentColor" />
            <circle cx="16" cy="10" r="1" fill="currentColor" />
          </svg>
        </div>
        <h1 class="empty-title">欢迎使用 AI 助手</h1>
        <p class="empty-description">开始新的对话，体验智能交流的乐趣</p>

        <div class="features-grid">
          <div class="feature-card">
            <div class="feature-icon icon-1">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path
                  d="M12 2a3 3 0 013 3v7h3a3 3 0 013 3v5a3 3 0 01-3 3H6a3 3 0 01-3-3v-5a3 3 0 013-3h3V5a3 3 0 013-3z"
                />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>
            <h3>智能对话</h3>
            <p>自然流畅的对话体验</p>
          </div>

          <div class="feature-card">
            <div class="feature-icon icon-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </div>
            <h3>代码生成</h3>
            <p>快速生成高质量代码</p>
          </div>

          <div class="feature-card">
            <div class="feature-icon icon-3">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3" />
                <path
                  d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z"
                />
              </svg>
            </div>
            <h3>深度思考</h3>
            <p>复杂问题逐步分析</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 消息列表 -->
    <div v-else class="messages-wrapper">
      <!-- 对话头部 -->
      <header class="conversation-header">
        <div class="header-left">
          <svg
            class="header-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
            <circle cx="8" cy="10" r="1" fill="currentColor" />
            <circle cx="12" cy="10" r="1" fill="currentColor" />
            <circle cx="16" cy="10" r="1" fill="currentColor" />
          </svg>
          <div class="header-info">
            <h2 class="header-title">{{ conversationTitle }}</h2>
            <span class="message-count">{{ conversationHistory.length }} 条消息</span>
          </div>
        </div>

        <div class="header-actions">
          <Button variant="ghost" size="sm" aria-label="导出对话" @click="$emit('export')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
          </Button>

          <Button variant="ghost" size="sm" aria-label="清空对话" @click="$emit('clear')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
          </Button>
        </div>
      </header>

      <!-- 消息容器 -->
      <div
        ref="messagesContainer"
        class="messages-container"
        role="log"
        aria-live="polite"
        aria-label="消息列表"
        @scroll="handleScroll"
      >
        <!-- 加载更多 -->
        <div v-if="isLoadingMore" class="load-more-indicator">
          <div class="spinner" />
          <span>加载更多历史消息...</span>
        </div>

        <!-- 消息列表 -->
        <MessageItem
          v-for="(message, index) in displayMessages"
          :id="message.id || index"
          :key="message.id || index"
          :type="message.isProjectGenerator ? 'ai' : index % 2 === 0 ? 'user' : 'ai'"
          :prompt="message.prompt"
          :response="message.response"
          :reasoning="message.reasoning || message.thinking"
          :created-at="message.createdAt || message.created_at"
          :streaming="message.isStreaming"
          :thinking-open="message.thinkingOpen"
          :is-project-generator="message.isProjectGenerator"
          :output-dir="message.outputDir"
          @download="handleDownload"
          @share="handleShare"
          @regenerate="handleRegenerate"
          @delete="handleDelete"
        />
      </div>
    </div>

    <!-- 分享弹窗 -->
    <ShareDialog
      :visible="showShareDialog"
      :message="shareTarget"
      :conversation-id="conversationId"
      @close="showShareDialog = false"
    />
  </div>
</template>

<script setup>
  import { ref, computed, watch } from 'vue'
  import MessageItem from './MessageItem.vue'
  import Button from '../ui/Button.vue'
  import ShareDialog from '../ShareDialog.vue'

  const props = defineProps({
    conversationHistory: { type: Array, default: () => [] },
    selectedHistoryItem: { type: Object, default: null },
    conversationId: { type: [String, Number], default: null },
    hasMoreHistory: { type: Boolean, default: false }
  })

  const emit = defineEmits([
    'load-more-history',
    'prepend-history',
    'export',
    'clear',
    'download',
    'regenerate',
    'delete'
  ])

  const messagesContainer = ref(null)
  const isLoadingMore = ref(false)
  const showShareDialog = ref(false)
  const shareTarget = ref({})

  const hasMessages = computed(() => props.conversationHistory.length > 0)

  const conversationTitle = computed(() => {
    if (props.selectedHistoryItem?.title) {
      return props.selectedHistoryItem.title
    }
    if (props.conversationHistory[0]?.prompt) {
      return props.conversationHistory[0].prompt.slice(0, 30) + '...'
    }
    return '新对话'
  })

  const displayMessages = computed(() => {
    return props.conversationHistory.map((msg, index) => ({
      ...msg,
      isProjectGenerator: msg.isProjectGenerator || false
    }))
  })

  const handleScroll = e => {
    const { scrollTop, scrollHeight, clientHeight } = e.target

    // 滚动到顶部时加载更多
    if (scrollTop < 100 && props.hasMoreHistory && !isLoadingMore.value) {
      loadMoreHistory()
    }
  }

  const loadMoreHistory = async () => {
    if (!props.conversationId) return

    isLoadingMore.value = true

    const lastMessage = props.conversationHistory[0]

    try {
      emit('load-more-history', {
        conversation_id: props.conversationId,
        last_history_id: lastMessage?.id,
        limit: 20
      })
    } finally {
      isLoadingMore.value = false
    }
  }

  const handleDownload = outputDir => {
    emit('download', outputDir)
  }

  const handleShare = message => {
    shareTarget.value = message
    showShareDialog.value = true
  }

  const handleRegenerate = messageId => {
    emit('regenerate', messageId)
  }

  const handleDelete = messageId => {
    emit('delete', messageId)
  }

  // 自动滚动到底部
  const scrollToBottom = () => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTo({
        top: messagesContainer.value.scrollHeight,
        behavior: 'smooth'
      })
    }
  }

  watch(
    () => props.conversationHistory.length,
    () => {
      if (hasMessages.value) {
        setTimeout(scrollToBottom, 100)
      }
    }
  )

  defineExpose({
    prependHistory: messages => {
      emit('prepend-history', messages)
    },
    scrollToBottom
  })
</script>

<style scoped>
  .chat-interface {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--bg-secondary);
  }

  /* Empty State */
  .empty-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--spacing-6);
  }

  .empty-content {
    text-align: center;
    max-width: 600px;
  }

  .empty-icon {
    width: 80px;
    height: 80px;
    margin: 0 auto var(--spacing-6);
    color: var(--color-blue-500);
  }

  .empty-icon svg {
    width: 100%;
    height: 100%;
  }

  .empty-title {
    font-size: var(--text-2xl);
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: var(--spacing-2);
  }

  .empty-description {
    font-size: var(--text-base);
    color: var(--text-secondary);
    margin-bottom: var(--spacing-8);
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--spacing-4);
    margin-top: var(--spacing-6);
  }

  .feature-card {
    padding: var(--spacing-4);
    background: var(--bg-primary);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-color);
    transition: all var(--transition-base);
  }

  .feature-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .feature-icon {
    width: 48px;
    height: 48px;
    margin: 0 auto var(--spacing-3);
    padding: var(--spacing-3);
    border-radius: var(--radius-lg);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .icon-1 {
    background: linear-gradient(135deg, var(--color-blue-100) 0%, var(--color-blue-50) 100%);
    color: var(--color-blue-600);
  }

  .icon-2 {
    background: linear-gradient(135deg, var(--color-teal-100) 0%, var(--color-teal-50) 100%);
    color: var(--color-teal-600);
  }

  .icon-3 {
    background: linear-gradient(135deg, var(--color-success-100) 0%, var(--color-success-50) 100%);
    color: var(--color-success-600);
  }

  .feature-icon svg {
    width: 24px;
    height: 24px;
  }

  .feature-card h3 {
    font-size: var(--text-base);
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: var(--spacing-1);
  }

  .feature-card p {
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  /* Messages Wrapper */
  .messages-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .conversation-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--spacing-4) var(--spacing-6);
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border-color);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
  }

  .header-icon {
    width: 32px;
    height: 32px;
    color: var(--color-blue-600);
  }

  .header-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .header-title {
    font-size: var(--text-lg);
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  .message-count {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
  }

  .header-actions {
    display: flex;
    gap: var(--spacing-2);
  }

  /* Messages Container */
  .messages-container {
    flex: 1;
    overflow-y: auto;
    padding: var(--spacing-6);
    scroll-behavior: smooth;
  }

  /* Load More Indicator */
  .load-more-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-2);
    padding: var(--spacing-4);
    color: var(--text-secondary);
    font-size: var(--text-sm);
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-color);
    border-top-color: var(--color-blue-600);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* Responsive */
  @media (max-width: 768px) {
    .features-grid {
      grid-template-columns: 1fr;
    }

    .conversation-header {
      padding: var(--spacing-3);
    }

    .messages-container {
      padding: var(--spacing-3);
    }

    .header-title {
      font-size: var(--text-base);
    }
  }
</style>
