<template>
  <div class="center-content-wrapper" :class="{ 'has-messages': hasMessages }">
    <!-- 加载骨架屏 -->
    <div v-if="isLoading" role="status" aria-live="polite" class="loading-skeleton">
      <div class="skeleton-header">
        <SkeletonLoader type="circle" width="42px" height="42px" />
        <div class="skeleton-header-info">
          <SkeletonLoader type="text" width="120px" height="17px" />
          <SkeletonLoader type="text" width="60px" height="12px" />
        </div>
      </div>
      <div class="skeleton-messages">
        <SkeletonLoader v-for="i in 4" :key="i" type="chat" :rows="2" animated />
      </div>
    </div>

    <!-- 有消息时的聊天界面 -->
    <div v-else-if="hasMessages" class="chat-interface">
      <!-- 对话头部 -->
      <header class="conversation-header" role="banner">
        <div class="conversation-info">
          <h2 id="conversation-title" class="conversation-title">
            {{
              selectedHistory?.title || truncateTitle(conversationHistory[0]?.prompt) || '新对话'
            }}
          </h2>
          <p class="conversation-kicker">
            <span class="message-count" aria-label="消息数量">{{ conversationHistory.length }} 条</span>
          </p>
        </div>
        <details ref="headerMenuEl" class="header-menu">
          <summary class="header-menu-btn" aria-label="对话操作">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <circle cx="5" cy="12" r="1.6" />
              <circle cx="12" cy="12" r="1.6" />
              <circle cx="19" cy="12" r="1.6" />
            </svg>
          </summary>
          <div class="header-menu-list" role="toolbar" aria-label="对话操作">
            <button type="button" class="header-menu-item" aria-label="导出对话" @click="runHeaderAction(exportConversation)">导出</button>
            <button type="button" class="header-menu-item" aria-label="清空对话" @click="runHeaderAction(clearConversation)">清空</button>
            <button type="button" class="header-menu-item danger" aria-label="关闭对话" @click="runHeaderAction(closeConversation)">关闭</button>
          </div>
        </details>
      </header>

      <!-- 消息列表 -->
      <main
        id="main-content"
        ref="messagesContainer"
        class="messages-container"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="对话消息列表"
        @scroll="handleScroll"
      >
        <!-- 加载更多指示器 -->
        <div v-if="isLoadingMore" role="status" class="load-more-indicator">
          <div class="spinner" aria-hidden="true"></div>
          <span>加载更多历史消息...</span>
        </div>

        <!-- 虚拟滚动顶部占位 -->
        <div
          v-if="conversationHistory.length > VIRTUAL_SCROLL_THRESHOLD"
          class="virtual-spacer"
          :style="{ height: `${offsetY}px` }"
          aria-hidden="true"
        ></div>

        <!-- 消息列表 -->
        <MessageList
          v-slot="{ message }"
          :messages="visibleMessages"
          :start-index="visibleStartIndex"
          @item-resize="handleMessageResize"
        >
          <!-- 用户消息 -->
          <div class="message message-user" :class="{ highlight: message.isNew }">
            <div class="message-avatar avatar-user" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
            <div class="message-body">
              <div class="message-header">
                <span class="sender-name">你</span>
                <time class="message-time" :datetime="message.createdAt ? new Date(message.createdAt).toISOString() : ''">{{ formatMessageTime(message.createdAt) }}</time>
                <button
                  class="message-action-btn"
                  :aria-label="'编辑消息: ' + message.prompt"
                  title="编辑消息"
                  @click="$emit('edit-message', message)"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
              </div>
              <div class="message-text user-text">
                <p>{{ message.prompt }}</p>
                <MessageAttachments :files="message.files" />
              </div>
            </div>
          </div>

          <!-- AI 消息 -->
          <div
            class="message message-ai"
            :class="{ highlight: message.isNew, streaming: message.isStreaming }"
          >
            <div class="message-avatar avatar-ai" aria-hidden="true">
              <svg
                v-if="!message.isStreaming"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M12 3l2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3z" />
              </svg>
              <div v-else class="ai-typing" role="status" aria-label="AI 正在输入">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
              </div>
            </div>
            <div class="message-body">
              <div class="message-header">
                <span class="sender-name sender-ai">CodingMatrix</span>
                <time class="message-time" :datetime="message.createdAt ? new Date(message.createdAt).toISOString() : ''">{{ formatMessageTime(message.createdAt) }}</time>
              </div>

              <!-- 步骤进度条（项目生成模式） -->
              <div
                v-if="message.isProjectGenerator && message.isStreaming && message.maxSteps"
                class="step-progress-bar"
              >
                <div class="step-progress-track">
                  <div
                    class="step-progress-fill"
                    :style="{ width: ((message.currentStep || 0) / message.maxSteps) * 100 + '%' }"
                  ></div>
                </div>
                <span class="step-progress-label">
                  步骤 {{ message.currentStep || 0 }}/{{ message.maxSteps }}
                  <span v-if="message.filesCreated"> | {{ message.filesCreated }} 个文件</span>
                </span>
              </div>

              <!-- 思考过程 -->
              <MessageThinking :message="message" :render-markdown="renderMarkdown" />
              <div v-if="message.model || message.usage" class="message-meta">
                <span v-if="message.model" class="chat-model meta-chip">{{ message.model }}</span>
                <span v-if="message.usage" class="chat-usage meta-chip" aria-label="模型用量">
                  {{ message.usage.total_tokens ?? ((message.usage.prompt_tokens || 0) + (message.usage.completion_tokens || 0)) }} tokens
                </span>
              </div>
              <details v-if="message.toolCalls?.length" class="chat-tool-calls">
                <summary>工具调用 <span>{{ message.toolCalls.length }}</span></summary>
                <div v-for="(toolCall, index) in message.toolCalls" :key="toolCall.id || index" class="chat-tool-call">
                  <strong>{{ toolCall.name || '未命名工具' }}</strong>
                  <code v-if="toolCall.arguments">{{ toolCall.arguments }}</code>
                </div>
              </details>
              <div v-if="message.chatStage" class="chat-stage" role="status">{{ message.chatStage }}</div>
              <div v-if="message.warnings?.length" class="chat-warnings" role="alert">
                <div v-for="(warning, index) in message.warnings" :key="index">{{ warning }}</div>
              </div>
              <details v-if="message.sources?.length" class="chat-sources" aria-label="参考来源">
                <summary class="chat-sources-title">参考来源 <span>{{ message.sources.length }}</span></summary>
                <div class="source-list">
                  <template v-for="(source, index) in message.sources" :key="source.url || source.title || index">
                    <div v-if="source.kind === 'file'" class="source-item">
                      <span class="source-kind">附件</span><span class="source-title">{{ source.title }}</span>
                    </div>
                    <a v-else class="source-item" :href="source.url" target="_blank" rel="noopener noreferrer">
                      <span class="source-kind">网页</span>
                      <span class="source-copy"><span class="source-title">{{ source.title }}</span><span v-if="source.snippet" class="source-snippet">{{ source.snippet }}</span></span>
                    </a>
                  </template>
                </div>
              </details>

              <!-- AI 响应内容 -->
              <div v-if="message.response || message.isStreaming" class="ai-response-content">
                <div class="response-card">
                  <div
                    class="card-content markdown-body"
                    v-html="renderMarkdown(message.response)"
                  ></div>

                  <div v-if="message.requestError" class="response-error-actions" role="alert">
                    <span>{{ message.requestError.message }}</span>
                    <button
                      v-if="message.retryRequest"
                      type="button"
                      class="response-retry-btn"
                      @click="$emit('retry-message', message.retryRequest)"
                    >{{ message.requestError.action || '重试' }}</button>
                  </div>

                  <!-- 下载按钮（项目生成模式） -->
                  <div
                    v-if="message.outputDir && !message.isStreaming && message.isProjectGenerator"
                    class="download-actions"
                  >
                    <button class="download-btn" @click="handleDownload(message.outputDir)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      <span>下载项目</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- 流式输出占位符 -->
              <div
                v-if="message.isStreaming && !message.response && !message.reasoning"
                class="streaming-placeholder"
                role="status"
                aria-label="AI 正在思考中"
              >
                <span class="streaming-label">正在写</span>
              </div>
            </div>
          </div>
        </MessageList>

        <!-- 虚拟滚动底部占位 -->
        <div
          v-if="conversationHistory.length > VIRTUAL_SCROLL_THRESHOLD"
          class="virtual-spacer"
          :style="{ height: `${bottomSpacerHeight}px` }"
          aria-hidden="true"
        ></div>
      </main>
    </div>

    <!-- 空状态 -->
    <EmptyState v-else @quick-prompt="prompt => $emit('quick-prompt', prompt)" />
  </div>
</template>

<script setup>
  import { ref, watch, nextTick, computed, onMounted, onUnmounted } from 'vue'
  import MessageAttachments from './chat/MessageAttachments.vue'
  import MessageList from './chat/MessageList.vue'
  import MessageThinking from './chat/MessageThinking.vue'
  import DOMPurify from 'dompurify'
  import { marked } from 'marked'
  import hljs from 'highlight.js/lib/core'
  import python from 'highlight.js/lib/languages/python'
  import javascript from 'highlight.js/lib/languages/javascript'
  import css from 'highlight.js/lib/languages/css'
  import html from 'highlight.js/lib/languages/xml'
  import typescript from 'highlight.js/lib/languages/typescript'
  import bash from 'highlight.js/lib/languages/bash'
  import json from 'highlight.js/lib/languages/json'
  import yaml from 'highlight.js/lib/languages/yaml'
  import sql from 'highlight.js/lib/languages/sql'
  import dockerfile from 'highlight.js/lib/languages/dockerfile'
  import 'highlight.js/styles/github-dark.css'
  import { api } from '@/utils/api/index'
  import EmptyState from './EmptyState.vue'
  import SkeletonLoader from './SkeletonLoader.vue'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import {
    calculateVisibleRange,
    getMessageOffset,
    getTotalMessageHeight
  } from '@/utils/messageVirtualizer'
  import { cloneForIndexedDb } from '@/utils/cloneForIndexedDb'

  hljs.registerLanguage('python', python)
  hljs.registerLanguage('javascript', javascript)
  hljs.registerLanguage('css', css)
  hljs.registerLanguage('html', html)
  hljs.registerLanguage('typescript', typescript)
  hljs.registerLanguage('bash', bash)
  hljs.registerLanguage('json', json)
  hljs.registerLanguage('yaml', yaml)
  hljs.registerLanguage('sql', sql)
  hljs.registerLanguage('dockerfile', dockerfile)

  const renderer = new marked.Renderer()
  renderer.image = (href, title, text) => {
    return `<img src="${href}" alt="${text}" title="${title || ''}" loading="lazy" decoding="async" class="markdown-image" />`
  }

  marked.setOptions({
    renderer,
    highlight: (code, lang) => {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value
      }
      return hljs.highlightAuto(code).value
    },
    breaks: true,
    gfm: true,
    headerIds: true,
    mangle: false
  })

  const props = defineProps({
    historyItem: { type: Object, default: null },
    conversationHistory: { type: Array, default: () => [] },
    conversationId: { type: [String, Number], default: null },
    hasMoreHistory: { type: Boolean, default: true },
    isLoading: { type: Boolean, default: false }
  })

  const emit = defineEmits([
    'loadMoreHistory',
    'prependHistory',
    'close',
    'syncHistory',
    'quick-prompt',
    'edit-message',
    'retry-message'
  ])

  const selectedHistory = ref(null)
  const messagesContainer = ref(null)
  const headerMenuEl = ref(null)
  const isLoadingMore = ref(false)
  const isHistoryLoaded = ref(false)
  const isUserScrolling = ref(false)
  const shouldAutoScroll = ref(true)
  let userScrollTimer = null
  let copyButtonsTimer = null
  let autoSaveTimer = null
  let scrollFrame = null

  const VIRTUAL_SCROLL_BUFFER = 5
  const VIRTUAL_SCROLL_THRESHOLD = 50
  const measuredMessageHeights = new Map()
  let conversationRevision = 0
  const measurementRevision = ref(0)

  const visibleStartIndex = ref(0)
  const visibleEndIndex = ref(VIRTUAL_SCROLL_THRESHOLD)

  const visibleMessages = computed(() => {
    if (props.conversationHistory.length <= VIRTUAL_SCROLL_THRESHOLD) {
      return props.conversationHistory
    }

    return props.conversationHistory.slice(visibleStartIndex.value, visibleEndIndex.value)
  })

  const totalMessageHeight = computed(() => {
    measurementRevision.value
    return getTotalMessageHeight(props.conversationHistory, measuredMessageHeights)
  })

  const offsetY = computed(() => {
    measurementRevision.value
    return getMessageOffset(
      props.conversationHistory,
      visibleStartIndex.value,
      measuredMessageHeights
    )
  })

  const bottomSpacerHeight = computed(() =>
    Math.max(
      0,
      totalMessageHeight.value -
        getMessageOffset(props.conversationHistory, visibleEndIndex.value, measuredMessageHeights)
    )
  )

  const updateVisibleRange = () => {
    if (!messagesContainer.value || props.conversationHistory.length <= VIRTUAL_SCROLL_THRESHOLD)
      return

    const container = messagesContainer.value
    const { start, end } = calculateVisibleRange({
      messages: props.conversationHistory,
      measuredHeights: measuredMessageHeights,
      scrollTop: container.scrollTop,
      viewportHeight: container.clientHeight,
      buffer: VIRTUAL_SCROLL_BUFFER
    })

    visibleStartIndex.value = start
    visibleEndIndex.value = end
  }

  const handleMessageResize = async ({ key, height }) => {
    const revision = conversationRevision
    const container = messagesContainer.value
    const scrollTop = container?.scrollTop
    const previousHeight = measuredMessageHeights.get(key)
    if (previousHeight !== undefined && Math.abs(previousHeight - height) < 0.5) return
    measuredMessageHeights.set(key, height)
    measurementRevision.value++
    const keepBottom = shouldAutoScroll.value && !isUserScrolling.value
    await nextTick()
    if (revision !== conversationRevision || container !== messagesContainer.value) return
    if (keepBottom && shouldAutoScroll.value && !isUserScrolling.value && container?.scrollTop === scrollTop) scrollToBottom()
    updateVisibleRange()
  }

  const FULL_TITLE = '欢迎使用 AI 助手'
  const FULL_SUBTITLE = '您的智能编程伙伴，让创意触手可及'

  const typingTitle = ref('')
  const typingSubtitle = ref('')
  const showSubtitle = ref(false)

  let titleTimer = null
  let subtitleTimer = null

  const startTypingAnimation = () => {
    typingTitle.value = ''
    showSubtitle.value = false

    let i = 0
    titleTimer = setInterval(() => {
      if (i < FULL_TITLE.length) {
        typingTitle.value += FULL_TITLE[i]
        i++
      } else {
        clearInterval(titleTimer)
        showSubtitle.value = true
        startSubtitleTyping()
      }
    }, 80)
  }

  const startSubtitleTyping = () => {
    typingSubtitle.value = ''

    let i = 0
    subtitleTimer = setInterval(() => {
      if (i < FULL_SUBTITLE.length) {
        typingSubtitle.value += FULL_SUBTITLE[i]
        i++
      } else {
        clearInterval(subtitleTimer)
      }
    }, 50)
  }

  const getParticleStyle = n => {
    const size = Math.random() * 6 + 4
    const left = Math.random() * 100
    const delay = Math.random() * 10
    const duration = Math.random() * 10 + 15
    return {
      width: `${size}px`,
      height: `${size}px`,
      left: `${left}%`,
      animationDelay: `${delay}s`,
      animationDuration: `${duration}s`
    }
  }

  const carouselPrompts = [
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>', text: '帮我写一个五子棋小游戏' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>', text: '用 Python 分析 CSV 数据并生成图表' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>', text: '设计一个个人博客网站' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>', text: '写一个 Docker 部署配置' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>', text: '做一个响应式登录页面' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>', text: '解释 Transformer 模型原理' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>', text: '帮我润色这段英文邮件' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>', text: '用 CSS 做一个加载动画' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>', text: '对比 React 和 Vue 的优缺点' },
    { icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>', text: '优化这段 SQL 查询性能' }
  ]

  // IndexedDB 相关
  let db = null
  const DB_NAME = 'AIChatDB'
  const DB_VERSION = 1
  const STORE_NAME = 'conversations'

  // 是否有消息
  const hasMessages = computed(() => {
    return props.conversationHistory && props.conversationHistory.length > 0
  })

  // 截断标题
  const truncateTitle = (text, maxLength = 30) => {
    if (!text) return ''
    return text.length > maxLength ? text.slice(0, maxLength) + '...' : text
  }

  // 初始化 IndexedDB
  const initIndexedDB = () => {
    return new Promise((resolve, reject) => {
      if (db) {
        resolve(db)
        return
      }

      const request = indexedDB.open(DB_NAME, DB_VERSION)

      request.onerror = () => {
        console.error('[ERR] IndexedDB init failed:', request.error)
        reject(request.error)
      }

      request.onsuccess = () => {
        db = request.result
        // IndexedDB 初始化成功
        resolve(db)
      }

      request.onupgradeneeded = event => {
        const database = event.target.result

        if (!database.objectStoreNames.contains(STORE_NAME)) {
          const objectStore = database.createObjectStore(STORE_NAME, { keyPath: 'conversationId' })
          objectStore.createIndex('conversationId', 'conversationId', { unique: true })
          objectStore.createIndex('lastUpdated', 'lastUpdated', { unique: false })
          // IndexedDB store 创建成功
        }
      }
    })
  }

  // 保存对话到 IndexedDB
  const saveConversationToIndexedDB = async (conversationId, messages) => {
    if (!conversationId || String(conversationId).startsWith('temp_')) return

    try {
      await initIndexedDB()

      const transaction = db.transaction([STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(STORE_NAME)

      const data = {
        conversationId: String(conversationId),
        messages: cloneForIndexedDb(messages),
        lastUpdated: Date.now()
      }

      const request = objectStore.put(data)

      request.onsuccess = () => {
      }

      request.onerror = () => {
        console.error('[ERR] Save chat to IndexedDB failed:', request.error)
      }
    } catch (error) {
      console.error('[ERR] Save chat to IndexedDB exception:', error)
    }
  }

  // 从 IndexedDB 加载对话
  const loadConversationFromIndexedDB = async conversationId => {
    if (!conversationId || String(conversationId).startsWith('temp_')) return null

    try {
      await initIndexedDB()

      const transaction = db.transaction([STORE_NAME], 'readonly')
      const objectStore = transaction.objectStore(STORE_NAME)
      const request = objectStore.get(String(conversationId))

      return new Promise((resolve, reject) => {
        request.onsuccess = () => {
          if (request.result) {
            resolve(request.result.messages)
          } else {
            resolve(null)
          }
        }

        request.onerror = () => {
          reject(request.error)
        }
      })
    } catch (error) {
      console.error('[ERR] Load chat from IndexedDB exception:', error)
      return null
    }
  }

  // 清除 IndexedDB 中的对话
  const clearConversationFromIndexedDB = async conversationId => {
    if (!conversationId) return

    try {
      await initIndexedDB()

      const transaction = db.transaction([STORE_NAME], 'readwrite')
      const objectStore = transaction.objectStore(STORE_NAME)
      const request = objectStore.delete(String(conversationId))

      request.onsuccess = () => {
      }
    } catch (error) {
      console.error('[ERR] Clear IndexedDB chat exception:', error)
    }
  }

  // 监听 historyItem 变化
  watch(
    () => props.historyItem,
    async newItem => {
      if (newItem) {
        selectedHistory.value = newItem
      } else {
        selectedHistory.value = null
        shouldAutoScroll.value = true
      }

      isHistoryLoaded.value = false
      await nextTick()
      setTimeout(() => {
        isHistoryLoaded.value = true
      }, 100)
    }
  )

  watch(
    [() => props.conversationId, isHistoryLoaded],
    async ([, loaded], [, oldLoaded] = []) => {
      const revision = conversationRevision
      if (loaded && !oldLoaded && props.conversationHistory.length > 0 && shouldAutoScroll.value) {
        await nextTick()
        if (revision === conversationRevision && shouldAutoScroll.value && !isUserScrolling.value) scrollToBottom()
      }
    }
  )

  // 实测高度只在切换会话时失效，loaded 变化保留当前窗口。
  watch(() => props.conversationId, () => {
    conversationRevision++
    measuredMessageHeights.clear()
    measurementRevision.value++
    visibleStartIndex.value = 0
    visibleEndIndex.value = VIRTUAL_SCROLL_THRESHOLD
  }, { flush: 'sync' })

  const streamContentSignature = computed(() => {
    const lastMessage = props.conversationHistory.at(-1)
    return [
      props.conversationHistory.length,
      lastMessage?.id,
      lastMessage?.response?.length || 0,
      lastMessage?.reasoning?.length || 0,
      Boolean(lastMessage?.isStreaming)
    ].join(':')
  })

  // 流式内容只监听最后一条消息的轻量签名，避免深度比较整段会话。
  watch(
    streamContentSignature,
    async () => {
      const lastMessage = props.conversationHistory.at(-1)
      const isNearBottom = messagesContainer.value
        ? messagesContainer.value.scrollHeight -
            messagesContainer.value.scrollTop -
            messagesContainer.value.clientHeight <
          50
        : true

      if (lastMessage?.isStreaming && !isUserScrolling.value && isNearBottom) {
        await nextTick()
        scrollToBottom()
      }

      if (copyButtonsTimer) clearTimeout(copyButtonsTimer)
      copyButtonsTimer = setTimeout(async () => {
        await nextTick()
        addCopyButtons()
      }, 500)
    }
  )

  watch(
    () => props.conversationHistory,
    () => {
      if (props.conversationId) {
        if (autoSaveTimer) clearTimeout(autoSaveTimer)
        autoSaveTimer = setTimeout(() => {
          saveConversationToIndexedDB(props.conversationId, props.conversationHistory)
        }, 2000)
      }
    },
    { deep: true }
  )

  // 滚动到底部
  const scrollToBottom = () => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }

  // 保存滚动状态
  const saveScrollState = () => {
    if (!messagesContainer.value) return
    const container = messagesContainer.value
    return {
      scrollTop: container.scrollTop,
      scrollHeight: container.scrollHeight
    }
  }

  // 恢复滚动位置
  const restoreScrollPosition = async scrollState => {
    if (!messagesContainer.value || !scrollState) return

    await nextTick()

    const container = messagesContainer.value
    const newScrollHeight = container.scrollHeight
    const heightDiff = newScrollHeight - scrollState.scrollHeight

    container.scrollTop = scrollState.scrollTop + heightDiff
  }

  const processScroll = async () => {
    if (!messagesContainer.value || isLoadingMore.value) return

    const container = messagesContainer.value
    const scrollTop = container.scrollTop

    updateVisibleRange()

    if (scrollTop === 0 && props.hasMoreHistory) {
      const scrollState = saveScrollState()
      await loadMoreHistory()

      setTimeout(async () => {
        await restoreScrollPosition(scrollState)
      }, 100)
    }
  }

  // 滚动意图立即更新，窗口计算合并到下一帧。
  const handleScroll = () => {
    const container = messagesContainer.value
    if (!container) return
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50

    if (!isNearBottom && shouldAutoScroll.value) {
      isUserScrolling.value = true
      shouldAutoScroll.value = false

      if (userScrollTimer) {
        clearTimeout(userScrollTimer)
      }

      userScrollTimer = setTimeout(() => {
        isUserScrolling.value = false
      }, 2000)
    } else if (isNearBottom && !shouldAutoScroll.value) {
      shouldAutoScroll.value = true
      isUserScrolling.value = false
    }

    if (scrollFrame !== null) return
    scrollFrame = requestAnimationFrame(async () => {
      scrollFrame = null
      await processScroll()
    })
  }

  // 加载更多历史
  const loadMoreHistory = async () => {
    if (!selectedHistory.value?.conversation_id) return

    isLoadingMore.value = true

    try {
      const nextMinId =
        props.conversationHistory.length > 0
          ? Math.min(...props.conversationHistory.map(m => m.id))
          : null

      emit('loadMoreHistory', {
        conversation_id: selectedHistory.value.conversation_id,
        last_history_id: nextMinId,
        limit: 20
      })
    } catch (error) {
      console.error('加载更多历史记录失败:', error)
    } finally {
      isLoadingMore.value = false
    }
  }

  // 渲染 Markdown
  const renderMarkdown = content => {
    if (!content) return ''
    return DOMPurify.sanitize(marked(content))
  }

  // 格式化消息时间
  const formatMessageTime = timestamp => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    const now = new Date()
    const diff = now - date

    // 少于 1 分钟
    if (diff < 60000) {
      return '刚刚'
    }

    // 少于 1 小时
    if (diff < 3600000) {
      return `${Math.floor(diff / 60000)}分钟前`
    }

    // 少于 24 小时
    if (diff < 86400000) {
      return `${Math.floor(diff / 3600000)}小时前`
    }

    // 少于 7 天
    if (diff < 604800000) {
      return `${Math.floor(diff / 86400000)}天前`
    }

    // 更长时间，显示具体日期
    return date.toLocaleDateString('zh-CN', {
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric'
    })
  }

  // 关闭对话
  const closeConversation = () => {
    emit('close')
  }

  const runHeaderAction = action => {
    action()
    if (headerMenuEl.value) headerMenuEl.value.open = false
  }

  // 清空对话
  const clearConversation = async () => {
    try {
      await ElMessageBox.confirm('确定要清空当前会话吗？', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }
    const scrollState = saveScrollState()

    await nextTick()
    emit('prependHistory', [])

    // 清除 IndexedDB 中的对话
    if (props.conversationId) {
      await clearConversationFromIndexedDB(props.conversationId)
    }

    setTimeout(async () => {
      await restoreScrollPosition(scrollState)
    }, 100)
  }

  // 导出对话
  const exportConversation = () => {
    if (props.conversationHistory.length === 0) return

    const exportData = {
      title: selectedHistory.value?.title || '未命名对话',
      createdAt: selectedHistory.value?.created_at || new Date().toISOString(),
      messages: props.conversationHistory
        .flatMap(msg => [
          {
            role: 'user',
            content: msg.prompt,
            timestamp: msg.createdAt
          },
          {
            role: 'assistant',
            content: msg.response,
            reasoning: msg.reasoning,
            timestamp: msg.createdAt
          }
        ])
        .filter(Boolean)
    }

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `conversation-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  // 复制代码
  const copyCode = async (codeElement, buttonElement) => {
    const code = codeElement.textContent

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(code)
      } else {
        const textArea = document.createElement('textarea')
        textArea.value = code
        textArea.style.position = 'fixed'
        textArea.style.left = '-999999px'
        textArea.style.top = '-999999px'
        document.body.appendChild(textArea)
        textArea.select()

        try {
          document.execCommand('copy')
        } catch (err) {
          throw new Error('复制失败', { cause: err })
        }

        document.body.removeChild(textArea)
      }

      const originalHTML = buttonElement.innerHTML
      buttonElement.innerHTML = '<span class="check-icon">✓</span> 已复制'
      buttonElement.classList.add('copied')

      setTimeout(() => {
        buttonElement.innerHTML = originalHTML
        buttonElement.classList.remove('copied')
      }, 2000)
    } catch (error) {
      console.error('复制代码失败:', error)
      buttonElement.textContent = '复制失败'
      setTimeout(() => {
        buttonElement.innerHTML =
          '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="3" width="13" height="13" rx="2"/></svg> 复制'
      }, 2000)
    }
  }

  // 添加复制按钮
  const addCopyButtons = () => {
    const oldButtons = messagesContainer.value?.querySelectorAll('.copy-button')
    if (oldButtons) {
      oldButtons.forEach(btn => btn.remove())
    }

    const codeBlocks = messagesContainer.value?.querySelectorAll('.response-card pre')

    if (!codeBlocks || codeBlocks.length === 0) return

    codeBlocks.forEach(preElement => {
      if (preElement.querySelector('.copy-button')) return

      preElement.style.position = 'relative'

      const codeElement = preElement.querySelector('code')
      const langClass = codeElement
        ? Array.from(codeElement.classList).find(c => c.startsWith('language-'))
        : null
      const lang = langClass ? langClass.replace('language-', '') : ''

      const headerDiv = document.createElement('div')
      headerDiv.className = 'code-block-header'

      if (lang) {
        const langSpan = document.createElement('span')
        langSpan.className = 'code-lang'
        langSpan.textContent = lang
        headerDiv.appendChild(langSpan)
      }

      const copyButton = document.createElement('button')
      copyButton.className = 'copy-button'
      copyButton.setAttribute('type', 'button')
      copyButton.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="3" width="13" height="13" rx="2"/></svg> 复制'

      copyButton.addEventListener('click', async e => {
        e.preventDefault()
        e.stopPropagation()

        if (codeElement) {
          await copyCode(codeElement, copyButton)
        }
      })

      headerDiv.appendChild(copyButton)
      preElement.insertBefore(headerDiv, preElement.firstChild)
    })
  }

  // 处理下载
  const handleDownload = async outputDir => {
    try {
      const token = localStorage.getItem('access_token')
      const downloadUrl = `/api/v1/agent/generate/download/${outputDir}`

      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = `${outputDir}.zip`

      const headers = new Headers()
      headers.append('Authorization', `Bearer ${token}`)

      const response = await fetch(downloadUrl, {
        method: 'GET',
        headers: headers
      })

      if (!response.ok) {
        throw new Error(`下载失败：${response.status}`)
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      link.href = url

      document.body.appendChild(link)
      link.click()

      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('下载失败:', error)
      ElMessage.error(`下载失败：${error.message}`)
    }
  }

  // 组件挂载时初始化
  onMounted(async () => {
    try {
      await initIndexedDB()
    } catch (error) {
      console.error('初始化 IndexedDB 失败:', error)
    }

    await nextTick()
    addCopyButtons()

    setTimeout(() => {
      isHistoryLoaded.value = true
      startTypingAnimation()
    }, 100)
  })

  onUnmounted(() => {
    conversationRevision++
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    if (copyButtonsTimer) clearTimeout(copyButtonsTimer)
    if (userScrollTimer) clearTimeout(userScrollTimer)
    if (titleTimer) clearInterval(titleTimer)
    if (subtitleTimer) clearInterval(subtitleTimer)
    if (scrollFrame !== null) cancelAnimationFrame(scrollFrame)
  })

  defineExpose({
    prependHistory: async newMessages => {
      if (!newMessages || newMessages.length === 0) return

      const scrollState = saveScrollState()
      emit('prependHistory', newMessages)

      await nextTick()
      await restoreScrollPosition(scrollState)

      addCopyButtons()
    }
  })
</script>

<style scoped>
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  .chat-model {
    margin: 0;
    color: inherit;
    font-size: inherit;
    overflow-wrap: anywhere;
  }

  .message-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .meta-chip {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    padding: 3px 8px;
    border: 1px solid var(--control-border);
    border-radius: 999px;
    background: color-mix(in srgb, var(--bg-secondary) 92%, transparent);
    color: var(--text-secondary);
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 11px;
    letter-spacing: 0.02em;
    overflow-wrap: anywhere;
  }

  .chat-stage {
    display: flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    margin: 2px 0 8px;
    padding: 0;
    color: var(--accent-primary);
    background: transparent;
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }

  .chat-stage::before {
    content: '';
    width: 5px;
    height: 5px;
    flex-shrink: 0;
    border-radius: 50%;
    background: currentColor;
  }

  .chat-sources {
    margin: 10px 0 14px;
    border: 1px solid var(--border-color);
    border-radius: 10px;
    background: var(--bg-secondary);
    font-size: 13px;
  }

  .chat-sources-title {
    padding: 10px 12px;
    color: var(--text-secondary);
    cursor: pointer;
    font-weight: 500;
  }

  .chat-sources-title span {
    margin-left: 6px;
    font-variant-numeric: tabular-nums;
    color: var(--color-primary-600);
  }

  .source-list {
    display: grid;
    gap: 4px;
    padding: 0 6px 6px;
  }

  .source-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    min-width: 0;
    padding: 10px;
    border-radius: 6px;
    color: var(--text-primary);
    text-decoration: none;
    overflow-wrap: anywhere;
  }

  a.source-item:hover {
    background: var(--bg-primary);
    color: var(--color-primary-600);
  }

  .source-kind {
    flex-shrink: 0;
    padding: 2px 5px;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 10px;
    color: var(--text-secondary);
  }

  .source-copy { min-width: 0; }
  .source-title { font-weight: 500; }
  .source-snippet {
    display: block;
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--text-secondary);
  }

  .chat-warnings {
    margin: 10px 0;
    padding: 10px 12px;
    border-left: 3px solid var(--color-warning-500);
    border-radius: 0 8px 8px 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-primary);
    background: var(--warning-bg);
    overflow-wrap: anywhere;
  }

  /* 焦点可见样式 */
  :focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 2px;
  }

  .action-btn:focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 2px;
    box-shadow: 0 0 0 4px var(--primary-100, #dbeafe);
  }

  .header-menu-btn:focus-visible,
  .header-menu-item:focus-visible {
    outline: 2px solid var(--accent-primary);
    outline-offset: 2px;
  }

  .message-action-btn:focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 1px;
  }

  .download-btn:focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 2px;
    box-shadow: 0 0 0 4px var(--primary-100, #dbeafe);
  }

  .center-content-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    background: var(--bg-primary);
    overflow: hidden;
    position: relative;
  }

  .center-content-wrapper.has-messages {
    background: var(--bg-primary);
  }

  .chat-interface {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  /* ========================================
    加载骨架屏
    ======================================== */
  .loading-skeleton {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 24px;
    overflow: hidden;
    animation: fadeIn 0.3s ease;
  }

  .skeleton-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 20px;
    margin-bottom: 24px;
    border-bottom: 1px solid var(--border-color);
  }

  .skeleton-header-info {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .skeleton-messages {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 24px;
    overflow-y: auto;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  /* ========================================
    对话头部
    ======================================== */
  .conversation-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 28px 8px;
    background: transparent;
    border-bottom: 1px solid color-mix(in srgb, var(--control-border) 80%, transparent);
    flex-shrink: 0;
    z-index: 100;
  }

  .conversation-info {
    display: flex;
    align-items: baseline;
    gap: 12px;
    min-width: 0;
    flex: 1;
  }

  .conversation-kicker {
    margin: 0;
    min-width: 0;
    flex-shrink: 0;
  }

  .conversation-title {
    min-width: 0;
    font-family: "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", Georgia, serif;
    font-size: clamp(18px, 2.2vw, 26px);
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.2;
    color: var(--text-primary, #1e293b);
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .message-count {
    color: var(--text-tertiary);
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }

  .header-menu {
    flex-shrink: 0;
    position: relative;
  }

  .header-menu-btn {
    list-style: none;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 0;
    border-radius: 999px;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .header-menu-btn::-webkit-details-marker {
    display: none;
  }

  .header-menu-btn::marker {
    content: none;
  }

  .header-menu-btn:hover,
  .header-menu[open] .header-menu-btn {
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .header-menu-btn svg {
    width: 18px;
    height: 18px;
  }

  .header-menu-list {
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    z-index: 20;
    display: grid;
    min-width: 132px;
    padding: 6px;
    border: 1px solid var(--control-border);
    border-radius: 14px;
    background: color-mix(in srgb, var(--bg-secondary) 92%, transparent);
    box-shadow: 0 16px 40px color-mix(in srgb, var(--text-primary) 10%, transparent);
    backdrop-filter: blur(12px);
  }

  .header-menu-item {
    padding: 8px 12px;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: var(--text-primary);
    font-size: 13px;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
  }

  .header-menu-item:hover {
    background: var(--bg-primary);
  }

  .header-menu-item.danger:hover {
    background: var(--danger-bg, color-mix(in srgb, #dc2626 12%, var(--bg-secondary)));
    color: var(--danger, #dc2626);
  }

  /* ========================================
   消息容器
   ======================================== */
  .messages-container {
    flex: 1;
    padding: 28px max(24px, calc((100% - 720px) / 2)) 64px;
    min-height: 0;
    scrollbar-gutter: stable;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0;
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--accent-primary) 6%, transparent), transparent 160px),
      var(--bg-primary);
  }

  .virtual-spacer {
    flex-shrink: 0;
    pointer-events: none;
  }

  .messages-container::-webkit-scrollbar {
    width: 8px;
  }

  .messages-container::-webkit-scrollbar-track {
    background: transparent;
    margin: 8px 0;
  }

  .messages-container::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--slate-300) 0%, var(--slate-400) 100%);
    border-radius: 4px;
    transition: background var(--transition-base);
  }

  .messages-container::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--slate-400) 0%, var(--slate-500) 100%);
  }

  /* 加载更多指示器 */
  .load-more-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 16px;
    background: transparent;
    color: var(--text-tertiary);
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    animation: fadeIn 0.3s ease;
  }

  .spinner {
    width: 22px;
    height: 22px;
    border: 3px solid var(--slate-200);
    border-top-color: var(--primary-500);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* ========================================
   消息样式
   ======================================== */
  .message-wrapper {
    animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .message {
    display: flex;
    gap: 12px;
    position: relative;
  }

  .message-wrapper:nth-child(odd) .message {
    animation-delay: 0s;
  }

  .message-wrapper:nth-child(even) .message {
    animation-delay: 0.05s;
  }

  .message.highlight {
    animation: highlightPulse 2s ease;
  }

  @keyframes highlightPulse {
    0%,
    100% {
      transform: scale(1);
    }
    50% {
      transform: scale(1.01);
    }
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .message-wrapper,
    .message.highlight,
    .typing-dot,
    .streaming-circle {
      animation: none;
    }
  }

  .message-user {
    flex-direction: row-reverse;
    justify-content: flex-start;
  }

  .message-ai {
    align-items: flex-start;
  }

  .message.streaming {
    animation: none;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.85;
    }
  }

  /* 头像 */
  .message-avatar {
    display: none;
  }

  .avatar-user {
    background: color-mix(in srgb, #c45c26 16%, var(--bg-secondary));
    border: 1px solid color-mix(in srgb, #c45c26 35%, var(--control-border));
    color: #c45c26;
  }

  .avatar-ai {
    background: var(--accent-primary);
    color: #fff;
  }

  .message-avatar svg {
    width: 15px;
    height: 15px;
    color: currentColor;
  }

  /* AI 输入指示器 */
  .ai-typing {
    display: flex;
    gap: 3px;
    padding: 0;
    align-items: center;
    justify-content: center;
  }

  .typing-dot {
    width: 4px;
    height: 4px;
    background: #fff;
    border-radius: 50%;
    animation: typingBounce 1.4s ease-in-out infinite;
  }

  .typing-dot:nth-child(1) {
    animation-delay: 0.32s;
  }
  .typing-dot:nth-child(2) {
    animation-delay: 0.16s;
  }
  .typing-dot:nth-child(3) {
    animation-delay: 0s;
  }

  @keyframes typingBounce {
    0%,
    80%,
    100% {
      transform: scale(0.6);
      opacity: 0.5;
    }
    40% {
      transform: scale(1);
      opacity: 1;
    }
  }

  /* 消息主体 */
  .message-body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
    max-width: 100%;
  }

  .message-header {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .sender-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--slate-700);
    letter-spacing: -0.01em;
  }

  .message-user .sender-name {
    color: #c45c26;
    font-size: 11px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }

  .sender-ai {
    color: var(--accent-primary);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  .message-time {
    font-size: 11px;
    color: var(--slate-400);
    font-weight: 500;
  }

  .message-action-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--text-tertiary, #94a3b8);
    cursor: pointer;
    border-radius: 8px;
    opacity: 0;
    transition: opacity 0.15s, background 0.15s, color 0.15s;
  }

  .message-user:hover .message-action-btn {
    opacity: 1;
  }

  .message-user:focus-within .message-action-btn {
    opacity: 1;
  }

  .message-user .message-body {
    align-items: flex-end;
    max-width: min(78%, 560px);
    margin-left: auto;
  }

  .message-user .message-header {
    width: 100%;
    justify-content: flex-end;
  }

  .message-ai .message-body {
    padding: 0 0 4px 18px;
    border-left: 3px solid color-mix(in srgb, #c45c26 42%, var(--accent-primary));
  }

  @media (hover: none) {
    .message-action-btn { opacity: 1; }
  }

  .message-action-btn:hover {
    background: var(--slate-100);
    color: var(--slate-700);
  }

  .message-action-btn svg {
    width: 14px;
    height: 14px;
  }

  /* 用户消息文本 */
  .message-text {
    padding: 12px 16px;
    border-radius: 18px 18px 6px 18px;
    font-size: 15px;
    line-height: 1.65;
    word-break: break-word;
  }

  .user-text {
    background: color-mix(in srgb, #c45c26 12%, var(--bg-secondary));
    color: var(--text-primary);
    border: 1px solid color-mix(in srgb, #c45c26 28%, var(--control-border));
  }

  .user-text p {
    margin: 0;
    white-space: pre-wrap;
  }

  /* ========================================
   思考区域
   ======================================== */
  .step-progress-bar {
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .step-progress-track {
    flex: 1;
    height: 6px;
    background: #e5e7eb;
    border-radius: 3px;
    overflow: hidden;
  }

  .step-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #2563eb);
    border-radius: 3px;
    transition: width 0.4s ease;
  }

  .step-progress-label {
    font-size: 12px;
    color: #6b7280;
    white-space: nowrap;
  }

  /* ========================================
   AI 响应区域
   ======================================== */
  .ai-response-content {
    width: 100%;
  }

  .response-card {
    background: transparent;
    border: 0;
    border-radius: 0;
    overflow: hidden;
    transition: none;
  }

  .response-card:hover {
    border-color: transparent;
  }

  .response-error-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    border: 1px solid color-mix(in srgb, var(--status-danger, #dc2626) 28%, var(--control-border));
    border-radius: 12px;
    background: color-mix(in srgb, var(--status-danger, #dc2626) 8%, var(--bg-secondary));
    color: var(--status-danger, #dc2626);
    font-size: 13px;
  }

  .response-retry-btn {
    flex: 0 0 auto;
    min-height: 32px;
    padding: 0 12px;
    border: 1px solid var(--primary, #14b8a6);
    border-radius: 6px;
    background: transparent;
    color: var(--primary, #0f766e);
    cursor: pointer;
  }

  .response-retry-btn:hover {
    background: var(--primary-50, #f0fdfa);
  }

  .chat-usage {
    margin: 0;
    color: inherit;
    font-size: inherit;
  }

  .chat-tool-calls {
    margin: 4px 0 0;
    padding: 0 12px 10px;
    border: 1px solid var(--control-border);
    border-radius: 12px;
    color: var(--text-secondary);
    background: color-mix(in srgb, var(--bg-secondary) 88%, transparent);
    font-size: 12px;
  }

  .chat-tool-call {
    display: grid;
    gap: 4px;
    margin-top: 6px;
    padding: 8px;
    border: 1px solid var(--border-color, #e2e8f0);
    border-radius: 6px;
    background: var(--bg-secondary, #f8fafc);
  }

  .chat-tool-call code {
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }

  .card-content {
    padding: 2px 0 4px;
    color: var(--text-primary, #1e293b);
    overflow-x: auto;
    font-size: 15px;
    line-height: 1.8;
    overflow-wrap: anywhere;
  }

  /* Markdown 内容样式 */
  .markdown-body :deep(h1),
  .markdown-body :deep(h2),
  .markdown-body :deep(h3) {
    margin: 24px 0 12px;
    color: var(--slate-800);
    font-weight: 700;
    line-height: 1.3;
    letter-spacing: -0.02em;
  }

  .markdown-body :deep(h1) {
    font-size: 24px;
  }
  .markdown-body :deep(h2) {
    font-size: 20px;
  }
  .markdown-body :deep(h3) {
    font-size: 17px;
  }

  .markdown-body :deep(p) {
    margin: 0 0 14px 0;
    color: var(--text-primary);
  }

  .markdown-body :deep(> :first-child) { margin-top: 0; }
  .markdown-body :deep(> :last-child) { margin-bottom: 0; }

  .markdown-body :deep(code) {
    background: var(--bg-secondary, #f1f5f9);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 13px;
    color: var(--primary, #14b8a6);
    border: 1px solid var(--border-color, #e2e8f0);
  }

  .markdown-body :deep(pre) {
    background: #17212f !important;
    padding: 0;
    border-radius: 4px 14px 14px 4px;
    overflow: hidden;
    position: relative;
    margin: 16px 0;
    border: 1px solid var(--control-border);
    border-left: 3px solid #c45c26;
    box-shadow: 0 10px 28px color-mix(in srgb, #c45c26 12%, transparent);
  }

  .markdown-body :deep(pre code) {
    background: transparent;
    color: #e2e8f0;
    font-size: 13px;
    padding: 18px;
    border: none;
    display: block;
    overflow-x: auto;
  }

  .code-block-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 14px;
    background: var(--bg-secondary, #f8fafc);
    border-bottom: 1px solid var(--border-color, #e2e8f0);
  }

  .code-lang {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-tertiary, #94a3b8);
    text-transform: lowercase;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
  }

  /* 复制按钮 */
  .markdown-body :deep(pre .copy-button),
  .code-block-header .copy-button {
    background: var(--primary, #14b8a6);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-base);
    z-index: 10;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .markdown-body :deep(pre .copy-button:hover),
  .code-block-header .copy-button:hover {
    background: var(--primary-hover, #0d9488);
    transform: translateY(-1px);
  }

  .markdown-body :deep(pre .copy-button.copied),
  .code-block-header .copy-button.copied {
    background: var(--success);
    border-color: var(--success);
  }

  /* 下载按钮 */
  .download-actions {
    padding: 14px 16px;
    border-top: 1px solid var(--slate-200);
    background: var(--slate-50);
  }

  .download-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 11px 20px;
    background: var(--gradient-primary);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    transition: all var(--transition-base);
    box-shadow: var(--shadow-md);
  }

  .download-btn:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
  }

  .download-btn svg {
    width: 18px;
    height: 18px;
  }

  /* 流式输出占位符 */
  .streaming-placeholder {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0;
    background: transparent;
    border: 0;
  }

  .streaming-animation {
    display: flex;
    gap: 8px;
  }

  .streaming-circle {
    width: 10px;
    height: 10px;
    background: var(--gradient-primary);
    border-radius: 50%;
    animation: streamingPulse 1.4s ease-in-out infinite;
  }

  .streaming-circle:nth-child(1) {
    animation-delay: 0.32s;
  }
  .streaming-circle:nth-child(2) {
    animation-delay: 0.16s;
  }
  .streaming-circle:nth-child(3) {
    animation-delay: 0s;
  }

  @keyframes streamingPulse {
    0%,
    80%,
    100% {
      transform: scale(0.6);
      opacity: 0.5;
    }
    40% {
      transform: scale(1);
      opacity: 1;
    }
  }

  .streaming-label {
    color: var(--accent-primary);
    font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
  }

  /* ========================================
   空状态
   ======================================== */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    position: relative;
    overflow: hidden;
    background: var(--bg-primary) !important;
  }

  .empty-state-bg {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }

  .bg-circle {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.6;
    animation: floatBg 20s ease-in-out infinite;
  }

  .bg-circle-1 {
    width: min(600px, 80vw);
    height: min(600px, 80vw);
    background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
    top: -200px;
    right: -100px;
    animation-delay: 0s;
    opacity: 0.15;
  }

  .bg-circle-2 {
    width: min(500px, 70vw);
    height: min(500px, 70vw);
    background: linear-gradient(135deg, var(--color-blue-500) 0%, var(--color-blue-600) 100%);
    bottom: -150px;
    left: -100px;
    animation-delay: -7s;
    opacity: 0.12;
  }

  .bg-circle-3 {
    width: min(400px, 60vw);
    height: min(400px, 60vw);
    background: linear-gradient(135deg, var(--color-success-500) 0%, var(--color-success-600) 100%);
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    animation-delay: -14s;
    opacity: 0.1;
  }

  @keyframes floatBg {
    0%,
    100% {
      transform: translate(0, 0) scale(1);
    }
    33% {
      transform: translate(30px, -30px) scale(1.05);
    }
    66% {
      transform: translate(-20px, 20px) scale(0.95);
    }
  }

  .empty-state-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    max-width: 700px;
    padding: 40px;
    z-index: 1;
  }

  .hero-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin-bottom: 32px;
  }

  .hero-icon {
    position: relative;
    width: 120px;
    height: 120px;
    margin-bottom: 28px;
  }

  .icon-ring {
    position: absolute;
    border-radius: 50%;
    border: 2px solid var(--color-primary-400);
    opacity: 0.4;
    animation: pulseRing 3s ease-out infinite;
  }

  .icon-ring-1 {
    inset: 0;
    animation-delay: 0s;
  }

  .icon-ring-2 {
    inset: -15px;
    border-color: var(--color-primary-300);
    animation-delay: 0.5s;
  }

  .icon-ring-3 {
    inset: -30px;
    border-color: var(--color-primary-200);
    animation-delay: 1s;
  }

  @keyframes pulseRing {
    0% {
      transform: scale(1);
      opacity: 0.4;
    }
    100% {
      transform: scale(1.5);
      opacity: 0;
    }
  }

  .icon-core {
    position: absolute;
    inset: 15px;
    background: var(--gradient-primary);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow:
      var(--shadow-xl),
      0 0 40px var(--color-primary-500);
  }

  .icon-core svg {
    width: 40px;
    height: 40px;
    color: white;
  }

  .hero-title {
    font-size: 42px;
    font-weight: 800;
    color: var(--text-primary);
    margin-bottom: 12px;
    letter-spacing: -0.03em;
    text-align: center;
    text-shadow: 0 2px 20px rgba(0, 0, 0, 0.1);
    min-height: 52px;
  }

  .hero-title::after {
    content: '|';
    animation: blink-cursor 1s step-end infinite;
    color: var(--color-primary-500);
    margin-left: 2px;
  }

  @keyframes blink-cursor {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0;
    }
  }

  .hero-subtitle {
    font-size: 18px;
    color: var(--text-secondary);
    text-align: center;
    font-weight: 500;
    min-height: 27px;
  }

  .quick-actions {
    margin-bottom: 32px;
    text-align: center;
  }

  .action-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 16px;
  }

  .action-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: center;
  }

  .action-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 100px;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.25s ease;
    box-shadow: var(--shadow-sm);
  }

  .action-chip:hover {
    background: var(--gradient-primary);
    color: white;
    border-color: transparent;
    transform: translateY(-3px);
    box-shadow:
      var(--shadow-lg),
      0 10px 30px rgba(20, 184, 166, 0.3);
  }

  .action-chip svg {
    width: 18px;
    height: 18px;
  }

  .features-section {
    text-align: center;
    width: 100%;
  }

  .section-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 20px;
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }

  .feature-card {
    background: var(--bg-secondary);
    padding: 24px 20px;
    border-radius: 16px;
    text-align: center;
    box-shadow: var(--shadow-md);
    transition: all 0.3s ease;
    border: 1px solid var(--border-color);
  }

  .feature-card:hover {
    transform: translateY(-8px);
    box-shadow: var(--shadow-xl);
    border-color: var(--color-primary-300);
    background: var(--bg-primary);
  }

  .feature-icon {
    width: 56px;
    height: 56px;
    margin: 0 auto 16px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-md);
  }

  .feature-icon svg {
    width: 28px;
    height: 28px;
    color: white;
  }

  .feature-icon-1 {
    background: linear-gradient(135deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
  }

  .feature-icon-2 {
    background: linear-gradient(135deg, var(--color-blue-500) 0%, var(--color-blue-600) 100%);
  }

  .feature-icon-3 {
    background: linear-gradient(135deg, var(--color-warning-500) 0%, var(--color-warning-600) 100%);
  }

  .feature-content h3 {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 6px;
  }

  .feature-content p {
    font-size: 13px;
    color: var(--text-secondary);
  }

  /* 浮动粒子 */
  .floating-particles {
    position: absolute;
    inset: 0;
    overflow: hidden;
    pointer-events: none;
  }

  .particle {
    position: absolute;
    bottom: -10px;
    background: var(--color-primary-400);
    border-radius: 50%;
    opacity: 0.15;
    animation: float-up linear infinite;
  }

  @keyframes float-up {
    0% {
      transform: translateY(0) rotate(0deg);
      opacity: 0;
    }
    10% {
      opacity: 0.15;
    }
    90% {
      opacity: 0.15;
    }
    100% {
      transform: translateY(-100vh) rotate(720deg);
      opacity: 0;
    }
  }

  /* 灵感提示轮播 */
  .prompt-carousel {
    margin-bottom: 36px;
    width: 100%;
  }

  .carousel-label {
    font-size: 13px;
    color: var(--text-tertiary);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 14px;
    text-align: center;
  }

  .carousel-track {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    animation: fadeInUp 0.6s ease 1.5s both;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(16px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .carousel-item {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-xl, 16px);
    font-size: 13px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-base, 200ms);
    box-shadow: var(--shadow-xs);
    max-width: 260px;
  }

  .carousel-item:hover {
    background: var(--gradient-primary);
    color: #ffffff;
    border-color: transparent;
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .carousel-item:active {
    transform: translateY(0);
  }

  .carousel-icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .carousel-icon svg {
    width: 100%;
    height: 100%;
  }

  .carousel-text {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* 移除旧的样式 */
  .empty-icon,
  .empty-title,
  .empty-description {
    display: none;
  }

  /* ========================================
   响应式设计
   ======================================== */
  @media (max-width: 1024px) {
    .message-user .message-body {
      max-width: min(86%, 560px);
    }

    .features-grid {
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }
  }

  @media (max-width: 768px) {
    .conversation-header {
      padding: 14px 18px;
    }

    .messages-container {
      padding: 16px 14px 40px;
      gap: 0;
    }

    .message-avatar {
      width: 28px;
      height: 28px;
      margin-top: 18px;
    }

    .message-body {
      max-width: 100%;
    }

    .message-user .message-body {
      max-width: calc(100% - 40px);
    }

    .message-ai .message-body {
      padding-left: 10px;
    }

    .card-content { padding: 0; }

    .features-grid {
      grid-template-columns: 1fr;
    }

    .hero-title {
      font-size: 30px;
    }

    .hero-subtitle {
      font-size: 15px;
    }

    .carousel-track {
      gap: 8px;
    }

    .carousel-item {
      font-size: 12px;
      padding: 8px 12px;
    }

    .feature-card {
      padding: 20px;
    }
  }

  @media (max-width: 480px) {
    .conversation-header {
      padding: 12px 14px;
    }

    .conversation-icon {
      width: 38px;
      height: 38px;
    }
  }

  @media (max-width: 480px) {
    .messages-container {
      padding: 12px;
    }

    .empty-title {
      font-size: 26px;
    }

    .empty-description {
      font-size: 14px;
    }
  }

  .markdown-image {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 12px 0;
    transition: opacity 0.3s ease;
  }

  .markdown-image[loading='lazy'] {
    opacity: 0;
  }

  .markdown-image.loaded {
    opacity: 1;
  }

  .markdown-image:hover {
    cursor: zoom-in;
  }
</style>
