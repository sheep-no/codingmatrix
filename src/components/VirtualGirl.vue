<template>
  <div v-if="showWindow && !usePiPMode" class="virtual-girl-window" :style="windowStyle">
    <!-- 自动隐藏时只显示侧边栏 -->
    <div v-if="isAutoHide" class="autohide-sidebar">
      <div class="autohide-content" @click.stop="expandWindow">
        <img :src="characterAvatarUrl" class="sidebar-avatar" alt="AI" />
        <span class="sidebar-text">AI</span>
      </div>
    </div>

    <!-- 正常窗口内容（非隐藏状态） -->
    <template v-else>
      <!-- 右下角调整手柄 -->
      <div class="resize-handle" @mousedown="startResize"></div>

      <!-- 跨网页模式切换按钮 -->
      <div
        class="mode-toggle-btn"
        title="切换到跨网页模式"
        @click="togglePiPMode"
      >
        <svg
          class="mode-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
          <line x1="8" y1="21" x2="16" y2="21"></line>
          <line x1="12" y1="17" x2="12" y2="21"></line>
        </svg>
      </div>

      <!-- 窗口头部 -->
      <div class="window-header" @mousedown="startDrag">
        <div class="window-title">
          <div class="ai-avatar">
            <img :src="characterAvatarUrl" alt="AI" />
          </div>
          <div class="title-content">
            <span class="title-text">{{ characterDisplayName }}</span>
            <span class="title-status" :class="{ online: isConnected, offline: !isConnected }">
              {{ isConnected ? '在线' : '离线' }}
            </span>
          </div>
        </div>
        <div class="window-controls">
          <button class="control-btn" title="搜索历史" @click.stop="showSearch = !showSearch">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </button>
          <button class="control-btn" title="导出对话" @click.stop="exportChat">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
          <button class="control-btn" title="最小化" @click.stop="toggleMinimize">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <button class="control-btn" title="清除历史" @click.stop="confirmClearHistory">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
          <button class="control-btn close-btn" title="关闭" @click.stop="closeWindow">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      <!-- 窗口内容 -->
      <div class="window-content-wrapper">
        <div class="window-content" :class="{ 'minimized-content': isMinimized }">
          <!-- 聊天区域 -->
          <div class="chat-section">
            <!-- 搜索栏（可折叠） -->
            <div v-if="showSearch" class="search-bar">
              <input
                v-model="searchQuery"
                type="text"
                class="search-input"
                placeholder="搜索对话历史..."
                @keyup.enter="handleSearch"
              />
              <button class="search-btn" :disabled="!searchQuery.trim()" @click="handleSearch">搜索</button>
              <button class="search-close" @click="showSearch = false; searchQuery = ''; searchResults = []">取消</button>
            </div>

            <!-- 搜索结果 -->
            <div v-if="searchResults.length > 0" class="search-results">
              <div class="search-results-header">
                <span>找到 {{ searchResults.length }} 条结果</span>
                <button @click="searchResults = []">清除</button>
              </div>
              <div v-for="(r, i) in searchResults" :key="i" class="search-result-item" @click="scrollToMessage(r)">
                <span class="search-result-role">{{ r.role === 'user' ? '你' : characterDisplayName }}</span>
                <span class="search-result-content">{{ r.content }}</span>
              </div>
            </div>

            <!-- 角色选择栏 -->
            <div class="character-selector">
              <div class="character-label">选择角色:</div>
              <select
                v-model="selectedCharacter"
                class="character-select"
                @change="onCharacterChange"
              >
                <optgroup label="内置角色">
                  <option value="gentle">温柔学姐</option>
                  <option value="lively">元气少女</option>
                  <option value="tsundere">傲娇妹妹</option>
                  <option value="intellectual">知性御姐</option>
                  <option value="companion">贴心伴侣</option>
                </optgroup>
                <optgroup v-if="customCharacters.length > 0" label="自定义角色">
                  <option v-for="c in customCharacters" :key="c.id" :value="'custom_' + c.id">
                    {{ c.name }}
                  </option>
                </optgroup>
              </select>
              <button class="add-character-btn" title="创建角色" @click="showCharacterForm = true">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
              <span class="character-indicator" :class="selectedCharacter">
                <svg
                  class="character-icon-svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path :d="getCharacterEmoji(selectedCharacter)"></path>
                </svg>
              </span>
            </div>

            <div ref="chatMessages" class="chat-messages" @scroll="handleScroll">
              <div
                v-for="(message, index) in chatHistory"
                :key="`msg-${index}`"
                :data-message-id="message.id || ''"
                :class="['message', message.role]"
              >
                <div class="message-avatar">
                  <img v-if="message.role === 'assistant'" :src="characterAvatarUrl" alt="AI" />
                  <svg
                    v-else
                    class="user-avatar-icon-svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                  </svg>
                </div>
                <div class="message-body">
                  <div class="message-header">
                    <span class="message-sender">{{
                      message.role === 'assistant' ? '虚拟姬' : '你'
                    }}</span>
                    <span class="message-time">{{ getMessageTime(index) }}</span>
                  </div>
                  <div class="message-content">{{ message.content }}</div>
                </div>
              </div>

              <!-- 加载中 -->
              <div v-if="isLoading" class="message assistant">
                <div class="message-avatar">
                  <img :src="characterAvatarUrl" alt="AI" />
                </div>
                <div class="message-body">
                  <div class="message-header">
                    <span class="message-sender">虚拟姬</span>
                  </div>
                  <div class="message-content typing">
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                    <span class="typing-dot"></span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 输入区域 -->
            <div class="input-section">
              <div class="input-wrapper">
                <input
                  v-model="inputMessage"
                  type="text"
                  class="chat-input"
                  placeholder="和虚拟姬聊天..."
                  :disabled="isLoading"
                  @keyup.enter="sendMessage"
                />
                <button
                  class="send-button"
                  :disabled="isLoading || !inputMessage.trim()"
                  @click="sendMessage"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <line x1="22" y1="2" x2="11" y2="13"></line>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 加载更多历史记录的提示 -->
      <div v-if="isLoadingMore" class="loading-more-overlay">
        <div class="loading-spinner">
          <div class="spinner-ring"></div>
          <div class="spinner-ring"></div>
          <div class="spinner-ring"></div>
        </div>
        <span class="loading-text">加载更多...</span>
      </div>

      <!-- 自定义角色创建表单 -->
      <div v-if="showCharacterForm" class="character-form-overlay" @click.self="showCharacterForm = false">
        <div class="character-form">
          <h3>创建自定义角色</h3>
          <div class="form-field">
            <label>角色名称 <span class="required">*</span></label>
            <input v-model="newCharacter.name" type="text" maxlength="50" placeholder="给角色起个名字" />
          </div>
          <div class="form-field">
            <label>描述</label>
            <input v-model="newCharacter.description" type="text" maxlength="200" placeholder="一句话描述角色" />
          </div>
          <div class="form-field">
            <label>性格</label>
            <input v-model="newCharacter.personality" type="text" maxlength="200" placeholder="如：温柔、活泼、傲娇" />
          </div>
          <div class="form-field">
            <label>说话风格</label>
            <input v-model="newCharacter.speaking_style" type="text" maxlength="200" placeholder="如：语气温柔，常用语气词" />
          </div>
          <div class="form-field">
            <label>开场白</label>
            <textarea v-model="newCharacter.greeting" rows="2" maxlength="200" placeholder="角色的第一句话"></textarea>
          </div>
          <div class="form-field">
            <label>头像颜色</label>
            <input v-model="newCharacter.avatar_color" type="color" />
          </div>
          <div class="form-actions">
            <button class="form-cancel" @click="showCharacterForm = false">取消</button>
            <button class="form-submit" :disabled="!newCharacter.name.trim()" @click="createCharacter">创建</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
  import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
  import { api } from '@/utils/api/index'
  import { ElMessage, ElMessageBox } from 'element-plus'
  import { useUserStore } from '@/stores/user'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close', 'update:visible'])

  // 模式选择
  const usePiPMode = ref(false)
  const userStore = useUserStore()
  const storageKey = computed(() => `virtualGirlChatHistory:${userStore.email || userStore.username || 'anonymous'}`)

  // 本地窗口显示状态
  const showWindow = ref(props.visible)

  // 监听 props.visible 变化
  watch(
    () => props.visible,
    async newVal => {
      showWindow.value = newVal

      if (newVal && chatHistory.value.length > 0) {
        await nextTick()
        setTimeout(() => {
          restoreScrollPosition()
        }, 100)
      }
    }
  )

  // 窗口状态
  const isMinimized = ref(false)
  const isDragging = ref(false)
  const isResizing = ref(false)
  const isAutoHide = ref(false)
  let pipWindowRef = null
  const windowPosition = ref({ x: 100, y: 100 })
  const windowSize = ref({ width: 400, height: 500 })
  const dragOffset = ref({ x: 0, y: 0 })
  const resizeOffset = ref({ x: 0, y: 0 })
  const isConnected = ref(true)

  // 保存窗口模式的滚动位置
  const windowScrollPosition = ref(0)

  // 分页加载状态
  const isLoadingMore = ref(false)
  const hasMoreHistory = ref(true)
  const currentOffset = ref(0)
  const HISTORY_PAGE_SIZE = 20

  // 聊天状态
  const chatHistory = ref([])
  const inputMessage = ref('')
  const isLoading = ref(false)
  const chatMessages = ref(null)
  const isHistoryLoaded = ref(false)
  const messageTimestamps = ref([])
  let historyRequestVersion = 0

  // 角色选择
  const selectedCharacter = ref('gentle')
  const characterDescriptions = {
    gentle: '温柔体贴，善解人意',
    lively: '活泼开朗，充满活力',
    tsundere: '口是心非，外冷内热',
    intellectual: '成熟稳重，博学多才',
    companion: '温柔陪伴，知心倾听'
  }

  // 角色头像 URL（动态根据角色切换）
  const characterAvatarUrl = computed(() => {
    const id = selectedCharacter.value
    if (id.startsWith('custom_')) {
      const customId = id.replace('custom_', '')
      const custom = customCharacters.value.find(c => c.id === customId)
      if (custom) {
        return generateCustomAvatarSvg(custom.name, custom.avatar_color)
      }
    }
    return `/api/v1/GirlAi/characters/${id}/avatar`
  })

  // 角色显示名称
  const characterDisplayName = computed(() => {
    const id = selectedCharacter.value
    if (id.startsWith('custom_')) {
      const customId = id.replace('custom_', '')
      const custom = customCharacters.value.find(c => c.id === customId)
      return custom ? custom.name : '自定义角色'
    }
    return getCharacterName(id)
  })

  // 自定义角色列表
  const customCharacters = ref([])

  // 搜索相关
  const showSearch = ref(false)
  const searchQuery = ref('')
  const searchResults = ref([])

  // 自定义角色表单
  const showCharacterForm = ref(false)
  const newCharacter = ref({
    name: '',
    description: '',
    personality: '',
    speaking_style: '',
    greeting: '',
    avatar_color: '#667eea'
  })

  // 生成自定义角色 SVG 头像
  function generateCustomAvatarSvg(name, color) {
    const initial = name.charAt(0)
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="48" fill="${color}"/><text x="50" y="62" text-anchor="middle" font-size="40" font-weight="bold" fill="white">${initial}</text></svg>`
    return 'data:image/svg+xml,' + encodeURIComponent(svg)
  }

  // 加载自定义角色
  async function loadCustomCharacters() {
    try {
      const data = await api.getCustomCharacters()
      customCharacters.value = data.characters || []
    } catch (e) {
      console.debug('加载自定义角色失败:', e)
    }
  }

  // 创建自定义角色
  async function createCharacter() {
    if (!newCharacter.value.name.trim()) return
    try {
      const data = await api.createCustomCharacter({
        name: newCharacter.value.name.trim(),
        description: newCharacter.value.description.trim(),
        personality: newCharacter.value.personality.trim(),
        speaking_style: newCharacter.value.speaking_style.trim(),
        greetings: newCharacter.value.greeting.trim() ? [newCharacter.value.greeting.trim()] : [],
        tags: [],
        avatar_color: newCharacter.value.avatar_color,
      })
      ElMessage.success('角色创建成功')
      showCharacterForm.value = false
      newCharacter.value = { name: '', description: '', personality: '', speaking_style: '', greeting: '', avatar_color: '#667eea' }
      await loadCustomCharacters()
      // 自动切换到新角色
      selectedCharacter.value = 'custom_' + data.id
      await onCharacterChange()
    } catch (e) {
      ElMessage.error('创建失败: ' + e.message)
    }
  }

  // 搜索历史
  async function handleSearch() {
    if (!searchQuery.value.trim()) return
    try {
      const data = await api.searchGirlAiHistory(searchQuery.value.trim())
      searchResults.value = data.records || []
      if (searchResults.value.length === 0) {
        ElMessage.info('未找到匹配的对话')
      }
    } catch (e) {
      ElMessage.error('搜索失败: ' + e.message)
    }
  }

  async function scrollToMessage(result) {
    const index = chatHistory.value.findIndex(message => message.id === result.id)
    if (index < 0) {
      ElMessage.info('该消息位于更早的历史记录中，请先加载更多记录')
      return
    }
    showSearch.value = false
    await nextTick()
    const element = chatMessages.value?.querySelectorAll('[data-message-id]')?.[index]
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 导出对话
  function exportChat() {
    if (chatHistory.value.length === 0) {
      ElMessage.info('暂无对话记录')
      return
    }
    const lines = chatHistory.value.map(m => {
      const role = m.role === 'user' ? '你' : characterDisplayName.value
      return `[${role}]\n${m.content}\n`
    })
    const text = `=== ${characterDisplayName.value} 对话记录 ===\n导出时间: ${new Date().toLocaleString('zh-CN')}\n\n${lines.join('\n')}`
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `虚拟姬对话_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('对话已导出')
  }

  // 防抖控制
  let historyLoadTimer = null
  const HISTORY_LOAD_DEBOUNCE = 2000
  const isHistoryLoading = ref(false)

  // 检测浏览器是否支持 Document Picture-in-Picture API
  const hasPiPSupport = ref(
    typeof window !== 'undefined' && window.documentPictureInPicture?.requestWindow !== undefined
  )

  // 窗口样式
  const windowStyle = computed(() => {
    const style = {
      position: 'fixed',
      left: windowPosition.value.x + 'px',
      top: windowPosition.value.y + 'px',
      width: windowSize.value.width + 'px',
      height: isMinimized.value ? '60px' : windowSize.value.height + 'px',
      zIndex: 2147483647
    }

    if (isAutoHide.value && !isDragging.value) {
      style.width = '80px'
    }

    return style
  })

  // 保存聊天历史到 localStorage
  const saveChatHistory = () => {
    try {
      localStorage.setItem(
        storageKey.value,
        JSON.stringify({
          history: chatHistory.value,
          timestamps: messageTimestamps.value,
          timestamp: Date.now()
        })
      )
    } catch (error) {
      console.error('保存聊天历史失败:', error)
    }
  }

  // 从后端 API 加载聊天历史
  const loadHistoryFromAPI = async (offset = 0, limit = HISTORY_PAGE_SIZE) => {
    try {
      const data = await api.getGirlAiHistory(limit, offset)
      if (data && data.records && Array.isArray(data.records)) {
        const records = [...data.records].reverse().map(record => ({
          id: record.id,
          role: record.role,
          content: record.content,
          timestamp: record.created_at ? new Date(record.created_at).getTime() : Date.now()
        }))

        return {
          history: records,
          total: data.total || 0,
          hasMore: data.has_more !== false
        }
      }
      return { history: [], total: 0, hasMore: false }
    } catch (error) {
      console.error('从 API 加载历史记录失败:', error)
      throw error
    }
  }

  // 加载更多历史记录
  const loadMoreHistory = async () => {
    if (isLoadingMore.value || !hasMoreHistory.value) return

    isLoadingMore.value = true

    const chatMessagesEl = chatMessages.value
    const oldScrollHeight = chatMessagesEl.scrollHeight
    const oldScrollTop = chatMessagesEl.scrollTop

    try {
      const result = await loadHistoryFromAPI(currentOffset.value, HISTORY_PAGE_SIZE)

      if (result && result.history && result.history.length > 0) {
        const existingIds = new Set(chatHistory.value.map(message => message.id).filter(Boolean))
        const newMessages = result.history.filter(message => !message.id || !existingIds.has(message.id))

        chatHistory.value = [...newMessages, ...chatHistory.value]
        currentOffset.value += result.history.length
        hasMoreHistory.value = result.hasMore

        await nextTick()
        const newScrollHeight = chatMessagesEl.scrollHeight
        chatMessagesEl.scrollTop = oldScrollTop + (newScrollHeight - oldScrollHeight)

        saveChatHistory()
      }
    } finally {
      isLoadingMore.value = false
    }
  }

  // 从 localStorage 恢复聊天历史
  const loadChatHistory = async () => {
    if (isHistoryLoading.value || isLoading.value) return

    if (historyLoadTimer) {
      clearTimeout(historyLoadTimer)
      historyLoadTimer = null
    }

    isHistoryLoading.value = true
    const requestVersion = ++historyRequestVersion

    try {
      chatHistory.value = []
      messageTimestamps.value = []
      isHistoryLoaded.value = false

      const result = await loadHistoryFromAPI(0, HISTORY_PAGE_SIZE)
      if (requestVersion !== historyRequestVersion) return

      if (result && result.history && result.history.length > 0) {
        chatHistory.value = result.history
        messageTimestamps.value = chatHistory.value.map(msg => msg.timestamp)
        currentOffset.value = result.history.length
        hasMoreHistory.value = result.hasMore
      } else {
        const greetings = getCharacterGreetings(selectedCharacter.value)
        const greeting = greetings[Math.floor(Math.random() * greetings.length)]
        chatHistory.value = [
          {
            role: 'assistant',
            content: greeting,
            timestamp: Date.now()
          }
        ]
        messageTimestamps.value = [Date.now()]
      }

      saveChatHistory()
      isHistoryLoaded.value = true
    } catch (error) {
      console.error('恢复聊天历史失败:', error)
    } finally {
      isHistoryLoading.value = false
    }
  }

  // 获取消息时间
  const getMessageTime = index => {
    const timestamp = chatHistory.value[index]?.timestamp
    if (timestamp) {
      const date = new Date(timestamp)
      return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit'
      })
    }
    return ''
  }

  // 监听聊天历史加载完成
  watch(
    [chatHistory, isHistoryLoaded],
    async newValues => {
      const [newHistory, loaded] = newValues
      if (loaded && newHistory && newHistory.length > 0) {
        await nextTick()
        scrollToBottom()
      }
    },
    { deep: true }
  )

  // 处理滚动事件
  const handleScroll = e => {
    const chatMessagesEl = e.target
    if (chatMessagesEl.scrollTop < 50 && !isLoadingMore.value && hasMoreHistory.value) {
      loadMoreHistory()
    }
  }

  // 切换到 PiP 模式
  const launchPiP = async () => {
    if (!hasPiPSupport.value) {
      ElMessage.warning('您的浏览器不支持 Document Picture-in-Picture API，请使用 Chrome 116+ 或 Safari 17+')
      return
    }

    showWindow.value = false
    emit('update:visible', false)
    usePiPMode.value = true

    createPiPWindow()
  }

  // 创建 PiP 窗口（通过 postMessage 与主窗口通信）
  const createPiPWindow = async () => {
    if (!hasPiPSupport.value) return

    try {
      const pipWindow = await documentPictureInPicture.requestWindow({
        width: 420,
        height: 520
      })
      pipWindowRef = pipWindow

      // 内联 CSS 变量值
      const cs = getComputedStyle(document.documentElement)
      const primary = cs.getPropertyValue('--primary').trim() || '#667eea'
      const primaryHover = cs.getPropertyValue('--primary-hover').trim() || '#5a6fd6'
      const textPrimary = cs.getPropertyValue('--text-primary').trim() || '#1a1a2e'
      const bgTertiary = cs.getPropertyValue('--bg-tertiary').trim() || '#f0f2f5'
      const borderColor = cs.getPropertyValue('--border-color').trim() || '#e2e8f0'

      pipWindow.document.open()
      pipWindow.document.write(`<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI 虚拟姬</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, ${primary} 0%, ${primaryHover} 100%);
      width: 100%; height: 100vh; overflow: hidden;
      display: flex; flex-direction: column;
    }
    .window-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 16px; background: rgba(255,255,255,0.95);
      backdrop-filter: blur(10px); flex-shrink: 0;
    }
    .window-title { font-size: 15px; font-weight: 700; color: ${textPrimary}; display: flex; align-items: center; gap: 8px; }
    .window-content { flex: 1; display: flex; flex-direction: column; padding: 16px; overflow: hidden; background: rgba(255,255,255,0.98); }
    .chat-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
    .message { display: flex; gap: 10px; animation: fadeIn 0.3s ease-out; }
    .message.user { flex-direction: row-reverse; }
    .message-avatar { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, ${primary} 0%, ${primaryHover} 100%); display: flex; align-items: center; justify-content: center; flex-shrink: 0; overflow: hidden; }
    .message-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .message-content { max-width: 75%; padding: 10px 14px; border-radius: 12px; font-size: 13px; line-height: 1.5; }
    .message.assistant .message-content { background: ${bgTertiary}; color: ${textPrimary}; border-bottom-left-radius: 4px; }
    .message.user .message-content { background: linear-gradient(135deg, ${primary} 0%, ${primaryHover} 100%); color: white; border-bottom-right-radius: 4px; }
    .typing { display: flex; gap: 4px; padding: 10px 14px; }
    .typing-dot { width: 8px; height: 8px; background: ${primary}; border-radius: 50%; animation: bounce 1.4s infinite; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-8px)} }
    @keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
    .input-section { display: flex; gap: 8px; padding-top: 12px; flex-shrink: 0; }
    .chat-input { flex:1; padding:10px 14px; border:2px solid ${borderColor}; border-radius:20px; font-size:13px; outline:none; height:40px; transition:all 0.2s; }
    .chat-input:focus { border-color:${primary}; box-shadow:0 0 0 3px rgba(102,126,234,0.2); }
    .send-button { padding:10px 20px; background:linear-gradient(135deg,${primary} 0%,${primaryHover} 100%); color:white; border:none; border-radius:20px; font-size:13px; font-weight:600; cursor:pointer; height:40px; transition:all 0.2s; }
    .send-button:hover:not(:disabled) { transform:translateY(-2px); box-shadow:0 4px 12px rgba(102,126,234,0.4); }
    .send-button:disabled { opacity:0.5; cursor:not-allowed; }
  </style>
</head>
<body>
  <div class="window-header">
    <div class="window-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
        <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
      </svg>
      虚拟姬 (跨网页模式)
    </div>
  </div>
  <div class="window-content">
    <div class="chat-messages" id="chatMessages"></div>
    <div class="input-section">
      <input type="text" class="chat-input" id="chatInput" placeholder="和虚拟姬聊天..." />
      <button class="send-button" id="sendButton">发送</button>
    </div>
  </div>
<script>
let isLoading = false;
const avatarSrc = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>');

function escapeHtml(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML}

function renderMessages(msgs){
  const el=document.getElementById('chatMessages');
  el.innerHTML=msgs.map(m=>{
    if(m.role==='assistant')return '<div class="message assistant"><div class="message-avatar"><img src="'+avatarSrc+'" /></div><div class="message-content">'+escapeHtml(m.content)+'</div></div>';
    return '<div class="message user"><div class="message-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" width="20" height="20"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div><div class="message-content">'+escapeHtml(m.content)+'</div></div>';
  }).join('');
  if(isLoading)el.innerHTML+='<div class="message assistant"><div class="message-avatar"><img src="'+avatarSrc+'" /></div><div class="message-content typing"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div></div>';
  el.scrollTop=el.scrollHeight;
}

function sendMessage(text){
  if(!text.trim()||isLoading)return;
  isLoading=true;
  window.opener.postMessage({type:'girlai-send',prompt:text},'*');
}

document.getElementById('sendButton').onclick=function(){
  const inp=document.getElementById('chatInput');
  sendMessage(inp.value);inp.value='';
};
document.getElementById('chatInput').onkeydown=function(e){
  if(e.key==='Enter'){const inp=e.target;sendMessage(inp.value);inp.value='';}
};

window.addEventListener('message',function(e){
  if(e.data&&e.data.type==='girlai-history'){renderMessages(e.data.messages);}
  if(e.data&&e.data.type==='girlai-response'){isLoading=false;}
});

window.opener.postMessage({type:'girlai-ready'},'*');
<` + `/script>
<` + `/body>
<` + `/html>`)
      pipWindow.document.close()

      // 监听 PiP 窗口的消息
      const handlePiPMessage = async event => {
        if (!event.data || !event.data.type) return

        if (event.data.type === 'girlai-ready') {
          // PiP 窗口就绪，发送当前聊天历史
          pipWindow.postMessage({
            type: 'girlai-history',
            messages: chatHistory.value.map(m => ({ role: m.role, content: m.content }))
          }, '*')
        }

        if (event.data.type === 'girlai-send') {
          // PiP 窗口发送消息，主窗口调用 API
          const userMsg = event.data.prompt
          if (isLoading.value) {
            pipWindow.postMessage({ type: 'girlai-busy' }, '*')
            return
          }
          isLoading.value = true
          const requestVersion = ++historyRequestVersion
          chatHistory.value.push({ role: 'user', content: userMsg, timestamp: Date.now() })
          messageTimestamps.value.push(Date.now())
          saveChatHistory()
          await nextTick()
          scrollToBottom()

          try {
            const data = await api.sendGirlAiMessage(userMsg, selectedCharacter.value)
            if (requestVersion !== historyRequestVersion) return
            chatHistory.value.push({ role: 'assistant', content: data.message, timestamp: Date.now() })
            messageTimestamps.value.push(Date.now())
            currentOffset.value += 2
          } catch {
            chatHistory.value.push({ role: 'assistant', content: '网络错误，请检查连接后重试。', timestamp: Date.now() })
          } finally {
            isLoading.value = false
            saveChatHistory()
            await nextTick()
            scrollToBottom()
            pipWindow.postMessage({
              type: 'girlai-history',
              messages: chatHistory.value.map(m => ({ role: m.role, content: m.content }))
            }, '*')
            pipWindow.postMessage({ type: 'girlai-response' }, '*')
          }
        }
      }
      pipWindow.addEventListener('message', handlePiPMessage)

      pipWindow.addEventListener('pagehide', () => {
        pipWindow.removeEventListener('message', handlePiPMessage)
        pipWindowRef = null
        usePiPMode.value = false
        showWindow.value = true
        emit('update:visible', true)
      })
    } catch (error) {
      console.error('创建 PiP 窗口失败:', error)
      ElMessage.error('创建 PiP 窗口失败：' + error.message)
      usePiPMode.value = false
      showWindow.value = true
      emit('update:visible', true)
    }
  }

  // 切换 PiP 模式
  const togglePiPMode = () => {
    if (!hasPiPSupport.value) {
      ElMessage.warning('您的浏览器不支持 Document Picture-in-Picture API，请使用 Chrome 116+ 或 Safari 17+')
      return
    }

    usePiPMode.value = !usePiPMode.value
    if (usePiPMode.value) {
      launchPiP()
    } else {
      showWindow.value = true
      emit('update:visible', true)
      nextTick(() => {
        setTimeout(() => {
          restoreScrollPosition()
        }, 100)
      })
    }
  }

  // 展开窗口
  const expandWindow = () => {
    isAutoHide.value = false
    isMinimized.value = false

    if (windowPosition.value.x < 100) {
      windowPosition.value.x = 100
    }
  }

  // 拖拽功能
  const startDrag = e => {
    if (isAutoHide.value || isMinimized.value) return

    if (e.target.closest('.control-btn')) return

    isDragging.value = true
    isAutoHide.value = false
    dragOffset.value = {
      x: e.clientX - windowPosition.value.x,
      y: e.clientY - windowPosition.value.y
    }

    e.preventDefault()
  }

  const onDrag = e => {
    if (!isDragging.value) return

    const newX = e.clientX - dragOffset.value.x
    const newY = e.clientY - dragOffset.value.y

    const screenWidth = window.innerWidth
    const screenHeight = window.innerHeight
    const windowHeight = isMinimized.value ? 60 : windowSize.value.height

    windowPosition.value = {
      x: Math.max(0, Math.min(newX, screenWidth - windowSize.value.width)),
      y: Math.max(0, Math.min(newY, screenHeight - windowHeight))
    }
  }

  const stopDrag = () => {
    isDragging.value = false
  }

  // 调整大小功能
  const startResize = e => {
    if (isAutoHide.value || isMinimized.value) return

    e.preventDefault()
    e.stopPropagation()

    isResizing.value = true
    resizeOffset.value = {
      x: e.clientX - windowSize.value.width,
      y: e.clientY - windowSize.value.height
    }
  }

  const onResize = e => {
    if (!isResizing.value) return

    const minWidth = 350
    const minHeight = 450
    const maxWidth = 800
    const maxHeight = 700

    const newWidth = windowSize.value.width + e.movementX
    const newHeight = windowSize.value.height + e.movementY

    windowSize.value = {
      width: Math.max(minWidth, Math.min(newWidth, maxWidth)),
      height: Math.max(minHeight, Math.min(newHeight, maxHeight))
    }
  }

  const stopResize = () => {
    isResizing.value = false
  }

  // 最小化/还原
  const toggleMinimize = () => {
    isMinimized.value = !isMinimized.value
    if (!isMinimized.value) {
      expandWindow()
    }
  }

  // 关闭窗口
  const closeWindow = () => {
    emit('update:visible', false)
    emit('close')
  }

  // 确认清除历史记录
  const confirmClearHistory = async () => {
    try {
      await ElMessageBox.confirm('确定要清除所有虚拟姬聊天历史吗？此操作不可恢复。', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }

    try {
      historyRequestVersion += 1
      const result = await api.deleteGirlAiHistory([], true)
      if (result && result.status === 'deleted') {
        chatHistory.value = []
        messageTimestamps.value = []
        currentOffset.value = 0
        hasMoreHistory.value = false
        localStorage.removeItem(storageKey.value)
        ElMessage.success(`已清除 ${result.count} 条历史记录`)
        if (pipWindowRef) {
          pipWindowRef.postMessage({ type: 'girlai-history', messages: [] }, '*')
        }
      } else {
        ElMessage.error('清除历史记录失败')
      }
    } catch (error) {
      console.error('清除历史记录出错:', error)
      ElMessage.error('清除历史记录失败')
    }
  }

  // 检测是否需要自动隐藏
  const checkAutoHide = () => {
    if (isMinimized.value) return

    const shouldHide = windowPosition.value.x < 100

    if (shouldHide !== isAutoHide.value) {
      isAutoHide.value = shouldHide
    }
  }

  // 获取角色 emoji
  const getCharacterEmoji = character => {
    const icons = {
      gentle: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
      lively: 'M12 2v20M2 12h20M4.93 4.93l14.14 14.14M19.07 4.93L4.93 19.07',
      tsundere: 'M12 2l2.4 7.2h7.6l-6 4.8 2.4 7.2-6-4.8-6 4.8 2.4-7.2-6-4.8h7.6z',
      intellectual: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20',
      companion:
        'M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z'
    }
    return icons[character] || icons.gentle
  }

  // 角色切换
  const onCharacterChange = async () => {
    // 从角色配置中随机选择一个开场白
    const greetings = getCharacterGreetings(selectedCharacter.value)
    const greeting = greetings[Math.floor(Math.random() * greetings.length)]

    chatHistory.value.push({
      role: 'assistant',
      content: greeting,
      timestamp: Date.now()
    })
    messageTimestamps.value.push(Date.now())

    saveChatHistory()

    await nextTick()
    scrollToBottom()
  }

  // 获取角色开场白列表
  const getCharacterGreetings = character => {
    const greetings = {
      gentle: ['亲爱的，今天过得怎么样呀？~', '欢迎回来~ 我一直在等你呢', '看到你来了真开心，想和我聊聊天吗？~'],
      lively: ['呀吼~！今天也要元气满满哦！(≧∇≦) ノ', '哇！你来啦！我等你好久啦~✨', '哈喽哈喽~ 今天有什么有趣的事情吗？٩(◕‿◕) ノ'],
      tsundere: ['哼、哼！才、才不是特意等你呢！(￣^￣)', '哦…你来了啊…我、我只是刚好路过而已！', '…笨蛋，下次别让我等这么久啦！'],
      intellectual: ['你好呀，今天也是求知的一天呢', '欢迎来到知识的殿堂，有什么我可以帮你的吗？', '又见面了，最近在读什么有趣的书吗？'],
      companion: ['亲爱的~ 我好想你呀！❤', '你终于来啦~ 我一直在想你呢 (´｡• ᵕ •｡`)', '最喜欢你啦~ 今天也想和你在一起 ❤']
    }
    if (character.startsWith('custom_')) {
      const customId = character.replace('custom_', '')
      const custom = customCharacters.value.find(c => c.id === customId)
      if (custom && custom.greetings && custom.greetings.length > 0) {
        return custom.greetings
      }
      return [`你好呀~ 我是${custom?.name || '你的自定义角色'}，请多指教~`]
    }
    return greetings[character] || greetings.gentle
  }

  // 获取角色名称
  const getCharacterName = character => {
    const names = {
      gentle: '温柔学姐',
      lively: '元气少女',
      tsundere: '傲娇妹妹',
      intellectual: '知性御姐',
      companion: '贴心伴侣'
    }
    return names[character] || '小美'
  }

  // 发送消息
  const sendMessage = async () => {
    if (!inputMessage.value.trim() || isLoading.value) return

    const message = inputMessage.value.trim()
    const requestVersion = ++historyRequestVersion
    const timestamp = Date.now()

    chatHistory.value.push({
      role: 'user',
      content: message,
      timestamp: timestamp
    })
    messageTimestamps.value.push(timestamp)

    inputMessage.value = ''
    isLoading.value = true
    isConnected.value = false

    await nextTick()
    scrollToBottom()

    try {
      const data = await api.sendGirlAiMessage(message, selectedCharacter.value)
      if (requestVersion !== historyRequestVersion) return

      const assistantTimestamp = Date.now()
      chatHistory.value.push({
        role: 'assistant',
        content: data.message,
        timestamp: assistantTimestamp
      })
      messageTimestamps.value.push(assistantTimestamp)
      currentOffset.value += 2
      isConnected.value = true
    } catch (error) {
      console.error('调用 GirlAi API 失败:', error)
      const errorTimestamp = Date.now()
      chatHistory.value.push({
        role: 'assistant',
        content: '网络错误，请检查连接后重试。',
        timestamp: errorTimestamp
      })
      messageTimestamps.value.push(errorTimestamp)
      isConnected.value = false
    } finally {
      isLoading.value = false

      saveChatHistory()

      await nextTick()
      scrollToBottom()
    }
  }

  // 滚动到底部
  const scrollToBottom = () => {
    if (chatMessages.value) {
      chatMessages.value.scrollTop = chatMessages.value.scrollHeight
    }
  }

  // 保存当前滚动位置
  const saveScrollPosition = () => {
    if (chatMessages.value && !usePiPMode.value) {
      windowScrollPosition.value = chatMessages.value.scrollTop
    }
  }

  // 恢复滚动位置
  const restoreScrollPosition = () => {
    if (chatMessages.value && !usePiPMode.value) {
      chatMessages.value.scrollTop = windowScrollPosition.value
    }
  }

  // 监听聊天历史变化（保存滚动位置 + 持久化）
  watch(
    chatHistory,
    async () => {
      await nextTick()
      saveScrollPosition()
      saveChatHistory()
    },
    { deep: true }
  )

  // 监听页面可见性变化
  const handleVisibilityChange = () => {
    if (!document.hidden) {
      if (historyLoadTimer) {
        clearTimeout(historyLoadTimer)
      }

      historyLoadTimer = setTimeout(() => {
        loadChatHistory()
      }, HISTORY_LOAD_DEBOUNCE)
    }
  }

  // 监听存储变化
  const handleStorage = e => {
    if (e.key === storageKey.value) {
      if (historyLoadTimer) {
        clearTimeout(historyLoadTimer)
      }

      historyLoadTimer = setTimeout(() => {
        loadChatHistory()
      }, HISTORY_LOAD_DEBOUNCE)
    }
  }

  // 初始化
  onMounted(() => {
    loadChatHistory()
    loadCustomCharacters()

    const screenWidth = window.innerWidth
    const screenHeight = window.innerHeight
    windowPosition.value = {
      x: screenWidth - windowSize.value.width - 20,
      y: screenHeight - windowSize.value.height - 100
    }

    document.addEventListener('mousemove', checkAutoHide)
    document.addEventListener('mousemove', onDrag)
    document.addEventListener('mouseup', stopDrag)
    document.addEventListener('mousemove', onResize)
    document.addEventListener('mouseup', stopResize)

    currentOffset.value = chatHistory.value.length

    document.addEventListener('visibilitychange', handleVisibilityChange)
    window.addEventListener('storage', handleStorage)
  })

  // 组件卸载时清理
  onUnmounted(() => {
    document.removeEventListener('mousemove', checkAutoHide)
    document.removeEventListener('mousemove', onDrag)
    document.removeEventListener('mouseup', stopDrag)
    document.removeEventListener('mousemove', onResize)
    document.removeEventListener('mouseup', stopResize)

    document.removeEventListener('visibilitychange', handleVisibilityChange)
    window.removeEventListener('storage', handleStorage)

    if (pipWindowRef) {
      pipWindowRef.close()
      pipWindowRef = null
    }
  })

  defineExpose({
    launchPiP,
    togglePiPMode
  })
</script>

<style scoped>
  /* 窗口主容器 */
  .virtual-girl-window {
    position: fixed;
    background: linear-gradient(135deg, var(--bg-secondary) 0%, #f1f5f9 100%);
    border-radius: 20px;
    box-shadow:
      0 20px 60px rgba(0, 0, 0, 0.3),
      0 0 0 1px rgba(255, 255, 255, 0.5);
    overflow: hidden;
    transition:
      background 0.3s,
      box-shadow 0.3s;
    backdrop-filter: blur(20px);
    border: 2px solid rgba(148, 163, 184, 0.2);
    display: flex;
    flex-direction: column;
  }

  /* SVG 图标样式 */
  .mode-icon-svg {
    width: 16px;
    height: 16px;
    color: white;
  }

  .user-avatar-icon-svg {
    width: 20px;
    height: 20px;
    color: var(--primary);
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 50%;
    padding: 6px;
  }

  .character-icon-svg {
    width: 20px;
    height: 20px;
  }

  .pip-window-icon {
    width: 18px;
    height: 18px;
    margin-right: 6px;
    vertical-align: middle;
  }

  /* 自动隐藏侧边栏 */
  .autohide-sidebar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--bg-secondary) 0%, #f1f5f9 100%);
    border-radius: 20px;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    border: 2px solid rgba(102, 126, 234, 0.3);
    animation: slideIn 0.3s ease-out;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: scale(0.95);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .autohide-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    transition: transform 0.2s;
    padding: 8px;
  }

  .autohide-content:hover {
    transform: scale(1.05);
  }

  .sidebar-avatar {
    width: 45px;
    height: 45px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--primary);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .sidebar-text {
    font-size: 12px;
    font-weight: 600;
    color: var(--primary);
  }

  /* 窗口头部 */
  .window-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 18px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    cursor: move;
    user-select: none;
    gap: 12px;
  }

  .window-title {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .ai-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    overflow: hidden;
    flex-shrink: 0;
    border: 2px solid rgba(255, 255, 255, 0.5);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .ai-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .title-content {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .title-text {
    font-weight: 700;
    font-size: 15px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .title-status {
    font-size: 11px;
    opacity: 0.9;
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.2);
    display: inline-block;
    width: fit-content;
  }

  .title-status.online {
    background: rgba(34, 197, 94, 0.3);
  }

  .title-status.offline {
    background: rgba(239, 68, 68, 0.3);
  }

  .window-controls {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
  }

  .control-btn {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.15);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .control-btn:hover {
    background: rgba(255, 255, 255, 0.3);
    transform: scale(1.1);
  }

  .control-btn.close-btn:hover {
    background: rgba(239, 68, 68, 0.5);
  }

  /* 模式切换按钮 */
  .mode-toggle-btn {
    position: absolute;
    top: 10px;
    right: 120px;
    background: rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 20px;
    padding: 6px 12px;
    cursor: pointer;
    z-index: 10;
    font-size: 18px;
    transition: all 0.2s;
    backdrop-filter: blur(10px);
  }

  .mode-toggle-btn:hover {
    background: rgba(255, 255, 255, 0.3);
    transform: scale(1.1);
  }

  /* 窗口内容 */
  .window-content-wrapper {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .window-content {
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
    height: 100%;
  }

  .chat-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
  }

  /* 角色选择栏 */
  .character-selector {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: linear-gradient(90deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .character-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .character-select {
    flex: 1;
    padding: 8px 12px;
    border: 2px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--bg-primary);
    cursor: pointer;
    transition: all 0.2s;
    outline: none;
  }

  .character-select:hover {
    border-color: var(--primary);
  }

  .character-select:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .character-indicator {
    font-size: 20px;
    padding: 4px 8px;
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--border-color) 100%);
    border-radius: 8px;
    transition: all 0.2s;
  }

  .character-indicator.gentle {
    background: linear-gradient(135deg, #fce7f3 0%, #fbcfe8 100%);
  }
  .character-indicator.lively {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  }
  .character-indicator.tsundere {
    background: linear-gradient(135deg, var(--danger-100) 0%, #fecaca 100%);
  }
  .character-indicator.intellectual {
    background: linear-gradient(135deg, var(--primary-100) 0%, #bfdbfe 100%);
  }
  .character-indicator.companion {
    background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    background: linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
  }

  .chat-messages::-webkit-scrollbar {
    width: 6px;
  }

  .chat-messages::-webkit-scrollbar-track {
    background: transparent;
  }

  .chat-messages::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #c7d2fe 0%, #a5b4fc 100%);
    border-radius: 3px;
  }

  /* 消息样式 */
  .message {
    display: flex;
    gap: 12px;
    animation: fadeIn 0.3s ease-out;
    max-width: 100%;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .message.user {
    flex-direction: row-reverse;
  }

  .message-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }

  .message-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .user-avatar-icon {
    font-size: 20px;
  }

  .message-body {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .message-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  .message-sender {
    font-weight: 600;
    color: var(--text-secondary);
  }

  .message.user .message-sender {
    color: var(--primary);
  }

  .message-time {
    color: var(--text-tertiary);
    font-size: 11px;
  }

  .message-content {
    padding: 12px 16px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.6;
    word-wrap: break-word;
    display: inline-block;
    max-width: 80%;
  }

  .message.assistant .message-content {
    background: var(--bg-primary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  .message.user .message-content {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }

  /* 打字动画 */
  .typing {
    display: flex;
    gap: 4px;
    padding: 12px 16px;
    background: var(--bg-primary) !important;
  }

  .typing-dot {
    width: 8px;
    height: 8px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 50%;
    animation: typingBounce 1.4s ease-in-out infinite;
  }

  .typing-dot:nth-child(2) {
    animation-delay: 0.2s;
  }

  .typing-dot:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes typingBounce {
    0%,
    60%,
    100% {
      transform: translateY(0);
    }
    30% {
      transform: translateY(-8px);
    }
  }

  /* 输入区域 */
  .input-section {
    padding: 16px;
    background: var(--bg-primary);
    border-top: 1px solid var(--border-color);
    flex-shrink: 0;
  }

  .input-wrapper {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .chat-input {
    flex: 1;
    padding: 12px 18px;
    border: 2px solid var(--border-color);
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s;
    background: var(--bg-secondary);
    height: 46px;
    box-sizing: border-box;
  }

  .chat-input:focus {
    border-color: var(--primary);
    background: var(--bg-primary);
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
  }

  .chat-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .send-button {
    width: 46px;
    height: 46px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    flex-shrink: 0;
  }

  .send-button:hover:not(:disabled) {
    transform: scale(1.05) rotate(-5deg);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .send-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* 调整大小手柄 */
  .resize-handle {
    position: absolute;
    bottom: 0;
    right: 0;
    width: 20px;
    height: 20px;
    cursor: nwse-resize;
    background: linear-gradient(135deg, transparent 50%, rgba(102, 126, 234, 0.3) 50%);
    border-radius: 0 0 20px 0;
    transition: all 0.2s;
  }

  .resize-handle:hover {
    background: linear-gradient(135deg, transparent 50%, rgba(102, 126, 234, 0.5) 50%);
    width: 25px;
    height: 25px;
  }

  /* 加载更多 overlay */
  .loading-more-overlay {
    position: absolute;
    top: 60px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border-radius: 20px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 10;
  }

  .loading-spinner {
    position: relative;
    width: 30px;
    height: 30px;
  }

  .spinner-ring {
    position: absolute;
    width: 100%;
    height: 100%;
    border: 3px solid transparent;
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
  }

  .spinner-ring:nth-child(2) {
    border-top-color: var(--primary-hover);
    animation-delay: -0.4s;
  }

  .spinner-ring:nth-child(3) {
    border-top-color: var(--primary);
    animation-delay: -0.8s;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    font-size: 12px;
    color: var(--primary);
    font-weight: 600;
  }

  /* 最小化状态 */
  .window-content.minimized-content {
    display: none;
  }

  /* 搜索栏 */
  .search-bar {
    display: flex;
    gap: 6px;
    padding: 8px 12px;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
  }

  .search-input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    outline: none;
  }

  .search-input:focus { border-color: var(--primary); }

  .search-btn, .search-close {
    padding: 6px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .search-btn { background: var(--primary); color: white; border-color: var(--primary); }
  .search-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* 搜索结果 */
  .search-results {
    max-height: 150px;
    overflow-y: auto;
    background: var(--bg-tertiary);
    border-bottom: 1px solid var(--border-color);
    padding: 8px;
  }

  .search-results-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }

  .search-results-header button {
    border: none;
    background: none;
    color: var(--primary);
    cursor: pointer;
    font-size: 12px;
  }

  .search-result-item {
    display: flex;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.2s;
  }

  .search-result-item:hover { background: var(--bg-primary); }

  .search-result-role {
    font-weight: 600;
    color: var(--primary);
    white-space: nowrap;
  }

  .search-result-content {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 添加角色按钮 */
  .add-character-btn {
    padding: 4px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: var(--bg-primary);
    color: var(--text-primary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .add-character-btn:hover { border-color: var(--primary); color: var(--primary); }

  /* 自定义角色表单 */
  .character-form-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .character-form {
    width: 320px;
    max-height: 90%;
    overflow-y: auto;
    background: var(--bg-secondary);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  }

  .character-form h3 {
    margin: 0 0 16px 0;
    font-size: 16px;
    color: var(--text-primary);
  }

  .form-field {
    margin-bottom: 12px;
  }

  .form-field label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 4px;
  }

  .form-field .required { color: #ef4444; }

  .form-field input[type="text"],
  .form-field textarea {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    outline: none;
    font-family: inherit;
    resize: vertical;
  }

  .form-field input[type="text"]:focus,
  .form-field textarea:focus { border-color: var(--primary); }

  .form-field input[type="color"] {
    width: 40px;
    height: 32px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    cursor: pointer;
    padding: 2px;
  }

  .form-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    margin-top: 16px;
  }

  .form-cancel, .form-submit {
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .form-cancel {
    border: 1px solid var(--border-color);
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .form-submit {
    border: none;
    background: var(--primary);
    color: white;
    font-weight: 500;
  }

  .form-submit:disabled { opacity: 0.5; cursor: not-allowed; }
  .form-submit:hover:not(:disabled) { transform: translateY(-1px); }
</style>
