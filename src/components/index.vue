  <template>
    <div class="main-layout">
      <ErrorBoundary component-name="左侧边栏">
        <Leftlist
          ref="leftlistRef"
          :class="{ 'sidebar-visible': true }"
          role="navigation"
          aria-label="主导航"
          @select-history="handleSelectHistory"
          @new-conversation="handleNewConversation"
          @use-tool="handleUseTool"
        />
      </ErrorBoundary>

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
          />
        </ErrorBoundary>
      </main>

      <!-- 底部输入区 -->
      <div class="bottom-wrapper" role="form" aria-label="消息输入区">
        <Bottominput
          ref="bottominputRef"
          :is-streaming="isStreamActive"
          :edit-message="editMessage"
          @send="handleSendMessage"
          @stop="abortStream"
          @require-login="handleRequireLogin"
          @save-edit="handleSaveEdit"
          @cancel-edit="handleCancelEdit"
        />
      </div>

      <!-- Toast 通知 -->
      <ToastContainer />

      <!-- 消息编辑器 -->
      <MessageEditor
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
        @update:visible="val => (navigationStore.showVirtualGirl = val)"
      />

      <TaskQueue
        v-if="showTaskQueue"
        :visible="showTaskQueue"
        @close="() => navigationStore.hideTool('taskQueue')"
      />

      <ImageGenerator
        v-if="showImageGenerator"
        :visible="showImageGenerator"
        @close="() => navigationStore.hideTool('imageGenerator')"
      />

      <Aicloud
        v-if="showAicloud"
        :visible="showAicloud"
        @close="() => navigationStore.hideTool('aicloud')"
      />

      <ServiceManager
        v-if="showServiceManager"
        :visible="showServiceManager"
        @close="() => navigationStore.hideTool('serviceManager')"
      />

      <ProjectGenerator
        v-if="showProjectGenerator"
        :visible="showProjectGenerator"
        @close="() => navigationStore.hideTool('projectGenerator')"
      />

      <EphemeralWorkflow
        v-if="showEphemeralWorkflow"
        :visible="showEphemeralWorkflow"
        @close="() => navigationStore.hideTool('ephemeralWorkflow')"
      />

      <!-- 快捷键帮助弹窗 -->
      <KeyboardShortcutsHelp
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
  import MessageEditor from './MessageEditor.vue'
  import KeyboardShortcutsHelp from './KeyboardShortcutsHelp.vue'
  import { useRouter } from 'vue-router'
  import { api } from '@/utils/api/index'
  import { streamManager } from '@/utils/streamManager'
  import { useNavigationStore } from '@/stores/navigation'
  import { useUserStore } from '@/stores/user'
  import { useApiKeyStore } from '@/stores/apikey'
  import { useToast } from '@/composables/useToast'
  import { useOfflineQueue } from '@/composables/useOfflineQueue'
  import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'

  // 工具组件延迟加载 - 减少初始包大小
  const NginxConfig = defineAsyncComponent(() => import('./NginxConfig.vue'))
  const Dockerfile = defineAsyncComponent(() => import('./Dockerfile.vue'))
  const VirtualGirl = defineAsyncComponent(() => import('./VirtualGirl.vue'))
  const ServiceManager = defineAsyncComponent(() => import('./ServiceManager.vue'))
  const ProjectGenerator = defineAsyncComponent(() => import('./ProjectGenerator.vue'))
  const EphemeralWorkflow = defineAsyncComponent(() => import('./EphemeralWorkflow.vue'))
  const TaskQueue = defineAsyncComponent(() => import('./TaskQueue.vue'))
  const ImageGenerator = defineAsyncComponent(() => import('./ImageGenerator.vue'))
  const Aicloud = defineAsyncComponent(() => import('./Aicloud.vue'))

  const router = useRouter()
  const apiUrl = import.meta.env.VITE_API_BASE || '/api/v1'

  const navigationStore = useNavigationStore()
  const userStore = useUserStore()
  const apiKeyStore = useApiKeyStore()
  const { error: showError, success: showSuccess } = useToast()
  const offlineQueue = useOfflineQueue()
  const { register } = useKeyboardShortcuts()

  const bottominputRef = ref(null)
  const showShortcutsHelp = ref(false)

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

  const showNginxConfig = computed(() => navigationStore.showNginxConfig)
  const showDockerConfig = computed(() => navigationStore.showDockerConfig)
  const showVirtualGirl = computed(() => navigationStore.showVirtualGirl)
  const showServiceManager = computed(() => navigationStore.showServiceManager)
  const showProjectGenerator = computed(() => navigationStore.showProjectGenerator)
  const showEphemeralWorkflow = computed(() => navigationStore.showEphemeralWorkflow)
  const showTaskQueue = computed(() => navigationStore.showTaskQueue)
  const showImageGenerator = computed(() => navigationStore.showImageGenerator)
  const showAicloud = computed(() => navigationStore.showAicloud)

  const MAX_CONVERSATION_CACHE = 50

  const saveConversationToMap = (conversationId, customHistory = null) => {
    if (conversationId) {
      const key = String(conversationId)
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

  const getConversationFromMap = conversationId => {
    if (conversationId) {
      const key = String(conversationId)
      const cached = conversationHistoryMap.value.get(key)
      if (cached) {
        return JSON.parse(JSON.stringify(cached))
      }
    }
    return null
  }

  const SESSION_RESTORE_MAX_AGE = 24 * 60 * 60 * 1000

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

      if (String(conversationId).startsWith('temp_')) {
        currentConversationId.value = conversationId
        conversationHistory.value = state.conversationHistory || []
        selectedHistoryItem.value = state.selectedHistoryItem
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
            const historyItems = data.items.map(message => ({
              id: message.id,
              conversation_id: parseInt(message.conversation_id, 10),
              prompt: message.prompt,
              response: message.response || '',
              reasoning: message.thinking || '',
              thinkingOpen: true,
              createdAt: message.created_at,
              title: message.title
            }))
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
    navigationStore.showTool(toolName)
  }

  const handleQuickPrompt = prompt => {
    handleSendMessage({
      prompt,
      model: 'Qwen/Qwen3-8B',
      use_reasoning: false
    })
  }

  const handleSendMessage = async messageData => {
    if (!userStore.isLoggedIn) {
      handleRequireLogin()
      return
    }
    if (isLoading.value) return

    // 检查 API Key 配置
    if (!apiKeyStore.hasSiliconflowKey) {
      showError('请先配置 API Key 后再使用')
      // 跳转到设置页面
      router.push('/settings')
      return
    }

    isLoading.value = true
    isStreamActive.value = true

    const requestId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    streamManager.currentRequestId = requestId

    const abortController = streamManager.createAbortController(requestId)

    if (!currentConversationId.value && !messageData.is_project_generator) {
      const tempId = `temp_${Date.now()}`
      tempConversationId.value = tempId
      currentConversationId.value = tempId

      conversationHistory.value = []
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

    const userMessage = {
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
      files: messageData.files?.filter(f => f.category === 'image') || []
    }

    conversationHistory.value.push(userMessage)
    saveConversationToMap(currentConversationId.value)

    const lastMessageIndex = conversationHistory.value.length - 1
    const currentMessageData = messageData
    const streamConversationId = currentConversationId.value

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



        streamManager.saveStreamRequestState(
          {
            prompt: messageData.prompt,
            model: messageData.model || 'Qwen/Qwen3-8B',
            stream: true,
            use_reasoning: messageData.use_reasoning || false,
            conversation_id: sendConversationId
          },
          messageData,
          sendConversationId
        )

        const requestData = {
          prompt: messageData.prompt,
          model: messageData.model || 'Qwen/Qwen3-8B',
          stream: true,
          use_reasoning: messageData.use_reasoning || false,
          conversation_id: sendConversationId,
          api_key_token: apiKeyStore.siliconflowKey?.token
        }

        // 集成 Vision: 将附件文件传递给后端自动处理
        if (messageData.files && messageData.files.length > 0) {
          requestData.files = messageData.files
            .filter(f => f.serverPath)
            .map(f => ({
              server_path: f.serverPath,
              name: f.name,
              type: f.type,
              category: f.category || 'document'
            }))
        }

        response = await api.stream('/chat', requestData, abortController.signal)
      }

      if (!response.ok) {
        let errorMessage = `HTTP error! status: ${response.status}`
        try {
          const errorData = await response.json()
          if (errorData.detail) {
            errorMessage += ` - ${errorData.detail}`
          }
        } catch (e) {
          console.error('无法解析错误响应:', response.statusText)
        }
        throw new Error(errorMessage)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      const readWithAbort = (reader, signal) => {
        if (signal.aborted) {
          return Promise.reject(new DOMException('Aborted', 'AbortError'))
        }

        return new Promise((resolve, reject) => {
          const onAbort = () => {
            reader
              .cancel()
              .then(() => reject(new DOMException('Aborted', 'AbortError')))
              .catch(reject)
          }

          signal.addEventListener('abort', onAbort)

          reader.read().then(
            result => {
              signal.removeEventListener('abort', onAbort)
              resolve(result)
            },
            error => {
              signal.removeEventListener('abort', onAbort)
              reject(error)
            }
          )
        })
      }

      while (true) {
        if (abortController.signal.aborted) {
          break
        }

        let readResult
        try {
          readResult = await readWithAbort(reader, abortController.signal)
        } catch (e) {
          break
        }

        const { done, value } = readResult
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter(line => line.trim())

        for (const line of lines) {
          try {
            if (line.startsWith('data: ')) {
              const data = JSON.parse(line.substring(6))

              if (currentMessageData.is_project_generator) {
                handleProjectGeneratorStream(data, lastMessageIndex)
              } else {
                handleChatStream(data, streamConversationId, lastMessageIndex, currentMessageData)
              }
            } else {
              const data = JSON.parse(line)

              if (currentMessageData.is_project_generator) {
                handleProjectGeneratorStream(data, lastMessageIndex)
              } else {
                handleChatStream(data, streamConversationId, lastMessageIndex, currentMessageData)
              }
            }
          } catch (e) {
            const conversationIdMatch = line.match(/conversation_id\s*[:\s]+\s*(\d+)/)
            if (conversationIdMatch) {
              const newConversationId = String(conversationIdMatch[1])
              const oldConversationId = currentConversationId.value
              currentConversationId.value = newConversationId

              if (oldConversationId && String(oldConversationId).startsWith('temp_')) {
                const cachedHistory = conversationHistoryMap.value.get(oldConversationId)
                if (cachedHistory) {
                  conversationHistoryMap.value.set(
                    newConversationId,
                    JSON.parse(JSON.stringify(cachedHistory))
                  )
                  conversationHistoryMap.value.delete(oldConversationId)

                }
              }

              if (tempConversationId.value) {
                tempConversationId.value = null
              }

              setTimeout(() => {
                if (leftlistRef.value && leftlistRef.value.addNewHistoryItem) {
                  const newItem = {
                    id: Number(conversationIdMatch[1]),
                    conversation_id: newConversationId,
                    title: messageData.prompt.slice(0, 50) + '...',
                    prompt: messageData.prompt,
                    created_at: new Date().toISOString()
                  }

                  if (oldConversationId && String(oldConversationId).startsWith('temp_')) {
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
            }
          }
        }
      }

      if (currentMessageData.is_project_generator) {
        if (conversationHistory.value[lastMessageIndex]) {
          conversationHistory.value[lastMessageIndex].isStreaming = false
        }
      } else {
        const streamHistory = conversationHistoryMap.value.get(streamConversationId)
        if (streamHistory && streamHistory.length > 0) {
          const streamLastIndex = streamHistory.length - 1
          streamHistory[streamLastIndex].isStreaming = false
          saveConversationToMap(streamConversationId, streamHistory)

          if (String(currentConversationId.value) === String(streamConversationId)) {
            if (conversationHistory.value[streamLastIndex]) {
              conversationHistory.value[streamLastIndex].isStreaming = false
            }
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error)

      const streamHistory = conversationHistoryMap.value.get(streamConversationId)
      if (streamHistory && streamHistory.length > 0) {
        const streamLastIndex = streamHistory.length - 1
        const lastMessage = streamHistory[streamLastIndex]

        const isUserAbort = error.name === 'AbortError' && abortController.signal.aborted

        if (isUserAbort) {
          lastMessage.isStreaming = false
          const existingResponse = lastMessage.response || ''
          const existingReasoning = lastMessage.reasoning || ''

          if (lastMessage.hasThinking && !lastMessage.thinkingClosed) {
            lastMessage.response += `</div></details>\n\n`
            lastMessage.thinkingClosed = true
          }

          if (!existingResponse.includes('[PAUSE] Output stopped')) {
            lastMessage.response += `\n\n[PAUSE] Project generation stopped (user interrupted)`
          }
          if (existingReasoning && !existingReasoning.includes('[PAUSE] Reasoning stopped')) {
            lastMessage.reasoning =
              existingReasoning + '\n\n[PAUSE] Reasoning stopped (user interrupted)'
          }
        } else {
          const hasPartialContent =
            (lastMessage.response && lastMessage.response.length > 0) ||
            (lastMessage.reasoning && lastMessage.reasoning.length > 0)

          if (lastMessage.hasThinking && !lastMessage.thinkingClosed) {
            lastMessage.response += `</div></details>\n\n`
            lastMessage.thinkingClosed = true
          }

          if (hasPartialContent) {
            const existingResponse = lastMessage.response || ''
            const existingReasoning = lastMessage.reasoning || ''

            if (!existingResponse.includes('[ERR] Response error')) {
              lastMessage.response = existingResponse + `\n\n[ERR] Response error: ${error.message}`
            }
            if (existingReasoning && !existingReasoning.includes('[ERR] Reasoning error')) {
              lastMessage.reasoning =
                existingReasoning + `\n\n[ERR] Reasoning error: ${error.message}`
            }
          } else {
            lastMessage.response = `[ERR] Request failed: ${error.message}`
          }
        }

        lastMessage.isStreaming = false
        saveConversationToMap(streamConversationId)

        if (String(currentConversationId.value) === String(streamConversationId)) {
          if (conversationHistory.value[streamLastIndex]) {
            Object.assign(conversationHistory.value[streamLastIndex], lastMessage)
          }
        }
      }
    } finally {
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
        message.response += `[SUCCESS] ${data.message}\n\n`
        break

      case 'file_create_start':
        message.isProjectGenerator = true
        message.response += `[CREATE] ${data.file_path}\n\n`
        break

      case 'file_created':
        message.isProjectGenerator = true
        message.filesCreated = (message.filesCreated || 0) + 1
        message.response += `[SUCCESS] ${data.file_path} (${data.file_size || ''})\n\n`
        break

      case 'file_error':
        message.isProjectGenerator = true
        message.response += `[ERROR] ${data.file_path}\n\n`
        break

      case 'file_skipped':
        message.isProjectGenerator = true
        message.response += `[SKIP] ${data.file_path}\n\n`
        break

      case 'validation':
        message.isProjectGenerator = true
        if (data.status === 'passed') {
          message.response += `[SUCCESS] ${data.message}\n\n`
        } else if (data.status === 'failed') {
          message.response += `[WARNING] ${data.message}\n\n`
          if (data.missing_deps) {
            message.response += `[WARNING] 缺失依赖: ${data.missing_deps.join(', ')}\n\n`
          }
        } else {
          message.response += `[INFO] ${data.message}\n\n`
        }
        break

      case 'validation_progress':
        message.isProjectGenerator = true
        message.response += `[INFO] ${data.message}\n\n`
        break

      case 'validation_complete':
        message.isProjectGenerator = true
        message.response += `[SUCCESS] 验证完成\n\n`
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
        message.response += `\n---\n\n**[COMPLETE] 项目生成完成**\n\n`
        message.response += `- 创建文件: ${totalFiles} 个\n`
        message.response += `- 输出目录: ${data.result?.output_dir ?? data.output_dir ?? '未知'}\n\n`
        message.isStreaming = false
        break
      }

      case 'error':
        message.isProjectGenerator = true
        message.response += `[ERROR] 生成失败: ${data.message}\n\n`
        message.isStreaming = false
        break

      case 'dependency_check':
        message.isProjectGenerator = true
        message.response += `[INFO] 依赖检查: ${data.message}\n\n`
        break

      case 'structure_check':
        message.isProjectGenerator = true
        message.response += `[INFO] 结构检查: ${data.message}\n\n`
        break

      case 'tool_start':
        message.isProjectGenerator = true
        message.response += `[INFO] 执行工具: ${data.tool_name || data.message}\n\n`
        break

      case 'tool_result':
        message.isProjectGenerator = true
        message.response += `[SUCCESS] ${data.message}\n\n`
        break
    }
  }

  let _streamChunkCount = 0

  const handleChatStream = (data, streamConversationId, lastIndex, messageData) => {
    const streamHistory = conversationHistoryMap.value.get(streamConversationId)
    if (!streamHistory) {
      console.warn('[WARN] Stream chat history not found:', streamConversationId)
      return
    }

    const history = streamHistory

    // 后端错误
    if (data.error) {
      if (history[lastIndex]) {
        history[lastIndex].response = (history[lastIndex].response || '') + `\n\n[ERROR] ${data.error}`
        Object.assign(history[lastIndex], { response: history[lastIndex].response })
        if (String(currentConversationId.value) === String(streamConversationId) && conversationHistory.value[lastIndex]) {
          Object.assign(conversationHistory.value[lastIndex], { response: history[lastIndex].response })
        }
      }
      return
    }

    if (data.conversation_id !== undefined) {
      const receivedConversationIdRef = data.conversation_id
      const oldConversationId = currentConversationId.value
      currentConversationId.value = String(receivedConversationIdRef)

      if (oldConversationId && oldConversationId.startsWith('temp_')) {
        const cachedHistory = conversationHistoryMap.value.get(oldConversationId)
        if (cachedHistory) {
          conversationHistoryMap.value.set(
            String(receivedConversationIdRef),
            JSON.parse(JSON.stringify(cachedHistory))
          )
          conversationHistoryMap.value.delete(oldConversationId)

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

      const currentResponse = history[lastIndex].response || ''
      const currentReasoning = history[lastIndex].reasoning || ''

      if (delta.reasoning_content) {
        history[lastIndex].reasoning = currentReasoning + delta.reasoning_content
      } else if (delta.content) {
        history[lastIndex].response = currentResponse + delta.content
      }

      Object.assign(history[lastIndex], {
        reasoning: history[lastIndex].reasoning,
        response: history[lastIndex].response
      })

      // 节流：每 20 个 chunk 才 deep clone 一次，避免长对话卡顿
      _streamChunkCount++
      if (_streamChunkCount % 20 === 0) {
        saveConversationToMap(streamConversationId, history)
        _streamChunkCount = 0
      }

      if (String(currentConversationId.value) === String(streamConversationId)) {
        if (conversationHistory.value[lastIndex]) {
          Object.assign(conversationHistory.value[lastIndex], {
            reasoning: history[lastIndex].reasoning,
            response: history[lastIndex].response
          })
        }
      }
    }
  }

  const abortStream = () => {
    if (isStreamActive.value) {
      streamManager.abortCurrentRequest()
    }
  }

  const handleSelectHistory = async item => {
    if (currentConversationId.value) {
      saveConversationToMap(currentConversationId.value)
    }

    selectedHistoryItem.value = item
    currentConversationId.value = item.conversation_id

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
            const historyItems = data.items.map(message => ({
              id: message.id,
              conversation_id: parseInt(message.conversation_id, 10),
              prompt: message.prompt,
              response: message.response || '',
              reasoning: message.thinking || '',
              thinkingOpen: true,
              createdAt: message.created_at,
              title: message.title
            }))
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
    conversationHistory.value = [...newMessages, ...conversationHistory.value]
  }

  const handleNewConversation = () => {
    if (currentConversationId.value) {
      saveConversationToMap(currentConversationId.value)
    }

    selectedHistoryItem.value = null
    currentConversationId.value = null
    tempConversationId.value = null
    conversationHistory.value = []
    localStorage.removeItem('chatState')
    streamManager.clearStreamRequestState()
  }

  const restoreStream = async () => {
    const savedState = streamManager.getStreamRequestState()
    if (!savedState || !savedState.isStreaming) {
      return
    }

    if (savedState.conversationId) {
      currentConversationId.value = String(savedState.conversationId)
    }

    const lastMessageIndex = conversationHistory.value.length - 1
    if (lastMessageIndex >= 0 && !conversationHistory.value[lastMessageIndex].isStreaming) {
      const lastMessage = conversationHistory.value[lastMessageIndex]

      const hasPartialContent =
        (lastMessage.response && lastMessage.response.includes('[WARN] Response interrupted')) ||
        (lastMessage.reasoning && lastMessage.reasoning.includes('[WARN] Reasoning interrupted'))

      if (hasPartialContent) {
        lastMessage.response = lastMessage.response.replace(
          '\n\n[WARN] Response interrupted (page refreshed)',
          ''
        )
        lastMessage.reasoning =
          lastMessage.reasoning?.replace('\n\n[WARN] Reasoning interrupted (page refreshed)', '') ||
          ''
        lastMessage.isStreaming = false

        await nextTick()
        const messagesContainer = centerContentRef.value?.$el?.querySelector('.messages-container')
        if (messagesContainer) {
          const restorePrompt = document.createElement('div')
          restorePrompt.className = 'stream-restore-prompt'
          restorePrompt.innerHTML = `
          <div class="restore-message">
            <span>[WARN] Page refreshed, previous output has been preserved</span>
          </div>
        `
          messagesContainer.appendChild(restorePrompt)
        }
      }
    }

    streamManager.clearStreamRequestState()
  }

  const _cleanupFns = []

  onMounted(async () => {
    // 加载 API Key 数据
    apiKeyStore.loadFromStorage()
    
    navigationStore.restoreNavigationFromStorage()
    await restoreStateFromStorage()
    await restoreStream()

    const onBeforeUnload = () => {
      streamManager.cleanup()
      navigationStore.saveNavigationToStorage()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    _cleanupFns.push(() => window.removeEventListener('beforeunload', onBeforeUnload))

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

    _cleanupFns.push(register('?', () => {
      showShortcutsHelp.value = true
    }))
  })

  onUnmounted(() => {
    _cleanupFns.forEach(fn => fn())
    _cleanupFns.length = 0
    streamManager.cleanup()
  })
</script>

<style lang="css" scoped>
  .main-layout {
    display: flex;
    flex-direction: row;
    width: 100%;
    height: 100vh;
    background: var(--bg-primary);
    overflow: hidden;
  }

  .main-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    background: var(--bg-primary);
  }

  .bottom-wrapper {
    position: relative;
    z-index: 100;
    flex-shrink: 0;
    flex-basis: auto;
  }
</style>
