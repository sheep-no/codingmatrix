<template>
  <div v-if="visible" class="task-queue-overlay" @click="close">
    <div class="task-queue-window" @click.stop>
      <!-- 窗口头部 -->
      <div class="task-queue-header">
        <h3 class="task-queue-title">任务队列</h3>
        <button class="icon-btn" title="关闭" @click="close">
          <svg
            width="18"
            height="18"
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

      <!-- 状态概览 -->
      <div class="status-overview">
        <div class="status-card">
          <div class="status-value">{{ stats.pending }}</div>
          <div class="status-label">等待中</div>
        </div>
        <div class="status-card running">
          <div class="status-value">{{ stats.running }}</div>
          <div class="status-label">运行中</div>
        </div>
        <div class="status-card completed">
          <div class="status-value">{{ stats.completed }}</div>
          <div class="status-label">已完成</div>
        </div>
        <div class="status-card failed">
          <div class="status-value">{{ stats.failed }}</div>
          <div class="status-label">失败</div>
        </div>
      </div>

      <!-- 任务列表 -->
      <div class="task-list-section">
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else-if="tasks.length === 0" class="empty-state">
          <svg
            width="64"
            height="64"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
          >
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
          </svg>
          <p>暂无任务</p>
        </div>

        <div v-else class="task-list">
          <div v-for="task in tasks" :key="task.task_id" class="task-item" :class="task.status">
            <div class="task-header">
              <div class="task-info">
                <span class="task-type-badge" :class="getTaskTypeClass(task.task_type)">
                  {{ getTaskTypeLabel(task.task_type) }}
                </span>
                <span class="task-id">{{ task.task_id.slice(0, 8) }}...</span>
              </div>
              <span class="task-status" :class="task.status">
                {{ getStatusLabel(task.status) }}
              </span>
            </div>

            <div class="task-progress-section">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :class="task.status"
                  :style="{ width: task.progress + '%' }"
                ></div>
              </div>
              <div class="progress-text">{{ task.progress }}%</div>
            </div>

            <div class="task-message">
              {{ task.progress_message || '等待执行...' }}
            </div>

            <div class="task-meta">
              <span class="task-time">
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
                {{ formatTime(task.created_at) }}
              </span>
              <div class="task-actions">
                <button
                  v-if="task.status === 'running' || task.status === 'pending'"
                  class="action-btn cancel"
                  @click="cancelTask(task.task_id)"
                >
                  取消
                </button>
                <button
                  v-if="task.status === 'failed'"
                  class="action-btn retry"
                  @click="retryTask(task.task_id)"
                >
                  重试
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 自动刷新开关 -->
      <div class="auto-refresh-section">
        <label class="switch-label">
          <input v-model="autoRefresh" type="checkbox" class="switch-input" />
          <span class="switch-text">自动刷新</span>
          <span class="refresh-interval">({{ refreshInterval }}秒)</span>
        </label>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
  import { api } from '@/utils/api/index'
  import { ElMessage, ElMessageBox } from 'element-plus'

  const props = defineProps({
    visible: { type: Boolean, default: false }
  })

  const emit = defineEmits(['close'])

  // 状态管理
  const loading = ref(false)
  const tasks = ref([])
  const autoRefresh = ref(true)
  const refreshInterval = ref(10)
  let refreshTimer = null

  // 统计信息
  const stats = computed(() => {
    return {
      pending: tasks.value.filter(t => t.status === 'pending').length,
      running: tasks.value.filter(t => t.status === 'running').length,
      completed: tasks.value.filter(t => t.status === 'completed').length,
      failed: tasks.value.filter(t => t.status === 'failed').length
    }
  })

  // 加载任务列表
  const loadTasks = async () => {
    loading.value = true
    try {
      const response = await api.request('/tasks?status=&page=1&page_size=50', { method: 'GET' })
      const data = response.ok ? await response.json() : { tasks: [] }
      if (data && data.tasks) {
        tasks.value = data.tasks
      }
    } catch (error) {
      console.error('加载任务列表失败:', error)
    } finally {
      loading.value = false
    }
  }

  // 取消任务
  const cancelTask = async taskId => {
    try {
      await ElMessageBox.confirm('确定要取消此任务吗？', '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    } catch {
      return
    }

    try {
      const success = await api.cancelTask(taskId)
      if (success) {
        await loadTasks()
      }
    } catch (error) {
      console.error('取消任务失败:', error)
      ElMessage.error('取消任务失败：' + error.message)
    }
  }

  // 重试任务
  const retryTask = async taskId => {
    try {
      const result = await api.retryTask(taskId)
      if (result?.success !== false) {
        await loadTasks()
      } else {
        throw new Error('服务器拒绝重试任务')
      }
    } catch (error) {
      console.error('重试任务失败:', error)
    }
  }

  // 任务类型样式
  const getTaskTypeClass = type => {
    const typeMap = {
      project_generate: 'type-project',
      code_generate: 'type-code',
      ppt_generate: 'type-ppt',
      file_process: 'type-file'
    }
    return typeMap[type] || 'type-default'
  }

  // 任务类型标签
  const getTaskTypeLabel = type => {
    const typeMap = {
      project_generate: '项目生成',
      code_generate: '代码生成',
      ppt_generate: 'PPT 生成',
      file_process: '文件处理'
    }
    return typeMap[type] || type
  }

  // 状态标签
  const getStatusLabel = status => {
    const statusMap = {
      pending: '等待中',
      running: '运行中',
      completed: '已完成',
      failed: '失败',
      cancelled: '已取消'
    }
    return statusMap[status] || status
  }

  // 格式化时间
  const formatTime = timeString => {
    if (!timeString) return ''
    const date = new Date(timeString)
    const now = new Date()
    const diff = now - date
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (minutes < 1) return '刚刚'
    if (minutes < 60) return `${minutes}分钟前`
    if (hours < 24) return `${hours}小时前`
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN')
  }

  // 自动刷新控制
  const startAutoRefresh = () => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
    }

    if (autoRefresh.value) {
      refreshTimer = setInterval(() => {
        loadTasks()
      }, refreshInterval.value * 1000)
    }
  }

  // 关闭
  const close = () => {
    emit('close')
  }

  // 生命周期
  onMounted(() => {
    if (props.visible) {
      loadTasks()
      startAutoRefresh()
    }
  })

  onUnmounted(() => {
    if (refreshTimer) {
      clearInterval(refreshTimer)
    }
  })

  // 监听 visible 变化
  watch(
    () => props.visible,
    newVal => {
      if (newVal) {
        loadTasks()
        startAutoRefresh()
      } else {
        if (refreshTimer) {
          clearInterval(refreshTimer)
        }
      }
    }
  )
</script>

<style scoped>
  .task-queue-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    backdrop-filter: blur(4px);
  }

  .task-queue-window {
    width: 90%;
    max-width: 700px;
    max-height: min(600px, 85vh);
    height: auto;
    background: var(--bg-primary);
    border-radius: 12px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .task-queue-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: linear-gradient(135deg, var(--primary) 0%, #14b8a6 100%);
    color: white;
  }

  .task-queue-title {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }

  .icon-btn {
    padding: 6px;
    background: rgba(255, 255, 255, 0.2);
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .icon-btn:hover {
    background: rgba(255, 255, 255, 0.3);
  }

  .status-overview {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    padding: 16px 20px;
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border-color);
  }

  .status-card {
    padding: 12px;
    background: var(--bg-primary);
    border-radius: 8px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }

  .status-card.running {
    border-left: 3px solid var(--primary);
  }

  .status-card.completed {
    border-left: 3px solid var(--success);
  }

  .status-card.failed {
    border-left: 3px solid var(--danger);
  }

  .status-value {
    font-size: 24px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .status-label {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .task-list-section {
    flex: 1;
    overflow-y: auto;
    padding: 0 20px;
  }

  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    gap: 12px;
    color: var(--text-tertiary);
  }

  .loading-spinner {
    width: 40px;
    height: 40px;
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

  .task-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px 0;
  }

  .task-item {
    padding: 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    transition: all 0.2s;
  }

  .task-item:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
  }

  .task-item.pending {
    border-left: 3px solid var(--warning);
  }

  .task-item.running {
    border-left: 3px solid var(--primary);
  }

  .task-item.completed {
    border-left: 3px solid var(--success);
    opacity: 0.8;
  }

  .task-item.failed {
    border-left: 3px solid var(--danger);
  }

  .task-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .task-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .task-type-badge {
    padding: 4px 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .task-type-badge.type-project {
    background: var(--primary-50);
    color: var(--primary);
  }
  .task-type-badge.type-code {
    background: var(--success-bg);
    color: var(--success);
  }
  .task-type-badge.type-ppt {
    background: var(--warning-bg);
    color: var(--warning);
  }
  .task-type-badge.type-file {
    background: #f9f0ff;
    color: var(--color-primary-700);
  }

  .task-id {
    font-size: 12px;
    color: var(--text-tertiary);
    font-family: monospace;
  }

  .task-status {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
  }

  .task-status.pending {
    background: var(--warning-bg);
    color: var(--warning);
  }
  .task-status.running {
    background: var(--primary-50);
    color: var(--primary);
  }
  .task-status.completed {
    background: var(--success-bg);
    color: var(--success);
  }
  .task-status.failed {
    background: var(--danger-bg);
    color: var(--danger);
  }

  .task-progress-section {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  }

  .progress-bar {
    flex: 1;
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--primary);
    transition: width 0.3s;
  }

  .progress-fill.running {
    animation: progress-pulse 2s infinite;
  }

  @keyframes progress-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.7;
    }
  }

  .progress-text {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
    min-width: 45px;
    text-align: right;
  }

  .task-message {
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 12px;
    padding: 8px;
    background: var(--bg-secondary);
    border-radius: 6px;
  }

  .task-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .task-time {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .task-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    padding: 4px 12px;
    border: none;
    border-radius: 4px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .action-btn.cancel {
    background: #ff4d4f;
    color: white;
  }

  .action-btn.cancel:hover {
    background: #ff7875;
  }

  .action-btn.retry {
    background: var(--primary);
    color: white;
  }

  .action-btn.retry:hover {
    background: #40a9ff;
  }

  .auto-refresh-section {
    padding: 12px 20px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
  }

  .switch-label {
    display: flex;
    align-items: center;
    gap: 12px;
    cursor: pointer;
  }

  .switch-input {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  .switch-text {
    font-size: 14px;
    color: var(--text-secondary);
  }

  .refresh-interval {
    font-size: 12px;
    color: var(--text-tertiary);
  }

  /* watch 函数缺失，需要导入 */
</style>
