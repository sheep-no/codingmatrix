  <template>
    <div class="main-layout">
      <div v-if="isMobile" class="mobile-home-toolbar">
        <button
          ref="homeMenuTrigger"
          class="mobile-home-menu"
          type="button"
          aria-label="打开主导航"
          @click="openHomeDrawer"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" aria-hidden="true">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="18" x2="20" y2="18" />
          </svg>
          <span>导航</span>
        </button>
        <span class="mobile-home-title">CodingMatrix</span>
      </div>

      <ErrorBoundary component-name="左侧边栏">
        <Leftlist
          ref="leftlistRef"
          :class="{ 'sidebar-visible': true, 'mobile-home-drawer-open': homeDrawerOpen }"
          aria-label="主导航"
          :role="homeDrawerOpen ? 'dialog' : undefined"
          :aria-modal="homeDrawerOpen ? 'true' : undefined"
          :tabindex="homeDrawerOpen ? -1 : undefined"
          @select-history="handleSelectHistory"
          @delete-history="handleDeleteHistory"
          @new-conversation="handleNewConversation"
          @use-tool="handleUseTool"
          @login="handleLogin"
          @logout="handleLogout"
        />
      </ErrorBoundary>

      <button
        v-if="homeDrawerOpen"
        class="mobile-home-scrim"
        type="button"
        aria-label="关闭主导航"
        @click="closeHomeDrawer"
      ></button>

      <!-- 主内容区 -->
      <main class="main-content" role="main">
        <ErrorBoundary component-name="对话内容">
          <CenterContent
            ref="centerContentRef"
            :conversation-history="conversationHistory"
            :history-item="selectedHistoryItem"
            :conversation-id="currentConversationId"
            :has-more-history="false"
            :is-loading="isHistoryLoading"
            aria-label="对话内容区"
            @load-more-history="handleLoadMoreHistory"
            @prepend-history="handlePrependHistory"
            @quick-prompt="handleQuickPrompt"
            @edit-message="handleEditMessage"
            @retry-message="handleSendMessage"
          />
        </ErrorBoundary>
      <!-- 底部输入区 -->
      <div class="bottom-wrapper" role="form" aria-label="消息输入区">
        <Bottominput
          ref="bottominputRef"
          :is-streaming="isStreamActive"
          :edit-message="editMessage"
          :conversation-id="currentConversationId"
          @send="handleSendMessage"
          @stop="abortStream"
          @require-login="handleRequireLogin"
          @save-edit="handleSaveEdit"
          @cancel-edit="handleCancelEdit"
        />
      </div>
      </main>

      <!-- Toast 通知 -->
      <ToastContainer />

      <!-- 消息编辑器 -->
      <MessageEditor
        v-if="showMessageEditor"
        :message="editMessage"
        :visible="showMessageEditor"
        @save="handleSaveEdit"
        @cancel="handleCancelEdit"
      />

      <!-- 工具组件们 -->
      <NginxConfig
        v-if="showNginxConfig"
        ref="nginxConfigRef"
        :visible="showNginxConfig"
        @close="() => navigationStore.hideTool('nginxConfig')"
      />

      <Dockerfile
        v-if="showDockerConfig"
        :visible="showDockerConfig"
        @close="() => navigationStore.hideTool('dockerConfig')"
      />

      <VirtualGirl
        v-if="showVirtualGirl"
        ref="virtualGirlRef"
        :visible="showVirtualGirl"
        @close="() => navigationStore.hideTool('virtualGirl')"
        @update:visible="val => { if (!val) navigationStore.hideTool('virtualGirl') }"
      />

      <TaskQueue
        v-if="showTaskQueue"
        :visible="showTaskQueue"
        @close="() => navigationStore.hideTool('taskQueue')"
      />

      <!-- 快捷键帮助弹窗 -->
      <KeyboardShortcutsHelp
        v-if="showShortcutsHelp"
        :visible="showShortcutsHelp"
        @close="showShortcutsHelp = false"
      />
    </div>
  </template>

<script setup>
  import { ref, onMounted, onUnmounted, watch, nextTick, computed, defineAsyncComponent } from 'vue'
  import Bottominput from './bottominput.vue'
  import CenterContent from './centerContent.vue'
  import Leftlist from './leftlist.vue'
  import ErrorBoundary from './ErrorBoundary.vue'
  import { useRoute, useRouter } from 'vue-router'
  import { api } from '@/utils/api/index'
  import { streamManager } from '@/utils/streamManager'
  import { consumeJsonStream } from '@/utils/streamParser'
  import { createStreamUpdateBatcher } from '@/utils/streamUpdateBatcher'
  import { useNavigationStore } from '@/stores/navigation'
  import { useUserStore } from '@/stores/user'
  import { useApiKeyStore } from '@/stores/apikey'
  import { useToast } from '@/composables/useToast'
  import { useOfflineQueue } from '@/composables/useOfflineQueue'
  import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
  import {
    normalizeRequestError,
    extractApiErrorMessage,
    stripTransportPlaceholderLines
  } from '@/utils/requestError'

  // 工具组件延迟加载 - 减少初始包大小
  const NginxConfig = defineAsyncComponent(() => import('./NginxConfig.vue'))
  const Dockerfile = defineAsyncComponent(() => import('./Dockerfile.vue'))
  const VirtualGirl = defineAsyncComponent(() => import('./VirtualGirl.vue'))
  const TaskQueue = defineAsyncComponent(() => import('./TaskQueue.vue'))
  const MessageEditor = defineAsyncComponent(() => import('./MessageEditor.vue'))
  const KeyboardShortcutsHelp = defineAsyncComponent(() => import('./KeyboardShortcutsHelp.vue'))

  const router = useRouter()
  const route = useRoute()
  const apiUrl = import.meta.env.VITE_API_BASE || '/api/v1'

  const navigationStore = useNavigationStore()
  const userStore = useUserStore()
  const apiKeyStore = useApiKeyStore()
  const { error: showError, success: showSuccess } = useToast()
  const offlineQueue = useOfflineQueue()
  const { register } = useKeyboardShortcuts()

  const bottominputRef = ref(null)
  const showShortcutsHelp = ref(false)
  const homeDrawerOpen = ref(false)
  const homeMenuTrigger = ref(null)

  // 移动工具条只在窄屏渲染：常驻 DOM 会让桌面端留下 0x0 的幽灵「导航」按钮，
  // 也会让读屏和自动化在桌面视图里发现一个实际不可见的入口。
  const mobileMediaQuery = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(max-width: 768px)')
    : null
  // 无 matchMedia 的环境（如 jsdom）按移动端处理，与原有 DOM 结构保持一致。
  const isMobile = ref(mobileMediaQuery ? mobileMediaQuery.matches : true)
  const handleMobileChange = event => {
    isMobile.value = event.matches
    if (!event.matches && homeDrawerOpen.value) closeHomeDrawer()
  }

  // 消息编辑状态
  const editMessage = ref('')
  const showMessageEditor = ref(false)

  const leftlistRef = ref(null)
  const centerContentRef = ref(null)
  const virtualGirlRef = ref(null)
  const nginxConfigRef = ref(null)
  const selectedHistoryItem = ref(null)
  const conversationHistory = ref([])
  const currentConversationId = ref(null)
  const tempConversationId = ref(null)
  const conversationHistoryMap = ref(new Map())
  const isLoading = ref(false)
  const isHistoryLoading = ref(false)
  const isStreamActive = ref(false)
  let pageUnloading = false

  const showNginxConfig = computed(() => navigationStore.showNginxConfig)
  const showDockerConfig = computed(() => navigationStore.showDockerConfig)
  const showVirtualGirl = computed(() => navigationStore.showVirtualGirl)
  const showTaskQueue = computed(() => navigationStore.showTaskQueue)

  const MAX_CONVERSATION_CACHE = 50

  const openHomeDrawer = async () => {
    homeDrawerOpen.value = true
    await nextTick()
    leftlistRef.value?.$el?.focus()
  }

  const closeHomeDrawer = async () => {
    homeDrawerOpen.value = false
    await nextTick()
    homeMenuTrigger.value?.focus()
  }

  const handleHomeDrawerKeydown = event => {
    if (!homeDrawerOpen.value) return
    if (event.key === 'Escape') {
      closeHomeDrawer()
      return
    }
    if (event.key !== 'Tab') return

    const drawer = leftlistRef.value?.$el
    const focusable = [...(drawer?.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    ) || [])]
    if (focusable.length === 0) {
      event.preventDefault()
      drawer?.focus()
      return
    }

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer)) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const conversationKey = conversationId => {
    if (conversationId === null || conversationId === undefined || conversationId === '') return ''
    return String(conversationId)
  }

  // 首轮消息拿到后端 conversation_id 后，缓存会从 temp_* 迁移到真实 ID。
  // 流式回调手里的旧 key 随之失效，需要回落到当前会话，否则增量与收尾都会丢。
  const resolveStreamKey = streamConversationId => {
    const key = conversationKey(streamConversationId)
    if (conversationHistoryMap.value.has(key)) return key
    return conversationKey(currentConversationId.value)
  }

  const saveConversationToMap = (conversationId, customHistory = null) => {
    if (conversationId) {
      const key = conversationKey(conversationId)
      const historyToSave = customHistory !== null ? customHistory : conversationHistory.value
      conversationHistoryMap.value.set(key, JSON.parse(JSON.stringify(historyToSave)))

      // LRU 清理：超出上限时淘汰最早的条目
      if (conversationHistoryMap.value.size > MAX_CONVERSATION_CACHE) {
        const evictCount = conversationHistoryMap.value.size - MAX_CONVERSATION_CACHE
        const keys = conversationHistoryMap.value.keys()
        for (let i = 0; i < evictCount; i++) {
          conversationHistoryMap.value.delete(keys.next().value)
        }
      }
    }
  }

  const streamUpdateBatcher = createStreamUpdateBatcher(update => {
    const updateKey = resolveStreamKey(update.conversationId)
    const history = conversationHistoryMap.value.get(updateKey)
    const message = history?.[update.lastIndex]
    if (!message) return

    message.response = (message.response || '') + update.responseDelta
    message.reasoning = (message.reasoning || '') + update.reasoningDelta

    if (String(currentConversationId.value) === updateKey) {
      const visibleMessage = conversationHistory.value[update.lastIndex]
      if (visibleMessage) {
        Object.assign(visibleMessage, {
          response: message.response,
          reasoning: message.reasoning
        })
      }
    }
  })

  const getConversationFromMap = conversationId => {
    if (conversationId) {
      const key = conversationKey(conversationId)
      const cached = conversationHistoryMap.value.get(key)
      if (cached) {
        return JSON.parse(JSON.stringify(cached))
      }
    }
    return null
  }

  const SESSION_RESTORE_MAX_AGE = 24 * 60 * 60 * 1000

  const normalizeHistoryMessage = message => {
    const metadata = message.metadata || {}
    const warnings = (metadata.warnings || []).map(warning => (
      typeof warning === 'string'
        ? warning
        : warning.error || warning.message || warning.stage || JSON.stringify(warning)
    ))

    return {
      id: message.id,
      conversation_id: parseInt(message.conversation_id, 10),
      prompt: message.prompt,
      // 旧版本曾把「出错：HTTP error! status: 400」写进正文，展示前清理。
      response: stripTransportPlaceholderLines(message.response || ''),
      reasoning: message.thinking || '',
      thinkingOpen: true,
      createdAt: message.created_at,
      title: message.title,
      sources: metadata.sources || [],
      model: metadata.model || message.model || '',
      searchDepth: metadata.search_depth || 'shallow',
      warnings,
      searchUnavailable: Boolean(metadata.search_unavailable),
      usage: metadata.usage || message.usage,
      toolCalls: metadata.tool_calls || message.tool_calls || []
    }
  }

  const saveStateToStorage = () => {
    const state = {
      selectedHistoryItem: selectedHistoryItem.value,
      conversationHistory: conversationHistory.value,
      currentConversationId: currentConversationId.value,
      timestamp: Date.now()
    }
    localStorage.setItem('chatState', JSON.stringify(state))
  }

  const restoreStateFromStorage = async () => {
    try {
      const savedState = localStorage.getItem('chatState')
      if (!savedState) return false

      const state = JSON.parse(savedState)
      if (Date.now() - state.timestamp > SESSION_RESTORE_MAX_AGE) {
        localStorage.removeItem('chatState')
        return false
      }

      const conversationId = state.currentConversationId
      if (!conversationId) return false

      const localHistory = state.conversationHistory || []
      const hasLiveStream = localHistory.some(message => message.isStreaming)
        || Boolean(streamManager.getStreamRequestState()?.isStreaming)

      if (hasLiveStream && localHistory.length) {
        currentConversationId.value = conversationId
        conversationHistory.value = localHistory
        selectedHistoryItem.value = state.selectedHistoryItem
        if (String(conversationId).startsWith('temp_')) {
          tempConversationId.value = conversationId
        }
        saveConversationToMap(conversationId)
        return true
      }

      if (String(conversationId).startsWith('temp_')) {
        currentConversationId.value = conversationId
        conversationHistory.value = localHistory
        selectedHistoryItem.value = state.selectedHistoryItem
        tempConversationId.value = conversationId
        saveConversationToMap(conversationId)
        return true
      }

      const cachedHistory = getConversationFromMap(conversationId)
      if (cachedHistory) {
        currentConversationId.value = conversationId
        conversationHistory.value = cachedHistory
        selectedHistoryItem.value = state.selectedHistoryItem
        return true
      }

      try {
        isHistoryLoading.value = true
        const convId = parseInt(conversationId, 10)
        if (isNaN(convId) || convId <= 0) {
          conversationHistory.value = []
          isHistoryLoading.value = false
          return false
        }
        const response = await api.post('/conversation/history', {
          conversation_id: convId,
          last_history_id: null,
          limit: 50
        })

        if (response.ok) {
          const data = await response.json()
          if (data.items && data.items.length > 0) {
            const historyItems = data.items.map(normalizeHistoryMessage)
            currentConversationId.value = conversationId
            conversationHistory.value = historyItems
            selectedHistoryItem.value = state.selectedHistoryItem
            saveConversationToMap(conversationId)
            return true
          }
        }
      } catch (e) {
        console.error('恢复会话历史失败:', e)
      } finally {
        isHistoryLoading.value = false
      }

      localStorage.removeItem('chatState')
      return false
    } catch (error) {
      console.error('[ERR] Restore state failed:', error)
      localStorage.removeItem('chatState')
      return false
    }
  }

  let _saveStateTimer = null
  const debouncedSaveState = () => {
    clearTimeout(_saveStateTimer)
    _saveStateTimer = setTimeout(() => saveStateToStorage(), 1000)
  }

  watch(
    [selectedHistoryItem, conversationHistory, currentConversationId],
    () => {
      debouncedSaveState()
    },
    { deep: true }
  )

  const handleRequireLogin = () => {
    if (leftlistRef.value?.openLogin) {
      leftlistRef.value.openLogin()
    }
  }

  const handleEditMessage = message => {
    editMessage.value = message.prompt
    showMessageEditor.value = true
  }

  const handleSaveEdit = data => {
    const newMessage = typeof data === 'string' ? data : data.newMessage
    const messageData = {
      prompt: newMessage,
      use_reasoning: typeof data === 'object' ? data.use_reasoning : false
    }

    editMessage.value = ''
    showMessageEditor.value = false

    if (!isLoading.value) {
      handleSendMessage(messageData)
    }
  }

  const handleCancelEdit = () => {
    editMessage.value = ''
    showMessageEditor.value = false
  }

  const handleUseTool = toolName => {
    if (homeDrawerOpen.value) closeHomeDrawer()
    navigationStore.showTool(toolName)
  }

  const handleQuickPrompt = prompt => {
    handleSendMessage({
      prompt,
      model: undefined,
      use_reasoning: false
    })
  }

  const createRetryRequest = messageData => {
    const retryRequest = {
      prompt: messageData.prompt,
      model: messageData.model,
      stream: messageData.stream,
      use_reasoning: messageData.use_reasoning,
      search_mode: messageData.search_mode,
      search_depth: messageData.search_depth,
      conversation_id: messageData.conversation_id,
      files: messageData.files,
      is_project_generator: messageData.is_project_generator,
      session_id: messageData.session_id,
      requirement: messageData.requirement
    }
    return Object.fromEntries(Object.entries(retryRequest).filter(([, value]) => value !== undefined))
  }

  const handleSendMessage = async (messageData, options = {}) => {
    const resume = Boolean(options && options.resume)
    if (!userStore.isLoggedIn) {
      handleRequireLogin()
      return
    }
    if (isLoading.value) return

    // 发消息前以后端记录为准：本地缓存可能为空、过期，或残留上一账号的令牌。
    // 每个账号在本次会话内只校准一次，校准失败时退回本地缓存判断。
    if (!messageData.model) {
      try {
        await apiKeyStore.ensureSynced()
      } catch (_error) {
        // 同步失败时按本地缓存继续判断
      }
    }
    if (!apiKeyStore.hasSiliconflowKey && !messageData.model) {
      showError('请先配置 API Key/接口密钥后再使用')
      // 直接落到 API Key 页签，避免用户停留在「自定义供应商」还要自己再切一次
      router.push({ path: '/settings', query: { tab: 'apikey' } })
      return
    }

    // 断网时先入队，网络恢复后由 flushQueue 按序重发
    if (!options.fromQueue && !offlineQueue.isOnline.value) {
      offlineQueue.queueMessage(messageData)
      return
    }

    isLoading.value = true
    isStreamActive.value = true

    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
    streamManager.currentRequestId = requestId

    const abortController = streamManager.createAbortController(requestId)

    if (!currentConversationId.value && !messageData.is_project_generator) {
      const tempId = `temp_${Date.now()}`
      tempConversationId.value = tempId
      currentConversationId.value = tempId

      if (!resume) conversationHistory.value = []
      saveConversationToMap(tempId)

      setTimeout(() => {
        if (leftlistRef.value && leftlistRef.value.addNewHistoryItem) {
          const tempItem = {
            id: tempId,
            conversation_id: tempId,
            title: messageData.prompt.slice(0, 50) + '...',
            prompt: messageData.prompt,
            created_at: new Date().toISOString(),
            is_temp: true
          }
          leftlistRef.value.addNewHistoryItem(tempItem)
        }
      }, 100)
    }

    if (resume) {
      const lastMessage = conversationHistory.value[conversationHistory.value.length - 1]
      if (!lastMessage || lastMessage.prompt !== messageData.prompt) {
        conversationHistory.value.push({
          id: Date.now(),
          prompt: messageData.prompt,
          response: '',
          reasoning: '',
          isStreaming: true,
          chatStage: '正在恢复回答',
          hasThinking: false,
          thinkingOpen: !messageData.is_project_generator,
          projectThinkingOpen: false,
          isProjectGenerator: messageData.is_project_generator || false,
          thinkingContent: '',
          otherContent: '',
          searchUnavailable: false,
          files: messageData.files || []
        })
      } else {
        lastMessage.isStreaming = true
        lastMessage.requestError = null
        lastMessage.retryRequest = null
        lastMessage.chatStage = lastMessage.chatStage || '正在恢复回答'
        lastMessage.response = ''
        lastMessage.reasoning = ''
        lastMessage.searchUnavailable = false
      }
    } else {
      conversationHistory.value.push({
        id: Date.now(),
        prompt: messageData.prompt,
        response: '',
        reasoning: '',
        isStreaming: true,
        hasThinking: false,
        thinkingOpen: messageData.is_project_generator ? false : true,
        projectThinkingOpen: false,
        isProjectGenerator: messageData.is_project_generator || false,
        thinkingContent: '',
        otherContent: '',
        searchUnavailable: false,
        files: messageData.files || []
      })
    }

    saveConversationToMap(currentConversationId.value)
    saveStateToStorage()

    const lastMessageIndex = conversationHistory.value.length - 1
    const currentMessageData = messageData
    const streamConversationId = conversationKey(currentConversationId.value)

    try {
      let response

      if (messageData.is_project_generator) {
        streamManager.saveStreamRequestState(
          {
            prompt: messageData.prompt,
            model: messageData.model,
            is_project_generator: true,
            session_id: messageData.session_id || `project_${Date.now()}`,
            requirement: messageData.prompt
          },
          messageData,
          null
        )

        const requestData = {
          session_id: messageData.session_id || `project_${Date.now()}`,
          requirement: messageData.prompt,
          model: messageData.model,
          api_key_token: apiKeyStore.siliconflowKey?.token
        }
        response = await api.stream('/agent/orchestrate/stream', requestData, abortController.signal)
      } else {
        const shouldSendConversationId =
          currentConversationId.value && !String(currentConversationId.value).startsWith('temp_')
        const sendConversationId = shouldSendConversationId
          ? parseInt(String(currentConversationId.value), 10)
          : null



        const requestData = {
          prompt: messageData.prompt,
          model: messageData.model || undefined,
          stream: true,
          use_reasoning: messageData.use_reasoning || false,
          search_mode: messageData.search_mode || 'auto',
          search_depth: messageData.search_depth || 'shallow',
          conversation_id: sendConversationId,
          api_key_token: apiKeyStore.siliconflowKey?.token
        }

        // 集成 Vision: 将附件文件传递给后端自动处理
        if (messageData.files && messageData.files.length > 0) {
          requestData.files = messageData.files
            .filter(f => f.serverPath || f.server_path)
            .map(f => ({
              server_path: f.serverPath || f.server_path,
              name: f.name,
              type: f.type,
              category: f.category || 'document'
            }))
        }

        streamManager.saveStreamRequestState(
          {
            prompt: requestData.prompt,
            model: requestData.model,
            stream: true,
            use_reasoning: requestData.use_reasoning,
            search_mode: requestData.search_mode,
            search_depth: requestData.search_depth,
            conversation_id: sendConversationId,
            files: requestData.files
          },
          messageData,
          currentConversationId.value
        )

        response = await api.stream('/chat', requestData, abortController.signal)
      }

      if (!response.ok) {
        let apiMessage = ''
        try {
          apiMessage = extractApiErrorMessage(await response.json())
        } catch (e) {
          console.warn('无法解析错误响应:', response.statusText)
        }
        // 优先携带后端可读文案，只有响应体不可解析时才退回状态码。
        const requestError = new Error(apiMessage || `HTTP error! status: ${response.status}`)
        requestError.status = response.status
        throw requestError
      }

      await consumeJsonStream(
        response,
        data => {
          if (currentMessageData.is_project_generator) {
            handleProjectGeneratorStream(data, lastMessageIndex)
          } else {
            handleChatStream(data, streamConversationId, lastMessageIndex, currentMessageData)
          }
        },
        { signal: abortController.signal }
      )

      streamUpdateBatcher.flush()

      if (currentMessageData.is_project_generator) {
        if (conversationHistory.value[lastMessageIndex]) {
          conversationHistory.value[lastMessageIndex].isStreaming = false
        }
      } else {
        const finalConversationKey = resolveStreamKey(streamConversationId)
        const streamHistory = conversationHistoryMap.value.get(finalConversationKey)
        if (streamHistory && streamHistory.length > 0) {
          const streamLastIndex = streamHistory.length - 1
           streamHistory[streamLastIndex].isStreaming = false
           streamHistory[streamLastIndex].chatStage = ''
          saveConversationToMap(finalConversationKey, streamHistory)

          if (String(currentConversationId.value) === finalConversationKey) {
            if (conversationHistory.value[streamLastIndex]) {
              conversationHistory.value[streamLastIndex].isStreaming = false
              conversationHistory.value[streamLastIndex].chatStage = ''
            }
          }
        }
      }
    } catch (error) {
      streamUpdateBatcher.flush()
      // 用户主动停止会以 AbortError 抛出，属于预期结束，不写入错误日志。
      const isUserAbort = error.name === 'AbortError' && abortController.signal.aborted
      if (!isUserAbort) {
        console.error('发送消息失败:', error)
      }

      const failedConversationKey = resolveStreamKey(streamConversationId)
      const streamHistory = conversationHistoryMap.value.get(failedConversationKey)
      if (!pageUnloading && streamHistory && streamHistory.length > 0) {
        const streamLastIndex = streamHistory.length - 1
        const lastMessage = streamHistory[streamLastIndex]

        if (isUserAbort) {
          lastMessage.isStreaming = false
          const existingResponse = lastMessage.response || ''
          const existingReasoning = lastMessage.reasoning || ''

          const pausedLabel = currentMessageData.is_project_generator
            ? '已暂停：项目生成已停止'
            : '已暂停：已停止生成'
          if (!existingResponse.includes(pausedLabel)) {
            lastMessage.response += `\n\n${pausedLabel}`
          }
          if (existingReasoning && !existingReasoning.includes('已暂停：思考已停止')) {
            lastMessage.reasoning =
              existingReasoning + '\n\n已暂停：思考已停止'
          }
        } else {
          const requestError = normalizeRequestError(error)
          const hasPartialContent =
            (lastMessage.response && lastMessage.response.length > 0) ||
            (lastMessage.reasoning && lastMessage.reasoning.length > 0)

          // 已生成的内容保持原样；没有内容时清空正文，错误只由 requestError 卡片展示一次。
          if (!hasPartialContent) lastMessage.response = ''
          lastMessage.requestError = requestError
          lastMessage.retryRequest = requestError.retryable ? createRetryRequest(currentMessageData) : null
        }

        lastMessage.isStreaming = false
        lastMessage.chatStage = ''
        saveConversationToMap(failedConversationKey)

        if (String(currentConversationId.value) === failedConversationKey) {
          if (conversationHistory.value[streamLastIndex]) {
            Object.assign(conversationHistory.value[streamLastIndex], lastMessage)
          }
        }
      }
    } finally {
      if (pageUnloading) {
        saveStateToStorage()
      } else {
        isLoading.value = false
        isStreamActive.value = false
        streamManager.clearStreamRequestState()

        if (
          !currentMessageData.is_project_generator &&
          leftlistRef.value &&
          leftlistRef.value.fetchHistory
        ) {
          leftlistRef.value.fetchHistory()
        }
      }
    }
  }

  // 离线队列接入实际发送链：恢复网络后按序重发队列消息
  offlineQueue.setSendCallback(async messageData => {
    if (isLoading.value) {
      // 抛错让队列保留消息，等下一次 flush 再发送
      throw new Error('正在生成回答，队列消息稍后重试')
    }
    await handleSendMessage(messageData, { fromQueue: true })
  })

  const toggleThinking = message => {
    if (message) {
      message.thinkingOpen = !message.thinkingOpen
    }
  }

  const handleProjectGeneratorStream = (data, lastIndex) => {
    if (!conversationHistory.value[lastIndex]) {
      console.warn('[WARN] Current message record not found:', lastIndex)
      return
    }

    const message = conversationHistory.value[lastIndex]

    switch (data.type) {
      case 'thinking':
        message.isProjectGenerator = true
        if (!message.reasoning) {
          message.reasoning = ''
        }
        message.reasoning += data.message || ''
        // 按 agent 分组存储 thinking
        if (!message.thinkingGroups) {
          message.thinkingGroups = {}
        }
        {
          const agent = data.agent || 'unknown'
          const model = data.model || ''
          if (!message.thinkingGroups[agent]) {
            message.thinkingGroups[agent] = { content: '', model: model }
          }
          message.thinkingGroups[agent].content += data.message || ''
          if (model && !message.thinkingGroups[agent].model) {
            message.thinkingGroups[agent].model = model
          }
        }
        break

      case 'status':
        message.isProjectGenerator = true
        message.response += `**${data.message}**\n\n`
        break

      case 'step_start':
        message.isProjectGenerator = true
        message.currentStep = data.step || 0
        message.maxSteps = data.max_steps || 0
        message.response += `**[步骤 ${data.step}/${data.max_steps}]** ${data.message}\n\n`
        break

      case 'step_end':
        message.isProjectGenerator = true
        message.response += `完成：${data.message}\n\n`
        break

      case 'file_create_start':
        message.isProjectGenerator = true
        message.response += `创建：${data.file_path}\n\n`
        break

      case 'file_created':
        message.isProjectGenerator = true
        message.filesCreated = (message.filesCreated || 0) + 1
        message.response += `完成：${data.file_path} (${data.file_size || ''})\n\n`
        break

      case 'file_error':
        message.isProjectGenerator = true
        message.response += `失败：${data.file_path}\n\n`
        break

      case 'file_skipped':
        message.isProjectGenerator = true
        message.response += `跳过：${data.file_path}\n\n`
        break

      case 'validation':
        message.isProjectGenerator = true
        if (data.status === 'passed') {
          message.response += `完成：${data.message}\n\n`
        } else if (data.status === 'failed') {
          message.response += `警告：${data.message}\n\n`
          if (data.missing_deps) {
            message.response += `警告：缺失依赖：${data.missing_deps.join(', ')}\n\n`
          }
        } else {
          message.response += `提示：${data.message}\n\n`
        }
        break

      case 'validation_progress':
        message.isProjectGenerator = true
        message.response += `提示：${data.message}\n\n`
        break

      case 'validation_complete':
        message.isProjectGenerator = true
        message.response += `完成：验证完成\n\n`
        break

      case 'complete': {
        message.isProjectGenerator = true
        if (data.result && data.result.output_dir) {
          message.outputDir = data.result.output_dir
        }
        const totalFiles = data.result?.total_files_created ?? data.total_files_created ?? 0
        message.filesCreated = totalFiles
        message.currentStep = data.step ?? data.total_steps ?? 0
        message.maxSteps = data.max_steps ?? data.total_steps ?? 0
        message.response += `\n---\n\n**项目生成完成**\n\n`
        message.response += `- 创建文件：${totalFiles} 个\n`
        message.response += `- 输出目录：${data.result?.output_dir ?? data.output_dir ?? '未知'}\n\n`
        message.isStreaming = false
        break
      }

      case 'error':
        message.isProjectGenerator = true
         message.response += `失败：生成失败：${data.message}\n\n`
        message.isStreaming = false
        break

      case 'dependency_check':
        message.isProjectGenerator = true
        message.response += `提示：依赖检查：${data.message}\n\n`
        break

      case 'structure_check':
        message.isProjectGenerator = true
        message.response += `提示：结构检查：${data.message}\n\n`
        break

      case 'tool_start':
        message.isProjectGenerator = true
        message.response += `提示：执行工具：${data.tool_name || data.message}\n\n`
        break

      case 'tool_result':
        message.isProjectGenerator = true
        message.response += `完成：${data.message}\n\n`
        break
    }
  }

  const handleChatStream = (data, streamConversationId, lastIndex, messageData) => {
    // 首轮数据里可能先返回 conversation_id，会话缓存随之换 key，
    // 后续事件必须回落到迁移后的会话，否则回复会静默丢失。
    const activeConversationKey = () => resolveStreamKey(streamConversationId)
    const streamHistory = conversationHistoryMap.value.get(activeConversationKey())
    if (!streamHistory) {
      console.warn('[WARN] Stream chat history not found:', streamConversationId)
      return
    }

    const history = streamHistory

    if (data.stage) {
      const labels = { parsing: '正在解析附件', searching: '正在搜索资料', answering: '正在生成回答' }
      if (data.stage === 'searching' && data.round) labels.searching = `正在搜索资料（第 ${data.round}/${data.total_rounds} 轮）`
      if (history[lastIndex]) {
        history[lastIndex].chatStage = ['completed', 'skipped', 'failed'].includes(data.status) ? '' : labels[data.stage] || data.stage
        if (['failed', 'skipped'].includes(data.status) && data.error) history[lastIndex].warnings = [...(history[lastIndex].warnings || []), data.error]
        if (data.sources) history[lastIndex].sources = data.sources
        if (data.model) history[lastIndex].model = data.model
        if (data.search_depth) history[lastIndex].searchDepth = data.search_depth
        if (data.search_unavailable !== undefined) history[lastIndex].searchUnavailable = data.search_unavailable
        if (String(currentConversationId.value) === activeConversationKey() && conversationHistory.value[lastIndex]) {
          Object.assign(conversationHistory.value[lastIndex], {
            chatStage: history[lastIndex].chatStage,
            sources: history[lastIndex].sources,
            warnings: history[lastIndex].warnings,
            model: history[lastIndex].model,
            searchDepth: history[lastIndex].searchDepth,
            searchUnavailable: history[lastIndex].searchUnavailable
          })
        }
      }
      return
    }

    // 后端错误
    if (data.error) {
      streamUpdateBatcher.flush()
      if (history[lastIndex]) {
        // 与请求失败路径一致：错误只写入 requestError 卡片一次，
        // 避免服务端再回传传输层占位串时正文与卡片各显示一行。
        const requestError = normalizeRequestError({
          message: data.error,
          status: data.status_code || data.status
        })
        Object.assign(history[lastIndex], {
          requestError,
          retryRequest: requestError.retryable ? createRetryRequest(messageData) : null
        })
        if (String(currentConversationId.value) === activeConversationKey() && conversationHistory.value[lastIndex]) {
          Object.assign(conversationHistory.value[lastIndex], {
            requestError: history[lastIndex].requestError,
            retryRequest: history[lastIndex].retryRequest
          })
        }
      }
      return
    }

    if (data.usage && history[lastIndex]) {
      history[lastIndex].usage = data.usage
      if (String(currentConversationId.value) === activeConversationKey() && conversationHistory.value[lastIndex]) {
        conversationHistory.value[lastIndex].usage = data.usage
      }
    }

    if (data.conversation_id !== undefined) {
      const receivedConversationIdRef = data.conversation_id
      const oldConversationId = conversationKey(currentConversationId.value)
      currentConversationId.value = conversationKey(receivedConversationIdRef)

      if (oldConversationId && oldConversationId.startsWith('temp_')) {
        const cachedHistory = conversationHistoryMap.value.get(conversationKey(oldConversationId))
        if (cachedHistory) {
          conversationHistoryMap.value.set(
            conversationKey(receivedConversationIdRef),
            JSON.parse(JSON.stringify(cachedHistory))
          )
          conversationHistoryMap.value.delete(conversationKey(oldConversationId))

        }
      }

      if (tempConversationId.value) {
        tempConversationId.value = null
      }

      setTimeout(() => {
        if (leftlistRef.value && leftlistRef.value.addNewHistoryItem) {
          const newItem = {
            id: receivedConversationIdRef,
            conversation_id: parseInt(receivedConversationIdRef, 10),
            title: messageData.prompt.slice(0, 50) + '...',
            prompt: messageData.prompt,
            created_at: new Date().toISOString()
          }

          if (oldConversationId && oldConversationId.startsWith('temp_')) {
            if (leftlistRef.value.updateHistoryItem) {
              leftlistRef.value.updateHistoryItem(oldConversationId, newItem)
            }
          } else {
            leftlistRef.value.addNewHistoryItem(newItem)
          }
        }

        if (leftlistRef.value && leftlistRef.value.fetchHistory) {
          leftlistRef.value.fetchHistory()
        }
      }, 500)
      return
    }

    if (data.choices && data.choices[0] && history[lastIndex]) {
      const delta = data.choices[0].delta
      if (delta.tool_calls?.length) {
        const toolCalls = history[lastIndex].toolCalls || []
        delta.tool_calls.forEach(toolCall => {
          const index = toolCall.index ?? toolCalls.length
          const current = toolCalls[index] || { id: toolCall.id || '', name: '', arguments: '' }
          current.id = current.id || toolCall.id || ''
          current.name = current.name || toolCall.function?.name || ''
          current.arguments += toolCall.function?.arguments || ''
          toolCalls[index] = current
        })
        history[lastIndex].toolCalls = toolCalls
        if (String(currentConversationId.value) === activeConversationKey() && conversationHistory.value[lastIndex]) {
          conversationHistory.value[lastIndex].toolCalls = toolCalls
        }
      }
      streamUpdateBatcher.enqueue({
        key: `${streamConversationId}:${lastIndex}`,
        conversationId: streamConversationId,
        lastIndex,
        reasoningDelta: delta.reasoning_content || '',
        responseDelta: delta.reasoning_content ? '' : delta.content || ''
      })
    }
  }

  const abortStream = () => {
    if (isStreamActive.value) {
      streamManager.abortCurrentRequest()
    }
  }

  const handleDeleteHistory = conversationId => {
    const key = String(conversationId)
    conversationHistoryMap.value.delete(key)

    if (String(currentConversationId.value) !== key) return

    selectedHistoryItem.value = null
    currentConversationId.value = null
    tempConversationId.value = null
    conversationHistory.value = []
    editMessage.value = ''
    showMessageEditor.value = false
    localStorage.removeItem('chatState')
    streamManager.clearStreamRequestState()
  }

  const handleSelectHistory = async item => {
    if (homeDrawerOpen.value) closeHomeDrawer()

    if (!item) {
      selectedHistoryItem.value = null
      currentConversationId.value = null
      tempConversationId.value = null
      conversationHistory.value = []
      localStorage.removeItem('chatState')
      return
    }

    if (currentConversationId.value) {
      saveConversationToMap(currentConversationId.value)
    }

    selectedHistoryItem.value = item
    currentConversationId.value = conversationKey(item.conversation_id)

    const cachedHistory = getConversationFromMap(item.conversation_id)

    if (String(item.conversation_id).startsWith('temp_')) {
      if (cachedHistory) {
        conversationHistory.value = cachedHistory

      } else {
        conversationHistory.value = []
      }
      return
    }

    if (cachedHistory) {
      conversationHistory.value = cachedHistory

    } else {
      conversationHistory.value = []
      isHistoryLoading.value = true

      try {
        const convId = parseInt(item.conversation_id, 10)
        if (isNaN(convId) || convId <= 0) {
          conversationHistory.value = []
          isHistoryLoading.value = false
          return
        }
        const response = await api.post('/conversation/history', {
          conversation_id: convId,
          last_history_id: null,
          limit: 50
        })

        if (response.ok) {
          const data = await response.json()
          if (data.items && data.items.length > 0) {
            const historyItems = data.items.map(normalizeHistoryMessage)
            conversationHistory.value = historyItems
            saveConversationToMap(item.conversation_id)
          } else {
            conversationHistory.value = []
          }
        } else {
          console.error('[ERR] Load chat history failed:', response.status)
          conversationHistory.value = []
        }
      } catch (error) {
        console.error('[ERR] Load chat history exception:', error)
        conversationHistory.value = []
      } finally {
        isHistoryLoading.value = false
      }
    }
  }

  const handleLoadMoreHistory = async ({ conversation_id, last_history_id, limit }) => {
    try {
      const convId = parseInt(conversation_id, 10)
      if (isNaN(convId) || convId <= 0) return
      const response = await api.post('/conversation/history', {
        conversation_id: convId,
        last_history_id,
        limit
      })

      if (!response.ok) {
        console.error('[ERR] API error:', response.status)
        return
      }

      const data = await response.json()

      if (data.items && data.items.length > 0) {
        centerContentRef.value.prependHistory(data.items)
      }
    } catch (error) {
      console.error('[ERR] Load more history failed:', error.message)
    }
  }

  const handlePrependHistory = newMessages => {
    const normalizedMessages = newMessages.map(normalizeHistoryMessage)
    conversationHistory.value = [...normalizedMessages, ...conversationHistory.value]
    if (currentConversationId.value) {
      saveConversationToMap(currentConversationId.value)
    }
  }

  const handleNewConversation = () => {
    if (homeDrawerOpen.value) closeHomeDrawer()

    // 会话打开态点「新建会话」：先中断仍在进行的流式请求，
    // 否则 isStreamActive 一直为 true，输入框保持禁用，看起来像点击无效。
    if (isStreamActive.value) {
      streamManager.abortCurrentRequest()
      isStreamActive.value = false
    }

    if (currentConversationId.value) {
      saveConversationToMap(currentConversationId.value)
    }

    selectedHistoryItem.value = null
    currentConversationId.value = null
    tempConversationId.value = null
    conversationHistory.value = []
    localStorage.removeItem('chatState')
    streamManager.clearStreamRequestState()
    leftlistRef.value?.clearActiveHistory?.()
    bottominputRef.value?.clearDraft?.()
  }

  const resetWorkspaceForAccountChange = () => {
    handleNewConversation()
    conversationHistoryMap.value.clear()
  }

  const handleLogin = async () => {
    resetWorkspaceForAccountChange()
    try {
      await leftlistRef.value?.fetchHistory?.(true)
    } catch (error) {
      console.error('[ERR] Refresh history after login failed:', error?.message || error)
    }

    // 未登录访问受保护页面时，守卫会把原地址写进 redirect，登录成功后回到那里
    const redirect = route.query.redirect
    if (typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//') && !redirect.includes('\\')) {
      await router.replace(redirect)
    }
  }

  const handleLogout = () => {
    // 中断仍在进行的流式生成，避免登出后旧请求继续写入会话
    if (isStreamActive.value) {
      streamManager.abortCurrentRequest()
      isStreamActive.value = false
    }
    resetWorkspaceForAccountChange()
    navigationStore.hideAllTools()
  }

  const restoreStream = async () => {
    let savedState = streamManager.getStreamRequestState()
    const lastMessage = conversationHistory.value[conversationHistory.value.length - 1]

    if ((!savedState || !savedState.isStreaming) && lastMessage?.isStreaming && lastMessage.prompt) {
      savedState = {
        isStreaming: true,
        conversationId: currentConversationId.value,
        requestData: {
          prompt: lastMessage.prompt,
          stream: true,
          search_mode: lastMessage.searchMode || 'auto',
          search_depth: lastMessage.searchDepth || 'shallow'
        },
        messageData: {
          prompt: lastMessage.prompt,
          search_mode: lastMessage.searchMode || 'auto',
          search_depth: lastMessage.searchDepth || 'shallow'
        }
      }
    }

    if (!savedState || !savedState.isStreaming) {
      return
    }

    if (savedState.requestData?.is_project_generator) {
      streamManager.clearStreamRequestState()
      return
    }

    if (savedState.conversationId) {
      currentConversationId.value = String(savedState.conversationId)
      if (String(savedState.conversationId).startsWith('temp_')) {
        tempConversationId.value = String(savedState.conversationId)
      }
    }

    const messageData = {
      prompt: savedState.messageData?.prompt || savedState.requestData?.prompt,
      model: savedState.messageData?.model || savedState.requestData?.model,
      use_reasoning: savedState.messageData?.use_reasoning || savedState.requestData?.use_reasoning || false,
      search_mode: savedState.messageData?.search_mode || savedState.requestData?.search_mode || 'auto',
      search_depth: savedState.messageData?.search_depth || savedState.requestData?.search_depth || 'shallow',
      files: savedState.messageData?.files || savedState.requestData?.files
    }

    if (!messageData.prompt) {
      streamManager.clearStreamRequestState()
      return
    }

    await handleSendMessage(messageData, { resume: true })
  }

  const _cleanupFns = []

  onMounted(async () => {
    // 加载 API Key 数据
    apiKeyStore.loadFromStorage()
    
    navigationStore.restoreNavigationFromStorage()
    await restoreStateFromStorage()
    await restoreStream()

    const onBeforeUnload = () => {
      pageUnloading = true
      saveStateToStorage()
      navigationStore.saveNavigationToStorage()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    _cleanupFns.push(() => window.removeEventListener('beforeunload', onBeforeUnload))
    window.addEventListener('keydown', handleHomeDrawerKeydown)
    _cleanupFns.push(() => window.removeEventListener('keydown', handleHomeDrawerKeydown))
    if (mobileMediaQuery) {
      if (mobileMediaQuery.addEventListener) {
        mobileMediaQuery.addEventListener('change', handleMobileChange)
        _cleanupFns.push(() => mobileMediaQuery.removeEventListener('change', handleMobileChange))
      } else {
        // 旧版 Safari 只有 addListener/removeListener。
        mobileMediaQuery.addListener(handleMobileChange)
        _cleanupFns.push(() => mobileMediaQuery.removeListener(handleMobileChange))
      }
    }

    _cleanupFns.push(register('mod+k', () => {
      nextTick(() => {
        const textarea = bottominputRef.value?.textareaRef
        if (textarea) {
          textarea.focus()
        }
      })
    }))

    _cleanupFns.push(register('mod+enter', () => {
      if (bottominputRef.value) {
        bottominputRef.value.sendMessage?.()
      }
    }))

    _cleanupFns.push(register('escape', () => {
      if (showShortcutsHelp.value) {
        showShortcutsHelp.value = false
        return
      }
      // 生成中按 Esc 应停止流式输出，与输入框页脚「Esc 停止」的提示一致。
      if (isStreamActive.value) {
        abortStream()
        return
      }
      leftlistRef.value?.closeToolkitMenu?.()
      navigationStore.hideAllTools()
      showMessageEditor.value = false
    }))

    _cleanupFns.push(register('mod+n', () => {
      handleNewConversation()
    }))

    _cleanupFns.push(register('mod+shift+l', () => {
      if (leftlistRef.value) {
        leftlistRef.value.toggleCollapse?.()
      }
    }))

    _cleanupFns.push(register('/', () => {
      if (leftlistRef.value) {
        leftlistRef.value.showSearchBox = true
        nextTick(() => {
          const searchInput = document.querySelector('.search-input')
          if (searchInput) searchInput.focus()
        })
      }
    }, { allowInInput: false }))

    _cleanupFns.push(register('mod+b', () => {
      navigationStore.toggleCollapse()
    }))

    _cleanupFns.push(register('shift+/', () => {
      showShortcutsHelp.value = true
    }))
  })

  onUnmounted(() => {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns.length = 0
    if (pageUnloading) {
      saveStateToStorage()
    } else {
      streamManager.cleanup()
    }
    streamUpdateBatcher.dispose()
  })
</script>

<style lang="css" scoped>
  .main-layout {
    display: flex;
    flex-direction: row;
    width: 100%;
    flex: 1;
    min-height: 0;
    background: var(--bg-primary);
    overflow: hidden;
  }

  .mobile-home-toolbar,
  .mobile-home-scrim {
    display: none;
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    background: var(--bg-primary);
  }

  .bottom-wrapper {
    position: relative;
    z-index: 100;
    flex-shrink: 0;
    flex-basis: auto;
    padding: 12px 24px max(16px, env(safe-area-inset-bottom));
    background: var(--bg-primary);
  }

  @media (max-width: 768px) {
    .main-layout {
      position: relative;
      flex-direction: column;
    }

    .mobile-home-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 48px;
      padding: 4px 12px;
      border-bottom: 1px solid var(--control-border);
      background: var(--surface-app);
      z-index: 90;
    }

    .mobile-home-menu {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-width: var(--control-min-size);
      min-height: var(--control-min-size);
      border: 1px solid var(--control-border);
      border-radius: var(--radius-md);
      background: var(--surface-subtle);
      color: var(--content-primary);
      cursor: pointer;
    }

    .mobile-home-title {
      color: var(--content-primary);
      font-size: var(--text-lg);
      font-weight: 600;
    }

    .main-layout > :deep(#leftlist) {
      position: fixed;
      inset: 0 auto 0 0;
      z-index: 120;
      width: min(86vw, 340px);
      transform: translateX(-105%);
      transition: transform var(--motion-base);
      box-shadow: var(--shadow-xl);
    }

    .main-layout > :deep(#leftlist.mobile-home-drawer-open) {
      transform: translateX(0);
    }

    .mobile-home-scrim {
      display: block;
      position: fixed;
      inset: 0;
      z-index: 110;
      border: 0;
      background: rgb(15 23 42 / 44%);
    }

    .main-content {
      flex: 1;
      min-height: 0;
    }

    .bottom-wrapper {
      padding: 8px 10px max(10px, env(safe-area-inset-bottom));
    }
  }
</style>
