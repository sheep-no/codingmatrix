<template>
  <div class="user-management">
    <!-- 头部 -->
    <div class="section-header-toggle">
      <button class="header-toggle-btn" @click="showHeader = !showHeader">
        <svg class="toggle-icon" :class="{ collapsed: !showHeader }" viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><path d="M4.646 5.646a.5.5 0 01.708 0L8 8.293l2.646-2.647a.5.5 0 01.708.708l-3 3a.5.5 0 01-.708 0l-3-3a.5.5 0 010-.708z"/></svg>
        <span>管理面板</span>
      </button>
      <button class="create-user-mini-btn" title="创建用户" @click="showCreateUserDialog = true">
        <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16"><path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1h-3v3a.5.5 0 01-1 0v-3h-3a.5.5 0 010-1h3v-3A.5.5 0 018 4z"/></svg>
      </button>
    </div>

    <div class="section-header" :class="{ collapsed: !showHeader }">
      <h3>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="22" height="22"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
        用户管理
      </h3>
      <button class="create-user-btn" @click="showCreateUserDialog = true">
        <svg viewBox="0 0 16 16" fill="currentColor" width="14" height="14"><path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1h-3v3a.5.5 0 01-1 0v-3h-3a.5.5 0 010-1h3v-3A.5.5 0 018 4z"/></svg>
        创建用户
      </button>
    </div>

    <!-- 用户筛选和搜索 -->
    <div v-if="showHeader" class="filter-toggle-wrapper">
      <button class="filter-toggle-btn" @click="showFilters = !showFilters">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <span>筛选和搜索</span>
        <svg class="arrow-icon" :class="{ open: showFilters }" viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><path d="M4.646 5.646a.5.5 0 01.708 0L8 8.293l2.646-2.647a.5.5 0 01.708.708l-3 3a.5.5 0 01-.708 0l-3-3a.5.5 0 010-.708z"/></svg>
      </button>
    </div>
    <div class="users-filters" :class="{ collapsed: !showFilters }">
      <div class="filter-group">
        <label>搜索</label>
        <input v-model="userFilters.keyword" type="text" placeholder="用户名或邮箱..." @input="debouncedFetchUsers" />
      </div>
      <div class="filter-group">
        <label>权限</label>
        <select v-model="userFilters.permission_level" @change="fetchUsers">
          <option value="">全部</option>
          <option value="normal">普通用户</option>
          <option value="admin">管理员</option>
          <option value="superadmin">超级管理员</option>
        </select>
      </div>
      <div class="filter-group">
        <label>排序</label>
        <select v-model="userFilters.sort_by" @change="fetchUsers">
          <option value="id">ID</option>
          <option value="username">用户名</option>
          <option value="email">邮箱</option>
          <option value="created_at">创建时间</option>
        </select>
      </div>
      <div class="filter-group">
        <label>方向</label>
        <select v-model="userFilters.sort_order" @change="fetchUsers">
          <option value="desc">降序</option>
          <option value="asc">升序</option>
        </select>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="users-content">
      <div v-if="usersLoading" class="status-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>
      <div v-else-if="usersError" class="status-state">
        <p class="error-text">{{ usersError }}</p>
        <button class="retry-btn" @click="fetchUsers">重试</button>
      </div>
      <div v-else-if="users.length === 0" class="status-state empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="64" height="64" opacity="0.3"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
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
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 7L2 7"/></svg>
                {{ user.email }}
              </div>
              <div class="user-meta">
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  ID: {{ user.id }}
                </span>
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
                  {{ formatDate(user.created_at) }}
                </span>
              </div>
            </div>
          </div>
          <div class="user-actions">
            <button class="action-btn edit" title="编辑" @click="openEditUser(user)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="action-btn reset" title="重置密码" @click="openResetPassword(user)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            </button>
            <button
              class="action-btn delete"
              title="删除"
              :disabled="user.id === userStore.userId"
              @click="confirmDeleteUser(user)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 分页控件 -->
      <div v-if="userPagination.total > 0" class="pagination">
        <button class="page-btn" :disabled="userPagination.page === 1" @click="changePage(userPagination.page - 1)">上一页</button>
        <span class="page-info">第 {{ userPagination.page }} / {{ totalPages }} 页 ({{ userPagination.total }} 条)</span>
        <button class="page-btn" :disabled="userPagination.page >= totalPages" @click="changePage(userPagination.page + 1)">下一页</button>
      </div>
    </div>

    <!-- 创建用户对话框 -->
    <div v-if="showCreateUserDialog" class="modal-overlay" @click.self="showCreateUserDialog = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>创建用户</h3>
          <button class="close-btn" @click="showCreateUserDialog = false">&times;</button>
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
          <button class="close-btn" @click="showEditUserDialog = false">&times;</button>
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
    <div v-if="showResetPasswordDialog" class="modal-overlay" @click.self="showResetPasswordDialog = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>重置密码</h3>
          <button class="close-btn" @click="showResetPasswordDialog = false">&times;</button>
        </div>
        <div class="modal-body">
          <p class="reset-user-info">为用户 <strong>{{ resetPasswordUser?.username }}</strong> 重置密码</p>
          <div class="form-group">
            <label>新密码 * (至少6位)</label>
            <input v-model="resetPasswordForm.new_password" type="password" placeholder="请输入新密码" />
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
    <div v-if="showDeleteConfirmDialog" class="modal-overlay" @click.self="showDeleteConfirmDialog = false">
      <div class="modal-content modal-sm">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="close-btn" @click="showDeleteConfirmDialog = false">&times;</button>
        </div>
        <div class="modal-body">
          <p class="delete-confirm-text">确定要删除用户 <strong>{{ deleteUserTarget?.username }}</strong> 吗？</p>
          <p class="delete-warning">此操作不可恢复</p>
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
import { ElMessage } from 'element-plus'
import { api } from '@/utils/api/index'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const showHeader = ref(true)
const showFilters = ref(true)

// 用户数据
const users = ref([])
const usersLoading = ref(false)
const usersError = ref('')
const userFilters = ref({ keyword: '', permission_level: '', sort_by: 'created_at', sort_order: 'desc' })
const userPagination = ref({ total: 0, page: 1, page_size: 10 })

// 创建用户
const showCreateUserDialog = ref(false)
const createUserForm = ref({ username: '', email: '', password: '', permission_level: 'normal' })
const isCreatingUser = ref(false)
const createUserError = ref('')

// 编辑用户
const showEditUserDialog = ref(false)
const editUserForm = ref({ username: '', email: '', permission_level: '' })
const isUpdatingUser = ref(false)
const editUserError = ref('')
const currentEditUserId = ref(null)

// 重置密码
const showResetPasswordDialog = ref(false)
const resetPasswordForm = ref({ new_password: '' })
const isResettingPassword = ref(false)
const resetPasswordError = ref('')
const resetPasswordUser = ref(null)

// 删除用户
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
    if (userFilters.value.keyword) params.keyword = userFilters.value.keyword
    if (userFilters.value.permission_level) params.permission_level = userFilters.value.permission_level

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
    usersError.value = '网络错误，请稍后重试'
  } finally {
    usersLoading.value = false
  }
}

let debounceTimer = null
const debouncedFetchUsers = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { userPagination.value.page = 1; fetchUsers() }, 500)
}

const totalPages = computed(() => Math.ceil(userPagination.value.total / userPagination.value.page_size))

const changePage = page => {
  if (page >= 1 && page <= totalPages.value) { userPagination.value.page = page; fetchUsers() }
}

const getPermissionLabel = level => {
  const labels = { normal: '普通用户', admin: '管理员', superadmin: '超级管理员' }
  return labels[level] || '普通用户'
}

const formatDate = dateStr => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const handleCreateUser = async () => {
  if (!createUserForm.value.username || !createUserForm.value.email || !createUserForm.value.password) {
    createUserError.value = '请填写所有必填字段'; return
  }
  if (createUserForm.value.password.length < 6) {
    createUserError.value = '密码至少需要6位'; return
  }
  isCreatingUser.value = true
  createUserError.value = ''
  try {
    const result = await api.createUser(createUserForm.value)
    if (result) {
      ElMessage.success('用户创建成功')
      showCreateUserDialog.value = false
      createUserForm.value = { username: '', email: '', password: '', permission_level: 'normal' }
      fetchUsers()
    } else {
      createUserError.value = '创建用户失败，请稍后重试'
    }
  } catch (error) {
    createUserError.value = '创建用户失败，请稍后重试'
  } finally {
    isCreatingUser.value = false
  }
}

const openEditUser = user => {
  currentEditUserId.value = user.id
  editUserForm.value = { username: user.username, email: user.email, permission_level: user.permission_level }
  editUserError.value = ''
  showEditUserDialog.value = true
}

const handleUpdateUser = async () => {
  if (!editUserForm.value.username || !editUserForm.value.email) {
    editUserError.value = '用户名和邮箱不能为空'; return
  }
  isUpdatingUser.value = true
  editUserError.value = ''
  try {
    const result = await api.updateUser(currentEditUserId.value, editUserForm.value)
    if (result) {
      ElMessage.success('用户信息更新成功')
      showEditUserDialog.value = false
      fetchUsers()
    } else {
      editUserError.value = '更新用户失败，请稍后重试'
    }
  } catch (error) {
    editUserError.value = '更新用户失败，请稍后重试'
  } finally {
    isUpdatingUser.value = false
  }
}

const openResetPassword = user => {
  resetPasswordUser.value = user
  resetPasswordForm.value = { new_password: '' }
  resetPasswordError.value = ''
  showResetPasswordDialog.value = true
}

const handleResetPassword = async () => {
  if (!resetPasswordForm.value.new_password) { resetPasswordError.value = '请输入新密码'; return }
  if (resetPasswordForm.value.new_password.length < 6) { resetPasswordError.value = '密码至少需要6位'; return }
  isResettingPassword.value = true
  resetPasswordError.value = ''
  try {
    const result = await api.resetUserPassword(resetPasswordUser.value.id, resetPasswordForm.value.new_password)
    if (result) {
      ElMessage.success('密码重置成功，请通知用户重新登录')
      showResetPasswordDialog.value = false
    } else {
      resetPasswordError.value = '重置密码失败，请稍后重试'
    }
  } catch (error) {
    resetPasswordError.value = '重置密码失败，请稍后重试'
  } finally {
    isResettingPassword.value = false
  }
}

const confirmDeleteUser = user => {
  deleteUserTarget.value = user
  showDeleteConfirmDialog.value = true
}

const handleDeleteUser = async () => {
  if (!deleteUserTarget.value) return
  isDeletingUser.value = true
  try {
    const success = await api.deleteUser(deleteUserTarget.value.id)
    if (success) {
      ElMessage.success('用户已删除')
      showDeleteConfirmDialog.value = false
      deleteUserTarget.value = null
      fetchUsers()
    } else {
      ElMessage.error('删除用户失败')
    }
  } catch (error) {
    ElMessage.error('删除用户失败')
  } finally {
    isDeletingUser.value = false
  }
}

onMounted(() => { fetchUsers() })
</script>

<style scoped>
/* ==================== 容器 ==================== */
.user-management {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  padding: 20px;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  gap: 16px;
}

/* ==================== 头部 ==================== */
.section-header-toggle {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: color-mix(in srgb, var(--primary), transparent 92%);
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--primary), transparent 80%);
}

.header-toggle-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s;
}
.header-toggle-btn:hover { opacity: 0.9; transform: translateY(-1px); }
.header-toggle-btn .toggle-icon { transition: transform 0.2s; }
.header-toggle-btn .toggle-icon.collapsed { transform: rotate(-90deg); }

.create-user-mini-btn {
  width: 36px; height: 36px;
  border: none; border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: var(--success, #10b981);
  color: white;
  transition: all 0.2s;
}
.create-user-mini-btn:hover { opacity: 0.9; transform: scale(1.05); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px;
  background: var(--primary);
  border-radius: 12px;
  transition: all 0.3s;
  max-height: 64px;
  overflow: hidden;
}
.section-header.collapsed { max-height: 0; padding: 0; margin: 0; opacity: 0; }
.section-header h3 {
  margin: 0; font-size: 18px; color: white;
  display: flex; align-items: center; gap: 10px; font-weight: 600;
}

.create-user-btn {
  padding: 8px 20px; background: var(--success, #10b981); color: white;
  border: none; border-radius: 8px; cursor: pointer;
  font-size: 14px; font-weight: 600;
  display: flex; align-items: center; gap: 6px;
  transition: all 0.2s;
}
.create-user-btn:hover { opacity: 0.9; transform: translateY(-1px); }

/* ==================== 筛选器 ==================== */
.filter-toggle-wrapper { margin-bottom: 0; }

.filter-toggle-btn {
  width: 100%; padding: 10px 16px;
  background: color-mix(in srgb, var(--primary), transparent 92%);
  color: var(--primary); border: 1px solid color-mix(in srgb, var(--primary), transparent 80%);
  border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 600;
  display: flex; align-items: center; gap: 8px; transition: all 0.2s;
}
.filter-toggle-btn:hover { background: color-mix(in srgb, var(--primary), transparent 85%); }
.filter-toggle-btn .arrow-icon { margin-left: auto; transition: transform 0.2s; }
.filter-toggle-btn .arrow-icon.open { transform: rotate(180deg); }

.users-filters {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px; padding: 16px; background: var(--bg-secondary);
  border-radius: 12px; border: 1px solid var(--border-color);
  transition: all 0.3s; overflow: hidden;
}
.users-filters.collapsed { padding: 0; height: 0; border: none; }

.filter-group { display: flex; align-items: center; gap: 10px; }
.filter-group label {
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
  white-space: nowrap; min-width: 40px;
}
.filter-group input,
.filter-group select {
  flex: 1; padding: 8px 12px; border: 1px solid var(--border-color);
  border-radius: 8px; font-size: 13px; color: var(--text-primary);
  background: var(--bg-primary); transition: border-color 0.2s; outline: none;
}
.filter-group input:focus,
.filter-group select:focus { border-color: var(--primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary), transparent 85%); }
.filter-group select {
  cursor: pointer; appearance: none; padding-right: 32px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center; background-size: 14px;
}

/* ==================== 用户列表 ==================== */
.users-content { flex: 1; display: flex; flex-direction: column; gap: 16px; overflow: hidden; }

.users-list {
  flex: 1; display: flex; flex-direction: column; gap: 12px;
  overflow-y: auto; padding-right: 4px;
}
.users-list::-webkit-scrollbar { width: 5px; }
.users-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }
.users-list::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }

/* ==================== 用户卡片 ==================== */
.user-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; background: var(--bg-primary);
  border: 1px solid var(--border-color); border-radius: 12px;
  transition: all 0.2s;
}
.user-card:hover {
  border-color: color-mix(in srgb, var(--primary), transparent 60%);
  box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}

.user-info { flex: 1; display: flex; gap: 16px; align-items: center; }

.user-avatar {
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--primary); color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; font-weight: 700; flex-shrink: 0;
  transition: transform 0.2s;
}
.user-card:hover .user-avatar { transform: scale(1.08); }

.user-details { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.user-header-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.user-name { font-size: 16px; font-weight: 700; color: var(--text-primary); }

.user-permission {
  padding: 2px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600;
}
.user-permission.superadmin { background: color-mix(in srgb, var(--warning, #f59e0b), transparent 85%); color: var(--warning, #d97706); }
.user-permission.admin { background: color-mix(in srgb, var(--success, #10b981), transparent 85%); color: var(--success, #059669); }
.user-permission.normal { background: color-mix(in srgb, var(--primary), transparent 88%); color: var(--primary); }

.user-email {
  font-size: 13px; color: var(--text-tertiary);
  display: flex; align-items: center; gap: 6px;
  max-width: fit-content;
}

.user-meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-tertiary); flex-wrap: wrap; }
.user-meta .meta-item { display: flex; align-items: center; gap: 4px; }

/* ==================== 操作按钮 ==================== */
.user-actions { display: flex; gap: 8px; }
.action-btn {
  width: 36px; height: 36px; border: 1px solid var(--border-color);
  border-radius: 8px; cursor: pointer; background: var(--bg-primary);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; color: var(--text-secondary);
}
.action-btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
.action-btn.edit:hover:not(:disabled) { background: var(--primary); color: white; border-color: var(--primary); }
.action-btn.reset:hover:not(:disabled) { background: var(--warning, #f59e0b); color: white; border-color: var(--warning, #f59e0b); }
.action-btn.delete:hover:not(:disabled) { background: var(--danger, #ef4444); color: white; border-color: var(--danger, #ef4444); }
.action-btn:disabled { opacity: 0.35; cursor: not-allowed; }

/* ==================== 分页 ==================== */
.pagination {
  display: flex; align-items: center; justify-content: center; gap: 16px;
  padding: 12px 20px; background: var(--bg-secondary);
  border-radius: 10px; border: 1px solid var(--border-color);
}
.page-btn {
  padding: 6px 16px; background: var(--primary); color: white;
  border: none; border-radius: 6px; cursor: pointer;
  font-size: 13px; font-weight: 600; transition: all 0.2s;
}
.page-btn:hover:not(:disabled) { opacity: 0.85; }
.page-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--text-secondary); }

/* ==================== 状态 ==================== */
.status-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px; padding: 60px 20px;
}
.status-state p { margin: 0; font-size: 15px; color: var(--text-tertiary); }
.status-state.empty { border: 2px dashed var(--border-color); border-radius: 12px; }
.error-text { color: var(--danger, #ef4444) !important; }

.spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.retry-btn {
  padding: 8px 20px; background: var(--primary); color: white;
  border: none; border-radius: 8px; cursor: pointer;
  font-size: 13px; font-weight: 600; transition: all 0.2s;
}
.retry-btn:hover { opacity: 0.85; }

/* ==================== 模态框 ==================== */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.45); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000; animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.modal-content {
  background: var(--bg-primary); border-radius: 16px;
  box-shadow: 0 16px 48px rgba(0,0,0,0.2);
  max-width: 480px; width: 90%;
  animation: slideDown 0.25s ease-out;
}
.modal-sm { max-width: 380px; }
@keyframes slideDown { from { opacity: 0; transform: translateY(-16px); } to { opacity: 1; transform: translateY(0); } }

.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid var(--border-color);
}
.modal-header h3 { margin: 0; font-size: 17px; font-weight: 700; color: var(--text-primary); }
.modal-header .close-btn {
  width: 28px; height: 28px; border: none; border-radius: 50%;
  background: var(--bg-tertiary); cursor: pointer; font-size: 20px;
  color: var(--text-tertiary); display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.modal-header .close-btn:hover { background: var(--border-color); color: var(--text-primary); }

.modal-body { padding: 20px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.form-group input,
.form-group select {
  width: 100%; padding: 10px 14px; border: 1px solid var(--border-color);
  border-radius: 8px; font-size: 14px; color: var(--text-primary);
  background: var(--bg-primary); transition: border-color 0.2s; outline: none;
  box-sizing: border-box;
}
.form-group input:focus,
.form-group select:focus { border-color: var(--primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary), transparent 85%); }
.form-group select {
  cursor: pointer; appearance: none; padding-right: 36px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%236b7280'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center; background-size: 14px;
}

.error-message {
  margin-top: 12px; padding: 10px 14px;
  background: color-mix(in srgb, var(--danger, #ef4444), transparent 88%);
  color: var(--danger, #dc2626); border-radius: 8px; font-size: 13px;
}
.reset-user-info {
  margin: 0 0 16px 0; padding: 12px 14px;
  background: color-mix(in srgb, var(--warning, #f59e0b), transparent 88%);
  color: var(--text-primary); border-radius: 8px; font-size: 14px;
}
.delete-confirm-text { margin: 0 0 8px 0; font-size: 15px; color: var(--text-secondary); }
.delete-warning { margin: 0; font-size: 13px; color: var(--danger, #ef4444); font-weight: 600; }

.modal-footer {
  display: flex; gap: 10px; justify-content: flex-end;
  padding: 16px 20px; border-top: 1px solid var(--border-color);
}
.btn-cancel, .btn-primary, .btn-danger {
  padding: 8px 20px; border: none; border-radius: 8px;
  cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s;
}
.btn-cancel { background: var(--bg-tertiary); color: var(--text-secondary); }
.btn-cancel:hover { background: var(--border-color); }
.btn-primary { background: var(--primary); color: white; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-danger { background: var(--danger, #ef4444); color: white; }
.btn-danger:hover:not(:disabled) { opacity: 0.9; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .user-card { flex-direction: column; align-items: flex-start; gap: 12px; }
  .user-actions { align-self: flex-end; }
}

@media (max-width: 768px) {
  .user-management { padding: 12px; }
  .users-filters { grid-template-columns: 1fr; }
  .user-card { padding: 14px; }
  .user-info { flex-direction: column; align-items: center; text-align: center; gap: 10px; }
  .user-header-row { justify-content: center; }
  .user-email { justify-content: center; width: 100%; max-width: none; }
  .user-meta { justify-content: center; }
  .user-actions { width: 100%; justify-content: center; }
  .pagination { flex-direction: column; gap: 8px; }
  .section-header { flex-direction: column; gap: 10px; text-align: center; }
}
</style>
