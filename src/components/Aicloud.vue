<template>
  <Modal :visible="visible" title="AI 云助手" size="xl" @close="$emit('close')">
    <div class="aicloud">
      <div class="welcome-section">
        <div class="welcome-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
        </div>
        <div class="welcome-text">
          <h3>AI 云助手</h3>
          <p>安全的 AI 助手，10 天记忆持久化，所有操作均有审计日志。</p>
        </div>
      </div>

      <div class="tab-bar">
        <button :class="['tab-btn', { active: activeTab === 'chat' }]" @click="activeTab = 'chat'">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          对话
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'knowledge' }]"
          @click="activeTab = 'knowledge'"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          知识库
        </button>
      </div>

      <div v-if="activeTab === 'chat'">
        <div class="memory-status">
          <div class="status-item">
            <span class="status-label">会话记忆:</span>
            <span class="status-value">{{ memoryDays }} 天</span>
          </div>
          <div class="status-item">
            <span class="status-label">消息数量:</span>
            <span class="status-value">{{ messageCount }} 条</span>
          </div>
          <div class="status-item">
            <span class="status-label">审查状态:</span>
            <span class="status-value" :class="reviewEnabled ? 'enabled' : 'disabled'">
              {{ reviewEnabled ? '人工审查开启' : '人工审查关闭' }}
            </span>
          </div>
        </div>

        <div class="chat-section">
          <div ref="messagesContainer" class="chat-messages">
            <div v-if="messages.length === 0" class="empty-messages">
              <p>开始对话吧！AI 云助手会记住 10 天内的所有对话。</p>
            </div>
            <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
              <div class="message-avatar">
                <span v-if="msg.role === 'user'">[USER]</span>
                <span v-else>🤖</span>
              </div>
              <div class="message-content">
                <div class="message-header">
                  <span class="sender">{{ msg.role === 'user' ? '你' : 'AI 助手' }}</span>
                  <span class="time">{{ formatTime(msg.created_at) }}</span>
                </div>
                <div class="message-text">{{ msg.content }}</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="pendingReview" class="review-notice">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>您有待审查的内容，请前往审查队列查看。</span>
        </div>

        <div class="input-section">
          <div class="model-selector">
            <label>模型:</label>
            <select v-model="selectedModel" class="model-select">
              <option v-for="model in availableModels" :key="model.id" :value="model.id">
                {{ model.name }}{{ model.is_default ? ' (默认)' : '' }}
              </option>
            </select>
          </div>
          <textarea
            v-model="inputMessage"
            class="message-input"
            placeholder="输入消息... (Ctrl+Enter 发送)"
            rows="3"
            :disabled="isSending"
            @keydown.enter.ctrl="sendMessage"
          ></textarea>
          <div class="input-actions">
            <Button variant="secondary" size="sm" @click="toggleReview">
              {{ reviewEnabled ? '关闭人工审查' : '开启人工审查' }}
            </Button>
            <Button variant="ghost" size="sm" @click="newSession"> 新会话 </Button>
            <Button
              variant="primary"
              :loading="isSending"
              :disabled="!inputMessage.trim() || isSending"
              @click="sendMessage"
            >
              {{ isSending ? 'AI 思考中...' : '发送' }}
            </Button>
          </div>
        </div>

        <div class="history-actions">
          <Button variant="ghost" size="sm" @click="showHistory = !showHistory">
            {{ showHistory ? '隐藏历史' : '查看历史' }}
          </Button>
          <Button variant="ghost" size="sm" @click="exportHistory"> 导出对话 </Button>
        </div>

        <div v-if="showHistory" class="history-panel">
          <h4>最近 10 天对话记录</h4>
          <div class="history-list">
            <div v-if="historySessions.length === 0" class="empty-history">暂无历史记录</div>
            <div
              v-for="session in historySessions"
              :key="session.id"
              class="history-session"
              @click="loadSession(session)"
            >
              <div class="session-info">
                <span class="session-preview">{{ getSessionPreview(session) }}</span>
                <span class="session-time">{{ formatTime(session.last_active_at) }}</span>
              </div>
              <span class="session-count">{{ session.messages?.length || 0 }} 条消息</span>
            </div>
          </div>
        </div>

        <div class="code-execution-section">
          <div class="section-header" @click="showCodeExec = !showCodeExec">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"></polyline>
              <polyline points="8 6 2 12 8 18"></polyline>
            </svg>
            <span>代码执行沙箱</span>
            <span class="toggle-icon">{{ showCodeExec ? '▼' : '▶' }}</span>
          </div>

          <div v-if="showCodeExec" class="code-execution-panel">
            <div class="code-input-area">
              <select v-model="codeLanguage" class="lang-select">
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="go">Go</option>
              </select>
              <textarea
                v-model="codeInput"
                class="code-input"
                placeholder="输入代码..."
                rows="6"
                spellcheck="false"
              ></textarea>
              <Button
                variant="secondary"
                size="sm"
                :loading="isExecuting"
                :disabled="!codeInput.trim()"
                @click="runCode"
              >
                {{ isExecuting ? '执行中...' : '运行代码' }}
              </Button>
            </div>

            <div v-if="codeOutput" class="code-output" :class="{ 'has-error': codeError }">
              <div class="output-header">
                <span>输出结果</span>
                <span class="exec-time">{{ executionTime }}s</span>
              </div>
              <pre class="output-content">{{ codeOutput }}</pre>
              <pre v-if="codeError" class="error-content">{{ codeError }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- 知识库标签页 -->
      <div v-if="activeTab === 'knowledge'" class="knowledge-panel">
        <div class="knowledge-header">
          <h3>知识库管理</h3>
          <Button variant="primary" size="sm" @click="showUploadModal = true">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              style="width: 14px; height: 14px; margin-right: 4px"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            上传文档
          </Button>
        </div>

        <div v-if="showUploadModal" class="knowledge-upload-area">
          <div class="upload-dropzone" @dragover.prevent @drop.prevent="handleFileDrop">
            <input
              ref="fileInput"
              type="file"
              accept=".txt,.md,.pdf,.docx,.py,.js,.ts,.json,.yaml,.yml,.csv,.log"
              style="display: none"
              @change="handleFileSelect"
            />
            <button class="upload-btn" @click="$refs.fileInput.click()">选择文件</button>
            <p>支持 TXT, MD, PDF, DOCX, PY, JS, JSON, YAML, CSV, LOG</p>
          </div>
          <div v-if="uploadingFile" class="upload-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <span>上传中... {{ uploadProgress }}%</span>
          </div>
        </div>

        <div class="knowledge-docs-list">
          <h4>已上传文档</h4>
          <div v-if="knowledgeDocs.length === 0" class="empty-docs">
            暂无文档，请上传文件到知识库
          </div>
          <div v-for="doc in knowledgeDocs" :key="doc.id" class="doc-item">
            <div class="doc-info">
              <span class="doc-name">{{ doc.filename }}</span>
              <span class="doc-meta"
                >{{ doc.chunk_count }} 块 | {{ formatTime(doc.created_at) }}</span
              >
            </div>
            <div class="doc-status" :class="doc.status">{{ doc.status }}</div>
            <button class="doc-delete" @click="deleteDoc(doc.id)">×</button>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup>
  import { ref, computed, watch, nextTick, onMounted } from 'vue'
  import Modal from './ui/Modal.vue'
  import Button from './ui/Button.vue'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close'])

  const activeTab = ref('chat')
  const inputMessage = ref('')
  const messages = ref([])
  const historySessions = ref([])
  const isSending = ref(false)
  const showHistory = ref(false)
  const reviewEnabled = ref(true)
  const pendingReview = ref(false)
  const messagesContainer = ref(null)
  const currentSessionId = ref(null)
  const selectedModel = ref('')
  const availableModels = ref([])
  const showCodeExec = ref(false)
  const codeLanguage = ref('python')
  const codeInput = ref('')
  const codeOutput = ref('')
  const codeError = ref('')
  const executionTime = ref(0)
  const isExecuting = ref(false)

  // 知识库相关
  const showUploadModal = ref(false)
  const uploadingFile = ref(false)
  const uploadProgress = ref(0)
  const knowledgeDocs = ref([])
  const fileInput = ref(null)

  const loadKnowledgeDocs = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/aicloud/knowledge/docs', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (response.ok) {
        knowledgeDocs.value = await response.json()
      }
    } catch (error) {
      console.error('加载知识库文档失败:', error)
    }
  }

  const handleFileSelect = async event => {
    const file = event.target.files[0]
    if (!file) return
    await uploadFile(file)
  }

  const handleFileDrop = async event => {
    const file = event.dataTransfer.files[0]
    if (!file) return
    await uploadFile(file)
  }

  const uploadFile = async file => {
    uploadingFile.value = true
    uploadProgress.value = 0

    const formData = new FormData()
    formData.append('file', file)

    try {
      const token = localStorage.getItem('access_token')
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/v1/aicloud/knowledge/upload')
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      }

      xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
          uploadProgress.value = Math.round((e.loaded / e.total) * 100)
        }
      }

      xhr.onload = () => {
        uploadingFile.value = false
        if (xhr.status === 200) {
          const result = JSON.parse(xhr.responseText)
          alert(`上传成功：${result.message}`)
          loadKnowledgeDocs()
          showUploadModal.value = false
        } else {
          alert('上传失败')
        }
      }

      xhr.onerror = () => {
        uploadingFile.value = false
        alert('上传请求失败')
      }

      xhr.send(formData)
    } catch (error) {
      uploadingFile.value = false
      console.error('上传失败:', error)
    }
  }
      }

      xhr.onload = () => {
        uploadingFile.value = false
        if (xhr.status === 200) {
          const result = JSON.parse(xhr.responseText)
          alert(`上传成功: ${result.message}`)
          loadKnowledgeDocs()
          showUploadModal.value = false
        } else {
          alert('上传失败')
        }
      }

      xhr.onerror = () => {
        uploadingFile.value = false
        alert('上传请求失败')
      }

      xhr.send(formData)
    } catch (error) {
      uploadingFile.value = false
      console.error('上传失败:', error)
    }
  }

  const deleteDoc = async docId => {
    if (!confirm('确定要删除此文档吗？')) return

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/api/v1/aicloud/knowledge/docs/${docId}`, {
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (response.ok) {
        await loadKnowledgeDocs()
      }
    } catch (error) {
      console.error('删除文档失败:', error)
    }
  }

  const runCode = async () => {
    if (!codeInput.value.trim() || isExecuting.value) return
    isExecuting.value = true
    codeOutput.value = ''
    codeError.value = ''

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/aicloud/execute', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          code: codeInput.value,
          language: codeLanguage.value
        })
      })

      const data = await response.json()
      executionTime.value = data.execution_time?.toFixed(2) || 0

      if (data.success) {
        codeOutput.value = data.output || '(无输出)'
      } else {
        codeError.value = data.error || '执行失败'
      }
    } catch (error) {
      codeError.value = `请求失败：${error.message}`
    } finally {
      isExecuting.value = false
    }
  }
    } catch (error) {
      codeError.value = `请求失败: ${error.message}`
    } finally {
      isExecuting.value = false
    }
  }

  const loadModels = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/aicloud/models', {
        method: 'GET',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })
      if (response.ok) {
        const data = await response.json()
        availableModels.value = data.models || []
        selectedModel.value = data.default_model || data.models?.[0]?.id
      }
    } catch (error) {
      console.error('加载模型列表失败:', error)
    }
  }

  const memoryDays = computed(() => 10)
  const messageCount = computed(() => messages.value.length)

  const getSessionId = () => {
    let sessionId = localStorage.getItem('aicloud_session_id')
    if (!sessionId) {
      sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2)
      localStorage.setItem('aicloud_session_id', sessionId)
    }
    return sessionId
  }

  const loadCurrentSession = async () => {
    const sessionId = getSessionId()
    currentSessionId.value = sessionId

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/api/v1/aicloud/history?days=10`, {
        method: 'GET',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })

      if (response.ok) {
        const sessions = await response.json()
        historySessions.value = sessions || []

        const currentSession = sessions?.find(s => s.id === sessionId)
        if (currentSession?.messages) {
          messages.value = currentSession.messages.map(msg => ({
            role: msg.role,
            content: msg.content,
            created_at: msg.created_at
          }))
        } else {
          messages.value = []
        }
      }
    } catch (error) {
      console.error('加载会话失败:', error)
      messages.value = []
    }
  }

  const loadHistory = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`/api/v1/aicloud/history?days=10`, {
        method: 'GET',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })

      if (response.ok) {
        const data = await response.json()
        historySessions.value = data || []
      }
    } catch (error) {
      console.error('加载历史失败:', error)
    }
  }

  const loadSession = session => {
    if (session.messages) {
      messages.value = session.messages.map(msg => ({
        role: msg.role,
        content: msg.content,
        created_at: msg.created_at
      }))
      localStorage.setItem('aicloud_session_id', session.id)
      currentSessionId.value = session.id
    }
    showHistory.value = false
  }

  const sendMessage = async () => {
    if (!inputMessage.value.trim() || isSending.value) return

    const userMessage = {
      role: 'user',
      content: inputMessage.value,
      created_at: new Date().toISOString()
    }

    messages.value.push(userMessage)
    inputMessage.value = ''
    isSending.value = true
    scrollToBottom()

    const aiMessageIndex = messages.value.length
    messages.value.push({
      role: 'assistant',
      content: 'AI 正在输入...',
      created_at: new Date().toISOString()
    })

    const sessionId = getSessionId()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/aicloud/chat/stream', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({
          message: userMessage.content,
          session_id: sessionId,
          model_id: selectedModel.value
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      let fullContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6)
              const data = JSON.parse(jsonStr)

              if (data.error) {
                throw new Error(data.error)
              }
              if (data.done) {
                currentSessionId.value = data.session_id
                localStorage.setItem('aicloud_session_id', data.session_id)
                await loadHistory()
                break
              }
              if (data.delta) {
                fullContent += data.delta
                messages.value[aiMessageIndex].content = fullContent
                scrollToBottom()
              }
            } catch (e) {
              if (!e.message.includes('Unexpected')) console.error('解析流数据失败:', e)
            }
          }
        }
      }

      if (!fullContent) {
        messages.value[aiMessageIndex].content = '抱歉，没有收到回复'
      }
    } catch (error) {
      console.error('发送消息失败:', error)
      messages.value[aiMessageIndex].content = `错误: ${error.message}`
    } finally {
      isSending.value = false
      scrollToBottom()
    }
  }

  const loadPendingReviews = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch('/api/v1/aicloud/reviews', {
        method: 'GET',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })

      if (response.ok) {
        const reviews = await response.json()
        pendingReview.value = Array.isArray(reviews) && reviews.length > 0
      }
    } catch (error) {
      console.error('检查待审查项失败:', error)
    }
  }

  const toggleReview = () => {
    reviewEnabled.value = !reviewEnabled.value
  }

  const newSession = () => {
    const newId = 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2)
    localStorage.setItem('aicloud_session_id', newId)
    currentSessionId.value = newId
    messages.value = []
  }

  const exportHistory = () => {
    const data = {
      session_id: currentSessionId.value,
      exported_at: new Date().toISOString(),
      messages: messages.value
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aicloud_history_${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const scrollToBottom = () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }

  const formatTime = timeString => {
    if (!timeString) return ''
    const date = new Date(timeString)
    return date.toLocaleString()
  }

  const getSessionPreview = session => {
    if (!session.messages || session.messages.length === 0) {
      return '新会话'
    }
    const lastMsg = session.messages[session.messages.length - 1]
    const content = lastMsg.content || ''
    return content.slice(0, 30) + (content.length > 30 ? '...' : '')
  }

  watch(
    () => props.visible,
    newVal => {
      if (newVal) {
        loadCurrentSession()
        loadPendingReviews()
        loadModels()
        loadKnowledgeDocs()
      }
    }
  )

  watch(activeTab, newTab => {
    if (newTab === 'knowledge') {
      loadKnowledgeDocs()
    }
  })

  watch(
    messages,
    () => {
      scrollToBottom()
    },
    { deep: true }
  )
</script>

<style scoped>
  .aicloud {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 70vh;
    max-height: 70vh;
  }

  .welcome-section {
    display: flex;
    gap: 12px;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .welcome-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--primary-color);
    border-radius: 8px;
    color: white;
  }

  .welcome-icon svg {
    width: 24px;
    height: 24px;
  }

  .welcome-text h3 {
    margin: 0;
    font-size: 16px;
    color: var(--text-primary);
  }

  .welcome-text p {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .memory-status {
    display: flex;
    gap: 16px;
    padding: 8px 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    font-size: 13px;
  }

  .status-item {
    display: flex;
    gap: 6px;
  }

  .status-label {
    color: var(--text-secondary);
  }

  .status-value {
    color: var(--text-primary);
    font-weight: 500;
  }

  .status-value.enabled {
    color: var(--success-color);
  }

  .status-value.disabled {
    color: var(--warning-color);
  }

  .chat-section {
    flex: 1;
    overflow: hidden;
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }

  .chat-messages {
    height: 100%;
    overflow-y: auto;
    padding: 12px;
  }

  .empty-messages {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
  }

  .message {
    display: flex;
    gap: 10px;
    margin-bottom: 12px;
  }

  .message.user {
    flex-direction: row-reverse;
  }

  .message-avatar {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-secondary);
    border-radius: 50%;
    font-size: 16px;
  }

  .message-content {
    max-width: 80%;
  }

  .message-header {
    display: flex;
    gap: 8px;
    margin-bottom: 4px;
    font-size: 12px;
  }

  .message.user .message-header {
    flex-direction: row-reverse;
  }

  .sender {
    font-weight: 500;
    color: var(--text-primary);
  }

  .time {
    color: var(--text-secondary);
  }

  .message-text {
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .message.user .message-text {
    background: var(--primary-color);
    color: white;
  }

  .message.assistant .message-text {
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .review-notice {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgba(255, 193, 7, 0.1);
    border: 1px solid var(--warning-color);
    border-radius: 6px;
    font-size: 13px;
    color: var(--warning-color);
  }

  .review-notice svg {
    width: 18px;
    height: 18px;
  }

  .input-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .model-selector {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .model-select {
    flex: 1;
    max-width: 250px;
    padding: 6px 10px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    cursor: pointer;
  }

  .model-select:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .message-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: 14px;
    resize: none;
    background: var(--bg-primary);
    color: var(--text-primary);
  }

  .message-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .message-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .input-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .history-actions {
    display: flex;
    gap: 8px;
  }

  .history-panel {
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .history-panel h4 {
    margin: 0 0 12px;
    font-size: 14px;
    color: var(--text-primary);
  }

  .history-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 200px;
    overflow-y: auto;
  }

  .empty-history {
    padding: 20px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 13px;
  }

  .history-session {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px;
    background: var(--bg-primary);
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }

  .history-session:hover {
    background: var(--bg-tertiary);
  }

  .session-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .session-preview {
    color: var(--text-primary);
  }

  .session-time {
    color: var(--text-secondary);
    font-size: 11px;
  }

  .session-count {
    color: var(--text-secondary);
    font-size: 11px;
  }

  .code-execution-section {
    margin-top: 12px;
    border-top: 1px solid var(--border-color);
    padding-top: 12px;
  }

  .section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    padding: 8px 0;
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .section-header svg {
    width: 18px;
    height: 18px;
  }

  .toggle-icon {
    margin-left: auto;
    font-size: 10px;
    color: var(--text-secondary);
  }

  .code-execution-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 8px;
  }

  .code-input-area {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .lang-select {
    padding: 6px 10px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    max-width: 120px;
  }

  .code-input {
    width: 100%;
    padding: 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-family: monospace;
    font-size: 13px;
    background: var(--bg-primary);
    color: var(--text-primary);
    resize: vertical;
  }

  .code-input:focus {
    outline: none;
    border-color: var(--primary-color);
  }

  .code-output {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    overflow: hidden;
  }

  .code-output.has-error {
    border-color: var(--error-color, #ef4444);
  }

  .output-header {
    display: flex;
    justify-content: space-between;
    padding: 8px 12px;
    background: var(--bg-tertiary);
    font-size: 12px;
    color: var(--text-secondary);
  }

  .output-content,
  .error-content {
    padding: 10px 12px;
    margin: 0;
    font-family: monospace;
    font-size: 13px;
    white-space: pre-wrap;
    max-height: 200px;
    overflow-y: auto;
  }

  .error-content {
    color: var(--error-color, #ef4444);
    border-top: 1px solid var(--border-color);
  }

  .tab-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
  }

  .tab-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
  }

  .tab-btn svg {
    width: 16px;
    height: 16px;
  }

  .tab-btn:hover {
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .tab-btn.active {
    background: var(--primary-color);
    border-color: var(--primary-color);
    color: white;
  }

  .knowledge-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 60vh;
    overflow-y: auto;
  }

  .knowledge-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .knowledge-header h3 {
    margin: 0;
    font-size: 16px;
  }

  .knowledge-upload-area {
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: 8px;
  }

  .upload-dropzone {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 32px;
    border: 2px dashed var(--border-color);
    border-radius: 8px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 13px;
  }

  .upload-btn {
    padding: 8px 20px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
  }

  .upload-progress {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
  }

  .progress-bar {
    width: 100%;
    height: 6px;
    background: var(--bg-tertiary);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--primary-color);
    transition: width 0.3s;
  }

  .knowledge-docs-list h4 {
    margin: 0 0 12px;
    font-size: 14px;
  }

  .empty-docs {
    padding: 32px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 13px;
  }

  .doc-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    margin-bottom: 8px;
  }

  .doc-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .doc-name {
    font-size: 14px;
    font-weight: 500;
  }

  .doc-meta {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .doc-status {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    text-transform: capitalize;
  }

  .doc-status.completed {
    background: rgba(34, 197, 94, 0.1);
    color: #22c55e;
  }

  .doc-status.processing {
    background: rgba(234, 179, 8, 0.1);
    color: #eab308;
  }

  .doc-status.failed {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }

  .doc-delete {
    width: 24px;
    height: 24px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 18px;
    border-radius: 4px;
  }

  .doc-delete:hover {
    background: rgba(239, 68, 68, 0.1);
    color: #ef4444;
  }
</style>
