<template>
  <!-- 权限验证失败显示 -->
  <div v-if="accessDenied" class="access-denied">
    <div class="denied-content">
      <div class="denied-icon">
        <svg
          width="80"
          height="80"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>
      </div>
      <h2>访问被拒绝</h2>
      <p>您没有权限访问管理员面板</p>
      <p class="hint">页面将在 2 秒后关闭或跳转到主页...</p>
    </div>
  </div>

  <!-- 正常管理员面板 -->
  <div v-else-if="showContent" class="admin-panel">
    <!-- 头部 -->
    <div class="admin-header">
      <div class="header-left">
        <div class="logo-section">
          <svg
            class="logo-icon"
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
          </svg>
          <div class="logo-text">
            <h1>
              {{ isSuperUser ? '系统管理控制台' : isAdmin ? '管理员控制台' : 'Nginx 配置工具' }}
            </h1>
            <span class="logo-subtitle">{{
              isSuperUser
                ? 'System Management Console'
                : isAdmin
                  ? 'Admin Console'
                  : 'Nginx Configuration Tool'
            }}</span>
          </div>
        </div>
      </div>
      <div class="header-right">
        <div class="header-info">
          <div class="info-item">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
            <span>{{ userStore.username || '未登录' }}</span>
          </div>
          <div class="info-item">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="16" y1="2" x2="16" y2="6"></line>
              <line x1="8" y1="2" x2="8" y2="6"></line>
              <line x1="3" y1="10" x2="21" y2="10"></line>
            </svg>
            <span>{{ currentDateTime }}</span>
          </div>
        </div>
        <button class="logout-btn" title="退出登录" @click="handleLogout">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <polyline points="16 17 21 12 16 7"></polyline>
            <line x1="21" y1="12" x2="9" y2="12"></line>
          </svg>
          <span>退出</span>
        </button>
      </div>
    </div>

    <!-- 主体内容 -->
    <div class="admin-body">
      <!-- 左侧侧边栏 -->
      <aside class="admin-sidebar">
        <div class="sidebar-header">
          <h3>功能导航</h3>
          <span class="stats-badge">{{ menuItems.length }} 个模块</span>
        </div>

        <!-- 搜索框 -->
        <div class="search-section">
          <svg
            class="search-icon"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索功能模块..."
            class="search-input"
            @input="handleSearch"
          />
          <button v-if="searchKeyword" class="clear-btn" title="清除搜索" @click="clearSearch">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <!-- 快速访问 -->
        <div class="quick-access">
          <div class="section-title">快速访问</div>
          <div class="quick-links">
            <button
              v-for="item in quickAccessItems"
              :key="item.id"
              class="quick-link"
              :class="{ active: activeMenu === item.id }"
              @click="handleMenuChange(item.id)"
            >
              <svg
                class="link-icon"
                :viewBox="item.viewBox"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path :d="item.path"></path>
              </svg>
              <span class="link-text">{{ item.name }}</span>
              <span class="link-count">{{ item.count }}</span>
            </button>
          </div>
        </div>

        <!-- 功能菜单 -->
        <nav class="sidebar-nav">
          <div class="section-title">所有功能</div>
          <div v-for="group in menuGroups" :key="group.name" class="nav-group">
            <div class="group-header">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
              </svg>
              <span>{{ group.name }}</span>
            </div>
            <div
              v-for="item in group.items"
              :key="item.id"
              class="nav-item"
              :class="{ active: activeMenu === item.id }"
              @click="handleMenuChange(item.id)"
            >
              <svg
                class="nav-icon"
                :viewBox="item.viewBox"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path :d="item.path"></path>
              </svg>
              <div class="nav-content">
                <span class="nav-title">{{ item.name }}</span>
                <span class="nav-desc">{{ item.description }}</span>
              </div>
            </div>
          </div>
          <div v-if="filteredMenuItems.length === 0" class="no-results">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <p>未找到匹配的功能</p>
            <button class="clear-search-link" @click="clearSearch">清除搜索条件</button>
          </div>
        </nav>
      </aside>

      <!-- 中间内容区域 -->
      <main class="admin-main">
        <!-- 顶部状态栏 -->
        <div class="status-bar">
          <div class="status-item">
            <span
              :class="['status-indicator', { online: isConnected, offline: !isConnected }]"
            ></span>
            <span class="status-label">{{ isConnected ? '系统在线' : '连接中...' }}</span>
          </div>
          <div v-if="lastUpdate" class="status-item">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span class="status-time">最后更新: {{ lastUpdate }}</span>
          </div>
          <div class="stats-summary">
            <div class="mini-stat">
              <span class="mini-stat-label">CPU</span>
              <span class="mini-stat-value">{{ systemData.cpu?.total_percent?.toFixed(1) }}%</span>
            </div>
            <div class="mini-stat">
              <span class="mini-stat-label">内存</span>
              <span class="mini-stat-value">{{ systemData.memory?.percent?.toFixed(1) }}%</span>
            </div>
            <div class="mini-stat">
              <span class="mini-stat-label">磁盘</span>
              <span class="mini-stat-value">{{ systemData.disk?.percent?.toFixed(1) }}%</span>
            </div>
          </div>
        </div>

        <!-- 内容区域 -->
        <div class="content-wrapper">
          <!-- 系统监控 -->
          <div v-if="activeMenu === 'monitor'" class="content-section monitor-section">
            <div class="section-header">
              <div class="header-left">
                <svg
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                  <line x1="8" y1="21" x2="16" y2="21"></line>
                  <line x1="12" y1="17" x2="12" y2="21"></line>
                </svg>
                <div>
                  <h2>系统监控仪表板</h2>
                  <p class="header-desc">实时监控系统资源使用情况</p>
                </div>
              </div>
              <div class="header-actions">
                <button class="action-btn primary" @click="refreshSystemInfo">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M23 4v6h-6"></path>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                  </svg>
                  <span>刷新</span>
                </button>
              </div>
            </div>

            <!-- 概览卡片 -->
            <div class="overview-cards">
              <div class="overview-card cpu-card">
                <div class="card-icon-wrapper cpu">
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <rect x="4" y="4" width="16" height="16" rx="2"></rect>
                    <rect x="9" y="9" width="6" height="6"></rect>
                    <line x1="9" y1="1" x2="9" y2="4"></line>
                    <line x1="15" y1="1" x2="15" y2="4"></line>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>CPU 使用率</h3>
                  <div class="card-value">{{ systemData.cpu?.total_percent?.toFixed(1) }}%</div>
                  <div class="card-detail">
                    <span>核心数: {{ systemData.cpu?.core_count || 0 }}</span>
                    <span :class="['status-badge', getStatusClass(systemData.cpu?.total_percent)]">
                      {{ getStatusText(systemData.cpu?.total_percent) }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="overview-card memory-card">
                <div class="card-icon-wrapper memory">
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M2 12h20"></path>
                    <path d="M2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6"></path>
                    <path d="M12 2v4"></path>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>内存使用</h3>
                  <div class="card-value">{{ systemData.memory?.percent?.toFixed(1) }}%</div>
                  <div class="card-detail">
                    <span>已用: {{ systemData.memory?.used_gb?.toFixed(2) }} GB</span>
                    <span>总计: {{ systemData.memory?.total_gb?.toFixed(2) }} GB</span>
                  </div>
                </div>
              </div>

              <div class="overview-card disk-card">
                <div class="card-icon-wrapper disk">
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>磁盘使用</h3>
                  <div class="card-value">{{ systemData.disk?.percent?.toFixed(1) }}%</div>
                  <div class="card-detail">
                    <span>已用: {{ systemData.disk?.used_gb?.toFixed(2) }} GB</span>
                    <span>总计: {{ systemData.disk?.total_gb?.toFixed(2) }} GB</span>
                  </div>
                </div>
              </div>

              <div class="overview-card network-card">
                <div class="card-icon-wrapper network">
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                    <path d="M12 20a8 8 0 0 0-5.76-2.5"></path>
                    <path d="M12 16a4 4 0 0 0-1.23-7.7"></path>
                    <path d="M12 10a2 2 0 0 0 3.96-1"></path>
                  </svg>
                </div>
                <div class="card-content">
                  <h3>网络流量</h3>
                  <div class="card-value-network">
                    <div class="network-metric">
                      <span class="metric-label">上传</span>
                      <span class="metric-value">{{
                        formatBytes(systemData.network?.bytes_sent || 0)
                      }}</span>
                    </div>
                    <div class="network-metric">
                      <span class="metric-label">下载</span>
                      <span class="metric-value">{{
                        formatBytes(systemData.network?.bytes_recv || 0)
                      }}</span>
                    </div>
                  </div>
                  <div class="card-detail">
                    <span class="network-status">网络正常</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 详细图表区域 -->
            <div class="charts-grid">
              <!-- CPU 详细图表 -->
              <div class="chart-panel">
                <div class="panel-header">
                  <div class="panel-title">
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <rect x="4" y="4" width="16" height="16" rx="2"></rect>
                      <rect x="9" y="9" width="6" height="6"></rect>
                    </svg>
                    <span>CPU 使用趋势</span>
                  </div>
                  <div class="panel-value">{{ systemData.cpu?.total_percent?.toFixed(1) }}%</div>
                </div>
                <div ref="cpuChartRef" class="chart-container"></div>
              </div>

              <!-- 内存详细图表 -->
              <div class="chart-panel">
                <div class="panel-header">
                  <div class="panel-title">
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path d="M2 12h20"></path>
                      <path d="M2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6"></path>
                    </svg>
                    <span>内存使用分布</span>
                  </div>
                  <div class="panel-value">{{ systemData.memory?.percent?.toFixed(1) }}%</div>
                </div>
                <div ref="memoryChartRef" class="chart-container"></div>
              </div>

              <!-- 磁盘详细图表 -->
              <div class="chart-panel">
                <div class="panel-header">
                  <div class="panel-title">
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <circle cx="12" cy="12" r="10"></circle>
                    </svg>
                    <span>磁盘使用率</span>
                  </div>
                  <div class="panel-value">{{ systemData.disk?.percent?.toFixed(1) }}%</div>
                </div>
                <div ref="diskChartRef" class="chart-container"></div>
              </div>

              <!-- 网络详细图表 -->
              <div class="chart-panel">
                <div class="panel-header">
                  <div class="panel-title">
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                    </svg>
                    <span>网络流量趋势</span>
                  </div>
                </div>
                <div ref="networkChartRef" class="chart-container"></div>
              </div>
            </div>
          </div>

          <!-- 系统日志 -->
          <div v-else-if="activeMenu === 'logs'" class="content-section logs-section">
            <SystemLogs />
          </div>

          <!-- 用户管理 -->
          <div v-else-if="activeMenu === 'users'" class="content-section users-section">
            <UserManagement />
          </div>

          <!-- Nginx配置 -->
          <div v-else-if="activeMenu === 'nginx'" class="content-section">
            <NginxConfig />
          </div>

          <!-- 服务管理 -->
          <div v-else-if="activeMenu === 'service-manager'" class="content-section">
            <ServiceManager />
          </div>

          <!-- 资源配置 -->
          <div v-else-if="activeMenu === 'resource-control'" class="content-section">
            <ResourceControl />
          </div>

          <!-- 模型管理 -->
          <div v-else-if="activeMenu === 'models'" class="content-section">
            <AdminModelManager />
          </div>

          <!-- 代码沙箱配置 -->
          <div v-else-if="activeMenu === 'sandbox'" class="content-section">
            <div class="sandbox-config">
              <h3>代码沙箱配置</h3>
              <p class="section-desc">配置工程师代码验证沙箱，允许工程师在生成代码后进行沙箱验证。</p>

              <div class="config-card">
                <div class="config-row">
                  <div class="config-label">
                    <span class="label-text">启用代码沙箱</span>
                    <span class="label-desc">开启后，工程师可在生成代码后使用 execute_code 工具验证代码正确性</span>
                  </div>
                  <el-switch
                    v-model="sandboxConfig.enable_code_sandbox"
                    @change="updateSandboxConfig"
                    active-text="启用"
                    inactive-text="禁用"
                  />
                </div>

                <div class="config-row">
                  <div class="config-label">
                    <span class="label-text">支持的语言</span>
                    <span class="label-desc">当前支持 Python 和 JavaScript，后续可扩展</span>
                  </div>
                  <div class="language-tags">
                    <el-tag
                      v-for="lang in sandboxConfig.sandbox_languages"
                      :key="lang"
                      type="success"
                      effect="plain"
                    >
                      {{ lang }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 页脚 -->
    <footer class="admin-footer">
      <div class="footer-left">
        <span>系统状态: </span>
        <span :class="['system-status', isConnected ? 'online' : 'offline']">
          {{ isConnected ? '正常运行' : '离线' }}
        </span>
      </div>
      <div class="footer-right">
        <span>版本: v2.0.0</span>
        <span>© 2024 系统管理控制台</span>
      </div>
    </footer>
  </div>
</template>

<script setup>
  import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
  import { ElMessage } from 'element-plus'
  import { useRouter } from 'vue-router'
  import { useUserStore } from '@/stores/user'
  import * as echarts from 'echarts'
  import { LineChart, BarChart, PieChart } from 'echarts/charts'
  import {
    GridComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    GraphicComponent
  } from 'echarts/components'
  import { CanvasRenderer } from 'echarts/renderers'

  // 注册必需的组件
  echarts.use([
    GridComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    GraphicComponent,
    LineChart,
    BarChart,
    PieChart,
    CanvasRenderer
  ])
  import { defineAsyncComponent } from 'vue'
  import { WebSocketManager, API_CONFIG } from '../utils/api/index'

  const UserManagement = defineAsyncComponent(() => import('./UserManagement.vue'))
  const SystemLogs = defineAsyncComponent(() => import('./SystemLogs.vue'))
  const NginxConfig = defineAsyncComponent(() => import('./NginxConfig.vue'))
  const ServiceManager = defineAsyncComponent(() => import('./ServiceManager.vue'))
  const ResourceControl = defineAsyncComponent(() => import('./ResourceControl.vue'))
  const AdminModelManager = defineAsyncComponent(() => import('./settings/AdminModelManager.vue'))

  // 代码沙箱配置
  const sandboxConfig = ref({
    enable_code_sandbox: true,
    sandbox_languages: ['python', 'javascript']
  })

  const fetchSandboxConfig = async () => {
    try {
      const token = userStore.token
      const resp = await fetch('/api/v2/admin/sandbox-config', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (resp.ok) {
        sandboxConfig.value = await resp.json()
      }
    } catch (e) {
      console.warn('获取沙箱配置失败:', e)
    }
  }

  const updateSandboxConfig = async () => {
    try {
      const token = userStore.token
      const resp = await fetch('/api/v2/admin/sandbox-config', {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          enable_code_sandbox: sandboxConfig.value.enable_code_sandbox,
          sandbox_languages: sandboxConfig.value.sandbox_languages.join(',')
        })
      })
      if (resp.ok) {
        const data = await resp.json()
        if (data.success) {
          ElMessage.success('沙箱配置已保存')
        }
      } else {
        ElMessage.error('保存失败')
      }
    } catch (e) {
      ElMessage.error('保存失败: ' + (e.message || '未知错误'))
    }
  }

  const router = useRouter()
  const userStore = useUserStore()
  const showContent = ref(false)
  const accessDenied = ref(false)

  // 从 userStore 获取权限状态
  const isAdmin = computed(() => userStore.isAdmin)
  const isSuperUser = computed(() => userStore.isSuperUser)

  // 菜单相关
  const activeMenu = ref('monitor')
  const searchKeyword = ref('')

  // 当前时间
  const currentDateTime = ref('')

  // 更新时间
  const updateCurrentTime = () => {
    const now = new Date()
    currentDateTime.value = now.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
  }

  // 快速访问项
  const quickAccessItems = computed(() => [
    {
      id: 'monitor',
      name: '系统监控',
      description: '实时系统资源监控',
      count: '4 项',
      viewBox: '0 0 24 24',
      path: 'M3 3v18h18'
    },
    {
      id: 'logs',
      name: '系统日志',
      description: '查看运行日志',
      count: '实时',
      viewBox: '0 0 24 24',
      path: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'
    }
  ])

  // 菜单分组
  const menuGroups = computed(() => {
    const groups = {}

    // admin 和 superadmin 都显示完整的管理菜单
    if (isAdmin.value) {
      groups['监控管理'] = {
        name: '监控管理',
        items: [
          {
            id: 'monitor',
            name: '系统监控',
            description: '实时监控 CPU、内存、磁盘和网络',
            viewBox: '0 0 24 24',
            path: 'M3 3v18h18'
          }
        ]
      }
      groups['日志管理'] = {
        name: '日志管理',
        items: [
          {
            id: 'logs',
            name: '系统日志',
            description: '查看和分析系统运行日志',
            viewBox: '0 0 24 24',
            path: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'
          }
        ]
      }
      groups['用户管理'] = {
        name: '用户与权限',
        items: [
          {
            id: 'users',
            name: '用户管理',
            description: '管理系统用户和权限配置',
            viewBox: '0 0 24 24',
            path: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2'
          }
        ]
      }
    }

    // 系统配置：所有用户都可见（但普通用户只能看到 Nginx 配置）
    const systemConfigItems = []

    // 所有用户都可见 Nginx 配置
    systemConfigItems.push({
      id: 'nginx',
      name: 'Nginx 配置',
      description: '配置和管理 Nginx 服务',
      viewBox: '0 0 24 24',
      path: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z'
    })

    // admin 和 superadmin 都可以看到服务管理和资源配置
    if (isAdmin.value) {
      systemConfigItems.push({
        id: 'service-manager',
        name: '服务管理',
        description: '监控和管理系统服务',
        viewBox: '0 0 24 24',
        path: 'M22 11.08V12a10 10 0 1 1-5.93-9.14'
      })
      systemConfigItems.push({
        id: 'resource-control',
        name: '资源配置',
        description: 'Docker 资源限制和功能开关',
        viewBox: '0 0 24 24',
        path: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'
      })
    }

    if (isSuperUser.value) {
      systemConfigItems.push({
        id: 'models',
        name: '模型管理',
        description: '切换默认模型、管理模型配置',
        viewBox: '0 0 24 24',
        path: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'
      })
      systemConfigItems.push({
        id: 'dashboard',
        name: '并发管理仪表板',
        description: '管理用户并发项目限制',
        viewBox: '0 0 24 24',
        path: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'
      })
      systemConfigItems.push({
        id: 'sandbox',
        name: '代码沙箱',
        description: '配置工程师代码验证沙箱（Python/JavaScript）',
        viewBox: '0 0 24 24',
        path: 'M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0L19.2 12l-4.6-4.6L16 6l6 6-6 6-1.4-1.4z'
      })
      if (!isAdmin.value) {
        systemConfigItems.push({
          id: 'service-manager',
          name: '服务管理',
          description: '监控和管理系统服务',
          viewBox: '0 0 24 24',
          path: 'M22 11.08V12a10 10 0 1 1-5.93-9.14'
        })
        systemConfigItems.push({
          id: 'resource-control',
          name: '资源配置',
          description: 'Docker 资源限制和功能开关',
          viewBox: '0 0 24 24',
          path: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'
        })
      }
    }

    groups['系统配置'] = {
      name: '系统配置',
      items: systemConfigItems
    }

    let allItems = []
    Object.keys(groups).forEach(key => {
      allItems = allItems.concat(groups[key].items)
    })

    if (!searchKeyword.value.trim()) {
      return groups
    }

    // 过滤菜单项
    const keyword = searchKeyword.value.toLowerCase().trim()
    const filteredGroups = {}

    Object.keys(groups).forEach(key => {
      const filteredItems = groups[key].items.filter(
        item =>
          item.name.toLowerCase().includes(keyword) ||
          item.description.toLowerCase().includes(keyword)
      )

      if (filteredItems.length > 0) {
        filteredGroups[key] = {
          name: groups[key].name,
          items: filteredItems
        }
      }
    })

    return filteredGroups
  })

  // 所有菜单项（从 menuGroups 派生，用于搜索）
  const menuItems = computed(() => {
    const groups = menuGroups.value
    const allItems = []
    Object.keys(groups).forEach(key => {
      allItems.push(...groups[key].items)
    })
    return allItems
  })

  // 过滤后的菜单项
  const filteredMenuItems = computed(() => {
    if (!searchKeyword.value.trim()) {
      return menuItems.value
    }

    const keyword = searchKeyword.value.toLowerCase().trim()
    return menuItems.value.filter(
      item =>
        item.name.toLowerCase().includes(keyword) ||
        item.description.toLowerCase().includes(keyword)
    )
  })

  // WebSocket 相关
  const isConnected = ref(false)
  const lastUpdate = ref('')
  const wsManager = ref(null)

  // 系统数据
  const systemData = ref({
    timestamp: '',
    cpu: {
      total_percent: 0,
      per_cpu: [],
      core_count: 0
    },
    memory: {
      total_gb: 0,
      used_gb: 0,
      percent: 0
    },
    disk: {
      total_gb: 0,
      used_gb: 0,
      percent: 0
    },
    network: {
      bytes_sent: 0,
      bytes_recv: 0
    }
  })

  // 图表引用
  const cpuChartRef = ref(null)
  const memoryChartRef = ref(null)
  const diskChartRef = ref(null)
  const networkChartRef = ref(null)

  // 图表实例
  let cpuChart = null
  let memoryChart = null
  let diskChart = null
  let networkChart = null

  // 网络历史数据
  const networkHistory = ref({
    times: [],
    sent: [],
    recv: []
  })

  // 搜索处理
  const handleSearch = () => {
    // 搜索逻辑由 computed 处理
  }

  const clearSearch = () => {
    searchKeyword.value = ''
  }

  // 菜单切换
  const handleMenuChange = menuId => {
    if (menuId === 'dashboard') {
      router.push('/admin/dashboard')
      return
    }
    activeMenu.value = menuId
    saveMenuState()
  }

  // 获取状态类名
  const getStatusClass = value => {
    if (value >= 80) return 'critical'
    if (value >= 60) return 'warning'
    return 'normal'
  }

  // 获取状态文本
  const getStatusText = value => {
    if (value >= 80) return '严重'
    if (value >= 60) return '警告'
    return '正常'
  }

  // 处理退出登录
  const handleLogout = () => {
    if (confirm('确定要退出登录吗？')) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('permission_level')
      router.push('/')
    }
  }

  // 刷新系统信息
  const refreshSystemInfo = () => {
    updateCharts()
  }

  // 格式化字节数
  const formatBytes = bytes => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i]
  }

  // 更新最后更新时间
  const updateLastTime = () => {
    const now = new Date()
    lastUpdate.value = now.toLocaleString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  // 保存菜单状态到 localStorage
  const saveMenuState = () => {
    try {
      const state = {
        activeMenu: activeMenu.value,
        searchKeyword: searchKeyword.value,
        timestamp: Date.now()
      }
      localStorage.setItem('adminMenuState', JSON.stringify(state))
    } catch (err) {
      console.warn('无法保存管理员菜单状态:', err)
    }
  }

  // 初始化 CPU 图表 - 使用仪表盘
  const initCpuChart = () => {
    if (!cpuChartRef.value) return

    if (cpuChart) {
      cpuChart.dispose()
      cpuChart = null
    }

    cpuChart = echarts.init(cpuChartRef.value)

    const option = {
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c}%'
      },
      series: [
        {
          type: 'gauge',
          startAngle: 180,
          endAngle: 0,
          min: 0,
          max: 100,
          splitNumber: 8,
          axisLine: {
            lineStyle: {
              width: 8,
              color: [
                [0.3, '#67e0e3'],
                [0.7, '#37a2da'],
                [1, '#fd666d']
              ]
            }
          },
          pointer: {
            length: '12%',
            width: 20,
            offsetCenter: [0, '-60%'],
            itemStyle: {
              color: 'auto'
            }
          },
          axisTick: {
            length: 12,
            lineStyle: {
              color: 'auto',
              width: 2
            }
          },
          splitLine: {
            length: 20,
            lineStyle: {
              color: 'auto',
              width: 5
            }
          },
          axisLabel: {
            color: '#464646',
            fontSize: 16,
            distance: -60
          },
          detail: {
            fontSize: 48,
            offsetCenter: [0, '0%'],
            valueAnimation: true,
            formatter: function (value) {
              return Math.round(value) + '%'
            },
            color: 'auto'
          },
          data: [
            {
              value: systemData.value.cpu?.total_percent || 0,
              name: 'CPU'
            }
          ]
        }
      ]
    }

    cpuChart.setOption(option)
  }

  // 初始化内存图表 - 使用饼图
  const initMemoryChart = () => {
    if (!memoryChartRef.value) return

    if (memoryChart) {
      memoryChart.dispose()
      memoryChart = null
    }

    memoryChart = echarts.init(memoryChartRef.value)

    const option = {
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {c} GB ({d}%)'
      },
      legend: {
        orient: 'vertical',
        left: 'left',
        top: 'middle',
        textStyle: {
          fontSize: 14
        }
      },
      series: [
        {
          name: '内存使用',
          type: 'pie',
          radius: ['40%', '70%'],
          center: ['60%', '50%'],
          avoidLabelOverlap: false,
          itemStyle: {
            borderRadius: 12,
            borderColor: '#fff',
            borderWidth: 3
          },
          label: {
            show: true,
            position: 'outside',
            formatter: '{b}: {d}%',
            fontSize: 14,
            fontWeight: 'bold'
          },
          emphasis: {
            label: {
              show: true,
              fontSize: 18,
              fontWeight: 'bold'
            },
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          },
          data: [
            {
              value: systemData.value.memory?.used_gb || 0,
              name: '已使用',
              itemStyle: { color: '#5470c6' }
            },
            {
              value:
                (systemData.value.memory?.total_gb || 0) - (systemData.value.memory?.used_gb || 0),
              name: '可用',
              itemStyle: { color: '#91cc75' }
            }
          ]
        }
      ]
    }

    memoryChart.setOption(option)
  }

  // 初始化磁盘图表 - 使用柱状图
  const initDiskChart = () => {
    if (!diskChartRef.value) return

    if (diskChart) {
      diskChart.dispose()
      diskChart = null
    }

    diskChart = echarts.init(diskChartRef.value)

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        },
        formatter: '{a}<br/>{b}: {c}%'
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: {
          formatter: '{value}%'
        }
      },
      yAxis: {
        type: 'category',
        data: ['磁盘使用'],
        axisLabel: {
          fontSize: 14
        }
      },
      series: [
        {
          name: '磁盘使用率',
          type: 'bar',
          data: [systemData.value.disk?.percent || 0],
          barWidth: '60%',
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#83bff6' },
              { offset: 0.5, color: '#188df0' },
              { offset: 1, color: '#188df0' }
            ]),
            borderRadius: [0, 20, 20, 0]
          },
          label: {
            show: true,
            position: 'right',
            formatter: '{c}%',
            fontSize: 18,
            fontWeight: 'bold'
          }
        }
      ]
    }

    diskChart.setOption(option)
  }

  // 初始化网络图表 - 使用折线图
  const initNetworkChart = () => {
    if (!networkChartRef.value) return

    if (networkChart) {
      networkChart.dispose()
      networkChart = null
    }

    networkChart = echarts.init(networkChartRef.value)

    networkHistory.value = {
      times: Array(20)
        .fill('')
        .map((_, i) => ''),
      sent: Array(20).fill(0),
      recv: Array(20).fill(0)
    }

    const option = {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          label: {
            backgroundColor: '#6a7985'
          }
        },
        formatter: function (params) {
          let result = params[0].axisValue + '<br/>'
          params.forEach(item => {
            result += `${item.marker}${item.seriesName}: ${formatBytes(item.value)}<br/>`
          })
          return result
        }
      },
      legend: {
        data: ['发送', '接收'],
        top: 0,
        textStyle: {
          fontSize: 14
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: networkHistory.value.times
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: function (value) {
            return formatBytes(value)
          }
        }
      },
      series: [
        {
          name: '发送',
          type: 'line',
          smooth: true,
          data: networkHistory.value.sent,
          itemStyle: {
            color: '#5470c6'
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(84, 112, 198, 0.5)' },
              { offset: 1, color: 'rgba(84, 112, 198, 0.1)' }
            ])
          }
        },
        {
          name: '接收',
          type: 'line',
          smooth: true,
          data: networkHistory.value.recv,
          itemStyle: {
            color: '#91cc75'
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(145, 204, 117, 0.5)' },
              { offset: 1, color: 'rgba(145, 204, 117, 0.1)' }
            ])
          }
        }
      ]
    }

    networkChart.setOption(option)
  }

  // 更新网络图表数据
  const updateNetworkChart = () => {
    if (!networkChart) return

    const now = new Date()
    const timeStr = now.toLocaleTimeString('zh-CN')

    networkHistory.value.times.shift()
    networkHistory.value.times.push(timeStr)
    networkHistory.value.sent.shift()
    networkHistory.value.sent.push(systemData.value.network?.bytes_sent || 0)
    networkHistory.value.recv.shift()
    networkHistory.value.recv.push(systemData.value.network?.bytes_recv || 0)

    networkChart.setOption({
      xAxis: {
        data: networkHistory.value.times
      },
      series: [{ data: networkHistory.value.sent }, { data: networkHistory.value.recv }]
    })
  }

  // 更新所有图表
  const updateCharts = () => {
    if (cpuChart) {
      cpuChart.setOption({
        series: [
          {
            data: [
              {
                value: systemData.value.cpu?.total_percent || 0,
                name: 'CPU'
              }
            ]
          }
        ]
      })
    }

    if (memoryChart) {
      memoryChart.setOption({
        series: [
          {
            data: [
              {
                value: systemData.value.memory?.used_gb || 0,
                name: '已使用',
                itemStyle: { color: '#5470c6' }
              },
              {
                value:
                  (systemData.value.memory?.total_gb || 0) -
                  (systemData.value.memory?.used_gb || 0),
                name: '可用',
                itemStyle: { color: '#91cc75' }
              }
            ]
          }
        ]
      })
    }

    if (diskChart) {
      diskChart.setOption({
        series: [
          {
            data: [systemData.value.disk?.percent || 0]
          }
        ]
      })
    }

    if (networkChart) {
      updateNetworkChart()
    }
  }

  // 连接 WebSocket
  const connectWebSocket = () => {
    if (wsManager.value) {
      wsManager.value.disconnect()
    }

    const apiUrl = API_CONFIG.WS_BASE_URL
    const wsUrl = `${apiUrl}/api/v2/Controller/sys-status?token={token}`

    wsManager.value = new WebSocketManager({
      wsUrl: wsUrl,
      userStore: userStore,
      onOpen: () => {
        isConnected.value = true
        updateLastTime()
      },
      onMessage: event => {
        try {
          const data = JSON.parse(event.data)

          if (data.type === 'system_stats' && data.data) {
            systemData.value = data.data
            updateLastTime()
            updateCharts()
          }
        } catch (error) {
          // 解析错误
        }
      },
      onError: error => {
        isConnected.value = false
      },
      onClose: event => {
        isConnected.value = false

        // 仅在非认证失败时重连，认证失败(code 1008)不重试
        if (wsManager.value && event && event.code !== 1008) {
          wsManager.value.scheduleReconnect()
        }
      },
      reconnectDelay: 5000
    })

    const token = userStore.getAccessToken() || localStorage.getItem('access_token')
    wsManager.value.connect(token)
  }

  // 权限检查 - 允许普通用户访问但只显示 Nginx 配置
  const checkPermission = () => {
    // 使用 userStore 获取 token（优先）, 回退到 localStorage
    const token = userStore.getAccessToken() || localStorage.getItem('access_token')
    const permissionLevel = localStorage.getItem('permission_level')

    if (!token) {
      console.error('未登录，缺少访问令牌')
      console.debug('[AdminPanel] Token check failed. sessionStorage:_token:', sessionStorage.getItem('_token'))
      console.debug('[AdminPanel] localStorage:access_token:', localStorage.getItem('access_token'))
      accessDenied.value = true
      showAccessDenied()
      return false
    }

    // 存储用户权限级别用于界面显示控制（从 userStore 获取）
    // 普通用户（normal）无法访问管理员面板
    // admin 可以访问大部分功能
    // superadmin 可以访问所有功能

    // 普通用户只能看到 Nginx 配置，admin 和 superadmin 可以看到所有功能
    if (!isAdmin.value) {
      console.log('普通用户访问，仅显示 Nginx 配置')
      // 自动跳转到 Nginx 配置页面
      activeMenu.value = 'nginx'
    } else if (isSuperUser.value) {
      console.log('超级管理员访问，显示所有功能')
    } else {
      console.log('管理员访问，显示大部分功能')
    }

    showContent.value = true
    console.log('权限验证通过')
    return true
  }

  // 显示拒绝访问页面
  const showAccessDenied = () => {
    setTimeout(() => {
      try {
        window.close()
        setTimeout(() => {
          window.location.href = '/'
        }, 1000)
      } catch (error) {
        console.error('关闭窗口失败:', error)
        window.location.href = '/'
      }
    }, 2000)
  }

  // 组件挂载
  let currentTimeInterval = null
  const resizeHandler = () => {
    cpuChart?.resize()
    memoryChart?.resize()
    diskChart?.resize()
    networkChart?.resize()
  }

  onMounted(() => {
    userStore.restoreUser()

    // 更新时间
    updateCurrentTime()
    currentTimeInterval = setInterval(updateCurrentTime, 1000)

    // 检查权限
    if (checkPermission()) {
      connectWebSocket()

      // 加载沙箱配置
      fetchSandboxConfig()

      setTimeout(() => {
        initCpuChart()
        initMemoryChart()
        initDiskChart()
        initNetworkChart()
        updateCharts()
      }, 100)
    }

    // 菜单变化监听
    watch(activeMenu, newMenu => {
      saveMenuState()

      if (newMenu === 'monitor') {
        nextTick(() => {
          setTimeout(() => {
            initCpuChart()
            initMemoryChart()
            initDiskChart()
            initNetworkChart()
            updateCharts()
          }, 100)
        })
      }
    })

    // 响应式图表
    window.addEventListener('resize', resizeHandler)
  })

  // 清理
  onBeforeUnmount(() => {
    if (wsManager.value) wsManager.value.disconnect()
    cpuChart?.dispose()
    memoryChart?.dispose()
    diskChart?.dispose()
    networkChart?.dispose()
    saveMenuState()
    if (currentTimeInterval) clearInterval(currentTimeInterval)
    window.removeEventListener('resize', resizeHandler)
  })
</script>

<style scoped>
  /* ========================================
   管理员界面 - 全新深色主题美化
   ======================================== */

  /* 访问被拒绝样式 */
  .access-denied {
    width: 100%;
    height: 100vh;
    background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 50%, #16213e 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
  }

  .access-denied::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background:
      radial-gradient(circle at 20% 80%, rgba(13, 148, 136, 0.15) 0%, transparent 50%),
      radial-gradient(circle at 80% 20%, rgba(20, 184, 166, 0.15) 0%, transparent 50%);
    animation: rotate 30s linear infinite;
  }

  @keyframes rotate {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  .denied-content {
    text-align: center;
    padding: 60px 80px;
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(30px);
    border-radius: 32px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow:
      0 25px 50px rgba(0, 0, 0, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
    z-index: 1;
    animation: slideUp 0.6s ease-out;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(30px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }

  .denied-icon {
    width: 120px;
    height: 120px;
    margin: 0 auto 24px;
    background: linear-gradient(135deg, rgba(255, 71, 87, 0.2) 0%, rgba(255, 71, 87, 0.05) 100%);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px solid rgba(255, 71, 87, 0.3);
  }

  .denied-icon svg {
    width: 60px;
    height: 60px;
    color: var(--danger);
    filter: drop-shadow(0 0 30px rgba(255, 71, 87, 0.5));
    animation: denied-pulse 2s ease-in-out infinite;
  }

  @keyframes denied-pulse {
    0%,
    100% {
      transform: scale(1);
      opacity: 1;
    }
    50% {
      transform: scale(1.1);
      opacity: 0.8;
    }
  }

  .access-denied h2 {
    margin: 0 0 12px 0;
    font-size: 32px;
    color: var(--danger);
    font-weight: 700;
    text-shadow: 0 0 40px rgba(255, 71, 87, 0.4);
    letter-spacing: 2px;
  }

  .access-denied p {
    margin: 8px 0;
    font-size: 16px;
    color: rgba(255, 255, 255, 0.6);
  }

  .access-denied .hint {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.4);
    margin-top: 20px;
  }

  /* 管理员面板主容器 */
  .admin-panel {
    width: 100%;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
    position: relative;
    overflow: hidden;
  }

  .admin-panel::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background:
      radial-gradient(circle at 10% 20%, rgba(13, 148, 136, 0.08) 0%, transparent 40%),
      radial-gradient(circle at 90% 80%, rgba(20, 184, 166, 0.08) 0%, transparent 40%);
    pointer-events: none;
  }

  /* 头部样式 */
  .admin-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    height: 60px;
    background: rgba(26, 26, 46, 0.9);
    backdrop-filter: blur(20px);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
    z-index: 100;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    position: relative;
  }

  .admin-header::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(13, 148, 136, 0.5),
      rgba(20, 184, 166, 0.5),
      transparent
    );
  }

  .header-left {
    display: flex;
    align-items: center;
  }

  .logo-section {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo-icon {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    padding: 8px;
    border-radius: 10px;
    box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3);
    position: relative;
    overflow: hidden;
  }

  .logo-icon::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.2) 0%, transparent 60%);
    animation: shimmer 3s ease-in-out infinite;
  }

  @keyframes shimmer {
    0%,
    100% {
      transform: translate(0, 0);
    }
    50% {
      transform: translate(20%, 20%);
    }
  }

  .logo-text h1 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 0.5px;
  }

  .logo-subtitle {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 600;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-info {
    display: flex;
    gap: 10px;
  }

  .info-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.8);
    font-weight: 500;
    transition: all 0.2s ease;
  }

  .info-item:hover {
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(13, 148, 136, 0.3);
  }

  .info-item svg {
    width: 16px;
    height: 16px;
    color: var(--primary);
  }

  .logout-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 16px;
    background: linear-gradient(135deg, rgba(255, 71, 87, 0.15) 0%, rgba(255, 71, 87, 0.08) 100%);
    color: var(--danger);
    border: 1px solid rgba(255, 71, 87, 0.3);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .logout-btn:hover {
    background: linear-gradient(135deg, var(--danger) 0%, var(--danger) 100%);
    color: white;
    border-color: transparent;
  }

  /* 主体内容 */
  .admin-body {
    flex: 1;
    display: flex;
    overflow: hidden;
    position: relative;
    z-index: 1;
  }

  /* 侧边栏 */
  .admin-sidebar {
    width: 240px;
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255, 255, 255, 0.05);
    display: flex;
    flex-direction: column;
    padding: 16px 0;
    overflow-y: auto;
    box-shadow: 2px 0 12px rgba(0, 0, 0, 0.2);
  }

  .admin-sidebar::-webkit-scrollbar {
    width: 6px;
  }

  .admin-sidebar::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.02);
  }

  .admin-sidebar::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 3px;
  }

  .sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 16px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .sidebar-header h3 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  .stats-badge {
    padding: 4px 10px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 700;
  }

  /* 搜索框 */
  .search-section {
    position: relative;
    margin: 0 16px 14px;
  }

  .search-icon {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 16px;
    height: 16px;
    color: rgba(255, 255, 255, 0.3);
    transition: color 0.2s ease;
  }

  .search-section:focus-within .search-icon {
    color: var(--primary);
  }

  .search-input {
    width: 100%;
    padding: 10px 36px 10px 36px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.9);
    outline: none;
    transition: all 0.2s ease;
    font-weight: 500;
    box-sizing: border-box;
  }

  .search-input::placeholder {
    color: rgba(255, 255, 255, 0.3);
  }

  .search-input:focus {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(13, 148, 136, 0.5);
    box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.15);
  }

  .clear-btn {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 26px;
    height: 26px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
    transition: all 0.3s ease;
  }

  .clear-btn svg {
    width: 14px;
    height: 14px;
    color: rgba(255, 255, 255, 0.5);
  }

  .clear-btn:hover {
    background: rgba(255, 71, 87, 0.2);
    border-color: rgba(255, 71, 87, 0.3);
    transform: translateY(-50%) scale(1.1);
  }

  .clear-btn:hover svg {
    color: var(--danger);
  }

  /* 快速访问 */
  .quick-access {
    padding: 0 16px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  }

  .section-title {
    font-size: 10px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.35);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 10px;
  }

  .quick-links {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .quick-link {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
  }

  .quick-link::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    width: 3px;
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
    opacity: 0;
    transition: all 0.3s ease;
  }

  .quick-link:hover {
    background: rgba(13, 148, 136, 0.1);
    border-color: rgba(13, 148, 136, 0.2);
    transform: translateX(8px);
    box-shadow: 0 4px 20px rgba(13, 148, 136, 0.15);
  }

  .quick-link:hover::before {
    opacity: 1;
  }

  .quick-link.active {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-color: transparent;
    box-shadow: 0 8px 30px rgba(13, 148, 136, 0.4);
  }

  .quick-link.active::before {
    opacity: 1;
    width: 100%;
    background: rgba(255, 255, 255, 0.3);
  }

  .quick-link.active svg,
  .quick-link.active .link-text,
  .quick-link.active .link-count {
    color: white;
  }

  .link-icon {
    width: 24px;
    height: 24px;
    color: var(--primary);
    flex-shrink: 0;
    transition: all 0.3s ease;
  }

  .quick-link.active .link-icon {
    color: white;
  }

  .link-text {
    flex: 1;
    font-size: 14px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.7);
    transition: all 0.3s ease;
  }

  .link-count {
    padding: 5px 12px;
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.4);
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    transition: all 0.3s ease;
  }

  .quick-link.active .link-count {
    background: rgba(255, 255, 255, 0.2);
    color: white;
  }

  /* 导航菜单 */
  .sidebar-nav {
    flex: 1;
    overflow-y: auto;
    padding: 14px 16px;
  }

  .sidebar-nav::-webkit-scrollbar {
    width: 6px;
  }

  .sidebar-nav::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.01);
  }

  .sidebar-nav::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 3px;
  }

  .nav-group {
    margin-bottom: 18px;
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 10px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.35);
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }

  .group-header svg {
    width: 14px;
    height: 14px;
    color: rgba(255, 255, 255, 0.25);
  }

  .nav-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
  }

  .nav-item::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    width: 3px;
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
    opacity: 0;
    transition: all 0.3s ease;
  }

  .nav-item:hover {
    background: rgba(13, 148, 136, 0.08);
    border-color: rgba(13, 148, 136, 0.2);
    transform: translateX(8px);
    box-shadow: 0 4px 20px rgba(13, 148, 136, 0.15);
  }

  .nav-item:hover::before {
    opacity: 1;
  }

  .nav-item.active {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-color: transparent;
    box-shadow: 0 8px 30px rgba(13, 148, 136, 0.4);
  }

  .nav-item.active::before {
    opacity: 1;
    width: 100%;
    background: rgba(255, 255, 255, 0.2);
  }

  .nav-icon {
    width: 20px;
    height: 20px;
    color: var(--primary);
    flex-shrink: 0;
    transition: all 0.2s ease;
    margin-top: 2px;
  }

  .nav-item.active .nav-icon {
    color: white;
  }

  .nav-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .nav-title {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
    transition: all 0.2s ease;
  }

  .nav-item.active .nav-title {
    color: white;
  }

  .nav-desc {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.35);
    transition: all 0.2s ease;
  }

  .nav-item.active .nav-desc {
    color: rgba(255, 255, 255, 0.7);
  }

  .no-results {
    text-align: center;
    padding: 60px 20px;
    color: rgba(255, 255, 255, 0.3);
  }

  .no-results svg {
    width: 48px;
    height: 48px;
    color: var(--border-color);
    margin-bottom: 16px;
    opacity: 0.3;
  }

  .no-results p {
    margin: 0 0 16px 0;
    font-size: 14px;
    color: rgba(255, 255, 255, 0.4);
  }

  .clear-search-link {
    color: var(--primary);
    background: none;
    border: none;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    padding: 0;
  }

  .clear-search-link:hover {
    color: var(--primary-hover);
    text-decoration: underline;
  }

  /* 主内容区域 */
  .admin-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: transparent;
  }

  /* 状态栏 */
  .status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }

  .status-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.7);
    font-weight: 500;
  }

  .status-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    animation: pulse 2s ease-in-out infinite;
  }

  .status-indicator.online {
    background: linear-gradient(135deg, var(--success) 0%, var(--success) 100%);
    box-shadow: 0 0 20px rgba(72, 187, 120, 0.6);
  }

  .status-indicator.offline {
    background: linear-gradient(135deg, var(--danger) 0%, var(--danger) 100%);
    box-shadow: 0 0 20px rgba(245, 101, 101, 0.6);
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.6;
      transform: scale(0.9);
    }
  }

  .status-time {
    color: rgba(255, 255, 255, 0.4);
    font-size: 13px;
  }

  .stats-summary {
    display: flex;
    gap: 10px;
  }

  .mini-stat {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 14px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 8px;
    transition: all 0.2s ease;
  }

  .mini-stat:hover {
    background: rgba(13, 148, 136, 0.1);
    border-color: rgba(13, 148, 136, 0.3);
  }

  .mini-stat-label {
    font-size: 9px;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.5px;
  }

  .mini-stat-value {
    font-size: 16px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  /* 内容包装器 */
  .content-wrapper {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    background: transparent;
  }

  .content-wrapper::-webkit-scrollbar {
    width: 8px;
  }

  .content-wrapper::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.01);
    border-radius: 4px;
  }

  .content-wrapper::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-hover) 100%);
    border-radius: 4px;
  }

  .content-wrapper::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--primary-hover) 0%, var(--primary) 100%);
  }

  /* 内容区域 */
  .content-section {
    height: 100%;
  }

  .monitor-section,
  .logs-section,
  .users-section {
    display: flex;
    flex-direction: column;
    gap: 24px;
  }

  /* 区块头部 */
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 18px 20px;
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(20px);
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    border: 1px solid rgba(255, 255, 255, 0.05);
  }

  .section-header .header-left {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .section-header .header-left svg {
    width: 28px;
    height: 28px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    padding: 6px;
    border-radius: 8px;
    color: white;
  }

  .section-header .header-left h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.9);
  }

  .section-header .header-desc {
    margin: 4px 0 0 0;
    font-size: 12px;
    color: rgba(255, 255, 255, 0.4);
  }

  .section-header .header-actions {
    display: flex;
    gap: 10px;
  }

  .section-header .action-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.03);
    color: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .section-header .action-btn:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(13, 148, 136, 0.3);
  }

  .section-header .action-btn.primary {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    color: white;
    border: none;
  }

  .section-header .action-btn.primary:hover {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary) 100%);
  }

  .section-header .action-btn svg {
    width: 16px;
    height: 16px;
  }

  /* 概览卡片 */
  .overview-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }

  .overview-card {
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 14px;
    padding: 18px;
    display: flex;
    gap: 14px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }

  .overview-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    transition: all 0.3s ease;
  }

  .overview-card::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.05) 0%, transparent 60%);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .overview-card:hover::after {
    opacity: 1;
  }

  .overview-card.cpu-card::before {
    background: linear-gradient(90deg, var(--warning) 0%, var(--warning) 100%);
  }

  .overview-card.memory-card::before {
    background: linear-gradient(90deg, var(--color-primary-400) 0%, var(--color-primary-500) 100%);
  }

  .overview-card.disk-card::before {
    background: linear-gradient(90deg, var(--color-primary-500) 0%, var(--color-primary-600) 100%);
  }

  .overview-card.network-card::before {
    background: linear-gradient(90deg, var(--success) 0%, var(--success) 100%);
  }

  .overview-card:hover {
    transform: translateY(-8px);
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
    border-color: rgba(13, 148, 136, 0.2);
  }

  .overview-card:hover::before {
    height: 6px;
  }

  .card-icon-wrapper {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.3s ease;
    position: relative;
  }

  .overview-card:hover .card-icon-wrapper {
    transform: scale(1.05);
  }

  .card-icon-wrapper.cpu {
    background: linear-gradient(135deg, rgba(246, 224, 94, 0.15) 0%, rgba(236, 201, 75, 0.1) 100%);
    border: 1px solid rgba(246, 224, 94, 0.2);
  }

  .card-icon-wrapper.cpu svg {
    color: var(--warning);
  }

  .card-icon-wrapper.memory {
    background: linear-gradient(135deg, rgba(99, 179, 237, 0.15) 0%, rgba(66, 153, 225, 0.1) 100%);
    border: 1px solid rgba(99, 179, 237, 0.2);
  }

  .card-icon-wrapper.memory svg {
    color: var(--color-primary-400);
  }

  .card-icon-wrapper.disk {
    background: linear-gradient(
      135deg,
      rgba(246, 135, 179, 0.15) 0%,
      rgba(237, 100, 166, 0.1) 100%
    );
    border: 1px solid rgba(246, 135, 179, 0.2);
  }

  .card-icon-wrapper.disk svg {
    color: var(--color-primary-500);
  }

  .card-icon-wrapper.network {
    background: linear-gradient(135deg, rgba(104, 211, 145, 0.15) 0%, rgba(72, 187, 120, 0.1) 100%);
    border: 1px solid rgba(104, 211, 145, 0.2);
  }

  .card-icon-wrapper.network svg {
    color: var(--success);
  }

  .card-icon-wrapper svg {
    width: 28px;
    height: 28px;
  }

  .card-content {
    flex: 1;
    position: relative;
    z-index: 1;
  }

  .card-content h3 {
    margin: 0 0 8px 0;
    font-size: 11px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.5);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .card-value {
    font-size: 28px;
    font-weight: 800;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 10px;
    line-height: 1;
  }

  .card-value-network {
    display: flex;
    gap: 20px;
  }

  .network-metric {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .metric-label {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.4);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 700;
  }

  .metric-value {
    font-size: 18px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.9);
  }

  .card-detail {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }

  .card-detail span {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
  }

  .status-badge {
    padding: 4px 10px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .status-badge.normal {
    background: linear-gradient(
      135deg,
      rgba(198, 246, 213, 0.2) 0%,
      rgba(154, 230, 180, 0.15) 100%
    );
    color: var(--success);
    border: 1px solid rgba(104, 211, 145, 0.3);
  }

  .status-badge.warning {
    background: linear-gradient(
      135deg,
      rgba(254, 235, 200, 0.2) 0%,
      rgba(251, 211, 141, 0.15) 100%
    );
    color: var(--warning);
    border: 1px solid rgba(251, 211, 141, 0.3);
  }

  .status-badge.critical {
    background: linear-gradient(
      135deg,
      rgba(254, 215, 215, 0.2) 0%,
      rgba(254, 178, 178, 0.15) 100%
    );
    color: var(--danger);
    border: 1px solid rgba(254, 178, 178, 0.3);
  }

  /* 图表网格 */
  .charts-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }

  .chart-panel {
    background: rgba(26, 26, 46, 0.8);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 14px;
    padding: 18px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
    transition: all 0.3s ease;
  }

  .chart-panel:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    border-color: rgba(13, 148, 136, 0.15);
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }

  .panel-title {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.9);
  }

  .panel-title svg {
    width: 18px;
    height: 18px;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    padding: 4px;
    border-radius: 6px;
    color: white;
  }

  .panel-value {
    font-size: 22px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .chart-container {
    flex: 1;
    min-height: 240px;
  }

  /* 页脚 */
  .admin-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    background: rgba(26, 26, 46, 0.9);
    backdrop-filter: blur(20px);
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    font-size: 12px;
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.15);
  }

  .footer-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .system-status {
    padding: 4px 10px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .system-status.online {
    background: linear-gradient(135deg, rgba(72, 187, 120, 0.2) 0%, rgba(56, 161, 105, 0.15) 100%);
    color: var(--success);
    border: 1px solid rgba(72, 187, 120, 0.3);
    box-shadow: 0 4px 15px rgba(72, 187, 120, 0.2);
  }

  .system-status.offline {
    background: linear-gradient(135deg, var(--color-danger-50, #fed7d7) 0%, var(--color-danger-100, #feb2b2) 100%);
    color: var(--text-primary);
    box-shadow: 0 2px 8px rgba(254, 178, 178, 0.4);
  }

  .footer-right {
    display: flex;
    gap: 20px;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  .footer-right span {
    opacity: 0.8;
  }

  /* 响应式设计 */
  @media (max-width: 1400px) {
    .overview-cards {
      grid-template-columns: repeat(2, 1fr);
    }

    .charts-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 1024px) {
    .admin-sidebar {
      width: 220px;
    }

    .overview-cards {
      grid-template-columns: 1fr;
    }

    .stats-summary {
      display: none;
    }
  }

  @media (max-width: 768px) {
    .admin-header {
      padding: 0 12px;
    }

    .logo-text h1 {
      font-size: 14px;
    }

    .logo-subtitle {
      display: none;
    }

    .header-info {
      display: none;
    }

    .admin-sidebar {
      width: 100%;
      max-width: 240px;
    }

    .content-wrapper {
      padding: 12px;
    }

      .section-header {
        flex-direction: column;
        gap: 12px;
        align-items: flex-start;
      }

    /* 代码沙箱配置 */
    .sandbox-config {
      h3 {
        color: var(--text-primary);
        font-size: 18px;
        margin: 0 0 8px;
      }

      .section-desc {
        color: var(--text-secondary);
        font-size: 14px;
        margin: 0 0 20px;
      }

      .config-card {
        background: var(--bg-secondary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 20px;
      }

      .config-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 0;

        &:not(:last-child) {
          border-bottom: 1px solid var(--border-color);
        }

        .config-label {
          display: flex;
          flex-direction: column;
          gap: 4px;

          .label-text {
            color: var(--text-primary);
            font-size: 14px;
            font-weight: 500;
          }

          .label-desc {
            color: var(--text-secondary);
            font-size: 12px;
          }
        }

        .language-tags {
          display: flex;
          gap: 8px;
        }
      }
    }
  }
</style>
