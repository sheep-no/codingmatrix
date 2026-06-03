<template>
  <div class="admin-dashboard">
    <!-- 顶部导航栏 -->
    <div class="admin-header">
      <div class="header-content">
        <div class="header-left">
          <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          <div>
            <h1 class="header-title">系统管理控制台</h1>
            <p class="header-subtitle">管理系统配置和用户并发限制</p>
          </div>
        </div>
        <div class="header-actions">
          <button class="btn btn-outline" @click="refreshAllData">
            <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M23 4v6h-6"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            刷新
          </button>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="admin-content">
      <!-- 统计概览 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon stat-icon-primary">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.totalUsers }}</div>
            <div class="stat-label">总用户数</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon stat-icon-success">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
              <line x1="1" y1="10" x2="23" y2="10"/>
            </svg>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.activeSessions }}</div>
            <div class="stat-label">活跃会话数</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon stat-icon-warning">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4"/>
              <path d="M12 18v4"/>
              <path d="M4.93 4.93l2.83 2.83"/>
              <path d="M16.24 16.24l2.83 2.83"/>
              <path d="M2 12h4"/>
              <path d="M18 12h4"/>
              <path d="M4.93 19.07l2.83-2.83"/>
              <path d="M16.24 7.76l2.83-2.83"/>
            </svg>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.customLimits }}</div>
            <div class="stat-label">自定义限制用户</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon stat-icon-info">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="16" x2="12" y2="12"/>
              <line x1="12" y1="8" x2="12.01" y2="8"/>
            </svg>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.configChanges }}</div>
            <div class="stat-label">配置变更次数</div>
          </div>
        </div>
      </div>

      <!-- 选项卡切换 -->
      <div class="tabs-container">
        <div class="tabs">
          <button 
            v-for="tab in tabs" 
            :key="tab.id"
            :class="['tab-btn', { active: activeTab === tab.id }]"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <!-- 用户并发限制管理 -->
      <div v-show="activeTab === 'user-limits'" class="tab-content">
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">用户并发限制管理</h3>
            <div class="panel-actions">
              <div class="search-box">
                <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="m21 21-4.35-4.35"/>
                </svg>
                <input 
                  v-model="userSearch" 
                  type="text" 
                  placeholder="搜索用户 ID 或用户名"
                  class="search-input"
                />
              </div>
            </div>
          </div>

          <div class="panel-body">
            <!-- 添加新用户限制 -->
            <div class="add-limit-form">
              <h4 class="form-title">添加用户限制</h4>
              <div class="form-row">
                <div class="form-group">
                  <label>用户 ID</label>
                  <input 
                    v-model="newLimit.userId" 
                    type="text" 
                    placeholder="输入用户 ID"
                    class="form-input"
                  />
                </div>
                <div class="form-group">
                  <label>并发限制数</label>
                  <input 
                    v-model.number="newLimit.limit" 
                    type="number" 
                    min="1"
                    max="100"
                    placeholder="1-100"
                    class="form-input"
                  />
                </div>
                <div class="form-group">
                  <label>限制类型</label>
                  <select v-model="newLimit.tier" class="form-select">
                    <option value="custom">自定义</option>
                    <option value="vip">VIP</option>
                    <option value="enterprise">企业版</option>
                  </select>
                </div>
                <div class="form-group form-actions">
                  <button class="btn btn-primary" :disabled="!isValidNewLimit" @click="addUserLimit">
                    <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <line x1="12" y1="5" x2="12" y2="19"/>
                      <line x1="5" y1="12" x2="19" y2="12"/>
                    </svg>
                    添加限制
                  </button>
                </div>
              </div>
            </div>

            <!-- 用户限制列表 -->
            <div class="data-table-wrapper">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>用户 ID</th>
                    <th>当前限制</th>
                    <th>限制类型</th>
                    <th>活跃会话</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="user in filteredUsers" :key="user.id">
                    <td>
                      <div class="user-cell">
                        <div class="user-avatar">{{ getUserInitial(user) }}</div>
                        <div>
                          <div class="user-name">{{ user.username || '未知用户' }}</div>
                          <div class="user-id">ID: {{ user.id }}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span class="limit-badge">{{ user.concurrentLimit }}</span>
                    </td>
                    <td>
                      <span :class="['tier-badge', getTierClass(user.tier)]">{{ getTierLabel(user.tier) }}</span>
                    </td>
                    <td>{{ user.activeSessions || 0 }}</td>
                    <td>
                      <span :class="['status-badge', user.activeSessions >= user.concurrentLimit ? 'status-warning' : 'status-success']">
                        {{ user.activeSessions >= user.concurrentLimit ? '已达上限' : '正常' }}
                      </span>
                    </td>
                    <td>
                      <div class="action-buttons">
                        <button class="btn-icon-sm" title="编辑" @click="editUserLimit(user)">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                          </svg>
                        </button>
                        <button class="btn-icon-sm btn-danger" title="移除" @click="removeUserLimit(user.id)">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="filteredUsers.length === 0">
                    <td colspan="6" class="empty-state">暂无用户数据</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- 角色默认限制配置 -->
      <div v-show="activeTab === 'role-limits'" class="tab-content">
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">角色默认限制配置</h3>
            <div class="panel-actions">
              <button class="btn btn-primary" :disabled="!roleLimitsDirty" @click="saveRoleLimits">
                <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17 21 17 13 7 13 7 21"/>
                  <polyline points="7 3 7 8 15 8"/>
                </svg>
                保存配置
              </button>
            </div>
          </div>

          <div class="panel-body">
            <div class="role-limits-grid">
              <div v-for="(limit, role) in roleLimits" :key="role" class="role-limit-card">
                <div class="role-header">
                  <div class="role-icon" :class="getRoleIconClass(role)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                      <circle cx="12" cy="7" r="4"/>
                    </svg>
                  </div>
                  <div class="role-info">
                    <div class="role-name">{{ getRoleName(role) }}</div>
                    <div class="role-key">{{ role }}</div>
                  </div>
                </div>
                <div class="role-limit-input">
                  <label>并发限制数</label>
                  <div class="input-with-unit">
                    <input 
                      v-model.number="roleLimits[role]" 
                      type="number" 
                      min="1"
                      max="100"
                      class="form-input"
                      @change="markRoleDirty"
                    />
                    <span class="input-unit">个</span>
                  </div>
                </div>
                <div class="role-description">
                  {{ getRoleDescription(role) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 系统配置 -->
      <div v-show="activeTab === 'system-config'" class="tab-content">
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">系统配置</h3>
            <div class="panel-actions">
              <button class="btn btn-primary" :disabled="!configDirty" @click="saveSystemConfig">
                <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                  <polyline points="17 21 17 13 7 13 7 21"/>
                  <polyline points="7 3 7 8 15 8"/>
                </svg>
                保存配置
              </button>
            </div>
          </div>

          <div class="panel-body">
            <div class="config-sections">
              <!-- 会话管理配置 -->
              <div class="config-section">
                <h4 class="config-section-title">会话管理</h4>
                <div class="config-grid">
                  <div class="config-item">
                    <label>启用会话清理</label>
                    <div class="toggle-wrapper">
                      <label class="toggle">
                        <input v-model="systemConfig.sessionManagement.cleanup_enabled" type="checkbox"/>
                        <span class="toggle-slider"></span>
                      </label>
                    </div>
                  </div>
                  <div class="config-item">
                    <label>最大活跃会话数</label>
                    <input 
                      v-model.number="systemConfig.sessionManagement.max_active_sessions" 
                      type="number" 
                      min="1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                  <div class="config-item">
                    <label>空闲超时（分钟）</label>
                    <input 
                      v-model.number="systemConfig.sessionManagement.idle_timeout_minutes" 
                      type="number" 
                      min="1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                </div>
              </div>

              <!-- PPT 生成配置 -->
              <div class="config-section">
                <h4 class="config-section-title">PPT 生成配置</h4>
                <div class="config-grid">
                  <div class="config-item">
                    <label>最大幻灯片数</label>
                    <input 
                      v-model.number="systemConfig.ppt_generation.max_slides" 
                      type="number" 
                      min="1"
                      max="100"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                  <div class="config-item full-width">
                    <label>支持的模板</label>
                    <div class="template-tags">
                      <span
v-for="template in systemConfig.ppt_generation.supported_templates" 
                          :key="template" 
                          class="template-tag">
                        {{ template }}
                        <button class="tag-remove" @click="removeTemplate(template)">x</button>
                      </span>
                      <div class="tag-add">
                        <input 
                          v-model="newTemplate" 
                          type="text" 
                          placeholder="添加模板"
                          class="tag-input"
                          @keyup.enter="addTemplate"
                        />
                        <button class="btn-icon-sm" @click="addTemplate">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="12" y1="5" x2="12" y2="19"/>
                            <line x1="5" y1="12" x2="19" y2="12"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 健康感知路由 -->
              <div class="config-section">
                <h4 class="config-section-title">健康感知路由</h4>
                <div class="config-grid">
                  <div class="config-item">
                    <label>启用健康检查</label>
                    <div class="toggle-wrapper">
                      <label class="toggle">
                        <input v-model="systemConfig.health_aware_routing.enabled" type="checkbox"/>
                        <span class="toggle-slider"></span>
                      </label>
                    </div>
                  </div>
                  <div class="config-item">
                    <label>系统过载阈值</label>
                    <input 
                      v-model.number="systemConfig.health_aware_routing.system_overload_threshold" 
                      type="number" 
                      min="0"
                      max="1"
                      step="0.1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                  <div class="config-item">
                    <label>模型负载权重</label>
                    <input 
                      v-model.number="systemConfig.health_aware_routing.model_load_weight" 
                      type="number" 
                      min="0"
                      max="1"
                      step="0.1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                  <div class="config-item">
                    <label>系统负载权重</label>
                    <input 
                      v-model.number="systemConfig.health_aware_routing.system_load_weight" 
                      type="number" 
                      min="0"
                      max="1"
                      step="0.1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                  <div class="config-item">
                    <label>最大并发请求数</label>
                    <input 
                      v-model.number="systemConfig.health_aware_routing.max_concurrent_requests" 
                      type="number" 
                      min="1"
                      class="form-input"
                      @change="configDirty = true"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 变更历史 -->
      <div v-show="activeTab === 'history'" class="tab-content">
        <div class="panel">
          <div class="panel-header">
            <h3 class="panel-title">配置变更历史</h3>
            <div class="panel-actions">
              <div class="limit-selector">
                <label>显示最近</label>
                <select v-model="historyLimit" class="form-select" @change="loadChangeHistory">
                  <option value="10">10 条</option>
                  <option value="50">50 条</option>
                  <option value="100">100 条</option>
                  <option value="200">200 条</option>
                </select>
              </div>
            </div>
          </div>

          <div class="panel-body">
            <div class="timeline">
              <div v-for="(record, index) in changeHistory" :key="index" class="timeline-item">
                <div class="timeline-dot"></div>
                <div class="timeline-content">
                  <div class="timeline-header">
                    <span class="timeline-role">{{ record.role || '系统' }}</span>
                    <span class="timeline-time">{{ formatTime(record.timestamp) }}</span>
                  </div>
                  <div class="timeline-body">
                    <p>
                      <span class="change-operator">{{ record.changed_by }}</span>
                      将限制从 
                      <span class="change-old">{{ record.old_limit }}</span>
                      修改为
                      <span class="change-new">{{ record.new_limit }}</span>
                    </p>
                    <p v-if="record.reason" class="timeline-reason">{{ record.reason }}</p>
                  </div>
                </div>
              </div>
              <div v-if="changeHistory.length === 0" class="empty-state">
                暂无变更记录
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑用户限制弹窗 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="closeEditModal">
      <div class="modal">
        <div class="modal-header">
          <h3>编辑用户限制</h3>
          <button class="modal-close" @click="closeEditModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户 ID</label>
            <input v-model="editingUser.userId" type="text" class="form-input" disabled/>
          </div>
          <div class="form-group">
            <label>新的限制数</label>
            <input v-model.number="editingUser.limit" type="number" min="1" max="100" class="form-input"/>
          </div>
          <div class="form-group">
            <label>限制类型</label>
            <select v-model="editingUser.tier" class="form-select">
              <option value="custom">自定义</option>
              <option value="vip">VIP</option>
              <option value="enterprise">企业版</option>
            </select>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeEditModal">取消</button>
          <button class="btn btn-primary" @click="confirmEditUser">保存</button>
        </div>
      </div>
    </div>

    <!-- 通知 -->
    <div v-if="notification.show" :class="['notification', notification.type]">
      <div class="notification-content">
        <svg v-if="notification.type === 'success'" class="notification-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <polyline points="22 4 12 14.01 9 11.01"/>
        </svg>
        <svg v-else-if="notification.type === 'error'" class="notification-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        <span>{{ notification.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { createAdminClient } from '@/utils/api/admin'
import { createClient } from '@/utils/api/client'

// API 客户端
const client = createClient()
const adminApi = createAdminClient(client)

// 响应式数据
const activeTab = ref('user-limits')
const userSearch = ref('')
const newTemplate = ref('')
const historyLimit = ref(50)
const showEditModal = ref(false)

const stats = reactive({
  totalUsers: 0,
  activeSessions: 0,
  customLimits: 0,
  configChanges: 0
})

const users = ref([])
const roleLimits = reactive({
  free: 1,
  basic: 2,
  premium: 5,
  enterprise: 10,
  superadmin: 50
})
const roleLimitsOriginal = ref({})
const roleLimitsDirty = ref(false)
const systemConfig = reactive({
  sessionManagement: {
    cleanup_enabled: true,
    max_active_sessions: 100,
    idle_timeout_minutes: 30
  },
  ppt_generation: {
    max_slides: 20,
    supported_templates: ['simple', 'business', 'creative']
  },
  health_aware_routing: {
    enabled: false,
    system_overload_threshold: 0.8,
    model_load_weight: 0.6,
    system_load_weight: 0.4,
    max_concurrent_requests: 100
  }
})
const configDirty = ref(false)
const changeHistory = ref([])

const newLimit = reactive({
  userId: '',
  limit: 1,
  tier: 'custom'
})

const editingUser = reactive({
  userId: '',
  limit: 1,
  tier: 'custom'
})

const notification = reactive({
  show: false,
  type: 'success',
  message: ''
})

// 选项卡
const tabs = [
  { id: 'user-limits', label: '用户限制' },
  { id: 'role-limits', label: '角色配置' },
  { id: 'system-config', label: '系统配置' },
  { id: 'history', label: '变更历史' }
]

// 计算属性
const filteredUsers = computed(() => {
  if (!userSearch.value) return users.value
  const search = userSearch.value.toLowerCase()
  return users.value.filter(user => 
    (user.username && user.username.toLowerCase().includes(search)) ||
    (user.id && user.id.toString().includes(search))
  )
})

const isValidNewLimit = computed(() => {
  return newLimit.userId && newLimit.limit >= 1 && newLimit.limit <= 100
})

// 方法
function showNotification(message, type = 'success') {
  notification.message = message
  notification.type = type
  notification.show = true
  setTimeout(() => {
    notification.show = false
  }, 3000)
}

async function refreshAllData() {
  await Promise.all([
    loadUsers(),
    loadRoleLimits(),
    loadSystemConfig(),
    loadChangeHistory()
  ])
  showNotification('数据已刷新')
}

async function loadUsers() {
  try {
    const usersRes = await adminApi.getUsers()
    const configRes = await adminApi.getSystemConfig()
    
    const overrides = configRes?.system_config?.user_concurrent_limits?.user_overrides || {}
    
    users.value = (usersRes.users || []).map(user => {
      const userOverride = overrides[user.id]
      return {
        ...user,
        concurrentLimit: userOverride?.limit || getDefaultLimit(user.role),
        tier: userOverride?.tier || 'default',
        activeSessions: 0
      }
    })
    
    stats.totalUsers = users.value.length
    stats.customLimits = users.value.filter(u => u.tier !== 'default').length
  } catch (error) {
    showNotification('加载用户失败', 'error')
  }
}

async function loadRoleLimits() {
  try {
    const config = await adminApi.getSystemConfig()
    const defaults = config?.system_config?.user_concurrent_limits?.default_tiers || {}
    
    Object.keys(roleLimits).forEach(key => {
      roleLimits[key] = defaults[key] || roleLimits[key]
    })
    
    roleLimitsOriginal.value = JSON.parse(JSON.stringify(roleLimits))
    roleLimitsDirty.value = false
  } catch (error) {
    showNotification('加载角色配置失败', 'error')
  }
}

async function loadSystemConfig() {
  try {
    const config = await adminApi.getSystemConfig()
    if (config?.system_config) {
      Object.assign(systemConfig, config.system_config)
    }
    configDirty.value = false
  } catch (error) {
    showNotification('加载系统配置失败', 'error')
  }
}

async function loadChangeHistory() {
  try {
    const response = await adminApi.getConcurrentLimitHistory(historyLimit.value)
    changeHistory.value = response.history || []
    stats.configChanges = changeHistory.value.length
  } catch (error) {
    showNotification('加载变更历史失败', 'error')
  }
}

function getDefaultLimit(role) {
  return roleLimits[role] || 1
}

function getRoleName(role) {
  const names = {
    free: '免费用户',
    basic: '基础用户',
    premium: '高级用户',
    enterprise: '企业用户',
    superadmin: '超级管理员'
  }
  return names[role] || role
}

function getRoleDescription(role) {
  const descriptions = {
    free: '免费账户，默认 1 个并发项目',
    basic: '付费基础账户，支持 2 个并发项目',
    premium: '高级账户，支持 5 个并发项目',
    enterprise: '企业账户，支持 10 个并发项目',
    superadmin: '管理员账户，支持 50 个并发项目'
  }
  return descriptions[role] || ''
}

function getRoleIconClass(role) {
  const classes = {
    free: 'role-icon-free',
    basic: 'role-icon-basic',
    premium: 'role-icon-premium',
    enterprise: 'role-icon-enterprise',
    superadmin: 'role-icon-superadmin'
  }
  return classes[role] || ''
}

function getTierLabel(tier) {
  const labels = {
    custom: '自定义',
    vip: 'VIP',
    enterprise: '企业版',
    default: '默认'
  }
  return labels[tier] || tier
}

function getTierClass(tier) {
  return 'tier-' + tier
}

function getUserInitial(user) {
  if (user.username) {
    return user.username.charAt(0).toUpperCase()
  }
  return 'U'
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN')
}

function markRoleDirty() {
  roleLimitsDirty.value = JSON.stringify(roleLimits) !== JSON.stringify(roleLimitsOriginal.value)
}

async function addUserLimit() {
  try {
    await adminApi.updateUserConcurrentLimit(newLimit.userId, newLimit.limit)
    showNotification('用户限制已添加')
    newLimit.userId = ''
    newLimit.limit = 1
    newLimit.tier = 'custom'
    loadUsers()
  } catch (error) {
    showNotification('添加失败', 'error')
  }
}

async function editUserLimit(user) {
  editingUser.userId = user.id
  editingUser.limit = user.concurrentLimit
  editingUser.tier = user.tier
  showEditModal.value = true
}

function closeEditModal() {
  showEditModal.value = false
}

async function confirmEditUser() {
  try {
    await adminApi.updateUserConcurrentLimit(editingUser.userId, editingUser.limit)
    showNotification('用户限制已更新')
    closeEditModal()
    loadUsers()
  } catch (error) {
    showNotification('更新失败', 'error')
  }
}

async function removeUserLimit(userId) {
  if (!confirm('确定要移除该用户的限制吗？移除后将恢复为角色默认限制。')) return
  
  try {
    await adminApi.removeUserConcurrentLimit(userId)
    showNotification('用户限制已移除')
    loadUsers()
  } catch (error) {
    showNotification('移除失败', 'error')
  }
}

async function saveRoleLimits() {
  try {
    await adminApi.saveRoleLimits(roleLimits)
    showNotification('角色配置已保存')
    roleLimitsOriginal.value = JSON.parse(JSON.stringify(roleLimits))
    roleLimitsDirty.value = false
  } catch (error) {
    showNotification('保存失败', 'error')
  }
}

function addTemplate() {
  if (newTemplate.value && !systemConfig.ppt_generation.supported_templates.includes(newTemplate.value)) {
    systemConfig.ppt_generation.supported_templates.push(newTemplate.value)
    newTemplate.value = ''
    configDirty.value = true
  }
}

function removeTemplate(template) {
  const index = systemConfig.ppt_generation.supported_templates.indexOf(template)
  if (index > -1) {
    systemConfig.ppt_generation.supported_templates.splice(index, 1)
    configDirty.value = true
  }
}

async function saveSystemConfig() {
  try {
    await adminApi.updateSystemConfig({
      path: 'system_config',
      value: systemConfig
    })
    showNotification('系统配置已保存')
    configDirty.value = false
  } catch (error) {
    showNotification('保存失败', 'error')
  }
}

// 生命周期
onMounted(() => {
  refreshAllData()
})
</script>

<style scoped>
.admin-dashboard {
  min-height: 100vh;
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  color: var(--text-primary);
}

/* 顶部导航栏 */
.admin-header {
  background: rgba(30, 41, 59, 0.8);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  padding: 1.5rem 2rem;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  max-width: 1600px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-icon {
  width: 40px;
  height: 40px;
  color: var(--primary);
}

.header-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  background: linear-gradient(135deg, var(--primary), var(--color-primary-500));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.header-subtitle {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0.25rem 0 0 0;
}

.admin-content {
  max-width: 1600px;
  margin: 0 auto;
  padding: 2rem;
}

/* 统计网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  transition: all 0.3s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(96, 165, 250, 0.3);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon svg {
  width: 24px;
  height: 24px;
}

.stat-icon-primary {
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: white;
}

.stat-icon-success {
  background: linear-gradient(135deg, var(--success), var(--success-hover));
  color: white;
}

.stat-icon-warning {
  background: linear-gradient(135deg, var(--warning), var(--warning-hover));
  color: white;
}

.stat-icon-info {
  background: linear-gradient(135deg, var(--color-primary-600), var(--color-primary-600));
  color: white;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--bg-primary);
}

.stat-label {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin-top: 0.25rem;
}

/* 选项卡 */
.tabs-container {
  margin-bottom: 2rem;
}

.tabs {
  display: flex;
  gap: 0.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  padding-bottom: 0;
}

.tab-btn {
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  border-radius: 8px 8px 0 0;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  background: rgba(96, 165, 250, 0.1);
  color: var(--text-primary);
}

.tab-btn.active {
  background: rgba(96, 165, 250, 0.15);
  color: var(--primary);
  border-bottom: 2px solid var(--primary);
}

.tab-content {
  padding: 0;
}

/* 面板 */
.panel {
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-title {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0;
  color: var(--bg-primary);
}

.panel-actions {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.panel-body {
  padding: 2rem;
}

/* 搜索框 */
.search-box {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
}

.search-input {
  width: 300px;
  padding: 0.625rem 1rem 0.625rem 2.5rem;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.search-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.1);
}

/* 添加限制表单 */
.add-limit-form {
  background: rgba(15, 23, 42, 0.5);
  padding: 1.5rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  margin-bottom: 1.5rem;
}

.form-title {
  margin: 0 0 1rem 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.form-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr auto;
  gap: 1rem;
  align-items: end;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group.form-actions {
  display: flex;
  align-items: flex-end;
  height: 82px;
}

.form-group label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.form-input,
.form-select {
  width: 100%;
  padding: 0.625rem 1rem;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.1);
}

.form-select {
  cursor: pointer;
}

/* 表格 */
.data-table-wrapper {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.data-table th,
.data-table td {
  padding: 1rem 1.5rem;
  text-align: left;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.data-table th {
  background: rgba(15, 23, 42, 0.5);
  font-weight: 600;
  color: var(--text-secondary);
}

.data-table tr:hover {
  background: rgba(96, 165, 250, 0.05);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary), var(--color-primary-500));
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: white;
  font-size: 0.875rem;
}

.user-name {
  font-weight: 500;
  color: var(--text-primary);
}

.user-id {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 0.25rem;
}

.empty-state {
  text-align: center;
  padding: 3rem;
  color: var(--text-tertiary);
}

/* 限制徽章 */
.limit-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  background: rgba(96, 165, 250, 0.2);
  color: var(--primary);
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.8125rem;
}

.tier-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.tier-custom {
  background: rgba(139, 92, 246, 0.2);
  color: var(--color-primary-500);
}

.tier-vip {
  background: rgba(245, 158, 11, 0.2);
  color: var(--warning);
}

.tier-enterprise {
  background: rgba(16, 185, 129, 0.2);
  color: var(--success);
}

.tier-default {
  background: rgba(148, 163, 184, 0.2);
  color: var(--text-tertiary);
}

.status-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 500;
}

.status-success {
  background: rgba(16, 185, 129, 0.2);
  color: var(--success);
}

.status-warning {
  background: rgba(245, 158, 11, 0.2);
  color: var(--warning);
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
}

/* 角色限制网格 */
.role-limits-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.role-limit-card {
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
}

.role-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.role-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.role-icon svg {
  width: 24px;
  height: 24px;
}

.role-icon-free {
  background: rgba(148, 163, 184, 0.2);
  color: var(--text-tertiary);
}

.role-icon-basic {
  background: rgba(59, 130, 246, 0.2);
  color: var(--primary);
}

.role-icon-premium {
  background: rgba(139, 92, 246, 0.2);
  color: var(--color-primary-500);
}

.role-icon-enterprise {
  background: rgba(16, 185, 129, 0.2);
  color: var(--success);
}

.role-icon-superadmin {
  background: rgba(245, 158, 11, 0.2);
  color: var(--warning);
}

.role-info {
  flex: 1;
}

.role-name {
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-primary);
}

.role-key {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 0.25rem;
}

.role-limit-input label {
  display: block;
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin-bottom: 0.5rem;
}

.input-with-unit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.input-unit {
  color: var(--text-tertiary);
  font-size: 0.875rem;
}

.role-description {
  margin-top: 1rem;
  font-size: 0.8125rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* 配置区域 */
.config-sections {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.config-section {
  background: rgba(15, 23, 42, 0.5);
  padding: 1.5rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.config-section-title {
  margin: 0 0 1.5rem 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-secondary);
  padding-bottom: 0.75rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-item.full-width {
  grid-column: 1 / -1;
}

.config-item label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.toggle-wrapper {
  display: flex;
  align-items: center;
}

/* 模板标签 */
.template-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.template-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  background: rgba(96, 165, 250, 0.2);
  color: var(--primary);
  border-radius: 6px;
  font-size: 0.8125rem;
}

.tag-remove {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--primary);
  cursor: pointer;
  border-radius: 50%;
  font-size: 1rem;
  line-height: 1;
  padding: 0;
}

.tag-remove:hover {
  background: rgba(96, 165, 250, 0.3);
}

.tag-add {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tag-input {
  width: 150px;
  padding: 0.375rem 0.75rem;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8125rem;
}

.tag-input:focus {
  outline: none;
  border-color: var(--primary);
}

/* 限制选择器 */
.limit-selector {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.limit-selector label {
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

/* 变更历史时间轴 */
.timeline {
  position: relative;
  padding-left: 1rem;
}

.timeline-item {
  display: flex;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
  margin-top: 0.25rem;
}

.timeline-content {
  flex: 1;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.timeline-role {
  font-weight: 600;
  color: var(--primary);
  text-transform: uppercase;
  font-size: 0.75rem;
}

.timeline-time {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.timeline-body {
  background: rgba(15, 23, 42, 0.5);
  padding: 1rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.timeline-body p {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.change-operator {
  font-weight: 600;
  color: var(--text-primary);
}

.change-old {
  color: var(--danger);
  font-weight: 600;
}

.change-new {
  color: var(--success);
  font-weight: 600;
}

.timeline-reason {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-style: italic;
}

/* 按钮 */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.btn-primary {
  background: linear-gradient(135deg, var(--primary), var(--primary-hover));
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, var(--primary-hover), var(--primary-hover));
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-outline {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.3);
  color: var(--text-primary);
}

.btn-outline:hover {
  background: rgba(148, 163, 184, 0.1);
  border-color: rgba(148, 163, 184, 0.5);
}

.btn-danger {
  background: rgba(239, 68, 68, 0.2);
  color: var(--danger);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.btn-danger:hover {
  background: rgba(239, 68, 68, 0.3);
}

.btn-icon-sm {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(148, 163, 184, 0.1);
  border: none;
  border-radius: 6px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-icon-sm:hover {
  background: rgba(148, 163, 184, 0.2);
  color: var(--text-primary);
}

.btn-icon-sm.btn-danger {
  background: rgba(239, 68, 68, 0.2);
  color: var(--danger);
}

.btn-icon-sm.btn-danger:hover {
  background: rgba(239, 68, 68, 0.3);
}

/* 切换开关 */
.toggle {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(148, 163, 184, 0.2);
  transition: 0.3s;
  border-radius: 24px;
}

.toggle-slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
}

.toggle input:checked + .toggle-slider {
  background: rgba(59, 130, 246, 0.5);
}

.toggle input:checked + .toggle-slider:before {
  transform: translateX(24px);
}

/* 通知 */
.notification {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  padding: 1rem 1.5rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  animation: slideIn 0.3s ease;
  z-index: 1000;
}

.notification.success {
  background: rgba(16, 185, 129, 0.2);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: var(--success);
}

.notification.error {
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--danger);
}

.notification-icon {
  width: 20px;
  height: 20px;
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-tertiary);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  width: 100%;
  max-width: 500px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.125rem;
  color: var(--bg-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-tertiary);
  cursor: pointer;
}

.modal-close:hover {
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-primary);
}

.modal-close svg {
  width: 20px;
  height: 20px;
}

.modal-body {
  padding: 2rem;
}

.modal-footer {
  padding: 1.5rem 2rem;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .admin-header {
    padding: 1rem;
  }

  .header-title {
    font-size: 1.25rem;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .admin-content {
    padding: 1rem;
  }

  .panel-body {
    padding: 1rem;
  }

  .form-row {
    grid-template-columns: 1fr;
  }

  .form-group.form-actions {
    height: auto;
  }

  .search-input {
    width: 100%;
  }
}
</style>