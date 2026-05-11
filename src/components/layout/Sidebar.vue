<template>
  <aside
    id="leftlist"
    :class="['sidebar', { collapsed: isCollapsed }]"
    role="navigation"
    aria-label="主导航"
  >
    <!-- Logo 区 -->
    <div :class="['sidebar-header', { collapsed: isCollapsed }]">
      <div class="logo-wrapper">
        <img src="../img/logo.jpg" class="logo-image" alt="AI 助手 Logo" />
        <span v-if="!isCollapsed" class="logo-text">AI 助手</span>
      </div>
      <button
        class="collapse-btn"
        :aria-label="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        @click="toggleCollapse"
      >
        <span :class="{ rotated: isCollapsed }">‹</span>
      </button>
    </div>

    <!-- 新建会话 -->
    <button class="btn-new-chat" aria-label="新建会话" @click="newConversation">
      <span class="icon">+</span>
      <span v-if="!isCollapsed">新建会话</span>
    </button>

    <!-- 工具集 -->
    <div class="toolkit-section">
      <button class="btn-toolkit" aria-label="工具集" @click="toggleToolkit">
        <svg
          class="icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
          />
        </svg>
        <span v-if="!isCollapsed">工具集</span>
      </button>

      <!-- 工具菜单 -->
      <Transition name="slide">
        <div v-if="showToolkitMenu" class="toolkit-menu" role="menu">
          <div
            v-for="tool in tools"
            :key="tool.name"
            class="toolkit-item"
            role="menuitem"
            @click="useTool(tool.name)"
          >
            <component :is="tool.icon" v-if="tool.icon" />
            <img v-else-if="tool.image" :src="tool.image" class="tool-image" :alt="tool.label" />
            <span>{{ tool.label }}</span>
          </div>
        </div>
      </Transition>
    </div>

    <!-- 搜索历史 -->
    <Transition name="slide">
      <div v-if="showSearchBox" class="search-box">
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索历史记录..."
          class="search-input"
          aria-label="搜索历史"
          @keyup.enter="handleSearch"
          @keyup.esc="clearSearch"
        />
        <div class="search-actions">
          <Button size="sm" variant="warning" @click="handleSearch">搜索</Button>
          <Button v-if="searchKeyword" size="sm" variant="ghost" @click="clearSearch">清除</Button>
          <Button size="sm" variant="danger" @click="closeSearch">关闭</Button>
        </div>
      </div>
    </Transition>

    <!-- 历史记录 -->
    <section class="history-section" aria-label="历史记录">
      <div class="section-header">
        <h3>历史记录</h3>
      </div>

      <div v-if="isLoading" class="loading-state">加载中...</div>

      <div v-else-if="loadError" class="error-state">
        <p>加载失败：{{ loadError }}</p>
        <Button size="sm" @click="fetchHistory">重试</Button>
      </div>

      <ul v-else-if="historyList.length > 0" class="history-list" role="list">
        <li
          v-for="item in historyList"
          :key="item.id"
          :class="['history-item', { active: item.id === activeId }]"
          role="listitem"
          tabindex="0"
          @click="selectHistory(item)"
          @keyup.enter="selectHistory(item)"
        >
          <svg
            class="history-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span
            class="item-text"
            v-html="highlightText(item.title || item.prompt.slice(0, 30))"
          ></span>
        </li>
      </ul>

      <div v-else class="empty-state">
        {{ userStore.isLoggedIn ? '暂无历史记录' : '登录后查看历史记录' }}
      </div>
    </section>

    <!-- 用户区 -->
    <footer class="user-section">
      <div v-if="!userStore.isLoggedIn" class="login-prompt">
        <Button variant="success" aria-label="登录" @click="showLoginDialog = true">
          <svg
            class="icon-svg-sm"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
          <span v-if="!isCollapsed">登录</span>
        </Button>
      </div>

      <div v-else class="user-info">
        <div class="user-avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <div class="user-details">
          <span class="username">{{ userStore.username }}</span>
          <button class="logout-btn" @click="handleLogout">退出</button>
        </div>
      </div>
    </footer>

    <!-- 登录弹窗 -->
    <Modal
      v-model:visible="showLoginDialog"
      title="用户登录"
      size="sm"
      @close="showLoginDialog = false"
    >
      <div class="login-form">
        <Input
          v-model="loginForm.email"
          type="email"
          placeholder="邮箱"
          label="邮箱"
          :required="true"
        />
        <Input
          v-model="loginForm.password"
          type="password"
          placeholder="密码"
          label="密码"
          :required="true"
          @keyup.enter="handleLogin"
        />
        <p v-if="loginError" class="error-message">{{ loginError }}</p>
      </div>
      <template #footer>
        <Button variant="ghost" @click="showLoginDialog = false">取消</Button>
        <Button variant="primary" :loading="isLoggingIn" @click="handleLogin">
          {{ isLoggingIn ? '登录中...' : '登录' }}
        </Button>
      </template>
    </Modal>
  </aside>
</template>

<script setup>
  import { ref, computed, onMounted } from 'vue'
  import { api } from '@/utils/api/index'
  import { useUserStore } from '@/stores/user'
  import Button from './ui/Button.vue'
  import Modal from './ui/Modal.vue'
  import Input from './ui/Input.vue'

  const emit = defineEmits(['newConversation', 'selectHistory', 'logout', 'useTool'])
  const userStore = useUserStore()

  const isCollapsed = ref(false)
  const activeId = ref(null)
  const showLoginDialog = ref(false)
  const isLoggingIn = ref(false)
  const loginError = ref('')
  const isLoading = ref(false)
  const loadError = ref('')
  const showToolkitMenu = ref(false)
  const showSearchBox = ref(false)
  const searchKeyword = ref('')

  const loginForm = ref({ email: '', password: '' })
  const historyList = ref([])

  // 工具图标组件
  const IconSVG = props =>
    h(
      'svg',
      {
        class: 'tool-icon-svg',
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        'stroke-width': '2'
      },
      h('path', { d: props.d })
    )

  const toolsBase = [
    { name: 'chartEditor', label: '图表编辑器', icon: IconSVG, d: 'M18 20V10M12 20V4M6 20v-6' },
    {
      name: 'nginxConfig',
      label: 'Nginx 配置',
      icon: IconSVG,
      d: 'M12 2a10 10 0 100 20 10 10 0 000-20zM2 12h20M12 2a15 15 0 014 10 15 15 0 01-4 10'
    },
    {
      name: 'dockerConfig',
      label: 'Docker 配置',
      icon: IconSVG,
      d: 'M4 10h16v10H4zM2 14h20M12 2V6M2 6h20M8 17a1 1 0 100-2 1 1 0 000 2zM12 17a1 1 0 100-2 1 1 0 000 2zM16 17a1 1 0 100-2 1 1 0 000 2z'
    },
    { name: 'virtualGirl', label: 'AI 虚拟姬', image: '../img/AiChat.jpeg' },
    {
      name: 'taskQueue',
      label: '任务队列',
      icon: IconSVG,
      d: 'M12 2a10 10 0 100 20 10 10 0 000-20zM12 6v6l4 2'
    },
    {
      name: 'pptGenerator',
      label: 'PPT 生成',
      icon: IconSVG,
      d: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M9 9H8'
    },
    {
      name: 'imageGenerator',
      label: 'AI 绘画',
      icon: IconSVG,
      d: 'M3 3h18v18H3zM8.5 8.5a1.5 1.5 0 110-3 1.5 1.5 0 010 3zM21 15l-5-5L5 21'
    },
    {
      name: 'projectGenerator',
      label: 'Agent',
      icon: IconSVG,
      d: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'
    },
    {
      name: 'ephemeralWorkflow',
      label: '工作流',
      icon: IconSVG,
      d: 'M22 12h-4l-3 9L9 3l-3 9H2'
    },
    {
      name: 'aicloud',
      label: 'AI 云助手',
      icon: IconSVG,
      d: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'
    },
    {
      name: 'admin',
      label: '管理面板',
      icon: IconSVG,
      d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'
    },
    {
      name: 'searchHistory',
      label: '搜索历史',
      icon: IconSVG,
      d: 'M11 11a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35'
    }
  ]

  const tools = computed(() =>
    toolsBase.filter(
      tool => userStore.isAdmin || (tool.name !== 'aicloud' && tool.name !== 'admin')
    )
  )

  const toggleCollapse = () => (isCollapsed.value = !isCollapsed.value)
  const toggleToolkit = () => (showToolkitMenu.value = !showToolkitMenu.value)
  const newConversation = () => {
    showToolkitMenu.value = false
    emit('newConversation')
  }

  const useTool = toolName => {
    showToolkitMenu.value = false
    if (toolName === 'searchHistory') {
      showSearchBox.value = true
      setTimeout(() => document.querySelector('.search-input')?.focus(), 100)
    } else if (!userStore.isLoggedIn) {
      showLoginDialog.value = true
    } else if (toolName === 'admin') {
      window.open('/admin', '_blank')
    } else if (toolName === 'imageGenerator') {
      window.open('/image-generate', '_blank')
    } else if (toolName === 'pptGenerator') {
      window.open('/ppt-generate', '_blank')
    } else if (toolName === 'projectGenerator') {
      window.open('/project-generate', '_blank')
    } else if (toolName === 'ephemeralWorkflow') {
      window.open('/workflow', '_blank')
    } else {
      emit('useTool', toolName)
    }
  }

  const closeSearch = () => {
    showSearchBox.value = false
    searchKeyword.value = ''
    fetchHistory()
  }

  const clearSearch = () => {
    searchKeyword.value = ''
    fetchHistory()
  }

  const handleSearch = async () => {
    if (!searchKeyword.value.trim()) {
      fetchHistory()
      return
    }

    isLoading.value = true
    loadError.value = ''

    try {
      const response = await api.post('/history', {
        prompt_keyword: searchKeyword.value.trim(),
        limit: 50,
        offset: 0
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      historyList.value = Array.isArray(data.items) ? data.items : []
    } catch (error) {
      loadError.value = error.message
      historyList.value = []
    } finally {
      isLoading.value = false
    }
  }

  const selectHistory = item => {
    activeId.value = item.id
    emit('selectHistory', item)
  }

  const highlightText = text => {
    if (!searchKeyword.value || !text) return text
    try {
      const escaped = searchKeyword.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const regex = new RegExp(`(${escaped})`, 'gi')
      return text.replace(regex, '<mark class="highlight">$1</mark>')
    } catch (e) {
      return text
    }
  }

  const addNewHistoryItem = newItem => {
    const exists = historyList.value.some(
      item => item.conversation_id === newItem.conversation_id || item.id === newItem.id
    )
    if (!exists) {
      historyList.value.unshift(newItem)
      if (historyList.value.length > 50) historyList.value = historyList.value.slice(0, 50)
    }
  }

  const updateHistoryItem = (oldId, newItem) => {
    const index = historyList.value.findIndex(item => item.id === oldId)
    if (index !== -1) {
      historyList.value[index] = { ...newItem, conversation_id: String(newItem.conversation_id) }
    } else {
      addNewHistoryItem(newItem)
    }
  }

  const fetchHistory = async () => {
    if (!userStore.isLoggedIn) return

    isLoading.value = true
    loadError.value = ''

    try {
      const response = await api.post('/history', {
        prompt_keyword: '',
        limit: 50,
        offset: 0
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      historyList.value = Array.isArray(data.items) ? data.items : []
    } catch (error) {
      if (error.message.includes('Token')) {
        userStore.clearUser()
        historyList.value = []
        loadError.value = '登录已过期，请重新登录'
      } else {
        loadError.value = error.message
      }
    } finally {
      isLoading.value = false
    }
  }

  const handleLogin = async () => {
    if (!loginForm.value.email || !loginForm.value.password) {
      loginError.value = '请填写邮箱和密码'
      return
    }

    isLoggingIn.value = true
    loginError.value = ''

    try {
      const data = await api.login({
        email: loginForm.value.email,
        password: loginForm.value.password
      })

      if (data) {
        userStore.setUser({
          username: data.username || loginForm.value.email.split('@')[0],
          permission_level: data.permission_level,
          access_token: data.access_token,
          expires_in: 3600
        })
        loginForm.value = { email: '', password: '' }
        showLoginDialog.value = false
        fetchHistory()
      } else {
        loginError.value = '登录失败'
      }
    } catch (error) {
      loginError.value = '网络请求失败'
    } finally {
      isLoggingIn.value = false
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('token_type')
    userStore.clearUser()
    historyList.value = []
    emit('logout')
  }

  defineExpose({ fetchHistory, addNewHistoryItem, updateHistoryItem })

  onMounted(() => {
    if (userStore.restoreUser()) {
      setTimeout(() => fetchHistory().catch(() => {}), 100)
    }
  })
</script>

<style scoped>
  /* Sidebar */
  .sidebar {
    height: 100vh;
    width: var(--sidebar-width);
    background: linear-gradient(180deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    padding: var(--spacing-3);
    transition: width var(--transition-slow);
    flex-shrink: 0;
  }

  .sidebar.collapsed {
    width: var(--sidebar-collapsed-width);
    padding: var(--spacing-2);
  }

  /* Header */
  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--spacing-3);
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-primary) 100%);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-color);
    margin-bottom: var(--spacing-4);
    transition: all var(--transition-slow);
  }

  .sidebar-header.collapsed {
    justify-content: center;
    padding: var(--spacing-3);
    border: none;
    background: transparent;
  }

  .logo-wrapper {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
    transition: all var(--transition-base);
  }

  .logo-image {
    width: 38px;
    height: 38px;
    border-radius: var(--radius-md);
    object-fit: cover;
    transition: all var(--transition-base);
  }

  .sidebar.collapsed .logo-image {
    width: 44px;
    height: 44px;
    border-radius: var(--radius-lg);
  }

  .logo-text {
    font-size: 16px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--color-blue-600) 0%, var(--color-teal-600) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    white-space: nowrap;
  }

  .sidebar.collapsed .logo-text {
    display: none;
  }

  .collapse-btn {
    width: 32px;
    height: 32px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    cursor: pointer;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-base);
    font-size: 20px;
  }

  .collapse-btn:hover {
    border-color: var(--color-blue-400);
    color: var(--color-blue-600);
    transform: scale(1.05);
  }

  .collapse-btn span.rotated {
    transform: rotate(180deg);
  }

  /* Buttons */
  .btn-new-chat,
  .btn-toolkit {
    width: 100%;
    background: linear-gradient(135deg, var(--color-blue-600) 0%, var(--color-blue-700) 100%);
    color: white;
    border: none;
    border-radius: var(--radius-lg);
    padding: 12px var(--spacing-4);
    cursor: pointer;
    transition: all var(--transition-base);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-3);
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.24);
    margin-bottom: var(--spacing-3);
  }

  .btn-new-chat:hover,
  .btn-toolkit:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.32);
  }

  .btn-toolkit {
    background: linear-gradient(135deg, var(--color-teal-600) 0%, #14b8a6 100%);
    box-shadow: 0 2px 8px rgba(139, 92, 246, 0.24);
  }

  .sidebar.collapsed .btn-new-chat,
  .sidebar.collapsed .btn-toolkit {
    padding: 12px;
  }

  .sidebar.collapsed .btn-new-chat span:not(.icon),
  .sidebar.collapsed .btn-toolkit span:not(.icon-svg) {
    display: none;
  }

  .icon {
    font-size: 20px;
    font-weight: 300;
  }

  .icon-svg {
    width: 19px;
    height: 19px;
  }

  /* Toolkit Menu */
  .toolkit-section {
    position: relative;
    margin-bottom: var(--spacing-3);
  }

  .toolkit-menu {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-xl);
    z-index: 100;
  }

  .toolkit-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
    padding: 12px var(--spacing-4);
    cursor: pointer;
    transition: all var(--transition-base);
    border-bottom: 1px solid var(--border-color);
  }

  .toolkit-item:last-child {
    border-bottom: none;
  }

  .toolkit-item:hover {
    background: var(--bg-tertiary);
    transform: translateX(4px);
  }

  .tool-icon-svg,
  .tool-image {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }

  .tool-image {
    width: 32px;
    height: 32px;
    border-radius: var(--radius-md);
    object-fit: cover;
  }

  /* Search Box */
  .search-box {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--spacing-3);
    margin-bottom: var(--spacing-3);
    box-shadow: var(--shadow-md);
  }

  .search-input {
    width: 100%;
    padding: var(--spacing-2) var(--spacing-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
    outline: none;
    margin-bottom: var(--spacing-2);
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .search-input:focus {
    border-color: var(--color-warning-500);
    background: var(--bg-primary);
  }

  .search-actions {
    display: flex;
    gap: var(--spacing-2);
  }

  /* History */
  .history-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    margin-bottom: var(--spacing-3);
  }

  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .loading-state,
  .error-state,
  .empty-state {
    text-align: center;
    padding: var(--spacing-6);
    color: var(--text-secondary);
  }

  .history-list {
    list-style: none;
    overflow-y: auto;
    flex: 1;
    padding-right: 2px;
    margin: 0;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-2);
    padding: 11px var(--spacing-3);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--transition-base);
    margin-bottom: 4px;
    color: var(--text-primary);
  }

  .history-item:hover {
    background: var(--bg-tertiary);
  }

  .history-item.active {
    background: linear-gradient(135deg, var(--color-blue-100) 0%, var(--color-blue-50) 100%);
    color: var(--color-blue-700);
    box-shadow: var(--shadow-sm);
    font-weight: 600;
  }

  .history-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .item-text {
    font-size: var(--text-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }

  :deep(.highlight) {
    background: linear-gradient(180deg, #fef3c7 0%, #fde68a 100%);
    color: #92400e;
    padding: 0 4px;
    border-radius: 3px;
    font-weight: 700;
  }

  /* User Section */
  .user-section {
    margin-top: auto;
    padding-top: var(--spacing-3);
    border-top: 1px solid var(--border-color);
  }

  .login-prompt {
    display: flex;
    justify-content: center;
  }

  .user-info {
    display: flex;
    align-items: center;
    gap: var(--spacing-3);
    padding: var(--spacing-3);
    background: linear-gradient(135deg, var(--bg-tertiary) 0%, var(--bg-primary) 100%);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-color);
  }

  .user-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--color-teal-600) 0%, #14b8a6 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    flex-shrink: 0;
  }

  .user-avatar svg {
    width: 24px;
    height: 24px;
  }

  .user-details {
    flex: 1;
    min-width: 0;
  }

  .username {
    display: block;
    font-weight: 600;
    color: var(--text-primary);
    font-size: var(--text-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .logout-btn {
    background: none;
    border: none;
    color: var(--color-danger-500);
    cursor: pointer;
    font-size: 11px;
    margin-top: 2px;
    padding: 0;
    text-decoration: underline;
    font-weight: 600;
  }

  .logout-btn:hover {
    color: var(--color-danger-600);
  }

  .sidebar.collapsed .user-section {
    display: none;
  }

  /* Login Form */
  .login-form {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .error-message {
    color: var(--color-danger-500);
    font-size: var(--text-sm);
    padding: var(--spacing-2);
    background: linear-gradient(90deg, #fef2f2 0%, #fff5f5 100%);
    border-radius: var(--radius-md);
    border-left: 3px solid var(--color-danger-500);
  }

  /* Transitions */
  .slide-enter-active,
  .slide-leave-active {
    transition: all var(--transition-spring);
  }

  .slide-enter-from,
  .slide-leave-to {
    opacity: 0;
    transform: translateY(-8px);
  }

  /* Icon sizes */
  .icon-svg-sm {
    width: 16px;
    height: 16px;
  }
</style>
