<template>
  <div id="leftlist" role="navigation" aria-label="侧边栏导航" :class="{ collapsed: isCollapsed }">
    <!-- 顶部区域 -->
    <div id="top-login" :class="{ collapsed: isCollapsed }">
      <div class="logo-wrapper">
        <img id="logo" src="../img/logo.jpg" alt="AI助手 Logo" />
        <span v-if="!isCollapsed" class="logo-text">AI助手</span>
      </div>
      <button
        id="collapse-btn"
        :aria-label="isCollapsed ? '展开侧边栏' : '收起侧边栏'"
        :aria-expanded="!isCollapsed"
        @click="toggleCollapse"
      >
        <span :class="{ rotated: isCollapsed }" aria-hidden="true">‹</span>
      </button>
    </div>

    <!-- 主题切换器 -->
    <div v-if="!isCollapsed" class="theme-switcher-wrapper">
      <ThemeSwitcher />
    </div>

    <!-- 新建会话按钮 -->
    <button
      id="newSpeak"
      aria-label="新建会话"
      @click="newConversation"
    >
      <span class="icon" aria-hidden="true">+</span>
      <span v-if="!isCollapsed">新建会话</span>
    </button>

    <!-- 工具集按钮 -->
    <button
      id="toolkit"
      :aria-label="'工具集' + (showToolkitMenu ? '，已展开' : '，已收起')"
      :aria-expanded="showToolkitMenu"
      :aria-controls="showToolkitMenu ? 'toolkit-menu' : null"
      @click="openToolkit"
    >
      <svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path
          d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
        ></path>
      </svg>
      <span v-if="!isCollapsed">工具集</span>
    </button>

    <!-- 工具集下拉菜单 -->
    <div
      v-if="showToolkitMenu"
      id="toolkit-menu"
      role="menu"
      aria-label="工具集菜单"
      class="toolkit-menu"
      @click.stop
    >
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item highlight"
        @click.stop="navigateToAgent"
        @keydown.enter="navigateToAgent"
        @keydown.space.prevent="navigateToAgent"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
        <span>Agent</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="openChartEditor"
        @keydown.enter="openChartEditor"
        @keydown.space.prevent="openChartEditor"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <line x1="18" y1="20" x2="18" y2="10"></line>
          <line x1="12" y1="20" x2="12" y2="4"></line>
          <line x1="6" y1="20" x2="6" y2="14"></line>
        </svg>
        <span>图表编辑器</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="useTool('dockerConfig')"
        @keydown.enter="useTool('dockerConfig')"
        @keydown.space.prevent="useTool('dockerConfig')"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="M4 10h16v10H4z"></path>
          <path d="M2 14h20"></path>
          <path d="M6 10V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v4"></path>
          <circle cx="8" cy="17" r="1" fill="currentColor"></circle>
          <circle cx="12" cy="17" r="1" fill="currentColor"></circle>
          <circle cx="16" cy="17" r="1" fill="currentColor"></circle>
        </svg>
        <span>Docker 配置</span>
      </div>
      <!-- 管理员工具 - 仅超级用户可见 -->
      <div
        v-if="userStore.isSuperUser"
        role="menuitem"
        tabindex="0"
        class="toolkit-item admin-tool"
        @click.stop="navigateToAdmin"
        @keydown.enter="navigateToAdmin"
        @keydown.space.prevent="navigateToAdmin"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <polygon
            points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"
          ></polygon>
        </svg>
        <span>管理员面板</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="useTool('virtualGirl')"
        @keydown.enter="useTool('virtualGirl')"
        @keydown.space.prevent="useTool('virtualGirl')"
      >
        <img src="../img/AiChat.jpeg" alt="AI 虚拟姬" class="tool-image" />
        <span class="tool-text">虚拟姬</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="openPPTGenerator"
        @keydown.enter="openPPTGenerator"
        @keydown.space.prevent="openPPTGenerator"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
          <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
        <span>PPT 生成</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="openImageGenerator"
        @keydown.enter="openImageGenerator"
        @keydown.space.prevent="openImageGenerator"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
          <circle cx="8.5" cy="8.5" r="1.5"></circle>
          <polyline points="21 15 16 10 5 21"></polyline>
        </svg>
        <span>AI 绘画</span>
      </div>
      <div
        v-if="userStore.isAdmin"
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="useTool('aicloud')"
        @keydown.enter="useTool('aicloud')"
        @keydown.space.prevent="useTool('aicloud')"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
          <path d="M2 17l10 5 10-5"></path>
          <path d="M2 12l10 5 10-5"></path>
        </svg>
        <span>AI 云助手</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="navigateToDocs"
        @keydown.enter="navigateToDocs"
        @keydown.space.prevent="navigateToDocs"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
          <polyline points="10 9 9 9 8 9"></polyline>
        </svg>
        <span>文档中心</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="openWorkflow"
        @keydown.enter="openWorkflow"
        @keydown.space.prevent="openWorkflow"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
        </svg>
        <span>临时工作流</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="useTool('searchHistory')"
        @keydown.enter="useTool('searchHistory')"
        @keydown.space.prevent="useTool('searchHistory')"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span>搜索历史</span>
      </div>
      <div
        role="menuitem"
        tabindex="0"
        class="toolkit-item"
        @click.stop="navigateToSettings"
        @keydown.enter="navigateToSettings"
        @keydown.space.prevent="navigateToSettings"
      >
        <svg
          class="tool-icon-svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
        <span>设置</span>
      </div>
    </div>

    <!-- 搜索框 -->
    <div v-if="showSearchBox" role="search" class="search-box">
      <input
        v-model="searchKeyword"
        type="text"
        placeholder="搜索历史记录..."
        aria-label="搜索历史记录"
        class="search-input"
        @keyup.enter="handleSearch"
        @keyup.esc="handleSearchClear"
      />
      <div class="search-actions">
        <button class="search-btn" @click="handleSearch">搜索</button>
        <button v-if="searchKeyword" class="clear-btn" @click="handleSearchClear">清除</button>
        <button class="close-btn" @click="closeSearchBox">关闭</button>
      </div>
    </div>

    <!-- 历史记录区域 -->
    <div v-if="!isCollapsed" class="history-section" aria-live="polite">
      <div class="section-header">
        <h3>历史记录</h3>
      </div>

      <!-- 加载中状态 -->
      <div v-if="isLoading" role="status" class="loading-state">
        <p>加载中...</p>
      </div>

      <!-- 错误状态 -->
      <div v-else-if="loadError" role="alert" class="error-state">
        <p>加载失败: {{ loadError }}</p>
        <button @click="fetchHistory">重试</button>
      </div>

      <!-- 历史记录列表 -->
      <VirtualHistoryList
        v-else-if="historyList.length > 0"
        ref="virtualListRef"
        :items="historyList"
        :active-id="activeId"
        :is-loading="isLoading"
        :search-keyword="searchKeyword"
        @select="selectHistory"
        @load-more="handleLoadMore"
        @delete="handleDeleteHistory"
      />

      <!-- 空状态 -->
      <div v-else-if="userStore.isLoggedIn" class="empty-state">
        <p>暂无历史记录</p>
      </div>
      <div v-else class="empty-state">
        <p>登录后查看历史记录</p>
      </div>
    </div>

    <!-- 用户登录区域 -->
    <div v-if="!isCollapsed" class="user-section">
      <div v-if="!userStore.isLoggedIn" class="login-prompt">
        <button class="login-btn" @click="showLoginDialog = true">
          <svg
            class="icon-svg-sm"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          <span>登录</span>
        </button>
      </div>
      <div v-else class="user-info">
        <div class="user-avatar" aria-hidden="true">
          <svg
            class="avatar-icon-svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
        </div>
        <div class="user-details">
          <span class="username">{{ userStore.username }}</span>
          <button class="logout-btn" @click="handleLogout">退出</button>
        </div>
      </div>
    </div>

    <!-- 登录弹窗 -->
    <LoginDialog
      :visible="showLoginDialog"
      @close="showLoginDialog = false"
      @success="emit('login')"
    />
  </div>
</template>

<script setup>
  import { ref, onMounted, onUnmounted, watch } from 'vue'
  import { api } from '@/utils/api/index'
  import { useUserStore } from '@/stores/user'
  import ThemeSwitcher from './ui/ThemeSwitcher.vue'
  import LoginDialog from './LoginDialog.vue'
  import VirtualHistoryList from './VirtualHistoryList.vue'
  import { ElMessage, ElMessageBox } from 'element-plus'

  const emit = defineEmits(['newConversation', 'selectHistory', 'deleteHistory', 'login', 'logout', 'useTool'])

  const userStore = useUserStore()

  const isCollapsed = ref(localStorage.getItem('sidebar-collapsed') === 'true')
  const activeId = ref(null)
  const showLoginDialog = ref(false)
  const isLoading = ref(false)
  const loadError = ref('')
  const showToolkitMenu = ref(false)
  const showSearchBox = ref(false)
  const searchKeyword = ref('')

  let searchDebounceTimer = null
  let handleClickOutside = null

  const historyList = ref([])
  const virtualListRef = ref(null)
  const currentPage = ref(0)
  const hasMore = ref(true)
  const pageSize = 50

  watch(isCollapsed, newVal => {
    localStorage.setItem('sidebar-collapsed', String(newVal))
  })

  const toggleCollapse = () => {
    isCollapsed.value = !isCollapsed.value
  }

  const newConversation = () => {
    emit('newConversation')
  }

  const openToolkit = () => {
    showToolkitMenu.value = !showToolkitMenu.value
  }

  const useTool = toolName => {
    showToolkitMenu.value = false

    if (toolName === 'searchHistory') {
      showSearchBox.value = true
      if (searchFocusTimer) clearTimeout(searchFocusTimer)
      searchFocusTimer = setTimeout(() => {
        const searchInput = document.querySelector('.search-input')
        if (searchInput) searchInput.focus()
        searchFocusTimer = null
      }, 100)
    } else if (!userStore.isLoggedIn) {
      showLoginDialog.value = true
    } else {
      emit('useTool', toolName)
    }
  }

  const openPPTGenerator = () => {
    showToolkitMenu.value = false
    window.open('/ppt-generate', '_blank')
  }

  const openChartEditor = () => {
    showToolkitMenu.value = false
    if (!userStore.isLoggedIn) {
      showLoginDialog.value = true
      return
    }
    window.open('/chart-editor', '_blank')
  }

  const navigateToAgent = () => {
    showToolkitMenu.value = false
    window.open('/agent', '_blank')
  }

  const openImageGenerator = () => {
    showToolkitMenu.value = false
    window.open('/image-generate', '_blank')
  }

  const openWorkflow = () => {
    showToolkitMenu.value = false
    window.open('/workflow', '_blank')
  }

  const navigateToAdmin = () => {
    showToolkitMenu.value = false
    window.open('/admin', '_blank')
  }

  const navigateToSettings = () => {
    showToolkitMenu.value = false
    window.open('/settings', '_blank')
  }

  const navigateToDocs = () => {
    showToolkitMenu.value = false
    window.open('/docs', '_blank')
  }

  const closeSearchBox = () => {
    showSearchBox.value = false
    searchKeyword.value = ''
    fetchHistory(true)
  }

  const handleSearch = () => {
    if (searchDebounceTimer) {
      clearTimeout(searchDebounceTimer)
    }

    searchDebounceTimer = setTimeout(async () => {
      if (!searchKeyword.value.trim()) {
        await fetchHistory(true)
        return
      }

      isLoading.value = true
      loadError.value = ''
      currentPage.value = 0
      hasMore.value = true

      try {
        const response = await api.post('/history', {
          prompt_keyword: searchKeyword.value.trim(),
          limit: pageSize,
          offset: 0
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data = await response.json()
        historyList.value = Array.isArray(data.items) ? data.items : []
      } catch (error) {
        loadError.value = error.message
        historyList.value = []
      } finally {
        isLoading.value = false
      }
    }, 300)
  }

  const handleSearchClear = () => {
    searchKeyword.value = ''
    fetchHistory(true)
  }

  const handleLoadMore = async () => {
    if (!userStore.isLoggedIn || isLoading.value || !hasMore.value) return

    currentPage.value++
    await fetchHistory(false)
  }

  const selectHistory = item => {
    activeId.value = item.id
    emit('selectHistory', item)
  }

  // 立即添加新的历史记录项到列表顶部
  const addNewHistoryItem = newItem => {
    // 检查是否已存在相同 ID 的项，避免重复
    const exists = historyList.value.some(
      item => item.conversation_id === newItem.conversation_id || item.id === newItem.id
    )

    if (!exists) {
      // 添加到列表顶部
      historyList.value.unshift(newItem)

      // 保持列表长度不超过 pageSize
      if (historyList.value.length > pageSize) {
        historyList.value = historyList.value.slice(0, pageSize)
      }
    }
  }

  // 更新历史记录项（用于将临时ID更新为真实ID）
  const updateHistoryItem = (oldId, newItem) => {
    const index = historyList.value.findIndex(item => item.id === oldId)
    if (index !== -1) {
      // 更新为真实的对话项
      historyList.value[index] = {
        ...newItem,
        conversation_id: parseInt(newItem.conversation_id, 10)
      }
    } else {
      // 如果找不到旧ID，直接添加新项
      addNewHistoryItem(newItem)
    }
  }

  // 删除会话历史
  const handleDeleteHistory = async (item) => {
    if (!item || !item.conversation_id) return

    try {
      await ElMessageBox.confirm('确定要删除这个会话吗？此操作不可恢复。', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }

    try {
      // 调用后端 API 删除
      const response = await api.deleteChatHistory([item.conversation_id])
      
      if (response.ok) {
        const result = await response.json()
        
        // 从本地列表中移除
        const index = historyList.value.findIndex(h => h.conversation_id === item.conversation_id)
        if (index !== -1) {
          historyList.value.splice(index, 1)
        }
        
        // 如果当前选中的是被删除的会话，清空选中状态
        if (activeId.value === item.conversation_id) {
          activeId.value = null
          emit('selectHistory', null)
        }
        
        // 删除本地 IndexedDB 缓存
        try {
          const chatDb = await import('@/utils/chatDatabase')
          const db = new chatDb.ChatDatabase()
          await db.init()
          await db.deleteConversation(item.conversation_id)
        } catch (dbError) {
          console.error('删除本地缓存失败:', dbError)
        }

        emit('deleteHistory', item.conversation_id)
      } else {
        const errorData = await response.json().catch(() => null)
        console.error('[ERR] 删除失败详情:', response.status, errorData)
        throw new Error(errorData?.message || errorData?.detail || `HTTP ${response.status}`)
      }
    } catch (error) {
      console.error('删除会话失败:', error)
      ElMessage.error('删除失败：' + error.message)
    }
  }

  // 获取历史记录（使用带自动刷新的 api 客户端）
  const fetchHistory = async (reset = true) => {
    if (!userStore.isLoggedIn) return

    if (reset) {
      isLoading.value = true
      currentPage.value = 0
      hasMore.value = true
    }
    loadError.value = ''

    const offset = currentPage.value * pageSize

    try {
      const response = await api.post('/history', {
        prompt_keyword: searchKeyword.value.trim(),
        limit: pageSize,
        offset
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()
      const newItems = Array.isArray(data.items) ? data.items : []

      if (reset) {
        historyList.value = newItems
      } else {
        historyList.value = [...historyList.value, ...newItems]
      }

      if (newItems.length < pageSize) {
        hasMore.value = false
      }
    } catch (error) {
      // 如果是 token 刷新失败相关错误，清除登录状态
      if (error.message.includes('Token refresh') || error.message.includes('Token retry limit')) {
        userStore.clearUser()
        historyList.value = []
        loadError.value = '登录已过期，请重新登录'
      } else {
        loadError.value = error.message
        if (reset) {
          historyList.value = []
        }
      }
    } finally {
      isLoading.value = false
    }
  }

  // 退出登录
  const handleLogout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('token_type')

    // 清除 store 中的用户信息
    userStore.clearUser()

    historyList.value = []

    emit('logout')
  }

  // 组件挂载时检查登录状态并加载历史记录
  let searchFocusTimer = null
  let historyFetchTimer = null

  onMounted(() => {
    // 恢复用户信息并等待 token 刷新完成后再加载历史记录
    if (userStore.restoreUser()) {
      // 等待 token 刷新完成后再加载历史记录，避免 401 错误
      if (historyFetchTimer) clearTimeout(historyFetchTimer)
      historyFetchTimer = setTimeout(() => {
        fetchHistory().catch(() => {})
        historyFetchTimer = null
      }, 500)
    }

    handleClickOutside = event => {
      if (
        showToolkitMenu.value &&
        !event.target.closest('.toolkit-menu') &&
        !event.target.closest('#toolkit')
      ) {
        showToolkitMenu.value = false
      }
    }
    document.addEventListener('click', handleClickOutside)
  })

  onUnmounted(() => {
    if (handleClickOutside) {
      document.removeEventListener('click', handleClickOutside)
    }
    if (searchDebounceTimer) {
      clearTimeout(searchDebounceTimer)
    }
    if (searchFocusTimer) clearTimeout(searchFocusTimer)
    if (historyFetchTimer) clearTimeout(historyFetchTimer)
  })

  // 暴露方法给父组件
  const openLogin = () => {
    showLoginDialog.value = true
  }

  defineExpose({
    fetchHistory,
    addNewHistoryItem,
    updateHistoryItem,
    openLogin,
    toggleCollapse,
    showSearchBox
  })
</script>

<style lang="css">
  /* ========================================
   全局重置与 CSS 变量
   ======================================== */
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  /* SVG 图标样式 */
  .icon-svg {
    width: 19px;
    height: 19px;
    flex-shrink: 0;
  }

  /* 全局焦点可见样式 */
  :focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 2px;
  }

  button:focus-visible,
  [role="button"]:focus-visible,
  [role="menuitem"]:focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 2px;
    box-shadow: 0 0 0 4px var(--primary-100, var(--color-primary-200));
  }

  input:focus-visible,
  textarea:focus-visible,
  select:focus-visible {
    outline: 2px solid var(--primary-500, #3b82f6);
    outline-offset: 0;
    box-shadow: 0 0 0 4px var(--primary-100, var(--color-primary-200));
  }

  .collapsed .toolkit-menu,
  .collapsed .search-box,
  .collapsed .history-section,
  .collapsed .user-section,
  .collapsed .theme-switcher-wrapper {
    aria-hidden: true;
  }

  .icon-svg-sm {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .tool-icon-svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }

  .avatar-icon-svg {
    width: 100%;
    height: 100%;
  }

  /* ========================================
   侧边栏容器
   ======================================== */
  #leftlist {
    flex-shrink: 0;
    width: var(--sidebar-width);
    background: var(--bg-primary);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    padding: var(--spacing-md);
    transition:
      width var(--transition-slow),
      background var(--transition-base);
    user-select: none;
    flex-shrink: 0;
    position: relative;
  }

  #leftlist::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 200px;
    background: linear-gradient(180deg, rgba(59, 130, 246, 0.03) 0%, transparent 100%);
    pointer-events: none;
    z-index: 0;
  }

  #leftlist.collapsed {
    width: var(--sidebar-collapsed-width);
    padding: var(--spacing-sm);
  }

  #leftlist.collapsed::before {
    display: none;
  }

  /* ========================================
   顶部品牌区域
   ======================================== */
  #top-login {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-lg);
    padding: var(--spacing-md);
    background: var(--bg-secondary);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-color);
    transition: all var(--transition-slow);
    position: relative;
    z-index: 1;
  }

  #top-login:hover {
    border-color: var(--primary-200);
    box-shadow: var(--shadow-sm);
  }

  #top-login.collapsed {
    justify-content: center;
    padding: var(--spacing-md);
    border: none;
    background: transparent;
  }

  #top-login.collapsed:hover {
    border: none;
    box-shadow: none;
  }

  .logo-wrapper {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    overflow: hidden;
    transition: all var(--transition-base);
  }

  #logo {
    width: 38px;
    height: 38px;
    border-radius: var(--radius-md);
    object-fit: cover;
    flex-shrink: 0;
    transition: all var(--transition-base);
    box-shadow: var(--shadow-xs);
    border: 1px solid var(--border-color);
  }

  .collapsed #logo {
    width: 44px;
    height: 44px;
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
  }

  .logo-text {
    font-size: 16px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary-600) 0%, var(--teal) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    white-space: nowrap;
    opacity: 1;
    transition: opacity var(--transition-base);
  }

  .collapsed .logo-text {
    opacity: 0;
    display: none;
  }

  .theme-switcher-wrapper {
    display: flex;
    justify-content: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .collapsed .theme-switcher-wrapper {
    display: none;
  }

  #collapse-btn {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, white 0%, var(--slate-50) 100%);
    border: 1px solid var(--border-color);
    padding: 0;
    cursor: pointer;
    border-radius: var(--radius-md);
    transition: all var(--transition-base);
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    flex-shrink: 0;
  }

  #collapse-btn::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    background: radial-gradient(circle, var(--primary-100) 0%, transparent 70%);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    transition: all var(--transition-base);
  }

  #collapse-btn:hover {
    border-color: var(--primary-300);
    color: var(--primary-600);
    box-shadow: var(--shadow-sm);
    transform: scale(1.05);
  }

  #collapse-btn:hover::before {
    width: 60px;
    height: 60px;
  }

  #collapse-btn:active {
    transform: scale(0.98);
  }

  #collapse-btn span {
    font-size: 20px;
    font-weight: 500;
    transition: all var(--transition-base);
    display: inline-block;
    position: relative;
    z-index: 1;
  }

  #collapse-btn:hover span {
    transform: scale(1.1);
  }

  #collapse-btn span.rotated {
    transform: rotate(180deg);
  }

  /* ========================================
   主要操作按钮
   ======================================== */
  #newSpeak {
    background: linear-gradient(135deg, var(--teal) 0%, var(--primary) 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    margin-bottom: var(--spacing-md) !important;
    cursor: pointer !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: var(--spacing-md) !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    box-shadow: 0 4px 15px rgba(20, 184, 166, 0.3) !important;
    position: relative !important;
    overflow: hidden !important;
    z-index: 1 !important;
  }

  #newSpeak::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      120deg,
      transparent 30%,
      rgba(255, 255, 255, 0.25) 50%,
      transparent 70%
    );
    transition: left 0.6s ease;
    z-index: -1;
  }

  #newSpeak:hover::before {
    left: 100%;
  }

  #newSpeak:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 6px 20px rgba(20, 184, 166, 0.4);
  }

  #newSpeak:active {
    transform: translateY(0) scale(0.98);
  }

  #newSpeak .icon {
    font-size: 18px;
    font-weight: 400;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 5px;
    transition: all 0.3s;
  }

  #newSpeak:hover .icon {
    background: rgba(255, 255, 255, 0.3);
    transform: rotate(90deg);
  }

  .collapsed #newSpeak {
    padding: 14px;
    border-radius: 12px;
  }

  .collapsed #newSpeak span:not(.icon) {
    display: none;
  }

  #toolkit {
    background: var(--color-surface, #ffffff) !important;
    color: var(--slate-700) !important;
    border: 1.5px solid var(--border-color, #e2e8f0) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    margin-bottom: var(--spacing-md) !important;
    cursor: pointer !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: var(--spacing-md) !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    position: relative !important;
    overflow: hidden !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
  }

  #toolkit:hover {
    background: var(--teal-50, #f0fdfa);
    border-color: var(--teal);
    color: var(--teal);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(20, 184, 166, 0.15);
  }

  #toolkit:active {
    transform: translateY(0);
  }

  #toolkit .icon-svg {
    transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }

  #toolkit:hover .icon-svg {
    transform: rotate(-15deg) scale(1.1);
  }

  .collapsed #toolkit {
    padding: 14px;
    border-radius: 12px;
  }

  .collapsed #toolkit span:not(.icon) {
    display: none;
  }

  /* ========================================
   工具集下拉菜单 (现代化重构)
   ======================================== */
  .toolkit-menu {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 12px;
    margin-bottom: var(--spacing-md);
    padding: 6px;
    box-shadow:
      0 10px 30px rgba(0, 0, 0, 0.1),
      0 2px 8px rgba(0, 0, 0, 0.05);
    animation: menuSlideDown 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    position: relative;
    z-index: 100;
    pointer-events: auto;
    flex-shrink: 0;
  }

  @keyframes menuSlideDown {
    from {
      opacity: 0;
      transform: translateY(-10px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .toolkit-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    min-height: 36px;
    cursor: pointer;
    transition: all 0.2s ease;
    border-radius: 8px;
    border: 1px solid transparent;
    position: relative;
    margin-bottom: 3px;
    flex-shrink: 0;
  }

  .toolkit-item:last-child {
    margin-bottom: 0;
  }

  .toolkit-item:hover {
    background: linear-gradient(135deg, rgba(20, 184, 166, 0.08) 0%, rgba(13, 148, 136, 0.04) 100%);
    border-color: rgba(20, 184, 166, 0.2);
    transform: translateX(4px) scale(1.01);
    box-shadow: 0 2px 8px rgba(20, 184, 166, 0.1);
  }

  .toolkit-item:active {
    transform: translateX(2px) scale(0.99);
  }

  .toolkit-item.highlight {
    background: linear-gradient(
      135deg,
      rgba(20, 184, 166, 0.12) 0%,
      rgba(13, 148, 136, 0.08) 100%
    ) !important;
    border-color: rgba(20, 184, 166, 0.3) !important;
    padding: 9px 12px !important;
  }

  .toolkit-item.highlight:hover {
    background: linear-gradient(135deg, rgba(20, 184, 166, 0.18) 0%, rgba(13, 148, 136, 0.12) 100%);
  }

  .toolkit-item span:not(.tool-icon) {
    font-size: 14px;
    color: var(--slate-700);
    font-weight: 500;
    transition: color 0.2s;
  }

  .toolkit-item:hover span:not(.tool-icon) {
    color: var(--teal);
    font-weight: 600;
  }

  .tool-icon-svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    color: var(--slate-500);
    transition: all 0.2s ease;
  }

  .toolkit-item:hover .tool-icon-svg {
    color: var(--teal);
    transform: scale(1.1);
  }

  .tool-image {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    object-fit: cover;
    flex-shrink: 0;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    border: 2px solid white;
  }

  .toolkit-item:hover .tool-image {
    transform: scale(1.1) rotate(3deg);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  /* ========================================
   搜索框
   ======================================== */
  .search-box {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--spacing-md);
    margin-bottom: var(--spacing-md);
    box-shadow: var(--shadow-md);
    animation: searchSlideDown 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  @keyframes searchSlideDown {
    from {
      opacity: 0;
      transform: translateY(-8px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .search-input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: 13px;
    outline: none;
    transition: all var(--transition-base);
    margin-bottom: var(--spacing-sm);
    background: var(--slate-50);
    color: var(--slate-700);
  }

  .search-input::placeholder {
    color: var(--slate-400);
  }

  .search-input:focus {
    border-color: var(--primary-500);
    background: var(--bg-primary);
    box-shadow: 0 0 0 3px var(--primary-100);
  }

  .search-actions {
    display: flex;
    gap: 6px;
  }

  .search-btn {
    flex: 1;
    padding: 8px 12px;
    background: linear-gradient(135deg, var(--warning) 0%, var(--warning-hover) 100%);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-base);
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2);
  }

  .search-btn:hover {
    background: linear-gradient(135deg, var(--warning-hover) 0%, var(--warning-hover) 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(245, 158, 11, 0.3);
  }

  .clear-btn {
    flex: 1;
    padding: 8px 12px;
    background: var(--slate-100);
    color: var(--slate-600);
    border: none;
    border-radius: var(--radius-md);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-base);
  }

  .clear-btn:hover {
    background: var(--slate-200);
    color: var(--slate-700);
  }

  .close-btn {
    flex: 1;
    padding: 8px 12px;
    background: linear-gradient(135deg, var(--danger) 0%, var(--danger-hover) 100%);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--transition-base);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .close-btn:hover {
    background: linear-gradient(135deg, var(--danger-hover) 0%, var(--danger-hover) 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.3);
  }

  /* ========================================
   历史记录区域
   ======================================== */
  .history-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    position: relative;
    z-index: 1;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--spacing-md);
    padding: 0 var(--spacing-xs);
  }

  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .loading-state,
  .error-state {
    text-align: center;
    padding: var(--spacing-xl);
    color: var(--text-secondary);
  }

  .error-state button {
    margin-top: var(--spacing-sm);
    padding: 8px 16px;
    background: linear-gradient(135deg, var(--primary-600) 0%, var(--primary-700) 100%);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
    transition: all var(--transition-base);
  }

  .error-state button:hover {
    background: linear-gradient(135deg, var(--primary-700) 0%, var(--primary-600) 100%);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }

  #history {
    list-style: none;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
    padding-right: 2px;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    padding: 11px var(--spacing-md);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--transition-base);
    margin-bottom: 4px;
    color: var(--slate-700);
    position: relative;
    overflow: hidden;
  }

  .history-item::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 0;
    height: 100%;
    background: linear-gradient(90deg, var(--primary-200) 0%, transparent 100%);
    transition: width var(--transition-base);
    z-index: -1;
  }

  .history-item:hover::before {
    width: 100%;
  }

  .history-item:hover {
    background: var(--slate-50);
  }

  .history-item.active {
    background: linear-gradient(135deg, var(--primary-100) 0%, var(--color-primary-200) 100%);
    color: var(--primary-700);
    box-shadow: var(--shadow-sm);
    font-weight: 600;
  }

  .history-item.active::before {
    width: 4px;
    background: linear-gradient(180deg, var(--primary-500) 0%, var(--primary-700) 100%);
  }

  .history-item .icon {
    font-size: 16px;
    flex-shrink: 0;
    opacity: 0.8;
  }

  .history-item:hover .icon {
    opacity: 1;
    transform: scale(1.1);
  }

  .item-text {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 500;
    transition: all var(--transition-base);
  }

  .history-item:hover .item-text {
    color: var(--slate-900);
  }

  .history-item.active .item-text {
    font-weight: 600;
  }

  .highlight {
    background: linear-gradient(180deg, var(--color-warning-50, #fef3c7) 0%, var(--color-warning-100, #fde68a) 100%);
    color: var(--text-primary);
    padding: 0 4px;
    border-radius: 3px;
    font-weight: 700;
    box-shadow: 0 1px 2px rgba(245, 158, 11, 0.15);
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px var(--spacing-lg);
    color: var(--text-secondary);
    font-size: 13px;
    text-align: center;
    line-height: 1.6;
    background: var(--bg-primary) !important;
  }

  .search-input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 13px;
    outline: none;
    transition: var(--transition);
    margin-bottom: 8px;
    background: var(--bg-secondary);
  }

  .search-input:focus {
    border-color: var(--warning);
    background: var(--bg-primary);
    box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15);
  }

  .search-actions {
    display: flex;
    gap: 6px;
  }

  .search-btn {
    flex: 1;
    padding: 7px 12px;
    background: linear-gradient(135deg, var(--warning), var(--warning-hover));
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    box-shadow: 0 2px 4px rgba(245, 158, 11, 0.2);
  }

  .search-btn:hover {
    background: linear-gradient(135deg, var(--warning-hover), var(--warning-hover));
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(245, 158, 11, 0.3);
  }

  .clear-btn {
    flex: 1;
    padding: 7px 12px;
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
  }

  .clear-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .close-btn {
    flex: 1;
    padding: 7px 12px;
    background: linear-gradient(135deg, var(--danger), var(--danger-hover));
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: var(--transition);
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
  }

  .close-btn:hover {
    background: linear-gradient(135deg, var(--danger-hover), var(--danger-hover));
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(239, 68, 68, 0.3);
  }

  /* 历史记录区域 */
  .history-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    padding: 0 4px;
  }

  .section-header h3 {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }

  /* 加载状态 */
  .loading-state,
  .error-state {
    text-align: center;
    padding: 20px;
    color: var(--text-secondary);
  }

  .error-state button {
    margin-top: 8px;
    padding: 6px 12px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: var(--border-radius);
    cursor: pointer;
    font-weight: 500;
    transition: var(--transition);
  }

  .error-state button:hover {
    background: var(--primary-hover);
  }

  /* 历史记录列表 */
  #history {
    list-style: none;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--border-radius);
    cursor: pointer;
    transition: var(--transition);
    margin-bottom: 4px;
    color: var(--text-primary);
  }

  .history-item:hover {
    background-color: var(--hover-bg);
  }

  .history-item.active {
    background: linear-gradient(90deg, var(--color-primary-200), var(--color-primary-50));
    color: var(--primary-color);
    box-shadow: var(--shadow-sm);
  }

  .history-item .icon {
    font-size: 16px;
    flex-shrink: 0;
  }

  .item-text {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 500;
  }

  /* 搜索高亮样式 */
  .highlight {
    background: var(--color-warning-50, #fef3c7);
    color: var(--text-primary);
    padding: 0 3px;
    border-radius: 2px;
    font-weight: 700;
  }

  /* 空状态 */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 30px 16px;
    color: var(--text-secondary);
    font-size: 13px;
    text-align: center;
    background: var(--bg-primary) !important;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding: 0 4px;
  }

  .section-header h3 {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  /* 加载状态 */
  .loading-state,
  .error-state {
    text-align: center;
    padding: 20px;
    color: var(--text-secondary);
  }

  .error-state button {
    margin-top: 8px;
    padding: 6px 12px;
    background: var(--primary-color);
    color: white;
    border: none;
    border-radius: var(--border-radius);
    cursor: pointer;
  }

  /* 历史记录列表 */
  #history {
    list-style: none;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }

  .history-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--border-radius);
    cursor: pointer;
    transition: var(--transition);
    margin-bottom: 4px;
    color: var(--text-primary);
  }

  .history-item:hover {
    background-color: var(--hover-bg);
  }

  .history-item.active {
    background-color: var(--color-primary-100);
    color: var(--primary-color);
  }

  .history-item .icon {
    font-size: 16px;
    flex-shrink: 0;
  }

  .item-text {
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* 搜索高亮样式 */
  .highlight {
    background: var(--color-warning-200, #fef08a);
    color: var(--text-primary);
    padding: 0 2px;
    border-radius: 2px;
    font-weight: 600;
  }

  /* 空状态 */
  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 20px;
    color: var(--text-secondary);
    font-size: 14px;
    background: var(--bg-primary) !important;
  }

  /* ========================================
   用户区域
   ======================================== */
  .user-section {
    margin-top: auto;
    padding-top: var(--spacing-md);
    border-top: 1px solid var(--slate-200);
    position: relative;
    z-index: 1;
  }

  .login-prompt {
    display: flex;
    justify-content: center;
  }

  .login-btn {
    background: linear-gradient(135deg, var(--success) 0%, var(--success-hover) 100%);
    color: white;
    border: none;
    border-radius: var(--radius-lg);
    padding: 11px var(--spacing-lg);
    cursor: pointer;
    transition: all var(--transition-base);
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    font-size: 14px;
    font-weight: 600;
    width: 100%;
    justify-content: center;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.24);
    position: relative;
    overflow: hidden;
  }

  .login-btn::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.25) 50%,
      transparent 100%
    );
    transition: left 0.5s ease;
  }

  .login-btn:hover::before {
    left: 100%;
  }

  .login-btn:hover {
    background: linear-gradient(135deg, var(--success-hover) 0%, var(--success-hover) 100%);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.32);
  }

  .login-btn:active {
    transform: translateY(0);
  }

  .user-info {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    padding: var(--spacing-md);
    background: linear-gradient(135deg, var(--slate-50) 0%, white 100%);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-color);
    transition: all var(--transition-base);
  }

  .user-info:hover {
    border-color: var(--primary-200);
    box-shadow: var(--shadow-sm);
  }

  .user-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--teal) 0%, var(--primary-hover) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 18px;
    flex-shrink: 0;
    box-shadow: var(--shadow-md);
    border: 2px solid white;
  }

  .user-details {
    flex: 1;
    min-width: 0;
  }

  .username {
    display: block;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 13px;
  }

  .logout-btn {
    background: none;
    border: none;
    color: var(--danger);
    cursor: pointer;
    font-size: 11px;
    margin-top: 2px;
    padding: 0;
    text-decoration: underline;
    font-weight: 600;
    transition: all var(--transition-fast);
    opacity: 0.8;
  }

  .logout-btn:hover {
    color: var(--danger-hover);
    opacity: 1;
  }

  .collapsed .user-section {
    display: none;
  }

  /* ========================================
   登录弹窗 - 美化版
   ======================================== */
  .login-modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(12px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: modalFadeIn 0.3s ease;
  }

  @keyframes modalFadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .login-form {
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
    transition: all var(--transition-base);
  }

  @keyframes modalSlideUp {
    from {
      opacity: 0;
      transform: translateY(40px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  /* Login Header */
  .login-header {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    padding: 32px 32px 40px;
    text-align: center;
    position: relative;
    overflow: hidden;
  }

  .login-header::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.1) 0%, transparent 60%);
    animation: shimmer 3s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%,
    100% {
      transform: translate(0, 0);
    }
    50% {
      transform: translate(10%, 10%);
    }
  }

  .login-logo {
    width: 72px;
    height: 72px;
    margin: 0 auto 16px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(10px);
    border: 2px solid rgba(255, 255, 255, 0.3);
    position: relative;
    z-index: 1;
  }

  .login-logo svg {
    width: 36px;
    height: 36px;
    color: white;
  }

  .login-header h3 {
    margin: 0 0 8px 0;
    color: white;
    font-size: 26px;
    font-weight: 700;
    position: relative;
    z-index: 1;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .login-header p {
    margin: 0;
    color: rgba(255, 255, 255, 0.85);
    font-size: 14px;
    position: relative;
    z-index: 1;
  }

  /* Login Body */
  .login-body {
    padding: 32px;
  }

  .input-group {
    position: relative;
    margin-bottom: 20px;
  }

  .input-icon {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    width: 20px;
    height: 20px;
    color: var(--slate-400);
    transition: color 0.3s ease;
    z-index: 1;
    pointer-events: none;
  }

  .input-icon svg {
    width: 100%;
    height: 100%;
  }

  .input-group input {
    width: 100%;
    padding: 16px 16px 16px 48px;
    border: 2px solid var(--border-color);
    border-radius: 12px;
    font-size: 15px;
    transition: all 0.3s ease;
    background: var(--bg-secondary);
    color: var(--text-primary);
  }

  .input-group input:focus {
    outline: none;
    border-color: var(--color-primary-500);
    background: var(--bg-secondary);
    box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.15);
  }

  .input-group.focused .input-icon {
    color: var(--color-primary-500);
  }

  .input-group label {
    position: absolute;
    left: 48px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 15px;
    color: var(--slate-400);
    pointer-events: none;
    transition: all 0.3s ease;
    background: transparent;
    padding: 0 4px;
  }

  .input-group input:focus ~ label,
  .input-group input:not(:placeholder-shown) ~ label,
  .input-group.filled label {
    top: 0;
    font-size: 12px;
    color: var(--color-primary-500);
    background: var(--bg-tertiary);
  }

  /* Login Options */
  .login-options {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .remember-me {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 14px;
    color: var(--slate-600);
    user-select: none;
  }

  .remember-me input {
    display: none;
  }

  .remember-me .checkmark {
    width: 18px;
    height: 18px;
    border: 2px solid var(--slate-300);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .remember-me input:checked + .checkmark {
    background: var(--primary);
    border-color: var(--primary);
  }

  .remember-me input:checked + .checkmark::after {
    content: '';
    width: 5px;
    height: 9px;
    border: solid white;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg) translateY(-1px);
  }

  .forgot-link {
    font-size: 14px;
    color: var(--primary);
    text-decoration: none;
    transition: color 0.2s ease;
  }

  .forgot-link:hover {
    color: var(--primary-hover);
    text-decoration: underline;
  }

  /* Error Message */
  .login-form .error-message {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--danger-hover);
    font-size: 14px;
    margin: 0 0 20px 0;
    padding: 12px 16px;
    background: linear-gradient(90deg, var(--color-danger-50, #fef2f2) 0%, var(--color-danger-50, #fff5f5) 100%);
    border-radius: 12px;
    border-left: 4px solid var(--danger-hover);
    animation: errorShake 0.4s ease;
  }

  .login-form .error-message svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  @keyframes errorShake {
    0%,
    100% {
      transform: translateX(0);
    }
    20%,
    60% {
      transform: translateX(-6px);
    }
    40%,
    80% {
      transform: translateX(6px);
    }
  }

  /* Login Footer */
  .login-footer {
    display: flex;
    gap: 12px;
    padding: 0 32px 24px;
  }

  .btn-cancel {
    flex: 1;
    padding: 14px 20px;
    background: var(--slate-100);
    color: var(--slate-600);
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .btn-cancel:hover {
    background: var(--slate-200);
    transform: translateY(-1px);
  }

  .btn-login {
    flex: 2;
    padding: 14px 20px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  }

  .btn-login:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
  }

  .btn-login:disabled {
    opacity: 0.7;
    cursor: not-allowed;
    transform: none;
  }

  .btn-login .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn-login .spinner {
    width: 18px;
    height: 18px;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  /* Login Divider */
  .login-divider {
    display: flex;
    align-items: center;
    padding: 0 32px 24px;
  }

  .login-divider::before,
  .login-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--slate-300), transparent);
  }

  .login-divider span {
    padding: 0 16px;
    color: var(--slate-400);
    font-size: 13px;
  }

  /* Social Login */
  .social-login {
    display: flex;
    gap: 12px;
    padding: 0 32px 32px;
  }

  .btn-social {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 16px;
    border: 2px solid var(--slate-200);
    border-radius: 12px;
    background: var(--bg-primary);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .btn-social svg {
    width: 18px;
    height: 18px;
  }

  .btn-github {
    color: var(--slate-700);
  }

  .btn-github:hover {
    border-color: var(--slate-400);
    background: var(--slate-50);
    transform: translateY(-1px);
  }

  .btn-google {
    color: var(--slate-700);
  }

  .btn-google:hover {
    border-color: var(--slate-400);
    background: var(--slate-50);
    transform: translateY(-1px);
  }

  .login-prompt {
    display: flex;
    justify-content: center;
  }

  .login-btn {
    background: linear-gradient(135deg, var(--success), var(--success-hover));
    color: white;
    border: none;
    border-radius: var(--border-radius);
    padding: 10px 16px;
    cursor: pointer;
    transition: var(--transition);
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 600;
    width: 100%;
    justify-content: center;
    box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
  }

  .login-btn:hover {
    background: linear-gradient(135deg, var(--success-hover), var(--success-hover));
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(16, 185, 129, 0.3);
  }

  .user-info {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px;
    background: linear-gradient(90deg, var(--bg-secondary), var(--bg-tertiary));
    border-radius: var(--border-radius);
    border: 1px solid var(--border-color);
  }

  .user-avatar {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--color-primary-500), var(--primary-hover));
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 18px;
    flex-shrink: 0;
    box-shadow: var(--shadow-sm);
  }

  .user-details {
    flex: 1;
    min-width: 0;
  }

  .username {
    display: block;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 13px;
  }

  .logout-btn {
    background: none;
    border: none;
    color: var(--danger);
    cursor: pointer;
    font-size: 11px;
    margin-top: 3px;
    padding: 0;
    text-decoration: underline;
    font-weight: 500;
  }

  .logout-btn:hover {
    color: var(--danger-hover);
  }

  .collapsed .user-section {
    display: none;
  }

  /* ========================================
   滚动条美化
   ======================================== */
  #history::-webkit-scrollbar {
    width: 6px;
  }

  #history::-webkit-scrollbar-track {
    background: transparent;
    margin: 4px 0;
  }

  #history::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--slate-300) 0%, var(--slate-400) 100%);
    border-radius: 3px;
    transition: background var(--transition-base);
  }

  #history::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--slate-400) 0%, var(--slate-500) 100%);
  }

  /* ========================================
   响应式设计
   ======================================== */
  @media (max-width: 768px) {
    :root {
      --sidebar-width: 260px;
    }
  }

  @media (max-width: 480px) {
    :root {
      --sidebar-width: 240px;
    }
  }

  /* ========================================
   动画工具类
   ======================================== */
  @keyframes shimmer {
    0% {
      background-position: -1000px 0;
    }
    100% {
      background-position: 1000px 0;
    }
  }

  .shimmer {
    background: linear-gradient(
      90deg,
      var(--slate-100) 0%,
      var(--slate-50) 50%,
      var(--slate-100) 100%
    );
    background-size: 1000px 100%;
    animation: shimmer 2s infinite;
  }
</style>
