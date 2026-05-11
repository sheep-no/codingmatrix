<template>
  <div v-if="showWindow && !usePiPMode" class="virtual-girl-window" :style="windowStyle">
    <!-- 自动隐藏时只显示侧边栏 -->
    <div v-if="isAutoHide" class="autohide-sidebar">
      <div class="autohide-content" @click.stop="expandWindow">
        <img src="../img/AiChat.jpeg" class="sidebar-avatar" alt="AI" />
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
        :title="usePiPMode ? '切换到普通模式' : '切换到跨网页模式'"
        @click="togglePiPMode"
      >
        <svg
          v-if="usePiPMode"
          class="mode-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="2" y1="12" x2="22" y2="12"></line>
          <path
            d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"
          ></path>
        </svg>
        <svg
          v-else
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
            <img src="../img/AiChat.jpeg" alt="AI" />
          </div>
          <div class="title-content">
            <span class="title-text">虚拟姬</span>
            <span class="title-status" :class="{ online: isConnected, offline: !isConnected }">
              {{ isConnected ? '在线' : '离线' }}
            </span>
          </div>
        </div>
        <div class="window-controls">
          <button class="control-btn" title="最小化" @click.stop="toggleMinimize">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
            >
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <button class="control-btn" title="清除历史" @click.stop="confirmClearHistory">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
            >
              <polyline points="3 6 5 6 21 6"></polyline>
              <path
                d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
              ></path>
            </svg>
          </button>
          <button class="control-btn close-btn" title="关闭" @click.stop="closeWindow">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>

      <!-- 窗口内容 -->
      <div class="window-content-wrapper">
        <div class="window-content" :class="{ 'minimized-content': isMinimized }">
          <!-- 聊天区域 -->
          <div class="chat-section">
            <!-- 角色选择栏 -->
            <div class="character-selector">
              <div class="character-label">选择角色:</div>
              <select
                v-model="selectedCharacter"
                class="character-select"
                @change="onCharacterChange"
              >
                <option value="gentle">温柔学姐</option>
                <option value="lively">元气少女</option>
                <option value="tsundere">傲娇妹妹</option>
                <option value="intellectual">知性御姐</option>
                <option value="companion">贴心伴侣</option>
              </select>
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
                :class="['message', message.role]"
              >
                <div class="message-avatar">
                  <img v-if="message.role === 'assistant'" src="../img/AiChat.jpeg" alt="AI" />
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
                  <img src="../img/AiChat.jpeg" alt="AI" />
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
    </template>
  </div>
</template>

<script setup>
  import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
  import { api } from '@/utils/api/index'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close', 'update:visible'])

  // 模式选择
  const usePiPMode = ref(false)
  const STORAGE_KEY = 'virtualGirlChatHistory'

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

  // 角色选择
  const selectedCharacter = ref('gentle')
  const characterDescriptions = {
    gentle: '温柔体贴，善解人意',
    lively: '活泼开朗，充满活力',
    tsundere: '口是心非，外冷内热',
    intellectual: '成熟稳重，博学多才',
    companion: '温柔陪伴，知心倾听'
  }

  // 防抖控制
  let historyLoadTimer = null
  const HISTORY_LOAD_DEBOUNCE = 2000
  const isHistoryLoading = ref(false)

  // 检测浏览器是否支持 Document Picture-in-Picture API
  const hasPiPSupport = ref(
    'documentPictureInPicture' in window && documentPictureInPicture.requestWindow !== undefined
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
        STORAGE_KEY,
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
        const records = data.records.map(record => ({
          role: record.role,
          content: record.content
        }))

        const newHistory = groupAndReversePairs(records)

        return {
          history: newHistory,
          total: data.total || 0,
          hasMore: data.has_more !== false
        }
      }
      return null
    } catch (error) {
      console.error('从 API 加载历史记录失败:', error)
      return null
    }
  }

  // 按反转对话对顺序，保持对话对内 user→assistant 的顺序
  const groupAndReversePairs = records => {
    const conversations = []
    let currentPair = []

    for (let i = 0; i < records.length; i++) {
      const record = records[i]

      if (record.role === 'user') {
        if (currentPair.length > 0) {
          conversations.push([...currentPair])
          currentPair = []
        }
        currentPair.push(record)

        if (i < records.length - 1 && records[i + 1]?.role === 'assistant') {
          currentPair.push(records[i + 1])
          i++
          conversations.push([...currentPair])
          currentPair = []
        }
      } else if (record.role === 'assistant') {
        if (currentPair.length === 0) {
          currentPair.push(record)
          conversations.push([...currentPair])
          currentPair = []
        }
      }
    }

    if (currentPair.length > 0) {
      conversations.push(currentPair)
    }

    if (
      conversations.length === 0 ||
      (conversations.length === 1 && conversations[0].length === records.length)
    ) {
      return records
    }

    const reversed = [...conversations].reverse()
    return reversed.flat()
  }

  // 加载更多历史记录
  const loadMoreHistory = async () => {
    if (isLoadingMore.value || !hasMoreHistory.value) return

    isLoadingMore.value = true

    const chatMessagesEl = chatMessages.value
    const oldScrollHeight = chatMessagesEl.scrollHeight
    const oldScrollTop = chatMessagesEl.scrollTop

    const result = await loadHistoryFromAPI(currentOffset.value, HISTORY_PAGE_SIZE)

    if (result && result.history && result.history.length > 0) {
      const newMessages = result.history.map(msg => ({
        ...msg,
        timestamp: Date.now()
      }))

      chatHistory.value = [...newMessages, ...chatHistory.value]
      currentOffset.value += result.history.length
      hasMoreHistory.value = result.hasMore

      await nextTick()
      const newScrollHeight = chatMessagesEl.scrollHeight
      chatMessagesEl.scrollTop = oldScrollTop + (newScrollHeight - oldScrollHeight)

      saveChatHistory()
    }

    isLoadingMore.value = false
  }

  // 从 localStorage 恢复聊天历史
  const loadChatHistory = async () => {
    if (isHistoryLoading.value) return

    if (historyLoadTimer) {
      clearTimeout(historyLoadTimer)
      historyLoadTimer = null
    }

    isHistoryLoading.value = true

    try {
      chatHistory.value = []
      messageTimestamps.value = []
      isHistoryLoaded.value = false

      const result = await loadHistoryFromAPI(0, HISTORY_PAGE_SIZE)

      if (result && result.history && result.history.length > 0) {
        chatHistory.value = result.history.map((msg, index) => ({
          ...msg,
          timestamp: Date.now() - (result.history.length - index) * 1000
        }))
        messageTimestamps.value = chatHistory.value.map(msg => msg.timestamp)
        currentOffset.value = result.history.length
        hasMoreHistory.value = result.hasMore
      } else {
        chatHistory.value = [
          {
            role: 'assistant',
            content: `你好呀~我是你的${getCharacterName(selectedCharacter.value)}，${characterDescriptions[selectedCharacter.value]}。有什么可以帮助你的吗？`,
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
    if (index < messageTimestamps.value.length) {
      const date = new Date(messageTimestamps.value[index])
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

        for (let i = 0; i < 5; i++) {
          await new Promise(resolve => setTimeout(resolve, 100))
          scrollToBottom()
        }
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
      alert('您的浏览器不支持 Document Picture-in-Picture API，请使用 Chrome 116+ 或 Safari 17+')
      return
    }

    showWindow.value = false
    emit('update:visible', false)
    usePiPMode.value = true

    createPiPWindow()
  }

  // 创建 PiP 窗口（简化版本）
  const createPiPWindow = async () => {
    if (!hasPiPSupport.value) return

    try {
      const savedHistory = JSON.parse(JSON.stringify(chatHistory.value))

      const pipWindow = await documentPictureInPicture.requestWindow({
        width: 420,
        height: 520
      })

      const pipJSCode = `
let chatHistory = ${JSON.stringify(savedHistory)};
let isLoading = false;

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function renderMessages() {
  const chatMessages = document.getElementById('chatMessages');
  chatMessages.innerHTML = chatHistory.map((msg, index) => {
    if (msg.role === 'assistant') {
      return \`<div class="message assistant"><div class="message-avatar"><img src="/src/img/AiChat.jpeg" alt="AI" /></div><div class="message-content">\${escapeHtml(msg.content)}</div></div>\`;
    } else {
      return \`<div class="message user"><div class="message-avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:20px;height:20px;color:white"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg></div><div class="message-content">\${escapeHtml(msg.content)}</div></div>\`;
    }
  }).join('');
  
  if (isLoading) {
    chatMessages.innerHTML += \`<div class="message assistant"><div class="message-avatar"><img src="/src/img/AiChat.jpeg" alt="AI" /></div><div class="message-content typing"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div></div>\`;
  }
  
  scrollToBottom();
}

function scrollToBottom() {
  const chatMessages = document.getElementById('chatMessages');
  if (chatMessages) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

function addMessage(role, content) {
  chatHistory.push({ role, content });
  renderMessages();
}

async function sendMessage(message) {
  if (!message.trim() || isLoading) return;
  
  addMessage('user', message);
  isLoading = true;
  renderMessages();
  
  try {
    const token = localStorage.getItem('access_token');
    const response = await fetch('/api/v1/GirlAi', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
      },
      body: JSON.stringify({
        prompt: message,
        temperature: 0.8
      })
    });
    
    if (response.ok) {
      const data = await response.json();
      addMessage('assistant', data.message || data.response || '抱歉，我无法理解您的意思。');
    } else {
      addMessage('assistant', '抱歉，我遇到了一些问题，请稍后再试。');
    }
  } catch (error) {
    addMessage('assistant', '网络错误，请检查连接后重试。');
  } finally {
    isLoading = false;
    renderMessages();
  }
}

renderMessages();

document.getElementById('sendButton').addEventListener('click', () => {
  const input = document.getElementById('chatInput');
  const message = input.value.trim();
  if (message) {
    sendMessage(message);
    input.value = '';
  }
});

document.getElementById('chatInput').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    const input = e.target;
    const message = input.value.trim();
    if (message) {
      sendMessage(message);
      input.value = '';
    }
  }
});
`

      const blob = new Blob([pipJSCode], { type: 'application/javascript' })
      const jsUrl = URL.createObjectURL(blob)

      pipWindow.document.open()
      pipWindow.document.write(`
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI 虚拟姬</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
      width: 100%;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .window-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      flex-shrink: 0;
    }
    .window-title {
      font-size: 15px;
      font-weight: 700;
      color: #1a1a1a;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .window-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 16px;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.98);
    }
    .chat-messages {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .message {
      display: flex;
      gap: 10px;
      animation: fadeIn 0.3s ease-out;
    }
    .message.user { flex-direction: row-reverse; }
    .message-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      flex-shrink: 0;
      overflow: hidden;
    }
    .message-avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .message-content {
      max-width: 75%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.5;
    }
    .message.assistant .message-content {
      background: #f3f4f6;
      color: #1f2937;
      border-bottom-left-radius: 4px;
    }
    .message.user .message-content {
      background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
      color: white;
      border-bottom-right-radius: 4px;
    }
    .typing {
      display: flex;
      gap: 4px;
      padding: 10px 14px;
    }
    .typing-dot {
      width: 8px;
      height: 8px;
      background: #0d9488;
      border-radius: 50%;
      animation: bounce 1.4s infinite;
    }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-8px); }
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .input-section {
      display: flex;
      gap: 8px;
      padding-top: 12px;
      flex-shrink: 0;
    }
    .chat-input {
      flex: 1;
      padding: 10px 14px;
      border: 2px solid #e5e7eb;
      border-radius: 20px;
      font-size: 13px;
      outline: none;
      height: 40px;
      transition: all 0.2s;
    }
    .chat-input:focus {
      border-color: #0d9488;
      box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
    }
    .send-button {
      padding: 10px 20px;
      background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
      color: white;
      border: none;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }
    .send-button:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    .send-button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  </style>
</head>
<body>
  <div class="window-header">
          <div class="window-title">
            <svg class="pip-window-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="2" y1="12" x2="22" y2="12"></line>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
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
  <script src="${jsUrl}"><\/script>
</body>
</html>
    `)
      pipWindow.document.close()

      pipWindow.addEventListener('pagehide', () => {
        usePiPMode.value = false
        showWindow.value = true
        emit('update:visible', true)
      })
    } catch (error) {
      console.error('创建 PiP 窗口失败:', error)
      alert('创建 PiP 窗口失败：' + error.message)
      usePiPMode.value = false
      showWindow.value = true
      emit('update:visible', true)
    }
  }

  // 切换 PiP 模式
  const togglePiPMode = () => {
    if (!hasPiPSupport.value) {
      alert('您的浏览器不支持 Document Picture-in-Picture API，请使用 Chrome 116+ 或 Safari 17+')
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
    if (!confirm('确定要清除所有虚拟姬聊天历史吗？此操作不可恢复。')) {
      return
    }

    try {
      const result = await api.deleteGirlAiHistory([], true)
      if (result && result.status === 'deleted') {
        chatHistory.value = []
        localStorage.removeItem(STORAGE_KEY)
        alert(`已清除 ${result.count} 条历史记录`)
      } else {
        alert('清除历史记录失败')
      }
    } catch (error) {
      console.error('清除历史记录出错:', error)
      alert('清除历史记录失败')
    }
  }

  // 检测是否需要自动隐藏
  const checkAutoHide = e => {
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
    const systemMessage = `你好呀~我是你的${getCharacterName(selectedCharacter.value)}，${characterDescriptions[selectedCharacter.value]}。有什么可以帮助你的吗？`

    chatHistory.value.push({
      role: 'assistant',
      content: systemMessage,
      timestamp: Date.now()
    })
    messageTimestamps.value.push(Date.now())

    saveChatHistory()

    await nextTick()
    scrollToBottom()
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

    saveChatHistory()

    await nextTick()
    scrollToBottom()

    try {
      const response = await api.post('/GirlAi', {
        prompt: message,
        temperature: 0.8,
        character: selectedCharacter.value
      })

      if (response.ok) {
        const data = await response.json()
        const assistantTimestamp = Date.now()
        chatHistory.value.push({
          role: 'assistant',
          content: data.message,
          timestamp: assistantTimestamp
        })
        messageTimestamps.value.push(assistantTimestamp)
        isConnected.value = true
      } else {
        const errorTimestamp = Date.now()
        chatHistory.value.push({
          role: 'assistant',
          content: '抱歉，我遇到了一些问题，请稍后再试。',
          timestamp: errorTimestamp
        })
        messageTimestamps.value.push(errorTimestamp)
      }
    } catch (error) {
      console.error('调用 GirlAi API 失败:', error)
      const errorTimestamp = Date.now()
      chatHistory.value.push({
        role: 'assistant',
        content: '网络错误，请检查连接后重试。',
        timestamp: errorTimestamp
      })
      messageTimestamps.value.push(errorTimestamp)
    } finally {
      isLoading.value = false
      isConnected.value = true

      saveChatHistory()

      await nextTick()
      scrollToBottom()

      if (hasMoreHistory.value) {
        currentOffset.value = 0
        hasMoreHistory.value = true
      }
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

  // 监听聊天历史变化
  watch(
    chatHistory,
    async () => {
      await nextTick()
      saveScrollPosition()
    },
    { deep: true }
  )

  // 监听来自 PiP 窗口的历史更新
  const handleMessage = event => {
    if (event.data && event.data.type === 'history-update') {
      chatHistory.value = event.data.data
      currentOffset.value = event.data.data.length
      hasMoreHistory.value = true
      saveChatHistory()
    }
  }

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
    if (e.key === STORAGE_KEY) {
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
    window.addEventListener('message', handleMessage)

    watch(
      [chatHistory],
      () => {
        saveChatHistory()
      },
      { deep: true }
    )
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
    window.removeEventListener('message', handleMessage)

    if (historyLoadTimer) {
      clearTimeout(historyLoadTimer)
      historyLoadTimer = null
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
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
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
    color: #0d9488;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
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
    border: 2px solid #0d9488;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .sidebar-text {
    font-size: 12px;
    font-weight: 600;
    color: #0d9488;
  }

  /* 窗口头部 */
  .window-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 18px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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
    background: linear-gradient(135deg, #ffffff 0%, #f9fafb 100%);
  }

  /* 角色选择栏 */
  .character-selector {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: linear-gradient(90deg, #f8fafc 0%, #ffffff 100%);
    border-bottom: 1px solid #e5e7eb;
    flex-shrink: 0;
  }

  .character-label {
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    white-space: nowrap;
  }

  .character-select {
    flex: 1;
    padding: 8px 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #1f2937;
    background: white;
    cursor: pointer;
    transition: all 0.2s;
    outline: none;
  }

  .character-select:hover {
    border-color: #0d9488;
  }

  .character-select:focus {
    border-color: #0d9488;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  }

  .character-indicator {
    font-size: 20px;
    padding: 4px 8px;
    background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
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
    background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
  }
  .character-indicator.intellectual {
    background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
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
    background: linear-gradient(180deg, #f8fafc 0%, #ffffff 100%);
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
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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
    color: #4b5563;
  }

  .message.user .message-sender {
    color: #0d9488;
  }

  .message-time {
    color: #9ca3af;
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
    background: white;
    color: #1f2937;
    border: 1px solid #e5e7eb;
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  .message.user .message-content {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
  }

  /* 打字动画 */
  .typing {
    display: flex;
    gap: 4px;
    padding: 12px 16px;
    background: white !important;
  }

  .typing-dot {
    width: 8px;
    height: 8px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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
    background: white;
    border-top: 1px solid #e5e7eb;
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
    border: 2px solid #e5e7eb;
    border-radius: 24px;
    font-size: 14px;
    outline: none;
    transition: all 0.2s;
    background: #f9fafb;
    height: 46px;
    box-sizing: border-box;
  }

  .chat-input:focus {
    border-color: #0d9488;
    background: white;
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
  }

  .chat-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .send-button {
    width: 46px;
    height: 46px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
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
    border-top-color: #0d9488;
    border-radius: 50%;
    animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
  }

  .spinner-ring:nth-child(2) {
    border-top-color: #14b8a6;
    animation-delay: -0.4s;
  }

  .spinner-ring:nth-child(3) {
    border-top-color: #0d9488;
    animation-delay: -0.8s;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .loading-text {
    font-size: 12px;
    color: #0d9488;
    font-weight: 600;
  }

  /* 最小化状态 */
  .window-content.minimized-content {
    display: none;
  }
</style>
