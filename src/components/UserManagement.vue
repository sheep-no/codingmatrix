<template>
  <div class="user-management">
    <!-- 头部 -->
    <div class="section-header-toggle">
      <button class="header-toggle-btn" @click="showHeader = !showHeader">
        <span class="toggle-icon">{{ showHeader ? '▼' : '▶' }}</span>
        <span>管理面板</span>
      </button>
      <button class="create-user-mini-btn" title="Create user" @click="showCreateUserDialog = true">
        <span class="icon">[+]</span>
      </button>
    </div>

    <div class="section-header" :class="{ collapsed: !showHeader }">
      <h3>
        <span class="icon">[USERS]</span>
        User Management
      </h3>
      <button class="create-user-btn" @click="showCreateUserDialog = true">
        <span class="icon">[+]</span>
        Create User
      </button>
    </div>

    <!-- 用户筛选和搜索 -->
    <div v-if="showHeader" class="filter-toggle-wrapper">
      <button class="filter-toggle-btn" @click="showFilters = !showFilters">
        <span :class="['toggle-icon', { active: showFilters }]">[FIND]</span>
        <span>筛选和搜索</span>
        <span :class="['arrow-icon', { open: showFilters }]">▼</span>
      </button>
    </div>
    <div class="users-filters" :class="{ collapsed: !showFilters }">
      <div class="filter-group">
        <label>搜索：</label>
        <input
          v-model="userFilters.keyword"
          type="text"
          placeholder="搜索用户名或邮箱..."
          @input="debouncedFetchUsers"
        />
      </div>
      <div class="filter-group">
        <label>权限：</label>
        <select v-model="userFilters.permission_level" @change="fetchUsers">
          <option value="">全部</option>
          <option value="normal">普通用户</option>
          <option value="admin">管理员</option>
          <option value="superadmin">超级管理员</option>
        </select>
      </div>
      <div class="filter-group">
        <label>排序：</label>
        <select v-model="userFilters.sort_by" @change="fetchUsers">
          <option value="id">ID</option>
          <option value="username">用户名</option>
          <option value="email">邮箱</option>
          <option value="created_at">创建时间</option>
        </select>
      </div>
      <div class="filter-group">
        <label>方向：</label>
        <select v-model="userFilters.sort_order" @change="fetchUsers">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="users-content">
      <div v-if="usersLoading" class="loading-state">
        <p>加载中...</p>
      </div>
      <div v-else-if="usersError" class="error-state">
        <p>{{ usersError }}</p>
        <button class="retry-btn" @click="fetchUsers">重试</button>
      </div>
      <div v-else-if="users.length === 0" class="empty-users">
        <span class="icon">👥</span>
        <p>暂无用户</p>
      </div>
      <div v-else class="users-list">
        <div v-for="user in users" :key="user.id" class="user-card">
          <div class="user-info">
            <div class="user-avatar">
              <span class="avatar-text">{{ user.username.charAt(0).toUpperCase() }}</span>
            </div>
            <div class="user-details">
              <div class="user-header-row">
                <span class="user-name">{{ user.username }}</span>
                <span :class="['user-permission', user.permission_level]">
                  {{ getPermissionLabel(user.permission_level) }}
                </span>
              </div>
              <div class="user-email">
                <span class="email-icon">📧</span>
                {{ user.email }}
              </div>
              <div class="user-meta">
                <span class="meta-item">
                  <span class="meta-icon">🆔</span>
                  ID: {{ user.id }}
                </span>
                <span class="meta-item">
                  <span class="meta-icon">📅</span>
                  {{ formatDate(user.created_at) }}
                </span>
              </div>
            </div>
          </div>
          <div class="user-actions">
            <button class="action-btn edit" title="编辑" @click="openEditUser(user)">[EDIT]</button>
            <button class="action-btn reset" title="重置密码" @click="openResetPassword(user)">
              [KEY]
            </button>
            <button
              class="action-btn delete"
              title="删除"
              :disabled="user.id === userStore.userId"
              @click="confirmDeleteUser(user)"
            >
              [DEL]
            </button>
          </div>
        </div>
      </div>

      <!-- 分页控件 -->
      <div v-if="userPagination.total > 0" class="pagination">
        <button
          class="page-btn"
          :disabled="userPagination.page === 1"
          @click="changePage(userPagination.page - 1)"
        >
          上一页
        </button>
        <span class="page-info">
          第 {{ userPagination.page }} 页 / 共 {{ totalPages }} 页 (共
          {{ userPagination.total }} 条)
        </span>
        <button
          class="page-btn"
          :disabled="userPagination.page >= totalPages"
          @click="changePage(userPagination.page + 1)"
        >
          下一页
        </button>
      </div>
    </div>

    <!-- 创建用户对话框 -->
    <div
      v-if="showCreateUserDialog"
      class="modal-overlay"
      @click.self="showCreateUserDialog = false"
    >
      <div class="modal-content">
        <div class="modal-header">
          <h3>创建用户</h3>
          <button class="close-btn" @click="showCreateUserDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户名 *</label>
            <input v-model="createUserForm.username" type="text" placeholder="请输入用户名" />
          </div>
          <div class="form-group">
            <label>邮箱 *</label>
            <input v-model="createUserForm.email" type="email" placeholder="请输入邮箱" />
          </div>
          <div class="form-group">
            <label>密码 * (至少6位)</label>
            <input v-model="createUserForm.password" type="password" placeholder="请输入密码" />
          </div>
          <div class="form-group">
            <label>权限级别</label>
            <select v-model="createUserForm.permission_level">
              <option value="normal">普通用户</option>
              <option value="admin">管理员</option>
              <option value="superadmin">超级管理员</option>
            </select>
          </div>
          <p v-if="createUserError" class="error-message">{{ createUserError }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showCreateUserDialog = false">取消</button>
          <button class="btn-primary" :disabled="isCreatingUser" @click="handleCreateUser">
            {{ isCreatingUser ? '创建中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 编辑用户对话框 -->
    <div v-if="showEditUserDialog" class="modal-overlay" @click.self="showEditUserDialog = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>编辑用户</h3>
          <button class="close-btn" @click="showEditUserDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户名</label>
            <input v-model="editUserForm.username" type="text" placeholder="请输入用户名" />
          </div>
          <div class="form-group">
            <label>邮箱</label>
            <input v-model="editUserForm.email" type="email" placeholder="请输入邮箱" />
          </div>
          <div class="form-group">
            <label>权限级别</label>
            <select v-model="editUserForm.permission_level">
              <option value="normal">普通用户</option>
              <option value="admin">管理员</option>
              <option value="superadmin">超级管理员</option>
            </select>
          </div>
          <p v-if="editUserError" class="error-message">{{ editUserError }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showEditUserDialog = false">取消</button>
          <button class="btn-primary" :disabled="isUpdatingUser" @click="handleUpdateUser">
            {{ isUpdatingUser ? '更新中...' : '更新' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 重置密码对话框 -->
    <div
      v-if="showResetPasswordDialog"
      class="modal-overlay"
      @click.self="showResetPasswordDialog = false"
    >
      <div class="modal-content">
        <div class="modal-header">
          <h3>重置密码</h3>
          <button class="close-btn" @click="showResetPasswordDialog = false">×</button>
        </div>
        <div class="modal-body">
          <p class="reset-user-info">
            为用户 <strong>{{ resetPasswordUser?.username }}</strong> 重置密码
          </p>
          <div class="form-group">
            <label>新密码 * (至少6位)</label>
            <input
              v-model="resetPasswordForm.new_password"
              type="password"
              placeholder="请输入新密码"
            />
          </div>
          <p v-if="resetPasswordError" class="error-message">{{ resetPasswordError }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showResetPasswordDialog = false">取消</button>
          <button class="btn-primary" :disabled="isResettingPassword" @click="handleResetPassword">
            {{ isResettingPassword ? '重置中...' : '重置' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除用户确认对话框 -->
    <div
      v-if="showDeleteConfirmDialog"
      class="modal-overlay"
      @click.self="showDeleteConfirmDialog = false"
    >
      <div class="modal-content" style="max-width: 400px">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="close-btn" @click="showDeleteConfirmDialog = false">×</button>
        </div>
        <div class="modal-body">
          <p class="delete-confirm-text">
            确定要删除用户 <strong>{{ deleteUserTarget?.username }}</strong> 吗？
          </p>
          <p class="delete-warning">此操作不可恢复！</p>
        </div>
        <div class="modal-footer">
          <button class="btn-cancel" @click="showDeleteConfirmDialog = false">取消</button>
          <button class="btn-danger" :disabled="isDeletingUser" @click="handleDeleteUser">
            {{ isDeletingUser ? '删除中...' : '删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, onMounted } from 'vue'
  import { api } from '@/utils/api/index'
  import { useUserStore } from '@/stores/user'

  const userStore = useUserStore()

  // 头部显示状态
  const showHeader = ref(true)

  // 筛选器显示状态
  const showFilters = ref(true)

  // 用户数据
  const users = ref([])
  const usersLoading = ref(false)
  const usersError = ref('')
  const userFilters = ref({
    keyword: '',
    permission_level: '',
    sort_by: 'created_at',
    sort_order: 'desc'
  })
  const userPagination = ref({
    total: 0,
    page: 1,
    page_size: 10
  })

  // 创建用户对话框
  const showCreateUserDialog = ref(false)
  const createUserForm = ref({
    username: '',
    email: '',
    password: '',
    permission_level: 'normal'
  })
  const isCreatingUser = ref(false)
  const createUserError = ref('')

  // 编辑用户对话框
  const showEditUserDialog = ref(false)
  const editUserForm = ref({
    username: '',
    email: '',
    permission_level: ''
  })
  const isUpdatingUser = ref(false)
  const editUserError = ref('')
  const currentEditUserId = ref(null)

  // 重置密码对话框
  const showResetPasswordDialog = ref(false)
  const resetPasswordForm = ref({
    new_password: ''
  })
  const isResettingPassword = ref(false)
  const resetPasswordError = ref('')
  const resetPasswordUser = ref(null)

  // 删除用户确认对话框
  const showDeleteConfirmDialog = ref(false)
  const isDeletingUser = ref(false)
  const deleteUserTarget = ref(null)

  // 获取用户列表
  const fetchUsers = async () => {
    usersLoading.value = true
    usersError.value = ''

    try {
      const params = {
        page: userPagination.value.page,
        page_size: userPagination.value.page_size,
        sort_by: userFilters.value.sort_by,
        sort_order: userFilters.value.sort_order
      }

      if (userFilters.value.keyword) {
        params.keyword = userFilters.value.keyword
      }

      if (userFilters.value.permission_level) {
        params.permission_level = userFilters.value.permission_level
      }

      const data = await api.getUsers(params)

      if (data) {
        users.value = data.users
        userPagination.value.total = data.total
        userPagination.value.page = data.page
        userPagination.value.page_size = data.page_size
      } else {
        usersError.value = '获取用户列表失败'
      }
    } catch (error) {
      console.error('获取用户列表出错:', error)
      usersError.value = '网络错误，请稍后重试'
    } finally {
      usersLoading.value = false
    }
  }

  // 防抖搜索
  let debounceTimer = null
  const debouncedFetchUsers = () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    debounceTimer = setTimeout(() => {
      userPagination.value.page = 1
      fetchUsers()
    }, 500)
  }

  // 计算总页数
  const totalPages = computed(() => {
    return Math.ceil(userPagination.value.total / userPagination.value.page_size)
  })

  // 切换页面
  const changePage = page => {
    if (page >= 1 && page <= totalPages.value) {
      userPagination.value.page = page
      fetchUsers()
    }
  }

  // 获取权限级别显示标签
  const getPermissionLabel = level => {
    const labels = {
      normal: '[USER] Normal',
      admin: '[ADMIN] Admin',
      superadmin: '[SUPER] Super Admin'
    }
    return labels[level] || '[USER] Normal'
  }

  // 格式化日期
  const formatDate = dateStr => {
    if (!dateStr) return '-'
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // 创建用户
  const handleCreateUser = async () => {
    if (
      !createUserForm.value.username ||
      !createUserForm.value.email ||
      !createUserForm.value.password
    ) {
      createUserError.value = '请填写所有必填字段'
      return
    }

    if (createUserForm.value.password.length < 6) {
      createUserError.value = '密码至少需要6位'
      return
    }

    isCreatingUser.value = true
    createUserError.value = ''

    try {
      const result = await api.createUser(createUserForm.value)

      if (result) {
        alert('用户创建成功')
        showCreateUserDialog.value = false
        // 重置表单
        createUserForm.value = {
          username: '',
          email: '',
          password: '',
          permission_level: 'normal'
        }
        // 刷新用户列表
        fetchUsers()
      } else {
        createUserError.value = '创建用户失败，请稍后重试'
      }
    } catch (error) {
      console.error('创建用户出错:', error)
      createUserError.value = '创建用户失败，请稍后重试'
    } finally {
      isCreatingUser.value = false
    }
  }

  // 打开编辑用户对话框
  const openEditUser = user => {
    currentEditUserId.value = user.id
    editUserForm.value = {
      username: user.username,
      email: user.email,
      permission_level: user.permission_level
    }
    editUserError.value = ''
    showEditUserDialog.value = true
  }

  // 更新用户
  const handleUpdateUser = async () => {
    if (!editUserForm.value.username || !editUserForm.value.email) {
      editUserError.value = '用户名和邮箱不能为空'
      return
    }

    isUpdatingUser.value = true
    editUserError.value = ''

    try {
      const result = await api.updateUser(currentEditUserId.value, editUserForm.value)

      if (result) {
        alert('用户信息更新成功')
        showEditUserDialog.value = false
        // 刷新用户列表
        fetchUsers()
      } else {
        editUserError.value = '更新用户失败，请稍后重试'
      }
    } catch (error) {
      console.error('更新用户出错:', error)
      editUserError.value = '更新用户失败，请稍后重试'
    } finally {
      isUpdatingUser.value = false
    }
  }

  // 打开重置密码对话框
  const openResetPassword = user => {
    resetPasswordUser.value = user
    resetPasswordForm.value = {
      new_password: ''
    }
    resetPasswordError.value = ''
    showResetPasswordDialog.value = true
  }

  // 重置用户密码
  const handleResetPassword = async () => {
    if (!resetPasswordForm.value.new_password) {
      resetPasswordError.value = '请输入新密码'
      return
    }

    if (resetPasswordForm.value.new_password.length < 6) {
      resetPasswordError.value = '密码至少需要6位'
      return
    }

    isResettingPassword.value = true
    resetPasswordError.value = ''

    try {
      const result = await api.resetUserPassword(
        resetPasswordUser.value.id,
        resetPasswordForm.value.new_password
      )

      if (result) {
        alert('密码重置成功，请通知用户重新登录')
        showResetPasswordDialog.value = false
      } else {
        resetPasswordError.value = '重置密码失败，请稍后重试'
      }
    } catch (error) {
      console.error('重置密码出错:', error)
      resetPasswordError.value = '重置密码失败，请稍后重试'
    } finally {
      isResettingPassword.value = false
    }
  }

  // 确认删除用户
  const confirmDeleteUser = user => {
    deleteUserTarget.value = user
    showDeleteConfirmDialog.value = true
  }

  // 删除用户
  const handleDeleteUser = async () => {
    if (!deleteUserTarget.value) return

    isDeletingUser.value = true

    try {
      const success = await api.deleteUser(deleteUserTarget.value.id)

      if (success) {
        alert('用户删除成功')
        showDeleteConfirmDialog.value = false
        deleteUserTarget.value = null
        // 刷新用户列表
        fetchUsers()
      } else {
        alert('删除用户失败，请稍后重试')
      }
    } catch (error) {
      console.error('删除用户出错:', error)
      alert('删除用户失败，请稍后重试')
    } finally {
      isDeletingUser.value = false
    }
  }

  // 组件挂载时加载数据
  onMounted(() => {
    fetchUsers()
  })
</script>

<style scoped>
  .user-management {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(248, 250, 252, 0.7) 100%);
    padding: 24px;
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
  }

  /* 头部切换按钮 */
  .section-header-toggle {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding: 12px 20px;
    background: linear-gradient(135deg, rgba(102, 126, 234, 0.08) 0%, rgba(118, 75, 162, 0.1) 100%);
    border-radius: 14px;
    border: 1px solid rgba(102, 126, 234, 0.2);
    backdrop-filter: blur(10px);
    transition: all 0.3s ease;
  }

  .section-header-toggle:hover {
    border-color: rgba(102, 126, 234, 0.3);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
  }

  .header-toggle-btn {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 18px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
  }

  .header-toggle-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.45);
  }

  .header-toggle-btn .toggle-icon {
    font-size: 12px;
    transition: transform 0.3s ease;
  }

  .create-user-mini-btn {
    width: 44px;
    height: 44px;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
    color: white;
    box-shadow: 0 4px 12px rgba(72, 187, 120, 0.35);
  }

  .create-user-mini-btn:hover {
    transform: translateY(-2px) scale(1.05);
    box-shadow: 0 6px 20px rgba(72, 187, 120, 0.45);
  }

  .create-user-mini-btn .icon {
    font-size: 20px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
    padding: 20px 24px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    border-radius: 16px;
    box-shadow: 0 8px 24px rgba(102, 126, 234, 0.3);
    transition: all 0.3s ease;
    overflow: hidden;
    max-height: 80px;
  }

  .section-header.collapsed {
    padding: 0;
    margin-bottom: 0;
    max-height: 0;
    opacity: 0;
  }

  .section-header h3 {
    margin: 0;
    font-size: 22px;
    color: white;
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 600;
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;
  }

  .section-header.collapsed h3 {
    opacity: 0;
    transform: translateY(-20px);
  }

  .section-header .icon {
    font-size: 26px;
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
  }

  /* 创建用户按钮 */
  .create-user-btn {
    padding: 12px 28px;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  .create-user-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
  }

  .create-user-btn .icon {
    font-size: 18px;
  }

  /* 筛选器切换按钮 */
  .filter-toggle-wrapper {
    margin-bottom: 16px;
  }

  .filter-toggle-btn {
    width: 100%;
    padding: 14px 20px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .filter-toggle-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .filter-toggle-btn .toggle-icon {
    font-size: 18px;
    transition: transform 0.3s ease;
  }

  .filter-toggle-btn .toggle-icon.active {
    transform: rotate(90deg);
  }

  .filter-toggle-btn .arrow-icon {
    font-size: 12px;
    transition: transform 0.3s ease;
  }

  .filter-toggle-btn .arrow-icon.open {
    transform: rotate(180deg);
  }

  /* 用户筛选器 */
  .users-filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
    padding: 24px 28px;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    border-radius: 20px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.5);
    transition: all 0.3s ease;
    overflow: hidden;
  }

  .users-filters.collapsed {
    padding: 0;
    margin-bottom: 0;
    grid-template-rows: 0fr;
    gap: 0;
  }

  .users-filters.collapsed .filter-group {
    display: none;
  }

  .users-filters .filter-group {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .users-filters .filter-group label {
    font-size: 13px;
    font-weight: 700;
    color: #4a5568;
    white-space: nowrap;
    min-width: 70px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .users-filters .filter-group input,
  .users-filters .filter-group select {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid rgba(203, 213, 225, 0.6);
    border-radius: 10px;
    font-size: 14px;
    color: #2d3748;
    background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%);
    transition: all 0.3s ease;
    outline: none;
    font-weight: 500;
  }

  .users-filters .filter-group input:hover,
  .users-filters .filter-group select:hover {
    border-color: #a78bfa;
    background: white;
  }

  .users-filters .filter-group input:focus,
  .users-filters .filter-group select:focus {
    border-color: #a78bfa;
    box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.15);
    background: white;
    transform: translateY(-1px);
  }

  .users-filters .filter-group select {
    cursor: pointer;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    background-size: 16px;
    padding-right: 36px;
    appearance: none;
  }

  /* 用户列表内容 */
  .users-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 24px;
    overflow: hidden;
    padding: 0;
  }

  .users-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 20px;
    overflow-y: auto;
    padding-right: 12px;
    padding-left: 4px;
  }

  .users-list::-webkit-scrollbar {
    width: 6px;
  }

  .users-list::-webkit-scrollbar-track {
    background: rgba(229, 231, 235, 0.4);
    border-radius: 3px;
  }

  .users-list::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #a78bfa 0%, #8b5cf6 100%);
    border-radius: 3px;
    transition: all 0.3s ease;
  }

  .users-list::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
  }

  /* 用户卡片 */
  .user-card {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 28px 32px;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.5);
    border-radius: 20px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
    animation: cardSlideIn 0.4s ease-out;
  }

  @keyframes cardSlideIn {
    from {
      opacity: 0;
      transform: translateX(-20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .user-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #0d9488 0%, #14b8a6 50%, #0d9488 100%);
    background-size: 200% 100%;
    animation: cardShimmer 3s ease-in-out infinite;
    opacity: 0;
    transition: opacity 0.35s ease;
  }

  @keyframes cardShimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }

  .user-card:hover::before {
    opacity: 1;
  }

  .user-card:hover {
    transform: translateX(8px) translateY(-4px);
    box-shadow: 0 12px 40px rgba(102, 126, 234, 0.25);
    border-color: rgba(167, 139, 250, 0.5);
  }

  .user-info {
    flex: 1;
    display: flex;
    gap: 20px;
    align-items: center;
  }

  /* 用户头像 */
  .user-avatar {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    font-weight: 700;
    color: white;
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.35);
    flex-shrink: 0;
    border: 3px solid rgba(102, 126, 234, 0.25);
    transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  .user-card:hover .user-avatar {
    transform: scale(1.15) rotate(8deg);
    box-shadow: 0 8px 32px rgba(102, 126, 234, 0.5);
  }

  .user-avatar .avatar-text {
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  }

  /* 用户操作按钮 */
  .user-actions {
    display: flex;
    gap: 12px;
  }

  .action-btn {
    width: 48px;
    height: 48px;
    border: 2px solid;
    border-radius: 14px;
    cursor: pointer;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  .action-btn:hover:not(:disabled) {
    transform: translateY(-4px) scale(1.1);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  }

  .action-btn.edit {
    border-color: rgba(59, 130, 246, 0.4);
    color: #3b82f6;
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, rgba(37, 99, 235, 0.12) 100%);
  }

  .action-btn.edit:hover:not(:disabled) {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    border-color: #3b82f6;
    box-shadow: 0 8px 24px rgba(59, 130, 246, 0.45);
  }

  .action-btn.reset {
    border-color: rgba(245, 158, 11, 0.4);
    color: #f59e0b;
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(217, 119, 6, 0.12) 100%);
  }

  .action-btn.reset:hover:not(:disabled) {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: white;
    border-color: #f59e0b;
    box-shadow: 0 8px 24px rgba(245, 158, 11, 0.45);
  }

  .action-btn.delete {
    border-color: rgba(239, 68, 68, 0.4);
    color: #ef4444;
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(220, 38, 38, 0.12) 100%);
  }

  .action-btn.delete:hover:not(:disabled) {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: white;
    border-color: #ef4444;
    box-shadow: 0 8px 24px rgba(239, 68, 68, 0.45);
  }

  .action-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    transform: none !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06) !important;
  }

  .user-card:hover .user-avatar {
    transform: scale(1.1) rotate(5deg);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .user-avatar .avatar-text {
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  }

  /* 用户详细信息 */
  .user-details {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }

  .user-header-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .user-name {
    font-size: 22px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: -0.5px;
    flex-shrink: 0;
  }

  .user-permission {
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    transition: all 0.3s ease;
  }

  .user-permission.superadmin {
    background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
    color: #78350f;
    border: 2px solid rgba(251, 191, 36, 0.4);
    box-shadow: 0 2px 8px rgba(251, 191, 36, 0.3);
  }

  .user-permission.admin {
    background: linear-gradient(135deg, #34d399 0%, #10b981 100%);
    color: #064e3b;
    border: 2px solid rgba(16, 185, 129, 0.4);
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }

  .user-permission.normal {
    background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
    color: #1e3a8a;
    border: 2px solid rgba(59, 130, 246, 0.4);
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  }

  .user-email {
    font-size: 15px;
    color: #6b7280;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-radius: 8px;
    border: 1px solid rgba(229, 231, 235, 0.8);
    transition: all 0.3s ease;
    max-width: fit-content;
  }

  .user-card:hover .user-email {
    background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%);
    border-color: rgba(59, 130, 246, 0.3);
  }

  .user-email .email-icon {
    font-size: 16px;
    flex-shrink: 0;
  }

  .user-meta {
    display: flex;
    gap: 16px;
    font-size: 13px;
    color: #9ca3af;
    flex-wrap: wrap;
  }

  .user-meta .meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-radius: 6px;
    transition: all 0.3s ease;
  }

  .user-card:hover .user-meta .meta-item {
    transform: translateY(-2px);
    box-shadow: 0 2px 8px rgba(251, 191, 36, 0.3);
  }

  .user-meta .meta-icon {
    font-size: 14px;
    flex-shrink: 0;
  }

  /* 用户操作按钮 */
  .user-actions {
    display: flex;
    gap: 10px;
  }

  .action-btn {
    width: 44px;
    height: 44px;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s ease;
    background: white;
    border: 2px solid rgba(229, 231, 235, 0.8);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  }

  .action-btn:hover:not(:disabled) {
    transform: translateY(-3px) scale(1.05);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
  }

  .action-btn.edit {
    color: #3b82f6;
    border-color: rgba(59, 130, 246, 0.3);
  }

  .action-btn.edit:hover:not(:disabled) {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    border-color: #3b82f6;
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
  }

  .action-btn.reset {
    color: #f59e0b;
    border-color: rgba(251, 191, 36, 0.3);
  }

  .action-btn.reset:hover:not(:disabled) {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: white;
    border-color: #f59e0b;
    box-shadow: 0 6px 20px rgba(251, 191, 36, 0.4);
  }

  .action-btn.delete {
    color: #ef4444;
    border-color: rgba(239, 68, 68, 0.3);
  }

  .action-btn.delete:hover:not(:disabled) {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: white;
    border-color: #ef4444;
    box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
  }

  .action-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none !important;
  }

  .action-btn:disabled:hover {
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06) !important;
    transform: none !important;
  }

  /* 分页控件 */
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 20px;
    padding: 20px 28px;
    background: white;
    border-radius: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    border: 1px solid rgba(229, 231, 235, 0.8);
  }

  .page-btn {
    padding: 12px 28px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    font-size: 15px;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  }

  .page-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
  }

  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
    transform: none !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06) !important;
  }

  .page-info {
    font-size: 15px;
    color: #4b5563;
    font-weight: 600;
    padding: 0 8px;
  }

  /* 空状态 */
  .empty-users {
    text-align: center;
    padding: 100px 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 24px;
    flex: 1;
    background: white;
    border-radius: 20px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
    border: 2px dashed rgba(229, 231, 235, 0.8);
  }

  .empty-users .icon {
    font-size: 96px;
    opacity: 0.4;
    filter: grayscale(30%);
  }

  .empty-users p {
    margin: 0;
    font-size: 18px;
    color: #9ca3af;
    font-weight: 600;
  }

  /* 模态框样式 */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.3s ease-out;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  .modal-content {
    background: white;
    border-radius: 20px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    max-width: 500px;
    width: 90%;
    animation: slideDown 0.3s ease-out;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 24px 28px;
    border-bottom: 1px solid #e5e7eb;
  }

  .modal-header h3 {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: #1f2937;
  }

  .modal-header .close-btn {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 50%;
    background: #f3f4f6;
    cursor: pointer;
    font-size: 24px;
    line-height: 1;
    color: #6b7280;
    transition: all 0.3s ease;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .modal-header .close-btn:hover {
    background: #e5e7eb;
    color: #1f2937;
  }

  .modal-body {
    padding: 28px;
  }

  .form-group {
    margin-bottom: 20px;
  }

  .form-group label {
    display: block;
    margin-bottom: 8px;
    font-size: 14px;
    font-weight: 600;
    color: #4b5563;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    padding: 12px 16px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    font-size: 14px;
    color: #1f2937;
    transition: all 0.3s ease;
    outline: none;
  }

  .form-group input:hover,
  .form-group select:hover {
    border-color: #a78bfa;
  }

  .form-group input:focus,
  .form-group select:focus {
    border-color: #7c3aed;
    box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
  }

  .form-group select {
    cursor: pointer;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    background-size: 16px;
    padding-right: 40px;
    appearance: none;
  }

  .error-message {
    margin-top: 16px;
    padding: 12px 16px;
    background: #fee2e2;
    color: #991b1b;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
  }

  .reset-user-info {
    margin: 0 0 20px 0;
    padding: 16px;
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    color: #92400e;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
  }

  .delete-confirm-text {
    margin: 0 0 12px 0;
    font-size: 16px;
    color: #4b5563;
  }

  .delete-warning {
    margin: 0;
    font-size: 14px;
    color: #dc2626;
    font-weight: 600;
  }

  .modal-footer {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
    padding: 24px 28px;
    border-top: 1px solid #e5e7eb;
  }

  .btn-cancel,
  .btn-primary,
  .btn-danger {
    padding: 12px 24px;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.3s ease;
  }

  .btn-cancel {
    background: #f3f4f6;
    color: #4b5563;
  }

  .btn-cancel:hover {
    background: #e5e7eb;
    transform: translateY(-2px);
  }

  .btn-primary {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-danger {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
    color: white;
  }

  .btn-danger:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
  }

  .btn-danger:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* 加载和错误状态 */
  .loading-state,
  .error-state {
    text-align: center;
    padding: 80px 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
  }

  .loading-state p,
  .error-state p {
    margin: 0;
    font-size: 16px;
    color: #6b7280;
    font-weight: 500;
  }

  .retry-btn {
    padding: 10px 24px;
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
    color: white;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.3s ease;
  }

  .retry-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  /* 响应式设计 */
  @media (max-width: 768px) {
    .users-filters {
      grid-template-columns: 1fr;
    }

    .user-info {
      flex-direction: column;
      gap: 16px;
      text-align: center;
    }

    .user-avatar {
      width: 60px;
      height: 60px;
      font-size: 24px;
    }

    .user-header-row {
      justify-content: center;
    }

    .user-email {
      justify-content: center;
      width: 100%;
      max-width: none;
    }

    .user-meta {
      justify-content: center;
    }

    .user-card {
      flex-direction: column;
      align-items: center;
      padding: 20px;
    }

    .user-details {
      width: 100%;
    }

    .user-actions {
      width: 100%;
      justify-content: center;
    }

    .pagination {
      flex-direction: column;
      gap: 12px;
    }
  }
</style>
