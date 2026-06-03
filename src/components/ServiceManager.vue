<template>
  <div class="service-manager">
    <!-- 头部 -->
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
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
        </svg>
        <div>
          <h2>服务管理</h2>
          <p class="header-desc">管理和监控系统服务</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="action-btn primary" @click="refreshServices">
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

    <!-- 统计卡片 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon learned">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"></path>
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"></path>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.learned }}</div>
          <div class="stat-label">已学习服务</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon enabled">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.enabled }}</div>
          <div class="stat-label">已启用服务</div>
        </div>
      </div>
    </div>

    <!-- 启动监控表单 -->
    <div class="card">
      <div class="card-header">
        <h3>启动服务监控</h3>
        <span class="card-subtitle">添加新的服务到监控列表</span>
      </div>
      <div class="card-body">
        <div class="form-grid">
          <div class="form-group">
            <label for="service-name">服务名称</label>
            <input
              id="service-name"
              v-model="startForm.service_name"
              type="text"
              placeholder="输入服务名称"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label for="port">端口号</label>
            <input
              id="port"
              v-model.number="startForm.port"
              type="number"
              placeholder="输入端口号"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label for="restart-cmd">重启命令</label>
            <input
              id="restart-cmd"
              v-model="startForm.restart_cmd"
              type="text"
              placeholder="输入重启命令"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label>&nbsp;</label>
            <button class="btn btn-primary" @click="startGuard">启动监控</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 服务列表 -->
    <div class="card">
      <div class="card-header">
        <div class="header-left">
          <h3>服务列表</h3>
          <span class="card-subtitle">所有被监控的服务</span>
        </div>
      </div>
      <div class="card-body">
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <p>加载中...</p>
        </div>
        <div v-else-if="services.length === 0" class="empty-state">
          <svg
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <p>暂无服务</p>
        </div>
        <div v-else class="service-list">
          <div
            v-for="service in services"
            :key="service.key || `${service.port}_${service.process_signature}`"
            class="service-item"
          >
            <div class="service-header">
              <div class="service-info">
                <h4 class="service-name">{{ service.display_name || service.name }}</h4>
                <span class="service-port">端口: {{ service.port }}</span>
                <span class="service-status" :class="getServiceStatusClass(service)">
                  {{ getServiceStatusText(service) }}
                </span>
              </div>
              <div class="service-actions">
                <button class="action-btn small" title="熔断配置" @click="showFuseConfig(service)">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path
                      d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.47a2 2 0 0 1 1-1.74l.15-.1a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
                    ></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </svg>
                </button>
                <button class="action-btn small" title="熔断状态" @click="showFuseStatus(service)">
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                  </svg>
                </button>
                <button
                  class="action-btn small"
                  title="健康检查"
                  @click="checkServiceHealth(service)"
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                  </svg>
                </button>
                <button class="action-btn small" title="重命名" @click="showRenameModal(service)">
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
                </button>
              </div>
            </div>
            <div class="service-details">
              <div class="detail-item">
                <span class="detail-label">重启命令:</span>
                <span class="detail-value">{{ service.restart_cmd || 'N/A' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">进程签名:</span>
                <span class="detail-value">{{ service.process_signature || 'N/A' }}</span>
              </div>
              <div v-if="service.fuse_enabled !== undefined" class="detail-item">
                <span class="detail-label">熔断状态:</span>
                <span class="detail-value" :class="service.fuse_enabled ? 'enabled' : 'disabled'">
                  {{ service.fuse_enabled ? '已启用' : '已禁用' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 熔断配置弹窗 -->
    <div v-if="showFuseModal" class="modal-overlay" @click="closeFuseModal">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>熔断配置 - {{ currentService?.display_name || currentService?.name }}</h3>
          <button class="modal-close" @click="closeFuseModal">
            <svg
              width="20"
              height="20"
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
        <div class="modal-body">
          <div class="form-group">
            <label for="fuse-enabled">启用熔断</label>
            <select id="fuse-enabled" v-model="fuseForm.fuse_enabled" class="form-input">
              <option :value="true">启用</option>
              <option :value="false">禁用</option>
            </select>
          </div>
          <div class="form-group">
            <label for="fuse-cooldown">冷却时间 (秒)</label>
            <input
              id="fuse-cooldown"
              v-model.number="fuseForm.fuse_cooldown"
              type="number"
              class="form-input"
            />
          </div>
          <div class="form-group">
            <label for="fuse-retry-times">重试次数</label>
            <input
              id="fuse-retry-times"
              v-model.number="fuseForm.fuse_retry_times"
              type="number"
              class="form-input"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeFuseModal">取消</button>
          <button class="btn btn-primary" :disabled="fuseSaving" @click="updateFuseConfig">
            {{ fuseSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 重命名弹窗 -->
    <div v-if="showRenameModalFlag" class="modal-overlay" @click="closeRenameModal">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>重命名服务</h3>
          <button class="modal-close" @click="closeRenameModal">
            <svg
              width="20"
              height="20"
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
        <div class="modal-body">
          <div class="form-group">
            <label for="new-name">新名称</label>
            <input
              id="new-name"
              v-model="renameForm.new_name"
              type="text"
              class="form-input"
              placeholder="输入新的服务名称"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeRenameModal">取消</button>
          <button class="btn btn-primary" :disabled="renameSaving" @click="renameService">
            {{ renameSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 熔断状态弹窗 -->
    <div v-if="showStatusModal" class="modal-overlay" @click="closeStatusModal">
      <div class="modal" @click.stop>
        <div class="modal-header">
          <h3>熔断状态 - {{ fuseStatusData.service_name }}</h3>
          <button class="modal-close" @click="closeStatusModal">
            <svg
              width="20"
              height="20"
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
        <div class="modal-body">
          <div class="status-grid">
            <div class="status-item">
              <span class="status-label">状态:</span>
              <span class="status-value" :class="fuseStatusData.state">{{
                fuseStatusData.state
              }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">重启次数:</span>
              <span class="status-value">{{ fuseStatusData.restart_count }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">熔断启用:</span>
              <span
                class="status-value"
                :class="fuseStatusData.fuse_enabled ? 'enabled' : 'disabled'"
              >
                {{ fuseStatusData.fuse_enabled ? '是' : '否' }}
              </span>
            </div>
            <div class="status-item">
              <span class="status-label">当前重试次数:</span>
              <span class="status-value">{{ fuseStatusData.fuse_retry_count }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">最大重试次数:</span>
              <span class="status-value">{{ fuseStatusData.fuse_retry_times }}</span>
            </div>
            <div class="status-item">
              <span class="status-label">冷却剩余时间:</span>
              <span class="status-value">{{ fuseStatusData.cooldown_remaining }} 秒</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 消息提示 -->
    <div v-if="message.show" class="message-toast" :class="message.type">
      {{ message.text }}
    </div>
  </div>
</template>

<script setup>
  import { ref, onMounted } from 'vue'
  import { createApiClient } from '@/utils/api/index'
  import { useUserStore } from '@/stores/user'

  const userStore = useUserStore()
  const api = createApiClient(userStore)

  // 状态
  const loading = ref(false)
  const services = ref([])
  const stats = ref({
    learned: 0,
    enabled: 0
  })

  // 启动监控表单
  const startForm = ref({
    service_name: '',
    port: '',
    restart_cmd: ''
  })

  // 熔断配置表单
  const showFuseModal = ref(false)
  const fuseSaving = ref(false)
  const currentService = ref(null)
  const fuseForm = ref({
    fuse_enabled: true,
    fuse_cooldown: 300,
    fuse_retry_times: 0
  })

  // 重命名表单
  const showRenameModalFlag = ref(false)
  const renameSaving = ref(false)
  const renameForm = ref({
    new_name: ''
  })

  // 熔断状态
  const showStatusModal = ref(false)
  const fuseStatusData = ref({})

  // 消息提示
  const message = ref({
    show: false,
    text: '',
    type: 'success'
  })

  // 刷新服务列表
  async function refreshServices() {
    loading.value = true
    try {
      const response = await api.get('/api/v2/services')

      if (!response.ok) {
        let errorMsg = `获取服务列表失败 (${response.status})`
        try {
          const errorData = await response.clone().json()
          errorMsg = errorData.detail || errorData.message || errorMsg
        } catch (e) {
          // 如果不是JSON，尝试获取响应文本
          try {
            const errorText = await response.text()
            if (errorText) {
              errorMsg = errorText
            }
          } catch (textError) {
            // 忽略文本读取错误，使用状态文本
          }
        }
        showMessage(errorMsg, 'error')
        return
      }

      const data = await response.json()
      services.value = data.services || []
      stats.value.learned = data.learned || 0
      stats.value.enabled = data.enabled || 0
      showMessage('刷新成功', 'success')
    } catch (error) {
      console.error('刷新服务失败:', error)
      showMessage('刷新失败: ' + error.message, 'error')
    } finally {
      loading.value = false
    }
  }

  // 启动监控
  async function startGuard() {
    if (!startForm.value.service_name || !startForm.value.port || !startForm.value.restart_cmd) {
      showMessage('请填写完整信息', 'error')
      return
    }

    try {
      const response = await api.post('/api/v2/guard/start', {
        service_name: startForm.value.service_name,
        port: startForm.value.port,
        restart_cmd: startForm.value.restart_cmd
      })

      if (!response.ok) {
        let errorMsg = `启动失败 (${response.status})`
        try {
          const errorData = await response.clone().json()
          errorMsg = errorData.detail || errorData.message || errorMsg
        } catch (e) {
          try {
            const errorText = await response.text()
            if (errorText) errorMsg = errorText
          } catch (textError) {
            // 忽略文本读取错误
          }
        }
        showMessage(errorMsg, 'error')
        return
      }

      const data = await response.json()
      showMessage(data.message, 'success')
      startForm.value.service_name = ''
      startForm.value.port = ''
      startForm.value.restart_cmd = ''
      refreshServices()
    } catch (error) {
      console.error('启动监控失败:', error)
      showMessage('启动失败: ' + error.message, 'error')
    }
  }

  // 显示熔断配置
  function showFuseConfig(service) {
    currentService.value = service
    fuseForm.value = {
      fuse_enabled: service.fuse_enabled !== undefined ? service.fuse_enabled : true,
      fuse_cooldown: service.fuse_cooldown || 300,
      fuse_retry_times: service.fuse_retry_times || 0
    }
    showFuseModal.value = true
  }

  // 更新熔断配置
  async function updateFuseConfig() {
    if (!currentService.value) return

    fuseSaving.value = true
    try {
      const result = await api.updateFuseConfig(
        currentService.value.port,
        currentService.value.process_signature,
        {
          fuse_enabled: fuseForm.value.fuse_enabled,
          fuse_cooldown: fuseForm.value.fuse_cooldown,
          fuse_retry_times: fuseForm.value.fuse_retry_times
        }
      )

      if (result.ok) {
        showMessage('熔断配置已更新', 'success')
        closeFuseModal()
        refreshServices()
      } else {
        showMessage(result.data.detail || '更新失败', 'error')
      }
    } catch (error) {
      console.error('更新熔断配置失败:', error)
      showMessage('更新失败: ' + error.message, 'error')
    } finally {
      fuseSaving.value = false
    }
  }

  // 关闭熔断配置弹窗
  function closeFuseModal() {
    showFuseModal.value = false
    currentService.value = null
  }

  // 显示重命名弹窗
  function showRenameModal(service) {
    currentService.value = service
    renameForm.value.new_name = service.display_name || service.name
    showRenameModalFlag.value = true
  }

  // 重命名服务
  async function renameService() {
    if (!currentService.value || !renameForm.value.new_name) {
      showMessage('请输入新名称', 'error')
      return
    }

    renameSaving.value = true
    try {
      const result = await api.renameService(
        currentService.value.port,
        currentService.value.process_signature,
        renameForm.value.new_name
      )

      if (result.ok) {
        showMessage('重命名成功', 'success')
        closeRenameModal()
        refreshServices()
      } else {
        showMessage(result.data.detail || '重命名失败', 'error')
      }
    } catch (error) {
      console.error('重命名失败:', error)
      showMessage('重命名失败: ' + error.message, 'error')
    } finally {
      renameSaving.value = false
    }
  }

  // 关闭重命名弹窗
  function closeRenameModal() {
    showRenameModalFlag.value = false
    currentService.value = null
    renameForm.value.new_name = ''
  }

  // 显示熔断状态
  async function showFuseStatus(service) {
    try {
      const response = await api.get(`/api/v2/service/${service.name}/fuse-status`)

      if (!response.ok) {
        let errorMsg = `获取状态失败 (${response.status})`
        try {
          const errorData = await response.clone().json()
          errorMsg = errorData.detail || errorMsg
        } catch (e) {
          try {
            const errorText = await response.text()
            if (errorText) errorMsg = errorText
          } catch (textError) {
            // 忽略文本读取错误
          }
        }
        showMessage(errorMsg, 'error')
        return
      }

      const data = await response.json()
      fuseStatusData.value = data
      showStatusModal.value = true
    } catch (error) {
      console.error('获取熔断状态失败:', error)
      showMessage('获取状态失败: ' + error.message, 'error')
    }
  }

  // 关闭状态弹窗
  function closeStatusModal() {
    showStatusModal.value = false
    fuseStatusData.value = {}
  }

  // 健康检查
  async function checkServiceHealth(service) {
    try {
      const response = await api.get(`/api/v2/health/${service.port}`)

      if (!response.ok) {
        let errorMsg = `健康检查失败 (${response.status})`
        try {
          const errorData = await response.clone().json()
          errorMsg = errorData.detail || errorMsg
        } catch (e) {
          try {
            const errorText = await response.text()
            if (errorText) errorMsg = errorText
          } catch (textError) {
            // 忽略文本读取错误
          }
        }
        showMessage(errorMsg, 'error')
        return
      }

      const data = await response.json()
      showMessage(
        `健康检查: ${data.status === 'open' ? '正常' : '异常'}`,
        data.status === 'open' ? 'success' : 'error'
      )
    } catch (error) {
      console.error('健康检查失败:', error)
      showMessage('健康检查失败: ' + error.message, 'error')
    }
  }

  // 获取服务状态样式
  function getServiceStatusClass(service) {
    if (!service.fuse_enabled || service.fuse_enabled === undefined) {
      return 'normal'
    }
    return 'fused'
  }

  // 获取服务状态文本
  function getServiceStatusText(service) {
    if (!service.fuse_enabled || service.fuse_enabled === undefined) {
      return '正常'
    }
    return '熔断中'
  }

  // 显示消息
  function showMessage(text, type = 'success') {
    message.value.text = text
    message.value.type = type
    message.value.show = true
    setTimeout(() => {
      message.value.show = false
    }, 3000)
  }

  // 初始化
  onMounted(() => {
    refreshServices()
  })
</script>

<style scoped>
  .service-manager {
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-left h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .header-desc {
    margin: 2px 0 0 0;
    font-size: 14px;
    color: var(--text-secondary);
  }

  .header-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .action-btn:hover {
    background: var(--border-color);
  }

  .action-btn.primary {
    background: var(--primary);
    color: white;
  }

  .action-btn.primary:hover {
    background: var(--primary-hover);
  }

  .action-btn.small {
    padding: 6px 12px;
    gap: 4px;
  }

  .stats-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }

  .stat-card {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
  }

  .stat-icon.learned {
    background: linear-gradient(135deg, #0d9488 0%, #14b8a6 100%);
  }

  .stat-icon.enabled {
    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  }

  .stat-content {
    flex: 1;
  }

  .stat-value {
    font-size: 32px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1;
  }

  .stat-label {
    font-size: 14px;
    color: var(--text-secondary);
    margin-top: 4px;
  }

  .card {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin-bottom: 24px;
  }

  .card-header {
    padding: 20px;
    border-bottom: 1px solid var(--border-color);
  }

  .card-header h3 {
    margin: 0 0 4px 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .card-subtitle {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .card-body {
    padding: 20px;
  }

  .form-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .form-group label {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .form-input {
    padding: 10px 12px;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    font-size: 14px;
    transition: all 0.2s;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.1);
  }

  .form-input:disabled {
    background: var(--bg-tertiary);
    cursor: not-allowed;
  }

  .btn {
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.2s;
  }

  .btn-primary {
    background: var(--primary);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background: var(--primary-hover);
  }

  .btn-primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: var(--bg-tertiary);
    color: var(--text-primary);
  }

  .btn-secondary:hover {
    background: var(--border-color);
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 40px;
  }

  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid var(--bg-tertiary);
    border-top: 3px solid var(--primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    padding: 40px;
    color: var(--text-tertiary);
  }

  .service-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .service-item {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
    transition: all 0.2s;
    cursor: pointer;
  }

  .service-item:hover {
    border-color: var(--primary);
    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.1);
  }

  .service-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
  }

  .service-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .service-name {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .service-port {
    padding: 4px 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .service-status {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
  }

  .service-status.normal {
    background: var(--color-success-50, #e8f5e9);
    color: var(--success);
  }

  .service-status.fused {
    background: var(--color-danger-50, #ffebee);
    color: var(--danger);
  }

  .service-actions {
    display: flex;
    gap: 8px;
  }

  .service-details {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .detail-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }

  .detail-label {
    color: var(--text-secondary);
    font-weight: 500;
  }

  .detail-value {
    color: var(--text-primary);
  }

  .detail-value.enabled {
    color: var(--success);
  }

  .detail-value.disabled {
    color: var(--danger);
  }

  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: var(--bg-primary);
    border-radius: 8px;
    max-width: 500px;
    width: 90%;
    max-height: 90vh;
    overflow-y: auto;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px;
    border-bottom: 1px solid var(--border-color);
  }

  .modal-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .modal-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 4px;
  }

  .modal-close:hover {
    color: var(--text-primary);
  }

  .modal-body {
    padding: 20px;
  }

  .status-grid {
    display: grid;
    gap: 16px;
  }

  .status-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
  }

  .status-label {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .status-value {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .status-value.normal {
    color: var(--success);
  }

  .status-value.fused {
    color: var(--danger);
  }

  .status-value.enabled {
    color: var(--success);
  }

  .status-value.disabled {
    color: var(--danger);
  }

  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 20px;
    border-top: 1px solid var(--border-color);
  }

  .message-toast {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 12px 20px;
    border-radius: 6px;
    color: white;
    font-size: 14px;
    font-weight: 500;
    z-index: 2000;
    animation: slideIn 0.3s ease;
  }

  .message-toast.success {
    background: var(--success);
  }

  .message-toast.error {
    background: var(--danger);
  }

  @keyframes slideIn {
    from {
      transform: translateX(400px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
</style>
