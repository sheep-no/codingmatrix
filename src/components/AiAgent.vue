<template>
  <div class="agent-container">
    <!-- 左侧栏：会话列表 + 快速操作 -->
    <aside class="agent-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <h3 v-show="!sidebarCollapsed">AI Agent</h3>
        <button class="btn-icon-sm" @click="sidebarCollapsed = !sidebarCollapsed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line v-if="sidebarCollapsed" x1="3" y1="6" x2="21" y2="6"/>
            <line v-if="sidebarCollapsed" x1="3" y1="12" x2="21" y2="12"/>
            <line v-if="sidebarCollapsed" x1="3" y1="18" x2="21" y2="18"/>
            <polyline v-else points="11 17 6 12 11 7"/>
            <polyline points="18 17 13 12 18 7"/>
          </svg>
        </button>
      </div>

      <AgentSessionSidebar
        v-show="!sidebarCollapsed"
        :sessions="sessions"
        :active-id="activeSessionId"
        @create="createSession"
        @select="selectSession"
        @delete="deleteSession"
      />
    </aside>

    <!-- 主内容区 -->
    <main class="agent-main">
      <!-- 标签栏 -->
      <div class="agent-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="tab.icon" />
          <span>{{ tab.label }}</span>
        </button>
      </div>

      <!-- 聊天面板 -->
      <div v-show="activeTab === 'chat'" class="panel-chat">
        <div class="chat-messages" ref="messagesContainer">
          <div v-if="messages.length === 0" class="chat-empty">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <h3>开始对话</h3>
            <p>描述您的需求，我将协助您完成项目开发</p>
          </div>

          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            :class="['message', msg.role]"
          >
            <div class="message-avatar">
              <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div class="message-content">
              <div class="message-text" v-html="renderMessage(msg)"></div>
            </div>
          </div>

          <div v-if="loading" class="message assistant">
            <div class="message-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div class="message-content">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <AgentReActSteps
            v-if="reactSteps.length > 0"
            :steps="reactSteps"
            :collapsed="!showReasoning"
            @toggle="showReasoning = !showReasoning"
          />
          <div class="input-wrapper">
            <textarea
              ref="inputRef"
              v-model="userInput"
              class="chat-input"
              placeholder="输入消息... (Ctrl+Enter 发送)"
              rows="1"
              @keydown.ctrl.enter="sendMessage"
              @keydown.enter.exact.prevent="handleEnter"
            />
            <div class="input-actions">
              <select v-model="selectedModel" class="model-select">
                <option value="">自动选择</option>
                <option v-for="m in models" :key="m.key" :value="m.key">{{ m.name }}</option>
              </select>
              <button :disabled="!userInput.trim() || loading" class="btn-send" @click="sendMessage">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 工作流面板 -->
      <div v-show="activeTab === 'workflow'" class="panel-workflow">
        <AgentWorkflowPanel />
      </div>

      <!-- 文件面板 -->
      <div v-show="activeTab === 'files'" class="panel-files">
        <AgentFileTree
          :files="projectFiles"
          :selected="selectedFile"
          @select="selectFile"
          @delete="deleteFile"
          @upload="uploadFile"
        />
        <AgentCodeViewer
          v-if="selectedFileContent"
          :filename="selectedFile.name"
          :content="selectedFileContent"
          :size="selectedFile.size"
          :editable="true"
          @edit="editFile"
        />
      </div>

      <!-- 预览面板 -->
      <div v-show="activeTab === 'preview'" class="panel-preview">
        <AgentProjectPreview
          :url="previewUrl"
          @startPreview="startPreview"
        />
      </div>

      <!-- 知识库面板 -->
      <div v-show="activeTab === 'knowledge'" class="panel-knowledge">
        <AgentKnowledgePanel
          :items="knowledgeItems"
          @add="addKnowledge"
          @delete="deleteKnowledge"
          @refresh="loadKnowledge"
        />
      </div>

      <!-- 项目管理面板 -->
      <div v-show="activeTab === 'project'" class="panel-project">
        <AgentProjectActions
          :saved-projects="savedProjects"
          :uploaded-projects="uploadedProjects"
          @load="loadProject"
          @deleteProject="deleteProject"
          @save="saveProject"
          @analyzeComplexity="analyzeComplexity"
          @orchestrate="startOrchestration"
          @downloadProject="downloadProject"
          @uploadZip="handleUploadZip"
          @loadUploaded="loadUploadedProject"
          @deleteUploaded="deleteUploadedProject"
          @refreshUploads="loadUploadedProjects"
        />
      </div>

      <!-- 统计面板 -->
      <div v-show="activeTab === 'stats'" class="panel-stats">
        <AgentStatsPanel
          :stats="modelStats"
          @refresh="loadStats"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
  import { ref, computed, nextTick, onMounted } from 'vue'
  import AgentSessionSidebar from './AgentSessionSidebar.vue'
  import AgentReActSteps from './AgentReActSteps.vue'
  import AgentFileTree from './AgentFileTree.vue'
  import AgentCodeViewer from './AgentCodeViewer.vue'
  import AgentProjectPreview from './AgentProjectPreview.vue'
  import AgentKnowledgePanel from './AgentKnowledgePanel.vue'
  import AgentProjectActions from './AgentProjectActions.vue'
  import AgentStatsPanel from './AgentStatsPanel.vue'
  import AgentWorkflowPanel from './AgentWorkflowPanel.vue'
  import { useMarkdown } from '../composables/useMarkdown'
  import { useAgentSSE } from '../composables/useAgentSSE'

  const { render } = useMarkdown()
  const { stream, abort } = useAgentSSE()

  const sidebarCollapsed = ref(false)
  const activeTab = ref('chat')
  const activeSessionId = ref(null)
  const userInput = ref('')
  const selectedModel = ref('')
  const loading = ref(false)
  const showReasoning = ref(false)
  const selectedFile = ref(null)
  const previewUrl = ref('')
  const messagesContainer = ref(null)
  const inputRef = ref(null)

  const tabs = [
    { key: 'chat', label: '对话', icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
    { key: 'workflow', label: '工作流', icon: '<circle cx="5" cy="6" r="3"/><circle cx="19" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><line x1="8" y1="7" x2="16" y2="7"/><line x1="6" y1="8" x2="10" y2="16"/><line x1="18" y1="8" x2="14" y2="16"/>' },
    { key: 'files', label: '文件', icon: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>' },
    { key: 'preview', label: '预览', icon: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>' },
    { key: 'knowledge', label: '知识', icon: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>' },
    { key: 'project', label: '项目', icon: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>' },
    { key: 'stats', label: '统计', icon: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>' }
  ]

  const sessions = ref([])
  const messages = ref([])
  const reactSteps = ref([])
  const projectFiles = ref([])
  const selectedFileContent = ref('')
  const knowledgeItems = ref([])
  const savedProjects = ref([])
  const uploadedProjects = ref([])
  const modelStats = ref([])
  const models = ref([])

  function renderMessage(msg) {
    if (msg.role === 'user') return escapeHtml(msg.content)
    return render(msg.content)
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }

  function scrollToBottom() {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }

  function handleEnter(e) {
    if (e.isComposing) return
    sendMessage()
  }

  async function sendMessage() {
    if (!userInput.value.trim() || loading.value) return
    const content = userInput.value.trim()
    userInput.value = ''
    messages.value.push({ role: 'user', content })
    loading.value = true
    scrollToBottom()

    const assistantMsg = { role: 'assistant', content: '' }
    messages.value.push(assistantMsg)
    reactSteps.value = []

    try {
      await stream({
        message: content,
        session_id: activeSessionId.value,
        model: selectedModel.value || undefined,
        onContent: (chunk) => {
          assistantMsg.content += chunk
          scrollToBottom()
        },
        onStep: (step) => {
          reactSteps.value.push(step)
        },
        onDone: (data) => {
          loading.value = false
          if (data?.session_id) activeSessionId.value = data.session_id
        },
        onError: (err) => {
          assistantMsg.content += '\n\n[错误] ' + (err.message || '请求失败')
          loading.value = false
        }
      })
    } catch (e) {
      assistantMsg.content += '\n\n[错误] ' + e.message
      loading.value = false
    }
  }

  async function createSession(name) {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/sessions', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ name: name || '新会话' })
      })
      const data = await res.json()
      sessions.value.unshift(data)
      activeSessionId.value = data.id
      messages.value = []
      reactSteps.value = []
    } catch (e) {
      console.error('Create session failed:', e)
    }
  }

  async function selectSession(id) {
    activeSessionId.value = id
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/sessions/${id}/messages`, {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      const data = await res.json()
      messages.value = data.messages || []
    } catch (e) {
      console.error('Load messages failed:', e)
    }
  }

  async function deleteSession(id) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch(`/api/v1/agent/sessions/${id}`, { 
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      sessions.value = sessions.value.filter(s => s.id !== id)
      if (activeSessionId.value === id) {
        activeSessionId.value = null
        messages.value = []
      }
    } catch (e) {
      console.error('Delete session failed:', e)
    }
  }

  async function selectFile(file) {
    selectedFile.value = file
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/files/${encodeURIComponent(file.path)}`, {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      selectedFileContent.value = await res.text()
    } catch (e) {
      selectedFileContent.value = '// 无法读取文件内容'
    }
  }

  async function deleteFile(path) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch(`/api/v1/agent/files/${encodeURIComponent(path)}`, { 
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      projectFiles.value = projectFiles.value.filter(f => f.path !== path)
      if (selectedFile.value?.path === path) {
        selectedFile.value = null
        selectedFileContent.value = ''
      }
    } catch (e) {
      console.error('Delete file failed:', e)
    }
  }

  async function uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const token = localStorage.getItem('access_token')
      await fetch('/api/v1/agent/files/upload', { 
        method: 'POST', 
        body: formData,
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      loadFiles()
    } catch (e) {
      console.error('Upload failed:', e)
    }
  }

  async function loadFiles() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/files', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      projectFiles.value = await res.json()
    } catch (e) {
      console.error('Load files failed:', e)
    }
  }

  function editFile() {
    console.log('Edit file:', selectedFile.value?.path)
  }

  async function startPreview() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/preview/start', { 
        method: 'POST',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      const data = await res.json()
      previewUrl.value = data.url
    } catch (e) {
      console.error('Start preview failed:', e)
    }
  }

  async function addKnowledge(data) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch('/api/v1/agent/knowledge', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify(data)
      })
      loadKnowledge()
    } catch (e) {
      console.error('Add knowledge failed:', e)
    }
  }

  async function deleteKnowledge(id) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch(`/api/v1/agent/knowledge/${id}`, { 
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      knowledgeItems.value = knowledgeItems.value.filter(k => k.id !== id)
    } catch (e) {
      console.error('Delete knowledge failed:', e)
    }
  }

  async function loadKnowledge() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/knowledge', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      knowledgeItems.value = await res.json()
    } catch (e) {
      console.error('Load knowledge failed:', e)
    }
  }

  async function saveProject(name) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch('/api/v1/agent/projects', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ name })
      })
      loadSavedProjects()
    } catch (e) {
      console.error('Save project failed:', e)
    }
  }

  async function loadProject(id) {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/projects/${id}/load`, { 
        method: 'POST',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      const data = await res.json()
      if (data.files) projectFiles.value = data.files
    } catch (e) {
      console.error('Load project failed:', e)
    }
  }

  async function deleteProject(id) {
    try {
      const token = localStorage.getItem('access_token')
      await fetch(`/api/v1/agent/projects/${id}`, { 
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      savedProjects.value = savedProjects.value.filter(p => p.id !== id)
    } catch (e) {
      console.error('Delete project failed:', e)
    }
  }

  async function loadSavedProjects() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/projects', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      savedProjects.value = await res.json()
    } catch (e) {
      console.error('Load projects failed:', e)
    }
  }

  async function analyzeComplexity() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/analysis/complexity', { 
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })
      const data = await res.json()
      messages.value.push({ role: 'assistant', content: `## 复杂度分析\n\n${data.report || '分析完成'}` })
      scrollToBottom()
    } catch (e) {
      console.error('Analyze complexity failed:', e)
    }
  }

  async function startOrchestration() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/orchestrate', { 
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      })
      const data = await res.json()
      messages.value.push({ role: 'assistant', content: `## 项目编排\n\n${data.plan || '编排完成'}` })
      scrollToBottom()
    } catch (e) {
      console.error('Orchestration failed:', e)
    }
  }

  async function downloadProject() {
    try {
      window.open('/api/v1/agent/projects/download', '_blank')
    } catch (e) {
      console.error('Download failed:', e)
    }
  }

  // ==================== 用户上传项目管理 ====================

  async function handleUploadZip(file, callbacks) {
    const token = localStorage.getItem('access_token')
    const formData = new FormData()
    formData.append('file', file)

    callbacks.onProgress(20)

    try {
      const res = await fetch('/api/v1/agent/projects/upload-zip', {
        method: 'POST',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' },
        body: formData
      })

      callbacks.onProgress(80)

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        callbacks.onError(errData.detail || `上传失败 (${res.status})`)
        return
      }

      const data = await res.json()
      callbacks.onProgress(100)
      callbacks.onSuccess(data.message || '上传成功')
      await loadUploadedProjects()
    } catch (e) {
      callbacks.onError('网络错误，上传失败')
    }
  }

  async function loadUploadedProjects() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/projects/user-uploads', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (res.ok) {
        uploadedProjects.value = await res.json()
      }
    } catch (e) {
      console.error('Load uploaded projects failed:', e)
    }
  }

  async function loadUploadedProject(projectPath) {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/generate/files?project_path=${encodeURIComponent(projectPath)}`, {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (res.ok) {
        const data = await res.json()
        projectFiles.value = data.files || []
        activeTab.value = 'files'
      }
    } catch (e) {
      console.error('Load uploaded project failed:', e)
    }
  }

  async function deleteUploadedProject(projectName) {
    if (!confirm(`确定要删除项目 "${projectName}" 吗？`)) return
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(`/api/v1/agent/projects/user-uploads/${encodeURIComponent(projectName)}`, {
        method: 'DELETE',
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      if (res.ok) {
        await loadUploadedProjects()
      }
    } catch (e) {
      console.error('Delete uploaded project failed:', e)
    }
  }

  async function loadStats() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/stats', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      modelStats.value = await res.json()
    } catch (e) {
      console.error('Load stats failed:', e)
    }
  }

  async function loadModels() {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch('/api/v1/agent/models', {
        headers: { 'Authorization': token ? `Bearer ${token}` : '' }
      })
      models.value = await res.json()
    } catch (e) {
      console.error('Load models failed:', e)
    }
  }

  onMounted(() => {
    loadFiles()
    loadKnowledge()
    loadSavedProjects()
    loadUploadedProjects()
    loadStats()
    loadModels()
  })
</script>

<style scoped>
  .agent-container {
    display: flex;
    height: 100%;
    background: var(--bg-primary, #0f172a);
    color: var(--text-primary, #e0e0e0);
  }

  .agent-sidebar {
    width: 260px;
    border-right: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    display: flex;
    flex-direction: column;
    transition: width 0.2s;
    flex-shrink: 0;
  }

  .agent-sidebar.collapsed { width: 48px; }

  .sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
  }

  .sidebar-header h3 { margin: 0; font-size: 16px; white-space: nowrap; }

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
    flex-shrink: 0;
  }

  .btn-icon-sm:hover { background: var(--bg-hover, #374151); }
  .btn-icon-sm svg { width: 16px; height: 16px; }

  .agent-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .agent-tabs {
    display: flex;
    gap: 4px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    overflow-x: auto;
  }

  .tab-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary, #9ca3af);
    cursor: pointer;
    white-space: nowrap;
    font-size: 13px;
  }

  .tab-btn:hover { background: var(--bg-hover, #374151); }
  .tab-btn.active { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }
  .tab-btn svg { width: 16px; height: 16px; }

  .panel-chat {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .chat-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-secondary, #9ca3af);
    text-align: center;
  }

  .empty-icon svg { width: 64px; height: 64px; opacity: 0.3; margin-bottom: 16px; }
  .chat-empty h3 { margin: 0 0 8px; font-size: 18px; color: var(--text-primary, #e0e0e0); }
  .chat-empty p { margin: 0; font-size: 14px; }

  .message {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    max-width: 900px;
  }

  .message.user { margin-left: auto; flex-direction: row-reverse; }

  .message-avatar {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  .assistant .message-avatar { background: var(--accent-muted, #4f46e533); color: var(--accent-color, #4f46e5); }
  .user .message-avatar { background: var(--bg-tertiary, #1f2937); color: var(--text-secondary, #9ca3af); }
  .message-avatar svg { width: 18px; height: 18px; }

  .message-content { flex: 1; min-width: 0; }

  .message-text {
    font-size: 14px;
    line-height: 1.7;
    padding: 12px 16px;
    border-radius: 12px;
  }

  .assistant .message-text { background: var(--bg-secondary, #16213e); }
  .user .message-text { background: var(--accent-color, #4f46e5); color: white; }

  .typing-indicator {
    display: flex;
    gap: 4px;
    padding: 12px 16px;
  }

  .typing-indicator span {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--text-secondary, #9ca3af);
    animation: typing 1.4s infinite;
  }

  .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
  .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

  @keyframes typing {
    0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
    30% { opacity: 1; transform: scale(1); }
  }

  .chat-input-area {
    border-top: 1px solid var(--border-color, #2d3748);
    padding: 12px 16px;
  }

  .input-wrapper {
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }

  .chat-input {
    flex: 1;
    padding: 12px 16px;
    border-radius: 12px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    color: var(--text-primary, #e0e0e0);
    font-size: 14px;
    resize: none;
    max-height: 120px;
  }

  .chat-input:focus { outline: none; border-color: var(--accent-color, #4f46e5); }

  .input-actions { display: flex; gap: 8px; align-items: flex-end; }

  .model-select {
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-color, #2d3748);
    background: var(--bg-secondary, #16213e);
    color: var(--text-primary, #e0e0e0);
    font-size: 13px;
  }

  .btn-send {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    border: none;
    background: var(--accent-color, #4f46e5);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-send:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-send svg { width: 18px; height: 18px; }

  .panel-files {
    flex: 1;
    display: flex;
    min-height: 0;
  }

  .panel-preview, .panel-knowledge, .panel-project, .panel-stats, .panel-workflow {
    flex: 1;
    min-height: 0;
  }
</style>
