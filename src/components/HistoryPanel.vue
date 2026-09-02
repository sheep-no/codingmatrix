<template>
  <div class="history-panel">
    <!-- 头部 -->
    <div class="history-header">
      <h2>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
        历史记录
      </h2>
      <button class="refresh-btn" :disabled="isLoading" @click="loadHistory">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spinning': isLoading }">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
    </div>

    <!-- 统计信息 -->
    <div v-if="stats" class="stats-section">
      <div class="stat-item">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">总计</div>
      </div>
      <div class="stat-item success">
        <div class="stat-value">{{ stats.completed }}</div>
        <div class="stat-label">成功</div>
      </div>
      <div class="stat-item error">
        <div class="stat-value">{{ stats.failed }}</div>
        <div class="stat-label">失败</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{{ stats.avg_slides_per_ppt }}</div>
        <div class="stat-label">平均页数</div>
      </div>
    </div>

    <!-- 历史记录列表 -->
    <div class="history-list">
      <!-- 加载中 -->
      <div v-if="isLoading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- 空状态 -->
      <div v-else-if="history.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/>
        </svg>
        <p>暂无历史记录</p>
        <p class="hint">生成的 PPT 将显示在这里</p>
      </div>

      <!-- 历史项 -->
      <div 
        v-for="item in history"
        v-else 
        :key="item.task_id" 
        class="history-item"
        :class="item.status"
      >
        <div class="item-header">
          <div class="item-title">{{ item.topic }}</div>
          <div class="item-status" :class="item.status">
            {{ statusText(item.status) }}
          </div>
        </div>
        
        <div class="item-details">
          <div class="detail-item">
            <span class="detail-label">模板</span>
            <span class="detail-value">{{ item.template_id }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">页数</span>
            <span class="detail-value">{{ item.slide_count }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ formatDate(item.created_at) }}</span>
          </div>
        </div>

        <!-- 错误信息 -->
        <div v-if="item.error_message" class="error-message">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{{ item.error_message }}</span>
        </div>

        <!-- 操作按钮 -->
        <div class="item-actions">
          <button 
            v-if="item.status === 'completed'" 
            class="action-btn view" 
            @click="viewPPT(item)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
            查看
          </button>
          <button 
            v-if="item.status === 'completed'" 
            class="action-btn download" 
            @click="downloadPPT(item)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="7 10 12 15 17 10"/>
              <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            下载
          </button>
          <button 
            class="action-btn delete" 
            @click="deleteHistory(item)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination">
      <button 
        class="page-btn" 
        :disabled="currentPage === 1" 
        @click="changePage(currentPage - 1)"
      >
        上一页
      </button>
      <span class="page-info">
        第 {{ currentPage }} / {{ totalPages }} 页
      </span>
      <button 
        class="page-btn" 
        :disabled="currentPage === totalPages" 
        @click="changePage(currentPage + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()

// 状态
const history = ref([])
const stats = ref(null)
const isLoading = ref(false)
const currentPage = ref(1)
const pageSize = 10
const totalPages = ref(1)

// 加载历史记录
async function loadHistory() {
  isLoading.value = true
  try {
    const result = await api.ppt.getHistory(currentPage.value, pageSize)
    history.value = result.records || []
    totalPages.value = result.total_pages || 1
  } catch (error) {
    console.error('加载历史记录失败:', error)
    history.value = []
  } finally {
    isLoading.value = false
  }
}

// 加载统计信息
async function loadStats() {
  try {
    stats.value = await api.ppt.getStats()
  } catch (error) {
    console.error('加载统计信息失败:', error)
  }
}

// 切换页码
function changePage(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    loadHistory()
  }
}

// 查看 PPT
function viewPPT(item) {
  router.push({
    name: 'PPTPreview',
    params: { id: item.task_id }
  })
}

// 下载 PPT
async function downloadPPT(item) {
  try {
      const blob = await api.ppt.downloadPPT(item.task_id || item.file_id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${item.topic}.pptx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('下载失败:', error)
    ElMessage.error('下载失败：' + error.message)
  }
}

// 删除历史记录
async function deleteHistory(item) {
  try {
    await ElMessageBox.confirm(`确定要删除 "${item.topic}" 的历史记录吗？`, '确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
  } catch {
    return
  }

  try {
    const result = await api.ppt.deleteHistory(item.task_id)
    if (result.success) {
      // 重新加载列表
      loadHistory()
      loadStats()
    } else {
      ElMessage.error('删除失败')
    }
  } catch (error) {
    console.error('删除失败:', error)
    ElMessage.error('删除失败：' + error.message)
  }
}

// 状态文本
function statusText(status) {
  const map = {
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    pending: '等待中',
    running: '生成中'
  }
  return map[status] || status
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadHistory()
  loadStats()
})
</script>

<style scoped>
.history-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.history-header h2 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.history-header h2 svg {
  width: 22px;
  height: 22px;
}

.refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--hover-bg);
  color: var(--text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 18px;
  height: 18px;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 统计信息 */
.stats-section {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.stat-item {
  text-align: center;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 8px;
}

.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-item.success .stat-value {
  color: var(--success-color, #10b981);
}

.stat-item.error .stat-value {
  color: var(--error-color, #ef4444);
}

/* 历史记录列表 */
.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

.empty-state svg {
  width: 48px;
  height: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-state .hint {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-top: 8px;
}

/* 历史项 */
.history-item {
  background: var(--bg-secondary);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid var(--border-color);
  transition: all 0.2s;
}

.history-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.history-item.failed {
  border-left: 3px solid var(--error-color, #ef4444);
}

.history-item.completed {
  border-left: 3px solid var(--success-color, #10b981);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.item-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-right: 12px;
}

.item-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.item-status.completed {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success-color, #10b981);
}

.item-status.failed {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color, #ef4444);
}

.item-details {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.detail-value {
  font-size: 13px;
  color: var(--text-primary);
}

/* 错误信息 */
.error-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(239, 68, 68, 0.05);
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--error-color, #ef4444);
}

.error-message svg {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* 操作按钮 */
.item-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn svg {
  width: 14px;
  height: 14px;
}

.action-btn.view {
  background: var(--color-primary);
  color: white;
}

.action-btn.view:hover {
  background: var(--color-primary-dark);
}

.action-btn.download {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.action-btn.download:hover {
  background: var(--bg-secondary);
}

.action-btn.delete {
  background: none;
  color: var(--text-tertiary);
}

.action-btn.delete:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color, #ef4444);
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-color);
}

.page-btn {
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.page-btn:hover:not(:disabled) {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 滚动条 */
.history-list::-webkit-scrollbar {
  width: 6px;
}

.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.history-list::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.history-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
</style>
